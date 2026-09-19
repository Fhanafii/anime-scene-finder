# Anime Scene Finder Backend

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

Backend untuk mencari anime, episode, scene, dan timestamp dari screenshot. Indexing berjalan private/local; hanya Search API yang diekspos melalui Cloudflare Tunnel → Nginx → FastAPI.

## Arsitektur

```text
                  Public Search Pipeline

                         INTERNET
                            │
                          HTTPS
                            │
                            ▼
                    Cloudflare Tunnel
                            │
                            ▼
                    127.0.0.1:8080
                            │
                            ▼
                       ┌────────┐
                       │ Nginx  │
                       └───┬────┘
                           │
                           ▼
                       ┌───────┐
                       │ API   │
                       │FastAPI│
                       └───┬───┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
                 OpenCLIP        OCR
                    │             │
                    └──────┬──────┘
                           ▼
                   PostgreSQL+ pgvector
                           │
                           ▼
                         MinIO


                 Private Local Indexing

                       ┌───────┐
                       │  FZF  │
                       └───┬───┘
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
             Local Source      ani-cli Adapter
                  │                 │
                  └────────┬────────┘
                           ▼
                       Raw Video
                           │
                           ▼
                     Index Worker
                           │
                  ┌────────┼────────┐
                  ▼        ▼        ▼
               FFmpeg    OCR     OpenCLIP
                  │        │        │
                  └────────┼────────┘
                           ▼
                   PostgreSQL + pgvector
                           +
                         MinIO
```

## Menjalankan Docker

Prasyarat: Docker, Docker Compose, source anime yang legal untuk diproses, dan Cloudflare Tunnel yang sudah tersedia.

1. Buat konfigurasi lokal dari template. Jangan commit file `.env`.

   ```bash
   cp .env.example .env
   ```

2. Isi konfigurasi lokal/credential pada `.env`, lalu build dan start:

   ```bash
   docker compose up -d --build
   ```

3. Periksa service:

   ```bash
   docker compose ps
   docker compose logs -f api worker nginx
   curl http://127.0.0.1:8090/health
   ```

4. Konfigurasi Cloudflare hostname:

   ```text
   Hostname: anisceneapi.fhanalabs.site
   Service:  http://127.0.0.1:8090
   ```

   Cloudflare Tunnel tetap menjadi public entrypoint; port internal PostgreSQL, Redis, MinIO, dan FastAPI tidak dipublish ke host.

## Indexing pipeline

### 1. Siapkan source video

Worker membaca source secara read-only dari struktur berikut di server:

```text
/data/anime-source/
└── frieren/
    └── season-01/
        └── episode-07.mkv
```

Folder `data/anime-source/` dan `data/processing/` di project di-ignore agar video dan artefak processing tidak masuk Git. Tambahkan source yang Anda miliki sendiri, misalnya:

```bash
mkdir -p data/anime-source/frieren/season-01
cp /path/to/episode-01.mkv data/anime-source/frieren/season-01/episode-01.mkv
```

Nama folder harus memuat pola `season-01` dan nama file harus memuat pola `episode-07` agar FZF dapat membaca metadata otomatis.

### 2. Jalankan FZF operator

FZF memilih source lokal, memverifikasi file/video, lalu mengirim job ke Redis. Indexing tetap dikerjakan worker di background.

```bash
docker compose --profile local run --rm index-cli anime-index-ui
```

FZF berjalan di container image, bukan dari Python host. Jika source belum ada, command akan berhenti dengan `no anime directories found`; jika ingin memastikan binary tersedia:

```bash
docker compose --profile local run --rm index-cli fzf --version
```

### 3. Alternatif: queue melalui CLI

```bash
docker compose --profile local run --rm index-cli \
  anime-index --queue \
  --anime Frieren \
  --season 1 \
  --episode 7 \
  --source /data/anime-source/frieren/season-01/episode-07.mkv
```

Worker yang sedang berjalan akan mengambil job dari Redis:

```bash
docker compose logs -f worker
```

Pipeline yang dijalankan:

```text
validate source
  → video metadata/checksum
  → scene detection
  → 3 representative keyframes per scene
  → OpenCLIP embedding
  → Tesseract OCR
  → upload keyframes ke MinIO
  → simpan metadata/vector/OCR ke PostgreSQL
```

Job dapat dilanjutkan setelah worker restart. Scene/frame memakai identity constraint sehingga retry tidak membuat duplicate record.

### 4. Reindex

Reindex harus eksplisit menggunakan `--force-reindex`:

```bash
docker compose --profile local run --rm index-cli \
  anime-index --queue --force-reindex \
  --anime Frieren --season 1 --episode 7 \
  --source /data/anime-source/frieren/season-01/episode-07.mkv
```

Jangan menjalankan reindex massal tanpa kebutuhan karena proses embedding/OCR dapat memakan waktu dan resource.

## Search API

Base URL publik:

```text
https://anisceneapi.fhanalabs.site
```

Swagger UI tersedia di root API:

```text
https://anisceneapi.fhanalabs.site/
```

Alternatif dokumentasi dan schema:

```text
https://anisceneapi.fhanalabs.site/redoc
https://anisceneapi.fhanalabs.site/openapi.json
```

### Health

```bash
curl https://anisceneapi.fhanalabs.site/health
```

Response:

```json
{"status":"ok"}
```

Readiness internal:

```bash
curl https://anisceneapi.fhanalabs.site/health/ready
```

### Search screenshot

Endpoint menerima `multipart/form-data` dengan field `image`. Field `limit` opsional, default 10 dan maksimum 50.

```bash
curl -X POST https://anisceneapi.fhanalabs.site/api/v1/search \
  -F "image=@./screenshot.jpg" \
  -F "limit=10"
```

Format response:

```json
{
  "query": {
    "type": "image",
    "ocr_text": "example subtitle"
  },
  "results": [
    {
      "anime": {
        "id": "1",
        "title": "Frieren"
      },
      "episode": {
        "id": "7",
        "season": 1,
        "episode": 7,
        "title": "Episode title"
      },
      "scene": {
        "id": "42",
        "start_time": 755.2,
        "end_time": 778.8,
        "representative_time": 766.4
      },
      "match": {
        "timestamp": 766.4,
        "visual_score": 0.9231,
        "ocr_score": 0.81,
        "final_score": 0.9005
      },
      "thumbnail_url": "/api/v1/scenes/42/thumbnail"
    }
  ]
}
```

Score adalah ranking signal teknis, bukan probabilitas kebenaran.

### Public routes

```text
GET  /health
GET  /health/ready
POST /api/v1/search
GET  /api/v1/scenes/{scene_id}
GET  /api/v1/scenes/{scene_id}/thumbnail
GET  /api/v1/anime/{anime_id}
GET  /api/v1/anime/{anime_id}/episodes
```

Tidak ada public endpoint untuk upload raw video, download source, membuat job indexing, reindex, atau menghapus index.

## Local development

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
PYTHONPATH=api python3 -m unittest discover -s tests -v
PYTHONPATH=api uvicorn app.main:app --app-dir api --reload
```

CLI yang tersedia:

```text
anime-embed       Compare two image embeddings
anime-index       Index or queue one episode
anime-worker      Consume Redis indexing jobs
anime-index-ui    Browse local sources with FZF
```

---

Built with care by [FHANA Labs](https://fhanalabs.site/).
