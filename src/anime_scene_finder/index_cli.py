from __future__ import annotations

import argparse
from pathlib import Path

from .indexer import IndexRequest, index_episode


def main() -> None:
    parser = argparse.ArgumentParser(description="Index one local anime episode")
    parser.add_argument("--anime", required=True)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--episode", required=True, type=int)
    parser.add_argument("--source", required=True)
    parser.add_argument("--title")
    args = parser.parse_args()
    print(index_episode(IndexRequest(args.anime, args.season, args.episode, Path(args.source), args.title)))


if __name__ == "__main__":
    main()
