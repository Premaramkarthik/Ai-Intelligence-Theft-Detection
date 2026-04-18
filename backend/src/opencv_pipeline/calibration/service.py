"""Camera calibration loading, undistortion, and image-to-world projection."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from src.opencv_pipeline.contracts import CalibrationProfile


class CalibrationService:
    """Load camera intrinsics/extrinsics and apply OpenCV calib3d operations."""

    def __init__(self) -> None:
        self._profiles: dict[str, CalibrationProfile] = {}

    def load_profile(self, camera_id: str, path: Path | None) -> CalibrationProfile | None:
        """Load one camera calibration profile from a JSON file if provided."""

        if path is None or not path.exists():
            return self._profiles.get(camera_id)

        payload = json.loads(path.read_text(encoding="utf-8"))
        profile = CalibrationProfile(
            camera_id=camera_id,
            camera_matrix=_to_matrix(payload.get("camera_matrix")),
            distortion_coefficients=_to_matrix(payload.get("distortion_coefficients")),
            homography=_to_matrix(payload.get("homography")),
            rotation_matrix=_to_matrix(payload.get("rotation_matrix")),
            translation_vector=_to_matrix(payload.get("translation_vector")),
        )
        self._profiles[camera_id] = profile
        return profile

    def get_profile(self, camera_id: str) -> CalibrationProfile | None:
        """Return a previously loaded profile."""

        return self._profiles.get(camera_id)

    def remove_camera(self, camera_id: str) -> None:
        """Discard cached calibration state for a removed camera."""

        self._profiles.pop(camera_id, None)

    def undistort(self, frame_bgr: np.ndarray, profile: CalibrationProfile | None) -> np.ndarray:
        """Apply intrinsic undistortion when a profile is available."""

        if (
            profile is None
            or profile.camera_matrix is None
            or profile.distortion_coefficients is None
        ):
            return frame_bgr
        return cv2.undistort(
            frame_bgr,
            profile.camera_matrix,
            profile.distortion_coefficients,
        )

    def align_to_world(
        self,
        frame_bgr: np.ndarray,
        profile: CalibrationProfile | None,
    ) -> np.ndarray | None:
        """Warp a frame into a world-aligned plane when a homography is provided."""

        if profile is None or profile.homography is None:
            return None
        return cv2.warpPerspective(
            frame_bgr,
            profile.homography,
            (frame_bgr.shape[1], frame_bgr.shape[0]),
        )

    def image_to_world(
        self,
        camera_id: str,
        x: float,
        y: float,
    ) -> tuple[float, float] | None:
        """Project an image point into a shared plane using the camera homography."""

        profile = self._profiles.get(camera_id)
        if profile is None or profile.homography is None:
            return None
        point = np.array([[[x, y]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, profile.homography)
        return (float(transformed[0, 0, 0]), float(transformed[0, 0, 1]))


def _to_matrix(value: object) -> np.ndarray | None:
    if value is None:
        return None
    return np.asarray(value, dtype=np.float32)
