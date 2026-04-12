"""Roboflow Inference-based person detector for the tracking pipeline."""

# pylint: disable=too-few-public-methods,too-many-arguments

from __future__ import annotations

import os
import shutil
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from src.services.tracking.contracts import PersonDetection


class _InferenceModel(Protocol):
    """Small protocol for Roboflow inference models used by the detector."""

    def infer(
        self,
        image: np.ndarray,
        **kwargs: Any,
    ) -> Sequence[Any]:
        """Run inference against a numpy image."""


@dataclass(slots=True, frozen=True)
class _Prediction:
    x: float
    y: float
    width: float
    height: float
    confidence: float
    class_name: str


_WINDOWS_SYMLINK_PRIVILEGE_ERROR = 1314
_INFERENCE_COMPAT_LOCK = threading.Lock()
_WINDOWS_INFERENCE_SYMLINK_FALLBACK_APPLIED = False


class InferencePersonDetector:
    """Detect persons with the Roboflow Inference Python SDK."""

    def __init__(
        self,
        model_id: str = "rfdetr-medium",
        *,
        confidence_threshold: float = 0.45,
        iou_threshold: float = 0.35,
        target_class_name: str = "person",
        api_key: str | None = None,
        model: _InferenceModel | None = None,
        model_factory: Callable[[str, str | None], _InferenceModel] | None = None,
    ) -> None:
        self._model_id = model_id
        self._confidence_threshold = confidence_threshold
        self._iou_threshold = iou_threshold
        self._target_class_name = target_class_name.strip().lower()
        self._api_key = api_key
        self._model = model
        self._model_factory = model_factory or _default_model_factory
        self._model_lock = threading.Lock()
        self._infer_lock = threading.Lock()

    def detect(self, frame: np.ndarray) -> list[PersonDetection]:
        """Detect persons in a BGR frame."""

        model = self._ensure_model()
        with self._infer_lock:
            results = model.infer(
                frame,
                confidence=self._confidence_threshold,
                iou_threshold=self._iou_threshold,
                class_filter=[self._target_class_name],
            )
        if not results:
            return []
        first_result = results[0]
        predictions = _extract_predictions(first_result)
        return [
            PersonDetection(
                left=prediction.x - (prediction.width / 2.0),
                top=prediction.y - (prediction.height / 2.0),
                width=prediction.width,
                height=prediction.height,
                confidence=prediction.confidence,
                class_name=prediction.class_name,
            )
            for prediction in predictions
            if prediction.class_name == self._target_class_name
            and prediction.confidence >= self._confidence_threshold
            and prediction.width > 0
            and prediction.height > 0
        ]

    def _ensure_model(self) -> _InferenceModel:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is None:
                self._model = self._model_factory(self._model_id, self._api_key)
        return self._model


def _default_model_factory(model_id: str, api_key: str | None) -> _InferenceModel:
    _configure_inference_environment()
    try:
        from inference import get_model
    except Exception as exc:  # pylint: disable=broad-except
        raise RuntimeError(
            "Roboflow Inference is unavailable. Install the `inference` package "
            "and verify its optional dependencies are configured correctly.",
        ) from exc
    return get_model(model_id=model_id, api_key=api_key)


def _configure_inference_environment() -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
    optional_feature_flags = {
        "CORE_MODEL_CLIP_ENABLED": "False",
        "CORE_MODEL_PE_ENABLED": "False",
        "CORE_MODEL_SAM_ENABLED": "False",
        "CORE_MODEL_SAM2_ENABLED": "False",
        "CORE_MODEL_SAM3_ENABLED": "False",
        "CORE_MODEL_GAZE_ENABLED": "False",
        "CORE_MODEL_DOCTR_ENABLED": "False",
        "CORE_MODEL_EASYOCR_ENABLED": "False",
        "CORE_MODEL_TROCR_ENABLED": "False",
        "CORE_MODEL_GROUNDINGDINO_ENABLED": "False",
        "CORE_MODEL_YOLO_WORLD_ENABLED": "False",
        "PALIGEMMA_ENABLED": "False",
        "FLORENCE2_ENABLED": "False",
        "MOONDREAM2_ENABLED": "False",
        "SMOLVLM2_ENABLED": "False",
        "GLM_OCR_ENABLED": "False",
        "QWEN_2_5_ENABLED": "False",
        "QWEN_3_ENABLED": "False",
        "QWEN_3_5_ENABLED": "False",
        "DEPTH_ESTIMATION_ENABLED": "False",
    }
    for key, value in optional_feature_flags.items():
        os.environ.setdefault(key, value)
    _apply_windows_inference_symlink_fallback()


def _apply_windows_inference_symlink_fallback() -> None:
    if os.name != "nt":
        return

    global _WINDOWS_INFERENCE_SYMLINK_FALLBACK_APPLIED
    if _WINDOWS_INFERENCE_SYMLINK_FALLBACK_APPLIED:
        return

    with _INFERENCE_COMPAT_LOCK:
        if _WINDOWS_INFERENCE_SYMLINK_FALLBACK_APPLIED:
            return
        try:
            from inference_models.models.auto_loaders import core as auto_loader_core
        except Exception:
            return

        original_handle_symlink_creation = getattr(
            auto_loader_core,
            "handle_symlink_creation",
            None,
        )
        original_handle_dependencies_directories_creation = getattr(
            auto_loader_core,
            "handle_dependencies_directories_creation",
            None,
        )
        if not callable(original_handle_symlink_creation) or not callable(
            original_handle_dependencies_directories_creation,
        ):
            return

        def _handle_symlink_creation_with_copy_fallback(
            target_path: str,
            link_name: str,
            model_download_file_lock_acquire_timeout: int = auto_loader_core.FILE_LOCK_ACQUIRE_TIMEOUT,
            on_symlink_created: Callable[[str, str], None] | None = None,
            on_symlink_deleted: Callable[[str], None] | None = None,
        ) -> None:
            try:
                original_handle_symlink_creation(
                    target_path=target_path,
                    link_name=link_name,
                    model_download_file_lock_acquire_timeout=model_download_file_lock_acquire_timeout,
                    on_symlink_created=on_symlink_created,
                    on_symlink_deleted=on_symlink_deleted,
                )
                return
            except OSError as exc:
                if not _is_windows_symlink_privilege_error(exc):
                    raise

            link_dir, link_file_name = os.path.split(os.path.abspath(link_name))
            os.makedirs(link_dir, exist_ok=True)
            lock_path = os.path.join(link_dir, f".{link_file_name}.lock")
            _copy_path_with_lock(
                source_path=target_path,
                destination_path=link_name,
                lock_path=lock_path,
                lock_timeout=model_download_file_lock_acquire_timeout,
                file_lock_cls=auto_loader_core.FileLock,
                on_created=on_symlink_created,
                on_deleted=on_symlink_deleted,
            )

        def _handle_dependencies_directories_creation_with_copy_fallback(
            model_package_cache_dir: str,
            model_dependencies_directories: dict[str, str] | None,
            model_download_file_lock_acquire_timeout: int = auto_loader_core.FILE_LOCK_ACQUIRE_TIMEOUT,
            on_symlink_created: Callable[[str, str], None] | None = None,
            on_symlink_deleted: Callable[[str], None] | None = None,
        ) -> set[str]:
            try:
                return original_handle_dependencies_directories_creation(
                    model_package_cache_dir=model_package_cache_dir,
                    model_dependencies_directories=model_dependencies_directories,
                    model_download_file_lock_acquire_timeout=model_download_file_lock_acquire_timeout,
                    on_symlink_created=on_symlink_created,
                    on_symlink_deleted=on_symlink_deleted,
                )
            except OSError as exc:
                if not _is_windows_symlink_privilege_error(exc):
                    raise

            resolved_files: set[str] = set()
            if not model_dependencies_directories:
                return resolved_files

            for dependency_name, dependency_directory in model_dependencies_directories.items():
                dependency_files = auto_loader_core.scan_dependency_directory_for_resolved_files(
                    dependency_directory=dependency_directory,
                )
                resolved_files.update(dependency_files)
                dependencies_sub_dir = os.path.join(
                    model_package_cache_dir,
                    auto_loader_core.MODEL_DEPENDENCIES_SUB_DIR,
                )
                target_dependency_dir = os.path.join(dependencies_sub_dir, dependency_name)
                os.makedirs(dependencies_sub_dir, exist_ok=True)
                dependency_lock_path = os.path.join(
                    dependencies_sub_dir,
                    f".{dependency_name}.lock",
                )
                _copy_path_with_lock(
                    source_path=dependency_directory,
                    destination_path=target_dependency_dir,
                    lock_path=dependency_lock_path,
                    lock_timeout=model_download_file_lock_acquire_timeout,
                    file_lock_cls=auto_loader_core.FileLock,
                    on_created=on_symlink_created,
                    on_deleted=on_symlink_deleted,
                )
            return resolved_files

        auto_loader_core.handle_symlink_creation = (
            _handle_symlink_creation_with_copy_fallback
        )
        auto_loader_core.handle_dependencies_directories_creation = (
            _handle_dependencies_directories_creation_with_copy_fallback
        )
        _WINDOWS_INFERENCE_SYMLINK_FALLBACK_APPLIED = True


def _is_windows_symlink_privilege_error(exc: OSError) -> bool:
    return os.name == "nt" and getattr(exc, "winerror", None) == _WINDOWS_SYMLINK_PRIVILEGE_ERROR


def _copy_path_with_lock(
    *,
    source_path: str,
    destination_path: str,
    lock_path: str,
    lock_timeout: int,
    file_lock_cls: Any,
    on_created: Callable[[str, str], None] | None = None,
    on_deleted: Callable[[str], None] | None = None,
) -> None:
    with file_lock_cls(lock_path, timeout=lock_timeout):
        if os.path.islink(destination_path):
            os.remove(destination_path)
            if on_deleted is not None:
                on_deleted(destination_path)
        elif os.path.exists(destination_path):
            return

        _copy_path_atomically(source_path=source_path, destination_path=destination_path)
        if on_created is not None:
            on_created(source_path, destination_path)


def _copy_path_atomically(*, source_path: str, destination_path: str) -> None:
    temp_destination_path = (
        f"{destination_path}.tmp-copy-{os.getpid()}-{threading.get_ident()}"
    )
    _remove_path_if_exists(temp_destination_path)
    try:
        if os.path.isdir(source_path):
            shutil.copytree(source_path, temp_destination_path)
        else:
            shutil.copy2(source_path, temp_destination_path)
        os.replace(temp_destination_path, destination_path)
    finally:
        _remove_path_if_exists(temp_destination_path)


def _remove_path_if_exists(path: str) -> None:
    if os.path.islink(path):
        os.remove(path)
        return
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
        return
    if os.path.exists(path):
        os.remove(path)


def _extract_predictions(result: Any) -> list[_Prediction]:
    raw_predictions = getattr(result, "predictions", None)
    if raw_predictions is None and isinstance(result, dict):
        raw_predictions = result.get("predictions")
    if raw_predictions is None:
        return []

    predictions: list[_Prediction] = []
    for raw_prediction in raw_predictions:
        prediction_mapping = _to_mapping(raw_prediction)
        class_name = _normalize_class_name(prediction_mapping)
        if class_name == "":
            continue
        predictions.append(
            _Prediction(
                x=float(prediction_mapping["x"]),
                y=float(prediction_mapping["y"]),
                width=float(prediction_mapping["width"]),
                height=float(prediction_mapping["height"]),
                confidence=float(prediction_mapping["confidence"]),
                class_name=class_name,
            ),
        )
    return predictions


def _to_mapping(raw_prediction: Any) -> dict[str, Any]:
    if isinstance(raw_prediction, dict):
        return raw_prediction
    model_dump = getattr(raw_prediction, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump())
    dict_method = getattr(raw_prediction, "dict", None)
    if callable(dict_method):
        return dict(dict_method())
    attributes = {
        "x": getattr(raw_prediction, "x", None),
        "y": getattr(raw_prediction, "y", None),
        "width": getattr(raw_prediction, "width", None),
        "height": getattr(raw_prediction, "height", None),
        "confidence": getattr(raw_prediction, "confidence", None),
        "class": getattr(raw_prediction, "class_name", None)
        or getattr(raw_prediction, "class_", None)
        or getattr(raw_prediction, "class", None),
    }
    return attributes


def _normalize_class_name(prediction_mapping: dict[str, Any]) -> str:
    class_name = prediction_mapping.get("class")
    if class_name is None:
        class_name = prediction_mapping.get("class_name")
    if class_name is None:
        return ""
    return str(class_name).strip().lower()
