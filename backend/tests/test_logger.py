from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from src.core.logger.logger import configure_logging


def test_configure_logging_writes_subsystem_logs_to_flat_files() -> None:
    workspace_temp_root = Path.cwd() / "runtime" / "test-logs"
    workspace_temp_root.mkdir(parents=True, exist_ok=True)
    temp_directory = Path(tempfile.mkdtemp(dir=workspace_temp_root))
    log_directory = temp_directory / "logs"
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

    for handler in logging.getLogger().handlers:
        flush = getattr(handler, "flush", None)
        if callable(flush):
            flush()

    try:
        all_logs = (log_directory / "all.log").read_text(encoding="utf-8")
        inference_logs = (log_directory / "inference.log").read_text(encoding="utf-8")
        detection_logs = (log_directory / "person_detection.log").read_text(encoding="utf-8")
        milvus_logs = (log_directory / "milvus.log").read_text(encoding="utf-8")

        assert "Inference sample received." in all_logs
        assert "Person detection batch completed." in all_logs
        assert "Milvus batch resolve completed." in all_logs

        assert "Inference sample received." in inference_logs
        assert "Person detection batch completed." in detection_logs
        assert "Milvus batch resolve completed." in milvus_logs
    finally:
        shutil.rmtree(temp_directory, ignore_errors=True)
