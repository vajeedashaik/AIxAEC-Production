# Build from the repo root: docker build -f services/vision/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY packages/contracts packages/contracts
COPY services/vision/pyproject.toml services/vision/uv.lock services/vision/
RUN cd services/vision && uv sync --frozen --no-dev
COPY services/vision services/vision
RUN useradd --create-home --uid 10001 app
USER app
WORKDIR /src/services/vision
ENV PATH="/opt/venv/bin:$PATH"
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/healthz').status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
