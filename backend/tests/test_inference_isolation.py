from services.inference.ml.pipeline import InferencePipeline


def test_per_camera_runtime_state_isolated():
    pipeline = InferencePipeline()

    cam_a = pipeline._new_state()
    cam_b = pipeline._new_state()

    cam_a.frame_count = 11
    cam_a.skip_n = 5
    cam_a.current_incident = None
    cam_a.buffer.push(__import__("numpy").zeros((2, 2, 3), dtype="uint8"))
    cam_a.interaction.update([{"id": "track-a"}], [])

    assert cam_b.frame_count == 0
    assert cam_b.skip_n != cam_a.skip_n
    assert len(cam_a.buffer) == 1
    assert len(cam_b.buffer) == 0
    assert cam_a.interaction is not cam_b.interaction
