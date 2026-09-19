from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image, UnidentifiedImageError

from .embedding import ImageEmbedder
from .aggregation import aggregate_scene_matches
from .hybrid import fuse_scores
from .ocr import TesseractOCR
from .vector_store import VectorStore
from .object_store import ObjectStore

MAX_IMAGE_BYTES = int(os.getenv("SEARCH_MAX_IMAGE_BYTES", "10485760"))
MAX_IMAGE_DIMENSION = int(os.getenv("SEARCH_MAX_IMAGE_DIMENSION", "4096"))
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "50"))
SEARCH_RESULT_LIMIT = int(os.getenv("SEARCH_RESULT_LIMIT", "10"))

app = FastAPI(title="Anime Scene Finder")
embedder = ImageEmbedder()
store = VectorStore(os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/anime_scene_finder"))
ocr = TesseractOCR()
objects = ObjectStore()


def error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> JSONResponse:
    try:
        store.check_connection()
        embedder._load()
    except Exception:
        return error("SERVICE_UNAVAILABLE", "Search service is not ready.", 503)
    return JSONResponse({"status": "ready"})


@app.get("/api/v1/scenes/{scene_id}")
def scene(scene_id: int) -> JSONResponse:
    value = store.get_scene(scene_id)
    if not value:
        return error("NOT_FOUND", "Scene not found.", 404)
    value["thumbnail_url"] = f"/api/v1/scenes/{scene_id}/thumbnail"
    value.pop("object_key", None)
    return JSONResponse(value)


@app.get("/api/v1/scenes/{scene_id}/thumbnail")
def thumbnail(scene_id: int) -> Response:
    value = store.get_scene(scene_id)
    if not value or not value.get("object_key"):
        return error("NOT_FOUND", "Thumbnail not found.", 404)
    try:
        return Response(objects.read(value["object_key"]), media_type="image/jpeg")
    except Exception:
        return error("NOT_FOUND", "Thumbnail not found.", 404)


@app.get("/api/v1/anime/{anime_id}")
def anime(anime_id: int) -> JSONResponse:
    value = store.get_anime(anime_id)
    return JSONResponse(value or {"error": {"code": "NOT_FOUND", "message": "Anime not found."}}, status_code=200 if value else 404)


@app.get("/api/v1/anime/{anime_id}/episodes")
def episodes(anime_id: int) -> JSONResponse:
    if not store.get_anime(anime_id):
        return error("NOT_FOUND", "Anime not found.", 404)
    return JSONResponse({"results": store.get_episodes(anime_id)})


@app.post("/api/v1/search")
async def search(image: UploadFile = File(...), limit: int = Query(SEARCH_RESULT_LIMIT, ge=1, le=50)) -> JSONResponse:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        return error("UNSUPPORTED_IMAGE_TYPE", "The uploaded file is not a supported image type.", 415)
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        return error("IMAGE_TOO_LARGE", "The uploaded image exceeds the size limit.", 413)
    try:
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.verify()
            if max(decoded.size) > MAX_IMAGE_DIMENSION:
                return error("IMAGE_DIMENSIONS_TOO_LARGE", "The uploaded image dimensions exceed the limit.", 413)
    except (UnidentifiedImageError, OSError):
        return error("INVALID_IMAGE", "The uploaded file is not a valid image.", 422)

    with tempfile.NamedTemporaryFile(suffix=Path(image.filename or ".image").suffix) as temporary:
        temporary.write(data)
        temporary.flush()
        try:
            vector = embedder.encode(temporary.name)
            query_ocr = ocr.extract(temporary.name)
            matches = store.search(
                vector,
                model=embedder.config.model_name,
                model_version=embedder.config.pretrained,
                limit=SEARCH_TOP_K,
            )
        except Exception:
            return error("SEARCH_UNAVAILABLE", "Search is temporarily unavailable.", 503)

    scores = {match.frame_id: fuse_scores(match.similarity, query_ocr, match.ocr_text) for match in matches}
    candidates = aggregate_scene_matches(matches, limit, scores)

    return JSONResponse(
        {
            "query": {"type": "image", "ocr_text": query_ocr},
            "results": [
                {
                    "anime": {"id": str(match.anime_id), "title": match.anime_title},
                    "episode": {
                        "id": str(match.episode_id),
                        "season": match.season,
                        "episode": match.episode,
                        "title": match.episode_title,
                    },
                    "scene": {
                        "id": str(match.scene_id),
                        "start_time": match.scene_start,
                        "end_time": match.scene_end,
                        "representative_time": match.scene_representative,
                    },
                    "match": {
                        "timestamp": match.timestamp,
                        "visual_score": match.similarity,
                        "ocr_score": candidate.ocr_score,
                        "final_score": candidate.final_score,
                    },
                    "thumbnail_url": f"/api/v1/scenes/{match.scene_id}/thumbnail",
                }
                for candidate in candidates
                for match in [candidate.match]
            ],
        }
    )
