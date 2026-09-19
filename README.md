# Anime Scene Finder

<p align="center">
  <img src="assets/AniScene.svg" alt="AniScene — by FHANA Labs" width="360"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/OpenCLIP-PyTorch-EE4C2C?logo=pytorch&logoColor=white" alt="OpenCLIP with PyTorch" />
  <img src="https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL and pgvector" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white" alt="Redis 7" />
  <img src="https://img.shields.io/badge/MinIO-object%20storage-C72E49?logo=minio&logoColor=white" alt="MinIO" />
  <img src="https://img.shields.io/badge/Nginx-reverse%20proxy-009639?logo=nginx&logoColor=white" alt="Nginx" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose" />
</p>

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
   curl http://127.0.0.1:8090/health
   ```
