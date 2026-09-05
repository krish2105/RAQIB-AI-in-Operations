FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 ffmpeg && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir uv
WORKDIR /app/edge
COPY pyproject.toml ./
COPY raqib_edge ./raqib_edge
COPY sites ./sites
# CPU torch wheels keep the image small; MPS/CUDA hosts run natively instead.
RUN uv pip install --system --no-cache --index-url https://download.pytorch.org/whl/cpu torch torchvision \
 && uv pip install --system --no-cache .
VOLUME ["/app/edge/data"]
ENTRYPOINT []
CMD ["raqib-edge", "run", "--site", "sites/retail_demo.yaml"]
