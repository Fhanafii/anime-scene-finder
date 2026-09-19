from __future__ import annotations

import os

from .ocr import text_similarity


VISUAL_SCORE_WEIGHT = float(os.getenv("VISUAL_SCORE_WEIGHT", "0.8"))
OCR_SCORE_WEIGHT = float(os.getenv("OCR_SCORE_WEIGHT", "0.2"))


def fuse_scores(visual_score: float, query_text: str, candidate_text: str | None) -> tuple[float, float]:
    ocr_score = text_similarity(query_text, candidate_text or "") if query_text else 0.0
    if not query_text:
        return 0.0, visual_score
    return ocr_score, visual_score * VISUAL_SCORE_WEIGHT + ocr_score * OCR_SCORE_WEIGHT
