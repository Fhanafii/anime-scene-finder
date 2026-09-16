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
                     embedding_model_version, embedding_dimension)
                VALUES (%s, %s, %s, %s::vector, %s, %s, %s)
                ON CONFLICT (scene_id, timestamp, embedding_model, embedding_model_version)
                DO UPDATE SET object_key = EXCLUDED.object_key,
                              embedding = EXCLUDED.embedding,
                              embedding_dimension = EXCLUDED.embedding_dimension
                RETURNING id
                """,
                (scene_id, timestamp, object_key, vector_literal(embedding), model, model_version, dimension),
            ).fetchone()
        return row[0]

    def check_connection(self) -> None:
        import psycopg

        with psycopg.connect(self.dsn) as connection:
            connection.execute("SELECT 1").fetchone()

    def upsert_episode(
        self, *, title: str, slug: str, season: int, episode: int, episode_title: str | None,
        duration: float, source_identifier: str,
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
                    (anime_id, season_number, episode_number, title, duration_seconds, source_identifier)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (anime_id, season_number, episode_number)
                DO UPDATE SET title = EXCLUDED.title, duration_seconds = EXCLUDED.duration_seconds,
                              source_identifier = EXCLUDED.source_identifier
                RETURNING id""",
                (anime_id, season, episode, episode_title, duration, source_identifier),
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
                       e.title, s.start_time, s.end_time, s.representative_time
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
