from __future__ import annotations

import asyncpg
import numpy as np
from PIL import Image
from shared.core.settings import get_settings
from shared.logging.logger import get_logger

import cv2
import torch
import torch.nn as nn
from torchvision import models, transforms

logger = get_logger(__name__)


class ReIDService:
    """Cross-camera person re-identification using pgvector when explicitly enabled."""

    def __init__(self, _unused_client=None):
        self._settings = get_settings()
        self.threshold = 0.7
        self.embedding_ttl = 3600
        self.available = False
        self.model = None
        self.device = torch.device("cpu")
        self.transform = None
        self._pool: asyncpg.Pool | None = None

        if not self._settings.reid_enabled or self._settings.reid_backend != "pgvector":
            logger.info(
                "ReIDService disabled",
                extra={"enabled": self._settings.reid_enabled, "backend": self._settings.reid_backend},
            )
            return

        try:
            weights_enum = getattr(models, "MobileNetV3_Small_Weights", None)
            if weights_enum is not None:
                backbone = models.mobilenet_v3_small(weights=weights_enum.DEFAULT)
            else:
                backbone = models.mobilenet_v3_small(pretrained=True)

            self.model = torch.nn.Sequential(*(list(backbone.children())[:-1]), nn.Flatten())
            self.model.eval()
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model.to(self.device)
            self.transform = transforms.Compose(
                [
                    transforms.Resize((224, 224)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ]
            )
            self.available = True
            logger.info("ReIDService ready", extra={"device": str(self.device), "backend": "pgvector"})
        except Exception as exc:
            logger.warning("ReIDService disabled", extra={"error": str(exc)})

    async def _ensure_pool(self) -> asyncpg.Pool | None:
        if not self.available:
            return None
        if self._pool is None:
            try:
                self._pool = await asyncpg.create_pool(dsn=self._settings.db_url, min_size=1, max_size=2)
            except Exception as exc:
                self.available = False
                logger.warning("ReIDService disabled", extra={"error": str(exc), "backend": "pgvector"})
                return None
        return self._pool

    @staticmethod
    def _vector_literal(embedding: np.ndarray) -> str:
        return "[" + ",".join(f"{float(value):.6f}" for value in embedding.tolist()) + "]"

    async def get_global_id(
        self,
        appearance_embedding: np.ndarray,
        *,
        organization_id: str = "default-org",
        store_id: str = "main-store",
    ) -> str | None:
        pool = await self._ensure_pool()
        if pool is None:
            return None
        try:
            row = await pool.fetchrow(
                """
                SELECT global_id, (embedding <=> $3::vector) AS distance
                FROM reid_identities
                WHERE organization_id = $1 AND store_id = $2
                ORDER BY distance ASC
                LIMIT 1
                """,
                organization_id,
                store_id,
                self._vector_literal(appearance_embedding),
            )
            if not row:
                return None
            similarity = 1.0 - float(row["distance"])
            return str(row["global_id"]) if similarity >= self.threshold else None
        except Exception as exc:
            logger.error("Re-ID matching failed", extra={"error": str(exc)})
            return None

    async def register_track(
        self,
        global_id: str,
        embedding: np.ndarray,
        *,
        organization_id: str = "default-org",
        store_id: str = "main-store",
    ) -> None:
        pool = await self._ensure_pool()
        if pool is None:
            return
        try:
            await pool.execute(
                """
                INSERT INTO reid_identities (global_id, organization_id, store_id, embedding, updated_at)
                VALUES ($1, $2, $3, $4::vector, NOW())
                ON CONFLICT (global_id) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    organization_id = EXCLUDED.organization_id,
                    store_id = EXCLUDED.store_id,
                    updated_at = NOW()
                """,
                global_id,
                organization_id,
                store_id,
                self._vector_literal(embedding),
            )
        except Exception as exc:
            logger.error("Re-ID registration failed", extra={"error": str(exc)})

    def extract_features(self, person_crop: np.ndarray) -> np.ndarray | None:
        if not self.available or self.model is None or self.transform is None:
            return None

        try:
            img = Image.fromarray(cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB))
            img_t = self.transform(img).unsqueeze(0).to(self.device)
            with torch.no_grad():
                features = self.model(img_t)
                features = features.cpu().numpy().flatten()
            return features / (np.linalg.norm(features) + 1e-6)
        except Exception as exc:
            logger.error("Feature extraction failed", extra={"error": str(exc)})
            return None
