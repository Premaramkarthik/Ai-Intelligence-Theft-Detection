from __future__ import annotations

from src.opencv_pipeline.output.publisher import InferenceOverlayCache


def test_inference_overlay_cache_is_scoped_by_camera() -> None:
    cache = InferenceOverlayCache()

    cache.record("cam_1", "track_1", "alert", 0.9, "alert")
    cache.record("cam_2", "track_1", "normal", 0.1, "normal")

    cam_1_items = cache.items_for_camera("cam_1")
    cam_2_items = cache.items_for_camera("cam_2")

    assert len(cam_1_items) == 1
    assert cam_1_items[0][1].label == "alert"
    assert len(cam_2_items) == 1
    assert cam_2_items[0][1].label == "normal"


def test_inference_overlay_cache_filters_to_active_tracks() -> None:
    cache = InferenceOverlayCache()

    cache.record("cam_1", "active_track", "warning", 0.6, "warning")
    cache.record("cam_1", "stale_track", "alert", 0.9, "alert")

    items = cache.items_for_camera("cam_1", {"active_track"})

    assert len(items) == 1
    assert items[0][0] == "active_track"
    assert items[0][1].label == "warning"


def test_inference_overlay_cache_retains_active_prediction_until_track_exits() -> None:
    cache = InferenceOverlayCache()

    cache.record("cam_1", "active_track", "warning", 0.6, "warning")

    first_read = cache.items_for_camera("cam_1", {"active_track"})
    second_read = cache.items_for_camera("cam_1", {"active_track"})

    assert first_read == second_read
    assert second_read[0][1].label == "warning"


def test_inference_overlay_cache_removes_inactive_tracks() -> None:
    cache = InferenceOverlayCache()

    cache.record("cam_1", "active_track", "warning", 0.6, "warning")
    cache.record("cam_1", "inactive_track", "alert", 0.9, "alert")

    cache.retain_active_tracks("cam_1", {"active_track"})

    items = cache.items_for_camera("cam_1")
    assert len(items) == 1
    assert items[0][0] == "active_track"
