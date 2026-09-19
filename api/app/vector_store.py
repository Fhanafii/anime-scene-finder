from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VectorMatch:
    frame_id: int
    scene_id: int
    timestamp: float
    object_key: str
    similarity: float
    anime_id: int
    anime_title: str
    episode_id: int
    season: int
    episode: int
    episode_title: str | None
    scene_start: float
    scene_end: float
    scene_representative: float
    ocr_text: str | None = None
    ocr_engine: str | None = None
    ocr_engine_version: str | None = None


def vector_literal(values: list[float]) -> str:
    if not values:
        raise ValueError("embedding must not be empty")
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _psycopg_dsn(url: str) -> str:
    return re.sub(r"^postgresql(?:\+\w+)?://", "postgresql://", url)


class VectorStore:
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = _psycopg_dsn(dsn or os.environ["DATABASE_URL"])

    def insert_frame(
        self,
        *,
        scene_id: int,
        timestamp: float,
        object_key: str,
        embedding: list[float],
        model: str,
        model_version: str,
        ocr_text: str = "",
        ocr_engine: str = "",
        ocr_engine_version: str = "",
    ) -> int:
        import psycopg

        dimension = len(embedding)
        if not dimension:
            raise ValueError("embedding must not be empty")
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """
                INSERT INTO scene_frames
                    (scene_id, timestamp, object_key, embedding, embedding_model,
                    embedding_model_version, embedding_dimension, ocr_text, ocr_engine,
                    ocr_engine_version)
                VALUES (%s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (scene_id, timestamp, embedding_model, embedding_model_version)
                DO UPDATE SET object_key = EXCLUDED.object_key,
                              embedding = EXCLUDED.embedding,
                              embedding_dimension = EXCLUDED.embedding_dimension,
                              ocr_text = EXCLUDED.ocr_text,
                              ocr_engine = EXCLUDED.ocr_engine,
                              ocr_engine_version = EXCLUDED.ocr_engine_version
                RETURNING id
                """,
                (scene_id, timestamp, object_key, vector_literal(embedding), model, model_version, dimension,
                 ocr_text, ocr_engine, ocr_engine_version),
            ).fetchone()
        return row[0]

    def check_connection(self) -> None:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            connection.execute("SELECT 1").fetchone()

    def get_scene(self, scene_id: int) -> dict | None:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """SELECT s.id, s.start_time, s.end_time, s.representative_time,
                e.id, e.season_number, e.episode_number, e.title,
                a.id, a.title
                FROM scenes s JOIN episodes e ON e.id = s.episode_id JOIN anime a ON a.id = e.anime_id
                WHERE s.id = %s""", (scene_id,)
            ).fetchone()
            if not row:
                return None
            thumbnail = connection.execute(
                "SELECT object_key FROM scene_frames WHERE scene_id = %s ORDER BY timestamp LIMIT 1", (scene_id,)
            ).fetchone()
        return {
            "id": row[0], "start_time": row[1], "end_time": row[2], "representative_time": row[3],
            "episode": {"id": row[4], "season": row[5], "episode": row[6], "title": row[7]},
            "anime": {"id": row[8], "title": row[9]}, "object_key": thumbnail[0] if thumbnail else None,
        }

    def get_anime(self, anime_id: int) -> dict | None:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            row = connection.execute("SELECT id, title, slug FROM anime WHERE id = %s", (anime_id,)).fetchone()
        return {"id": row[0], "title": row[1], "slug": row[2]} if row else None

    def get_episodes(self, anime_id: int) -> list[dict]:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            rows = connection.execute(
                """SELECT id, season_number, episode_number, title, duration_seconds
                FROM episodes WHERE anime_id = %s ORDER BY season_number, episode_number""", (anime_id,)
            ).fetchall()
        return [{"id": row[0], "season": row[1], "episode": row[2], "title": row[3], "duration": row[4]} for row in rows]

    def start_or_resume_job(
        self, episode_id: int, total_scenes: int, embedding_model: str, embedding_version: str,
        ocr_engine: str, ocr_version: str,
    ) -> int:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            row = connection.execute(
                """SELECT id FROM indexing_jobs
                WHERE episode_id = %s AND status IN ('PENDING', 'PROCESSING')
                ORDER BY id DESC LIMIT 1""", (episode_id,)
            ).fetchone()
            if row:
                job_id = row[0]
                connection.execute(
                    """UPDATE indexing_jobs SET status = 'PROCESSING', total_scenes = %s,
                    embedding_model = %s, embedding_model_version = %s,
                    ocr_engine = %s, ocr_engine_version = %s,
                    started_at = COALESCE(started_at, CURRENT_TIMESTAMP), updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s""", (total_scenes, embedding_model, embedding_version, ocr_engine, ocr_version, job_id)
                )
                return job_id
            return connection.execute(
                """INSERT INTO indexing_jobs
                    (episode_id, status, total_scenes, embedding_model, embedding_model_version,
                     ocr_engine, ocr_engine_version, started_at)
                VALUES (%s, 'PROCESSING', %s, %s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING id""",
                (episode_id, total_scenes, embedding_model, embedding_version, ocr_engine, ocr_version),
            ).fetchone()[0]

    def scene_frame_count(self, scene_id: int, model: str, model_version: str) -> int:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            return connection.execute(
                """SELECT count(*) FROM scene_frames
                WHERE scene_id = %s AND embedding_model = %s AND embedding_model_version = %s""",
                (scene_id, model, model_version),
            ).fetchone()[0]

    def mark_scene_processed(self, job_id: int, scene_index: int, frame_count: int) -> None:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                """UPDATE indexing_jobs SET processed_scenes = GREATEST(processed_scenes, %s),
                processed_frames = GREATEST(processed_frames, (%s * %s)),
                progress = LEAST(1.0, GREATEST(processed_scenes, %s)::float / NULLIF(total_scenes, 0)),
                updated_at = CURRENT_TIMESTAMP WHERE id = %s""",
                (scene_index + 1, scene_index + 1, frame_count, scene_index + 1, job_id),
            )

    def complete_job(self, job_id: int) -> None:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                """UPDATE indexing_jobs SET status = 'COMPLETED', progress = 1.0,
                completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = %s""", (job_id,)
            )

    def fail_job(self, job_id: int, message: str) -> None:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                """UPDATE indexing_jobs SET status = 'FAILED', error_message = %s,
                updated_at = CURRENT_TIMESTAMP WHERE id = %s""", (message[:1000], job_id)
            )

    def upsert_episode(
        self, *, title: str, slug: str, season: int, episode: int, episode_title: str | None,
        duration: float, source_identifier: str, source_path: str, source_checksum: str, source_size: int,
    ) -> tuple[int, int]:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            anime_id = connection.execute(
                """INSERT INTO anime (title, slug) VALUES (%s, %s)
                ON CONFLICT (slug) DO UPDATE SET title = EXCLUDED.title
                RETURNING id""", (title, slug)
            ).fetchone()[0]
            episode_id = connection.execute(
                """INSERT INTO episodes
                    (anime_id, season_number, episode_number, title, duration_seconds, source_identifier,
                     source_path, source_checksum, source_size)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (anime_id, season_number, episode_number)
                DO UPDATE SET title = EXCLUDED.title, duration_seconds = EXCLUDED.duration_seconds,
                              source_identifier = EXCLUDED.source_identifier,
                              source_path = EXCLUDED.source_path,
                              source_checksum = EXCLUDED.source_checksum,
                              source_size = EXCLUDED.source_size
                RETURNING id""",
                (anime_id, season, episode, episode_title, duration, source_identifier,
                 source_path, source_checksum, source_size),
            ).fetchone()[0]
        return anime_id, episode_id

    def insert_scene(self, episode_id: int, scene_index: int, start: float, end: float, representative: float) -> int:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            return connection.execute(
                """INSERT INTO scenes (episode_id, scene_index, start_time, end_time, representative_time)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (episode_id, scene_index)
                DO UPDATE SET start_time = EXCLUDED.start_time, end_time = EXCLUDED.end_time,
                              representative_time = EXCLUDED.representative_time
                RETURNING id""",
                (episode_id, scene_index, start, end, representative),
            ).fetchone()[0]

    def search(
        self,
        embedding: list[float],
        *,
        model: str,
        model_version: str,
        limit: int = 10,
    ) -> list[VectorMatch]:
        import psycopg

        if limit < 1:
            raise ValueError("limit must be positive")
        dimension = len(embedding)
        if not dimension:
            raise ValueError("embedding must not be empty")
        with psycopg.connect(self.dsn) as connection:
            rows = connection.execute(
                """
                SELECT sf.id, sf.scene_id, sf.timestamp, sf.object_key,
                       1 - (sf.embedding <=> %s::vector) AS similarity,
                       a.id, a.title, e.id, e.season_number, e.episode_number,
                       e.title, s.start_time, s.end_time, s.representative_time,
                       sf.ocr_text, sf.ocr_engine, sf.ocr_engine_version
                FROM scene_frames sf
                JOIN scenes s ON s.id = sf.scene_id
                JOIN episodes e ON e.id = s.episode_id
                JOIN anime a ON a.id = e.anime_id
                WHERE sf.embedding_model = %s
                  AND sf.embedding_model_version = %s
                  AND sf.embedding_dimension = %s
                ORDER BY sf.embedding <=> %s::vector
                LIMIT %s
                """,
                (vector_literal(embedding), model, model_version, dimension, vector_literal(embedding), limit),
            ).fetchall()
        return [VectorMatch(*row) for row in rows]

    def ensure_hnsw_index(self, dimension: int) -> None:
        """Create a dimension-specific index; pgvector cannot index mixed dimensions."""
        if dimension < 1:
            raise ValueError("dimension must be positive")
        with_dimension = f"scene_frames_embedding_hnsw_{dimension}"
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                f"""CREATE INDEX IF NOT EXISTS {with_dimension}
                ON scene_frames USING hnsw ((embedding::vector({dimension})) vector_cosine_ops)
                WHERE embedding_dimension = {dimension}"""
            )
