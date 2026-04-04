"""Appearance embedding retained for Milvus-backed person re-identification."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import torch
from torchvision.transforms import transforms

from src.services.tracking.reid.mobilenetv2_backbone import MobileNetV2Bottle

LOGGER = logging.getLogger(__name__)
INPUT_WIDTH = 224
DEFAULT_WEIGHTS_PATH = (
    Path(__file__).resolve().parent / "weights" / "mobilenetv2_bottleneck_wts.pt"
)


class TrackingReIdEmbedder:
    """Build and run the retained appearance embedder used for Milvus re-id."""

    def __init__(
        self,
        embedder_name: str,
        *,
        weights_path: str | Path | None = None,
        half: bool = True,
        max_batch_size: int = 16,
        expects_bgr: bool = True,
        gpu: bool = True,
    ) -> None:
        normalized_name = (embedder_name or "mobilenet").strip().lower()
        if normalized_name not in {"mobilenet", "mobilenetv2"}:
            raise ValueError(
                f"Unsupported tracking re-id embedder '{embedder_name}'.",
            )

        model_weights_path = (
            Path(weights_path)
            if weights_path is not None
            else DEFAULT_WEIGHTS_PATH
        )
        if not model_weights_path.exists():
            raise FileNotFoundError(
                f"Tracking re-id weights not found at {model_weights_path}.",
            )

        self._model = MobileNetV2Bottle(input_size=INPUT_WIDTH, width_mult=1.0)
        self._model.load_state_dict(torch.load(str(model_weights_path)))

        self._gpu = gpu and torch.cuda.is_available()
        if self._gpu:
            self._model.cuda()
            self._half = half
            if self._half:
                self._model.half()
        else:
            self._half = False

        self._model.eval()
        self._max_batch_size = max_batch_size
        self._expects_bgr = expects_bgr
        self._transform = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ],
        )

        LOGGER.info("Tracking re-id embedder initialised.")
        LOGGER.info("- gpu enabled: %s", self._gpu)
        LOGGER.info("- half precision: %s", self._half)
        LOGGER.info("- max batch size: %s", self._max_batch_size)
        LOGGER.info("- expects BGR: %s", self._expects_bgr)

        self.embed([np.zeros((100, 100, 3), dtype=np.uint8)])

    def embed(self, image_chips: list[np.ndarray]) -> list[np.ndarray]:
        """Return one normalized embedding vector per cropped detection chip."""

        if not image_chips:
            return []

        preprocessed_images = [self._preprocess(image) for image in image_chips]
        embeddings: list[np.ndarray] = []
        with torch.inference_mode():
            for batch_start in range(0, len(preprocessed_images), self._max_batch_size):
                batch_tensor = torch.cat(
                    preprocessed_images[batch_start : batch_start + self._max_batch_size],
                    dim=0,
                )
                if self._gpu:
                    batch_tensor = batch_tensor.cuda()
                    if self._half:
                        batch_tensor = batch_tensor.half()
                output = self._model.forward(batch_tensor)
                embeddings.extend(
                    np.asarray(embedding, dtype=np.float32).reshape(-1)
                    for embedding in output.cpu().data.numpy()
                )
        return embeddings

    def _preprocess(self, image: np.ndarray) -> torch.Tensor:
        image_rgb = image[..., ::-1] if self._expects_bgr else image
        # OpenCV exposes resize dynamically, which pylint cannot introspect.
        # pylint: disable=no-member
        resized_image = cv2.resize(image_rgb, (INPUT_WIDTH, INPUT_WIDTH))
        tensor = self._transform(resized_image)
        return tensor.view(1, 3, INPUT_WIDTH, INPUT_WIDTH)
