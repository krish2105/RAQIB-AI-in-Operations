FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_SYSTEM_PYTHON=1
RUN pip install --no-cache-dir uv
WORKDIR /app/cloud
COPY pyproject.toml ./
COPY raqib_api ./raqib_api
RUN uv pip install --no-cache .
# the API imports site YAML from the edge folder at runtime
COPY --from=edge-sites . /app/edge/sites/
EXPOSE 8000
CMD ["uvicorn", "raqib_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
