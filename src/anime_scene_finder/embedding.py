from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str = "ViT-B-32"
    pretrained: str = "openai"
    device: str = "auto"

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        return cls(
            model_name=os.getenv("EMBEDDING_MODEL_NAME", cls.model_name),
            pretrained=os.getenv("EMBEDDING_PRETRAINED", cls.pretrained),
            device=os.getenv("EMBEDDING_DEVICE", cls.device),
        )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must have the same non-zero dimension")
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if not left_norm or not right_norm:
        raise ValueError("vectors must not be zero vectors")
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


class ImageEmbedder:
    """OpenCLIP image embedder; model and preprocessing are loaded once."""

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or EmbeddingConfig.from_env()
        self._model = None
        self._preprocess = None
        self._torch = None
        self.device = None

    def _load(self) -> None:
        if self._model is not None:
            return

        import open_clip
        import torch

        device = self.config.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            self.config.model_name,
            pretrained=self.config.pretrained,
            device=self.device,
        )
        self._model.eval()
        self._torch = torch

    def encode(self, image_path: str | Path) -> list[float]:
        self._load()
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        tensor = self._preprocess(image).unsqueeze(0).to(self.device)
        with self._torch.inference_mode():
            vector = self._model.encode_image(tensor)
            vector /= vector.norm(dim=-1, keepdim=True)
        return vector[0].cpu().tolist()
