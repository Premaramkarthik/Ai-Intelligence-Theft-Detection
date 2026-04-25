FROM nvcr.io/nvidia/tritonserver:24.08-py3

# Install PyTorch (CPU) and HuggingFace Transformers for the VJEPA2 Python backend model
RUN pip3 install --no-cache-dir \
        torch --index-url https://download.pytorch.org/whl/cpu && \
    pip3 install --no-cache-dir \
        transformers \
        safetensors
