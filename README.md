# Anime Scene Finder

Backend system to search anime episode and timestamp based on screenshot queries, featuring separate Indexing Pipeline (local/private) and Search Pipeline (public REST API).

## Tech Stack
- Python 3.12+, FastAPI, Pydantic, Uvicorn
- OpenCLIP (pretrained image embedding)
- PostgreSQL + pgvector
- MinIO (object storage for keyframes/thumbnails)
- Redis (job queue for indexing)
- Docker & Docker Compose

## Local embedding proof of concept

Install the package in a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Compare two images with the same OpenCLIP preprocessing and model:

```bash
anime-embed path/to/query.jpg path/to/candidate.jpg
```

The command prints the embedding dimension and cosine similarity. The model is
loaded once per process and uses CPU by default when CUDA is unavailable.

Phase 2 adds `VectorStore` for pgvector inserts and cosine nearest-neighbor
search. Install dependencies with `python3 -m pip install -e .` before using
it; PostgreSQL must have the migration applied.

Index a local episode after PostgreSQL and MinIO are available:

```bash
anime-index --anime Frieren --season 1 --episode 7 \
  --source /data/anime-source/frieren/season-1/episode-07.mkv
```

Run the API locally with `uvicorn app.main:app --app-dir api` and send a
`multipart/form-data` upload to `POST /api/v1/search`.

Queue indexing through Redis and run the resumable worker:

```bash
anime-index --queue --anime Frieren --season 1 --episode 7 \
  --source /data/anime-source/frieren/season-1/episode-07.mkv
anime-worker
```

For the v2 Docker stack, copy `.env.example` to `.env` and run
`docker compose up -d --build`. Public local ingress is
`http://127.0.0.1:8090`; API, PostgreSQL, Redis, and MinIO stay on the private
Docker network. Use `--profile local` to start the FZF operator container.

## Getting Started

1. Copy `.env.example` to `.env`.
2. Start services with Docker Compose:
   ```bash
   docker compose up -d --build
   ```
3. Check health:
   ```bash
   curl http://localhost:8000/health
   ```
