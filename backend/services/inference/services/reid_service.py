import numpy as np
import redis.asyncio as redis
from shared.logging.logger import get_logger

logger = get_logger(__name__)

import cv2
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

class ReIDService:
    """Service for cross-camera person re-identification using feature embeddings."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.threshold = 0.7 
        self.embedding_ttl = 3600
        self.redis_key_prefix = "reid:embeddings:"
        
        # Load a lightweight feature extractor
        try:
            # Using MobileNetV3 Small as a fast feature extractor (576 output features)
            backbone = models.mobilenet_v3_small(weights=models.MobileNetV3_Small_Weights.DEFAULT)
            # Remove the classifier head to get embeddings
            self.model = torch.nn.Sequential(*(list(backbone.children())[:-1]), nn.Flatten())
            self.model.eval()
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model.to(self.device)
            
            self.transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
            logger.info("ReIDService: Feature extractor loaded", extra={"device": str(self.device)})
        except Exception as e:
            logger.error("ReIDService: Failed to load model, using fallback", extra={"error": str(e)})
            self.model = None

    async def get_global_id(self, appearance_embedding: np.ndarray) -> str | None:
        """Compare current embedding with stored global embeddings in Redis."""
        try:
            # MVP: Key scanning. Production: RediSearch HNSW.
            keys = await self.redis.keys(f"{self.redis_key_prefix}*")
            if not keys:
                return None

            best_match_id = None
            max_sim = -1.0

            for key in keys:
                stored_bytes = await self.redis.get(key)
                if not stored_bytes:
                    continue
                
                stored_emb = np.frombuffer(stored_bytes, dtype=np.float32)
                # Cosine similarity (already normalized vectors)
                sim = np.dot(appearance_embedding, stored_emb)
                
                if sim > self.threshold and sim > max_sim:
                    max_sim = sim
                    # key format: 'reid:embeddings:global_uuid'
                    best_match_id = key.decode().split(":")[-1]

            return best_match_id
            
        except Exception as e:
            logger.error("Re-ID matching failed", extra={"error": str(e)})
            return None

    async def register_track(self, global_id: str, embedding: np.ndarray):
        """Register a new global track embedding in Redis."""
        key = f"{self.redis_key_prefix}{global_id}"
        await self.redis.set(key, embedding.tobytes(), ex=self.embedding_ttl)

    def extract_features(self, person_crop: np.ndarray) -> np.ndarray:
        """Extract normalized feature vector from person crop."""
        if self.model is None:
            # Fallback to random for stability if model fails to load
            vec = np.random.rand(576).astype(np.float32)
            return vec / np.linalg.norm(vec)

        try:
            # Convert OpenCV BGR to RGB PIL Image
            img = Image.fromarray(cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB))
            img_t = self.transform(img).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                features = self.model(img_t)
                features = features.cpu().numpy().flatten()
                
            # L2 Normalize
            return features / (np.linalg.norm(features) + 1e-6)
        except Exception as e:
            logger.error("Feature extraction failed", extra={"error": str(e)})
            return np.zeros(576, dtype=np.float32)
