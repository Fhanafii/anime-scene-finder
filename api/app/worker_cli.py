from __future__ import annotations

from .indexer import index_episode
from .jobs import dequeue, enqueue


def main() -> None:
    while True:
        request = dequeue()
        if request is not None:
            try:
                index_episode(request)
            except Exception:
                if request.retries < 3:
                    enqueue(request.__class__(
                        anime=request.anime,
                        season=request.season,
                        episode=request.episode,
                        source=request.source,
                        title=request.title,
                        retries=request.retries + 1,
                        force_reindex=request.force_reindex,
                    ))


if __name__ == "__main__":
    main()
