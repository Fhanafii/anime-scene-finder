from __future__ import annotations

import argparse
from pathlib import Path

from .indexer import IndexRequest, index_episode
from .jobs import enqueue


def main() -> None:
    parser = argparse.ArgumentParser(description="Index one local anime episode")
    parser.add_argument("--anime", required=True)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--episode", required=True, type=int)
    parser.add_argument("--source", required=True)
    parser.add_argument("--title")
    parser.add_argument("--queue", action="store_true", help="enqueue for anime-worker")
    parser.add_argument("--force-reindex", action="store_true")
    args = parser.parse_args()
    request = IndexRequest(args.anime, args.season, args.episode, Path(args.source), args.title, 0, args.force_reindex)
    if args.queue:
        enqueue(request)
        return
    print(index_episode(request))


if __name__ == "__main__":
    main()
