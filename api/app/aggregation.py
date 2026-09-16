from __future__ import annotations

from dataclasses import dataclass

from .vector_store import VectorMatch


@dataclass(frozen=True)
class SceneCandidate:
    match: VectorMatch
    frame_count: int
    average_similarity: float


def aggregate_scene_matches(matches: list[VectorMatch], limit: int) -> list[SceneCandidate]:
    if limit < 1:
        raise ValueError("limit must be positive")
    grouped: dict[int, list[VectorMatch]] = {}
    for match in matches:
        grouped.setdefault(match.scene_id, []).append(match)

    candidates = []
    for frames in grouped.values():
        best = max(frames, key=lambda frame: frame.similarity)
        average = sum(frame.similarity for frame in frames) / len(frames)
        candidates.append(SceneCandidate(best, len(frames), average))
    candidates.sort(key=lambda candidate: (candidate.match.similarity, candidate.average_similarity), reverse=True)
    return candidates[:limit]
