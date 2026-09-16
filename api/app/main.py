from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

from .embedding import ImageEmbedder
from .vector_store import VectorStore

MAX_IMAGE_BYTES = int(os.getenv("SEARCH_MAX_IMAGE_BYTES", "10485760"))
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = FastAPI(title="Anime Scene Finder")
embedder = ImageEmbedder()
store = VectorStore(os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/anime_scene_finder"))


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


@app.post("/api/v1/search")
async def search(image: UploadFile = File(...), limit: int = Query(10, ge=1, le=50)) -> JSONResponse:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        return error("UNSUPPORTED_IMAGE_TYPE", "The uploaded file is not a supported image type.", 415)
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        return error("IMAGE_TOO_LARGE", "The uploaded image exceeds the size limit.", 413)
    try:
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.verify()
    except (UnidentifiedImageError, OSError):
        return error("INVALID_IMAGE", "The uploaded file is not a valid image.", 422)

    with tempfile.NamedTemporaryFile(suffix=Path(image.filename or ".image").suffix) as temporary:
        temporary.write(data)
        temporary.flush()
        try:
            vector = embedder.encode(temporary.name)
            matches = store.search(
                vector,
                model=embedder.config.model_name,
                model_version=embedder.config.pretrained,
                limit=limit,
            )
        except Exception:
            return error("SEARCH_UNAVAILABLE", "Search is temporarily unavailable.", 503)

    return JSONResponse(
        {
            "query": {"type": "image"},
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
                    "match": {"timestamp": match.timestamp, "similarity": match.similarity},
                    "thumbnail_url": f"/api/v1/scenes/{match.scene_id}/thumbnail",
                }
                for match in matches
            ],
        }
    )
