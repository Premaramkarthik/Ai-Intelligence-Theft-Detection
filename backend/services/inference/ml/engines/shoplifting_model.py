"""
ShopliftingModel — EfficientX3D / MoViNet classifier for video clips.
Loads physical weights from the models/ directory.
"""
from __future__ import annotations

import torch
import torch.nn as nn
from torchvision.models import efficientnet_b0
import numpy as np
import cv2
from shared.logging.logger import get_logger

log = get_logger(__name__)

class EfficientNet_Transformer(nn.Module):
    def __init__(self, num_classes=1, d_model=1280, nhead=8):
        super().__init__()
        backbone = efficientnet_b0(weights=None)
        backbone.classifier = nn.Identity()
        self.backbone = backbone

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)
        self.fc = nn.Linear(d_model, num_classes)

    def forward(self, x):
        # x shape: (b, t, c, h, w)
        b, t, c, h, w = x.shape
        x = x.view(b*t, c, h, w)

        feats = self.backbone(x)        # (b*t, 1280)
        feats = feats.view(b, t, -1)

        out = self.transformer(feats)
        out = out.mean(dim=1)

        return torch.sigmoid(self.fc(out))

class EfficientNetB0_LSTM(nn.Module):
    def __init__(self, hidden_size=128, num_classes=1):
        super().__init__()
        backbone = efficientnet_b0(weights=None)
        backbone.classifier = nn.Identity()
        self.backbone = backbone

        self.lstm = nn.LSTM(
            input_size=1280,
            hidden_size=hidden_size,
            batch_first=True
        )
        self.dropout = nn.Dropout(0.5)
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x):
        b, t, c, h, w = x.shape
        x = x.view(b * t, c, h, w)
        feats = self.backbone(x)
        feats = feats.view(b, t, -1)

        _, (h_n, _) = self.lstm(feats)
        h_n = h_n.squeeze(0)

        out = self.dropout(h_n)
        out = self.fc(out)
        return torch.sigmoid(out)

class ShopliftingModel:
    def __init__(self, model_path: str, device: str = "cuda", clip_frames: int = 16) -> None:
        self._model_path = model_path
        self._device = device
        self._clip_frames = clip_frames
        self._model: nn.Module | None = None
        self._load()

    def _load(self) -> None:
        try:
            import os
            if not os.path.exists(self._model_path):
                log.warning("Shoplifting model path does not exist", extra={"path": self._model_path})
                return

            # Map backend strings to valid torch devices
            torch_device = self._device
            if self._device == "tensorrt":
                torch_device = "cuda" if torch.cuda.is_available() else "cpu"
            elif self._device == "openvino":
                torch_device = "cpu"

            log.info("Loading shoplifting model weights", extra={"path": self._model_path, "device": torch_device})
            
            # Load weights first to identify architecture if needed
            state_dict = torch.load(self._model_path, map_location="cpu")
            if not isinstance(state_dict, dict):
                # If it's the whole model, extract state_dict
                if hasattr(state_dict, "state_dict"):
                    temp_model = state_dict
                    state_dict = temp_model.state_dict()
                else:
                    log.error("Loaded object is not a valid model or state_dict")
                    return

            # Identify model type based on keys or path
            has_lstm = any("lstm" in k.lower() for k in state_dict.keys()) or "lstm" in self._model_path.lower()
            
            if has_lstm:
                self._model = EfficientNetB0_LSTM()
                log.info("Detected LSTM architecture")
            else:
                self._model = EfficientNet_Transformer()
                log.info("Detected Transformer architecture")
            
            self._model.load_state_dict(state_dict)
            self._model.to(torch_device)
            self._model.eval()
            self._actual_device = torch_device # For use in preprocess
            log.info("Shoplifting model loaded successfully")
        except Exception as exc:
            log.error("Critical error in shoplifting model load", extra={"error": str(exc)})
            self._model = None

    def _preprocess(self, clip: list[np.ndarray]) -> torch.Tensor:
        """Prepare video clip for classification."""
        processed = []
        for frame in clip:
            img = cv2.resize(frame, (224, 224))
            img = img.astype(np.float32) / 255.0
            # ImageNet normalization
            img = (img - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
            processed.append(img)
        
        video = np.array(processed) # [T, H, W, C]
        video = np.transpose(video, (0, 3, 1, 2)) # [T, C, H, W]
        # Use self._actual_device if it exists, fallback to cpu
        device = getattr(self, "_actual_device", "cpu")
        return torch.from_numpy(video).float().unsqueeze(0).to(device) # [1, T, C, H, W]

    async def classify(self, clip: list[np.ndarray]) -> tuple[str, float]:
        """Classify a clip of frames. Returns (label, confidence)."""
        if self._model is None or not clip:
            return "unknown", 0.0

        try:
            input_tensor = self._preprocess(clip)
            with torch.no_grad():
                # Both Transformer and LSTM models end in sigmoid(fc(x))
                output = self._model(input_tensor) # [1, 1]
                score = output.item()
                
                # Binary classification threshold 0.5
                label = "shoplifting" if score > 0.5 else "normal"
                # If score < 0.5, confidence is probability of being 'normal' (1 - score)
                confidence = score if score > 0.5 else (1.0 - score)
                
                return label, confidence
        except Exception as exc:
            log.error("Shoplifting inference failed", extra={"error": str(exc)})
            return "error", 0.0
