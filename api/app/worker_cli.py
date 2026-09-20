from __future__ import annotations

import logging

from .indexer import index_episode
from .jobs import dequeue, enqueue


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    while True:
        request = dequeue()
        if request is not None:
            logger.info("indexing %s S%02dE%02d (attempt %d)", request.anime, request.season, request.episode, request.retries + 1)
            try:
                episode_id = index_episode(request)
                logger.info("indexed episode %s: %s S%02dE%02d", episode_id, request.anime, request.season, request.episode)
            except Exception:
                if request.retries < 3:
                    logger.exception("indexing failed; retrying %s S%02dE%02d", request.anime, request.season, request.episode)
                    enqueue(request.__class__(
                        anime=request.anime,
                        season=request.season,
                        episode=request.episode,
                        source=request.source,
                        title=request.title,
                        retries=request.retries + 1,
                        force_reindex=request.force_reindex,
                    ))
                else:
                    logger.exception("indexing failed permanently: %s S%02dE%02d", request.anime, request.season, request.episode)


if __name__ == "__main__":
    main()
