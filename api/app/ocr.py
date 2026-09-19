from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


def normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def text_similarity(query: str, candidate: str) -> float:
    query = normalize_text(query)
    candidate = normalize_text(candidate)
    if not query or not candidate:
        return 0.0
    query_tokens = set(query.split())
    candidate_tokens = set(candidate.split())
    token_score = len(query_tokens & candidate_tokens) / len(query_tokens)
    substring_score = 1.0 if query in candidate or candidate in query else 0.0
    return max(token_score, substring_score)


class TesseractOCR:
    engine = "tesseract"

    def __init__(self, language: str | None = None) -> None:
        self.language = language or os.getenv("OCR_LANGUAGE", "eng")

    @property
    def version(self) -> str:
        result = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, check=True)
        return result.stdout.splitlines()[0] if result.stdout else "unknown"

    def extract(self, image_path: str | Path) -> str:
        result = subprocess.run(
            ["tesseract", str(image_path), "stdout", "-l", self.language, "--psm", "6"],
            capture_output=True,
            text=True,
            check=True,
        )
        return normalize_text(result.stdout)
