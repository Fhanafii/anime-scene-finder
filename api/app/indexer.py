from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .embedding import ImageEmbedder
from .media import detect_scenes, extract_frame, representative_times, video_duration
from .object_store import ObjectStore
from .vector_store import VectorStore


@dataclass(frozen=True)
class IndexRequest:
    anime: str
    season: int
    episode: int
    source: Path
    title: str | None = None
    retries: int = 0


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def index_episode(request: IndexRequest) -> int:
    if not request.source.is_file():
        raise FileNotFoundError(request.source)

    store = VectorStore()
    object_store = ObjectStore()
    embedder = ImageEmbedder()
    anime_id, episode_id = store.upsert_episode(
        title=request.anime,
        slug=slugify(request.anime),
        season=request.season,
        episode=request.episode,
        episode_title=request.title,
        duration=video_duration(request.source),
        source_identifier=str(request.source),
    )
    del anime_id

    scenes = detect_scenes(request.source)
    job_id = store.start_or_resume_job(episode_id, len(scenes))
    try:
        for scene_index, (start, end) in enumerate(scenes):
            scene_id = store.insert_scene(episode_id, scene_index, start, end, (start + end) / 2)
            timestamps = representative_times(start, end)
            if store.scene_frame_count(scene_id, embedder.config.model_name, embedder.config.pretrained) >= len(timestamps):
                store.mark_scene_processed(job_id, scene_index, len(timestamps))
                continue
            for frame_index, timestamp in enumerate(timestamps):
                object_key = f"{slugify(request.anime)}/s{request.season:02d}/e{request.episode:03d}/scene-{scene_index:05d}-{frame_index}.jpg"
                frame_path = request.source.parent / ".keyframes" / object_key
                extract_frame(request.source, timestamp, frame_path)
                object_store.upload(frame_path, object_key)
                store.insert_frame(
                    scene_id=scene_id,
                    timestamp=timestamp,
                    object_key=object_key,
                    embedding=embedder.encode(frame_path),
                    model=embedder.config.model_name,
                    model_version=embedder.config.pretrained,
                )
            store.mark_scene_processed(job_id, scene_index, len(timestamps))
        store.complete_job(job_id)
    except Exception as exc:
        store.fail_job(job_id, str(exc))
        raise
    return episode_id
