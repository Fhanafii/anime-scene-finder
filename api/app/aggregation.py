from __future__ import annotations

from dataclasses import dataclass

from .vector_store import VectorMatch


@dataclass(frozen=True)
class SceneCandidate:
    match: VectorMatch
    frame_count: int
    average_similarity: float
    ocr_score: float = 0.0
    final_score: float | None = None


def aggregate_scene_matches(matches: list[VectorMatch], limit: int, scores: dict[int, tuple[float, float]] | None = None) -> list[SceneCandidate]:
    if limit < 1:
        raise ValueError("limit must be positive")
    grouped: dict[int, list[VectorMatch]] = {}
    for match in matches:
        grouped.setdefault(match.scene_id, []).append(match)

    candidates = []
    for frames in grouped.values():
        best = max(frames, key=lambda frame: scores.get(frame.frame_id, (0.0, frame.similarity))[1] if scores else frame.similarity)
        average = sum(frame.similarity for frame in frames) / len(frames)
        ocr_score, final_score = scores.get(best.frame_id, (0.0, best.similarity)) if scores else (0.0, best.similarity)
        candidates.append(SceneCandidate(best, len(frames), average, ocr_score, final_score))
    candidates.sort(key=lambda candidate: (candidate.final_score or 0.0, candidate.average_similarity), reverse=True)
    return candidates[:limit]
