from __future__ import annotations

import logging
import shutil
from pathlib import Path

from src.core.logger.logger import configure_logging


def test_configure_logging_writes_subsystem_logs_to_flat_files() -> None:
    temp_directory = Path.cwd() / "runtime" / "logger-test-output"
    shutil.rmtree(temp_directory, ignore_errors=True)
    temp_directory.mkdir(parents=True, exist_ok=True)
    log_directory = temp_directory
    configure_logging(
        "DEBUG",
        False,
        enable_file_logging=True,
        log_directory=log_directory,
        log_file_prefix="backend",
        enable_subsystem_file_logging=True,
    )

    logging.getLogger("src.services.tracking.updates").info(
        "Inference sample received.",
        extra={"structured": {"event": "inference.input_received", "camera_id": "cam_1"}},
    )
    logging.getLogger("src.opencv_pipeline.detection.yolo").info(
        "Person detection batch completed.",
        extra={"structured": {"event": "person_detection.batch_completed", "frame_count": 1}},
    )
    logging.getLogger("src.services.tracking.identity.milvus_store").info(
        "Milvus batch resolve completed.",
        extra={"structured": {"event": "milvus.batch_resolved", "stored_records": 2}},
    )
    logging.getLogger("src.services.inference.orchestrator").info(
        "Inference prediction emitted: camera_id=cam_1 local_track_id=track_7 "
        "persistent_id=person_42 strategy=vjepa_probe model_name=vjepa_finetune "
        "label=warning alert_level=warning score=0.742100",
        extra={
            "structured": {
                "event": "inference.prediction_emitted",
                "camera_id": "cam_1",
                "local_track_id": "track_7",
                "persistent_id": "person_42",
                "model_name": "vjepa_finetune",
                "label": "warning",
                "alert_level": "warning",
                "score": 0.7421,
            }
        },
    )

    for handler in logging.getLogger().handlers:
        flush = getattr(handler, "flush", None)
        if callable(flush):
            flush()

    try:
        all_logs = (log_directory / "all.log").read_text(encoding="utf-8")
        inference_logs = (log_directory / "inference.log").read_text(encoding="utf-8")
        prediction_logs = (log_directory / "prediction.log").read_text(encoding="utf-8")
        detection_logs = (log_directory / "person_detection.log").read_text(encoding="utf-8")
        milvus_logs = (log_directory / "milvus.log").read_text(encoding="utf-8")

        assert "Inference sample received." in all_logs
        assert "Person detection batch completed." in all_logs
        assert "Milvus batch resolve completed." in all_logs
        assert "Inference prediction emitted:" in all_logs

        assert "Inference sample received." in inference_logs
        assert "Inference prediction emitted:" in inference_logs
        assert "track_7" in prediction_logs
        assert "warning" in prediction_logs
        assert "Person detection batch completed." in detection_logs
        assert "Milvus batch resolve completed." in milvus_logs
    finally:
        shutil.rmtree(temp_directory, ignore_errors=True)
