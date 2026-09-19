from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

from .indexer import IndexRequest
from .jobs import enqueue
from .source import verify_source


def select(items: list[str], prompt: str) -> str:
    result = subprocess.run(["fzf", "--prompt", prompt], input="\n".join(items), text=True, capture_output=True, check=False)
    if result.returncode or not result.stdout.strip():
        raise SystemExit(0)
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local FZF indexing operator")
    parser.add_argument("--source-root", default=os.getenv("SOURCE_ROOT", "/data/anime-source"))
    args = parser.parse_args()
    root = Path(args.source_root)
    anime_dirs = sorted(path for path in root.iterdir() if path.is_dir())
    if not anime_dirs:
        raise SystemExit("no anime directories found")
    anime_dir = Path(select([str(path) for path in anime_dirs], "Anime> "))
    season_dirs = sorted(path for path in anime_dir.iterdir() if path.is_dir())
    if not season_dirs:
        raise SystemExit("no season directories found")
    season_dir = Path(select([str(path) for path in season_dirs], "Season> "))
    sources = sorted(str(path) for path in season_dir.iterdir() if path.suffix.lower() in {".mkv", ".mp4", ".avi", ".webm"})
    if not sources:
        raise SystemExit("no video episodes found")
    source = Path(select(sources, "Episode> "))
    verify_source(source)
    episode_match = re.search(r"episode[-_ ]?(\d+)", source.stem, re.IGNORECASE)
    season_match = re.search(r"season[-_ ]?(\d+)", str(source.parent), re.IGNORECASE)
    if not episode_match or not season_match:
        raise SystemExit("source path must contain season-01 and episode-01")
    anime = anime_dir.name
    enqueue(IndexRequest(anime, int(season_match.group(1)), int(episode_match.group(1)), source))
    print(f"queued {source}")


if __name__ == "__main__":
    main()
