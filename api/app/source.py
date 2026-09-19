from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .media import video_metadata


def verify_source(path: Path) -> dict[str, int | float | str]:
    if not path.is_file() or not os.access(path, os.R_OK):
        raise ValueError("source file is missing or unreadable")
    return {"source_path": str(path), "source_size": path.stat().st_size, **video_metadata(path)}


class AniCliProvider:
    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.getenv("ANI_CLI_BIN", "ani-cli")

    def search(self, title: str) -> str:
        result = subprocess.run([self.binary, "--search", title], check=True, capture_output=True, text=True)
        return result.stdout

    def list_episodes(self, title: str) -> str:
        result = subprocess.run([self.binary, "--episodes", title], check=True, capture_output=True, text=True)
        return result.stdout

    def download_episode(self, title: str, episode: int, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [self.binary, "--download", "--episode", str(episode), "--output", str(output_dir), title],
            check=True,
        )
