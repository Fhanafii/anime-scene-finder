from __future__ import annotations

import io
import os
import tempfile
import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Query, Request, UploadFile
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
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"}
SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "50"))
SEARCH_RESULT_LIMIT = int(os.getenv("SEARCH_RESULT_LIMIT", "10"))

app = FastAPI(
    title="Anime Scene Finder API",
    description="Search anime scenes from screenshots using visual and OCR signals.",
    version="0.9.0",
    docs_url="/",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
logger = logging.getLogger("anime_scene_finder.api")
embedder = ImageEmbedder()
store = VectorStore(os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/anime_scene_finder"))
ocr = TesseractOCR()
objects = ObjectStore()


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info("request_id=%s method=%s path=%s status=%s duration_ms=%.2f", request_id, request.method, request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
    return response
def error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@app.get(
    "/health",
    summary="Liveness check",
    description="Returns OK when the API process is running.",
    responses={200: {"content": {"application/json": {"example": {"status": "ok"}}}}},
)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/health/ready",
    summary="Readiness check",
    description="Checks PostgreSQL, MinIO, OpenCLIP, and OCR availability.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "ready"}}}},
        503: {"content": {"application/json": {"example": {"error": {"code": "SERVICE_UNAVAILABLE", "message": "Search service is not ready."}}}}},
    },
)
def readiness() -> JSONResponse:
    try:
        store.check_connection()
        objects.check_connection()
        embedder._load()
        ocr.version
    except Exception:
        return error("SERVICE_UNAVAILABLE", "Search service is not ready.", 503)
    return JSONResponse({"status": "ready"})


@app.get(
    "/api/v1/scenes/{scene_id}",
    summary="Get scene details",
    description="Example: scene ID 1 belongs to Overlord season 1 episode 1.",
    responses={
        200: {"content": {"application/json": {"example": {
            "id": 1, "start_time": 0.0, "end_time": 14.139, "representative_time": 7.0695,
            "episode": {"id": 1, "season": 1, "episode": 1, "title": None},
            "anime": {"id": 5, "title": "Overlord"},
            "thumbnail_url": "/api/v1/scenes/1/thumbnail",
        }}}},
        404: {"content": {"application/json": {"example": {"error": {"code": "NOT_FOUND", "message": "Scene not found."}}}}},
    },
)
def scene(scene_id: int) -> JSONResponse:
    value = store.get_scene(scene_id)
    if not value:
        return error("NOT_FOUND", "Scene not found.", 404)
    value["thumbnail_url"] = f"/api/v1/scenes/{scene_id}/thumbnail"
    value.pop("object_key", None)
    return JSONResponse(value)


@app.get(
    "/api/v1/scenes/{scene_id}/thumbnail",
    summary="Get scene thumbnail",
    description="Returns the representative keyframe as a JPEG image. Example scene ID: 1.",
    responses={
        200: {"content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"content": {"application/json": {"example": {"error": {"code": "NOT_FOUND", "message": "Thumbnail not found."}}}}},
    },
)
def thumbnail(scene_id: int) -> Response:
    value = store.get_scene(scene_id)
    if not value or not value.get("object_key"):
        return error("NOT_FOUND", "Thumbnail not found.", 404)
    try:
        return Response(objects.read(value["object_key"]), media_type="image/jpeg")
    except Exception:
        return error("NOT_FOUND", "Thumbnail not found.", 404)


@app.get(
    "/api/v1/anime/{anime_id}",
    summary="Get anime metadata",
    description="Example: anime ID 5 is Overlord.",
    responses={
        200: {"content": {"application/json": {"example": {"id": 5, "title": "Overlord", "slug": "overlord"}}}},
        404: {"content": {"application/json": {"example": {"error": {"code": "NOT_FOUND", "message": "Anime not found."}}}}},
    },
)
def anime(anime_id: int) -> JSONResponse:
    value = store.get_anime(anime_id)
    return JSONResponse(value or {"error": {"code": "NOT_FOUND", "message": "Anime not found."}}, status_code=200 if value else 404)


@app.get(
    "/api/v1/anime/{anime_id}/episodes",
    summary="List anime episodes",
    description="Example anime ID 5 returns the indexed Overlord episode.",
    responses={
        200: {"content": {"application/json": {"example": {"results": [{"id": 1, "season": 1, "episode": 1, "title": None, "duration": 1454.12}]}}}},
        404: {"content": {"application/json": {"example": {"error": {"code": "NOT_FOUND", "message": "Anime not found."}}}}},
    },
)
def episodes(anime_id: int) -> JSONResponse:
    if not store.get_anime(anime_id):
        return error("NOT_FOUND", "Anime not found.", 404)
    return JSONResponse({"results": store.get_episodes(anime_id)})


@app.post(
    "/api/v1/search",
    summary="Search scenes by screenshot",
    description="Upload a JPG, PNG, WEBP, GIF, BMP, or TIFF screenshot as multipart/form-data. Example file: an Overlord episode screenshot.",
    openapi_extra={"requestBody": {"content": {"multipart/form-data": {"example": {"image": "overlord-episode-01.jpg", "limit": 10}}}}},
    responses={
        200: {"content": {"application/json": {"example": {
            "query": {"type": "image", "ocr_text": "OVERLORD"},
            "results": [{
                "anime": {"id": "5", "title": "Overlord"},
                "episode": {"id": "1", "season": 1, "episode": 1, "title": None},
                "scene": {"id": "1", "start_time": 0.0, "end_time": 14.139, "representative_time": 7.0695},
                "match": {"timestamp": 7.0695, "visual_score": 0.91, "ocr_score": 0.82, "final_score": 0.88},
                "thumbnail_url": "/api/v1/scenes/1/thumbnail",
            }],
        }}}},
        415: {"content": {"application/json": {"example": {"error": {"code": "UNSUPPORTED_IMAGE_TYPE", "message": "The uploaded file is not a supported image type."}}}}},
        422: {"content": {"application/json": {"example": {"error": {"code": "INVALID_IMAGE", "message": "The uploaded file is not a valid image."}}}}},
        503: {"content": {"application/json": {"example": {"error": {"code": "SEARCH_UNAVAILABLE", "message": "Search is temporarily unavailable."}}}}},
    },
)
async def search(image: UploadFile = File(..., description="Screenshot file (JPG, PNG, WEBP, GIF, BMP, or TIFF)"), limit: int = Query(..., ge=1, le=50, description="Required maximum results, from 1 to 50; use 10 for the standard request")) -> JSONResponse:
    data = await image.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        return error("IMAGE_TOO_LARGE", "The uploaded image exceeds the size limit.", 413)
    try:
        with Image.open(io.BytesIO(data)) as decoded:
            image_format = decoded.format
            decoded.verify()
            if image_format not in ALLOWED_IMAGE_FORMATS:
                return error("UNSUPPORTED_IMAGE_TYPE", "The uploaded file is not a supported image type.", 415)
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
