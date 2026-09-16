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
                SELECT id, scene_id, timestamp, object_key,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM scene_frames
                WHERE embedding_model = %s
                  AND embedding_model_version = %s
                  AND embedding_dimension = %s
                ORDER BY embedding <=> %s::vector
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
