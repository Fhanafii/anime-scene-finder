from __future__ import annotations

import argparse
import json

from .embedding import ImageEmbedder, cosine_similarity


def main() -> None:
    parser = argparse.ArgumentParser(description="Create OpenCLIP image embeddings")
    parser.add_argument("image", help="first image path")
    parser.add_argument("candidate", help="second image path to compare")
    args = parser.parse_args()

    embedder = ImageEmbedder()
    first = embedder.encode(args.image)
    second = embedder.encode(args.candidate)
    print(json.dumps({"dimension": len(first), "cosine_similarity": cosine_similarity(first, second)}))


if __name__ == "__main__":
    main()
