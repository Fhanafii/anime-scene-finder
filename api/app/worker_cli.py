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
                    enqueue(request.__class__(request.anime, request.season, request.episode, request.source, request.title, request.retries + 1))


if __name__ == "__main__":
    main()
