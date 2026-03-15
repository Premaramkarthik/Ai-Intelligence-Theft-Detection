"""
Behavior classifier wrapper for TensorRT or ONNX classifier models.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from shared.logging.logger import get_logger

log = get_logger(__name__)

CLASSIFIER_ENGINE_FILENAME = "cnn_transformer.engine"
CLASSIFIER_ONNX_FILENAME = "cnn_transformer.onnx"
INPUT_SIZE = (224, 224)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass
class TensorBinding:
    name: str
    dtype: Any
    is_input: bool
    shape: tuple[int, ...]
    ptr: int | None = None
    nbytes: int = 0


class BehaviorClassifier:
    def __init__(self, model_path: str, device: str = "cuda", clip_frames: int = 16) -> None:
        self._model_path = model_path
        self._device = device
        self._clip_frames = clip_frames
        self._is_onnx = model_path.endswith(".onnx")
        self._engine: Any | None = None
        self._context: Any | None = None
        self._trt: Any | None = None
        self._cudart: Any | None = None
        self._stream: Any | None = None
        self._input_name: str | None = None
        self._output_name: str | None = None
        self._bindings: dict[str, TensorBinding] = {}
        self._onnx_session: Any | None = None
        self._onnx_input_name: str | None = None
        self._load()

    def _load(self) -> None:
        if os.path.isdir(self._model_path) or not os.path.exists(self._model_path):
            raise FileNotFoundError(
                f"Required classifier model is missing: {self._model_path}. "
                f"Expected `{CLASSIFIER_ENGINE_FILENAME}` or `{CLASSIFIER_ONNX_FILENAME}`."
            )
        if self._model_path.endswith(".onnx"):
            try:
                import onnxruntime as ort  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "onnxruntime is required to load cnn_transformer.onnx on CPU"
                ) from exc
            session = ort.InferenceSession(self._model_path, providers=["CPUExecutionProvider"])
            inputs = session.get_inputs()
            if not inputs:
                raise RuntimeError("Classifier ONNX model exposes no inputs")
            self._onnx_session = session
            self._onnx_input_name = str(inputs[0].name)
            log.info("BehaviorClassifier loaded", extra={"path": self._model_path, "device": "cpu"})
            return
        if not self._model_path.endswith(".engine"):
            raise ValueError(f"Classifier must use a TensorRT engine or ONNX model, got: {self._model_path}")
        if self._device != "cuda":
            raise RuntimeError("cnn_transformer.engine requires a CUDA execution device")

        try:
            import tensorrt as trt  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "TensorRT Python bindings are required to load cnn_transformer.engine"
            ) from exc

        try:
            from cuda import cudart  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "cuda-python is required to execute cnn_transformer.engine"
            ) from exc

        logger = trt.Logger(trt.Logger.WARNING)
        with open(self._model_path, "rb") as engine_file, trt.Runtime(logger) as runtime:
            engine = runtime.deserialize_cuda_engine(engine_file.read())
        if engine is None:
            raise RuntimeError(f"TensorRT could not deserialize classifier engine: {self._model_path}")

        context = engine.create_execution_context()
        if context is None:
            raise RuntimeError(f"TensorRT could not create execution context: {self._model_path}")

        status, stream = cudart.cudaStreamCreate()
        if status != cudart.cudaError_t.cudaSuccess:
            raise RuntimeError("Failed to create CUDA stream for classifier execution")

        self._trt = trt
        self._cudart = cudart
        self._engine = engine
        self._context = context
        self._stream = stream
        self._initialize_bindings()
        log.info("BehaviorClassifier loaded", extra={"path": self._model_path, "device": self._device})

    def _initialize_bindings(self) -> None:
        assert self._engine is not None
        assert self._trt is not None

        tensor_names = [self._engine.get_tensor_name(i) for i in range(self._engine.num_io_tensors)]
        for name in tensor_names:
            mode = self._engine.get_tensor_mode(name)
            binding = TensorBinding(
                name=name,
                dtype=self._trt.nptype(self._engine.get_tensor_dtype(name)),
                is_input=mode == self._trt.TensorIOMode.INPUT,
                shape=tuple(int(dim) for dim in self._engine.get_tensor_shape(name)),
            )
            self._bindings[name] = binding
            if binding.is_input and self._input_name is None:
                self._input_name = name
            elif not binding.is_input and self._output_name is None:
                self._output_name = name

        if self._input_name is None or self._output_name is None:
            raise RuntimeError("Classifier engine must expose one input and one output tensor")

    def _preprocess(self, clip: list[np.ndarray]) -> np.ndarray:
        processed = []
        for frame in clip[-self._clip_frames :]:
            img = cv2.resize(frame, INPUT_SIZE)
            img = img.astype(np.float32) / 255.0
            img = (img - IMAGENET_MEAN) / IMAGENET_STD
            processed.append(img)

        video = np.stack(processed, axis=0)
        video = np.transpose(video, (0, 3, 1, 2))
        return np.expand_dims(video, axis=0).astype(np.float32)

    def _shape_with_batch(self, shape: tuple[int, ...], batch_shape: tuple[int, ...]) -> tuple[int, ...]:
        if -1 not in shape:
            return shape
        resolved = list(shape)
        for idx, dim in enumerate(resolved):
            if dim == -1:
                resolved[idx] = batch_shape[idx]
        return tuple(resolved)

    def _ensure_tensor(self, name: str, shape: tuple[int, ...]) -> None:
        assert self._bindings[name].dtype is not None
        assert self._context is not None
        assert self._cudart is not None

        binding = self._bindings[name]
        dtype = np.dtype(binding.dtype)
        nbytes = int(np.prod(shape)) * dtype.itemsize
        if binding.ptr is not None and binding.nbytes == nbytes and binding.shape == shape:
            return

        if binding.ptr is not None:
            self._cudart.cudaFree(binding.ptr)

        status, ptr = self._cudart.cudaMalloc(nbytes)
        if status != self._cudart.cudaError_t.cudaSuccess:
            raise RuntimeError(f"Failed to allocate CUDA memory for tensor {name}")

        binding.ptr = ptr
        binding.nbytes = nbytes
        binding.shape = shape
        self._context.set_tensor_address(name, ptr)

    def _infer(self, input_tensor: np.ndarray) -> np.ndarray:
        assert self._context is not None
        assert self._cudart is not None
        assert self._input_name is not None
        assert self._output_name is not None
        assert self._stream is not None

        self._context.set_input_shape(self._input_name, tuple(int(dim) for dim in input_tensor.shape))
        self._ensure_tensor(self._input_name, tuple(int(dim) for dim in input_tensor.shape))

        output_shape = tuple(int(dim) for dim in self._context.get_tensor_shape(self._output_name))
        output_shape = self._shape_with_batch(output_shape, tuple(int(dim) for dim in input_tensor.shape))
        self._ensure_tensor(self._output_name, output_shape)

        input_binding = self._bindings[self._input_name]
        output_binding = self._bindings[self._output_name]
        output = np.empty(output_shape, dtype=np.dtype(output_binding.dtype))

        self._cudart.cudaMemcpyAsync(
            input_binding.ptr,
            input_tensor.ctypes.data,
            input_binding.nbytes,
            self._cudart.cudaMemcpyKind.cudaMemcpyHostToDevice,
            self._stream,
        )
        if not self._context.execute_async_v3(self._stream):
            raise RuntimeError("TensorRT classifier execution failed")
        self._cudart.cudaMemcpyAsync(
            output.ctypes.data,
            output_binding.ptr,
            output_binding.nbytes,
            self._cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,
            self._stream,
        )
        self._cudart.cudaStreamSynchronize(self._stream)
        return output

    def _infer_onnx(self, input_tensor: np.ndarray) -> np.ndarray:
        assert self._onnx_session is not None
        assert self._onnx_input_name is not None
        outputs = self._onnx_session.run(None, {self._onnx_input_name: input_tensor})
        if not outputs:
            raise RuntimeError("Classifier ONNX inference returned no outputs")
        return np.asarray(outputs[0])

    def classify_sync(self, clip: list[np.ndarray]) -> tuple[str, float]:
        if not clip or len(clip) < self._clip_frames:
            return "normal", 0.0

        input_tensor = self._preprocess(clip)
        output = self._infer_onnx(input_tensor) if self._onnx_session is not None else self._infer(input_tensor)
        score = float(np.ravel(output)[0])
        label = "shoplifting" if score > 0.5 else "normal"
        confidence = score if score > 0.5 else (1.0 - score)
        return label, confidence
