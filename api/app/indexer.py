from __future__ import annotations

import re
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .embedding import ImageEmbedder
from .media import detect_scenes, extract_frame, representative_times, video_duration
from .object_store import ObjectStore
from .ocr import TesseractOCR
from .source import verify_source
from .vector_store import VectorStore


@dataclass(frozen=True)
class IndexRequest:
    anime: str
    season: int
    episode: int
    source: Path
    title: str | None = None
    retries: int = 0
    force_reindex: bool = False


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def index_episode(request: IndexRequest) -> int:
    source_metadata = verify_source(request.source)

    store = VectorStore()
    object_store = ObjectStore()
    embedder = ImageEmbedder()
    ocr = TesseractOCR()
    ocr_version = ocr.version
    with request.source.open("rb") as source_file:
        source_checksum = hashlib.file_digest(source_file, "sha256").hexdigest()
    anime_id, episode_id = store.upsert_episode(
        title=request.anime,
        slug=slugify(request.anime),
        season=request.season,
        episode=request.episode,
        episode_title=request.title,
        duration=source_metadata["duration"],
        width=source_metadata["width"],
        height=source_metadata["height"],
        fps=source_metadata["fps"],
        codec=source_metadata["codec"],
        source_identifier=str(request.source),
        source_path=str(request.source),
        source_checksum=source_checksum,
        source_size=request.source.stat().st_size,
    )
    del anime_id

    if store.completed_job_exists(episode_id) and not request.force_reindex:
        raise ValueError("episode is already indexed; use --force-reindex to run it again")

    scenes = detect_scenes(request.source)
    job_id = store.start_or_resume_job(
        episode_id,
        len(scenes),
        embedder.config.model_name,
        embedder.config.pretrained,
        ocr.engine,
        ocr_version,
    )
    try:
        for scene_index, (start, end) in enumerate(scenes):
            scene_id = store.insert_scene(episode_id, scene_index, start, end, (start + end) / 2)
            timestamps = representative_times(start, end)
            if store.scene_frame_count(scene_id, embedder.config.model_name, embedder.config.pretrained) >= len(timestamps):
                store.mark_scene_processed(job_id, scene_index, len(timestamps))
                continue
            for frame_index, timestamp in enumerate(timestamps):
                object_key = f"{slugify(request.anime)}/s{request.season:02d}/e{request.episode:03d}/scene-{scene_index:05d}-{frame_index}.jpg"
                frame_path = Path(os.getenv("PROCESSING_ROOT", "/data/processing")) / "keyframes" / object_key
                try:
                    extract_frame(request.source, timestamp, frame_path)
                    object_store.upload(frame_path, object_key)
                    ocr_text = ocr.extract(frame_path)
                    store.insert_frame(
                        scene_id=scene_id,
                        timestamp=timestamp,
                        object_key=object_key,
                        embedding=embedder.encode(frame_path),
                        model=embedder.config.model_name,
                        model_version=embedder.config.pretrained,
                        ocr_text=ocr_text,
                        ocr_engine=ocr.engine,
                        ocr_engine_version=ocr_version,
                    )
                finally:
                    frame_path.unlink(missing_ok=True)
            store.mark_scene_processed(job_id, scene_index, len(timestamps))
        store.complete_job(job_id)
    except Exception as exc:
        store.fail_job(job_id, str(exc))
        raise
    return episode_id
