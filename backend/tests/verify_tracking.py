
import asyncio
import numpy as np
import torch
import redis.asyncio as aioredis
from services.inference.ml.engines.person_detector import PersonDetector
from services.inference.services.reid_service import ReIDService
from shared.logging.logger import get_logger

log = get_logger("verification")

async def test_reid_registration():
    redis = aioredis.from_url("redis://localhost", decode_responses=False)
    reid = ReIDService(redis)
    
    # Create a dummy person crop (BGR)
    crop = np.random.randint(0, 255, (200, 100, 3), dtype=np.uint8)
    
    log.info("Extracting features...")
    emb1 = reid.extract_features(crop)
    assert emb1.shape == (576,)
    
    log.info("Registering track...")
    await reid.register_track("test_id_123", emb1)
    
    log.info("Verifying match...")
    matched_id = await reid.get_global_id(emb1)
    log.info(f"Matched ID: {matched_id}")
    assert matched_id == "test_id_123"
    
    log.info("ReID test passed!")
    await redis.aclose()

async def test_tracking():
    detector = PersonDetector()
    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
    
    log.info("Running track on first frame...")
    boxes1, masks1, ids1 = detector.track(frame)
    
    log.info("Running track on second frame (persist=True)...")
    boxes2, masks2, ids2 = detector.track(frame)
    
    log.info(f"Tracks: {ids2}")
    
if __name__ == "__main__":
    asyncio.run(test_reid_registration())
    # Skipping test_tracking as it requires model weights and GUI might not be available
