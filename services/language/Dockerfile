# Build from the repo root: docker build -f services/language/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
# Audio is decoded with PyAV (bundled FFmpeg libs): no system ffmpeg needed.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY packages/contracts packages/contracts
COPY services/language/pyproject.toml services/language/uv.lock services/language/
RUN cd services/language && uv sync --frozen --no-dev
COPY services/language services/language
# The cache dir must exist and be ours: the compose volume inherits its ownership from here.
RUN useradd --create-home --uid 10001 app && mkdir -p /home/app/.cache/huggingface && chown -R app /home/app/.cache
USER app
WORKDIR /src/services/language
ENV PATH="/opt/venv/bin:$PATH"
EXPOSE 8003
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8003/healthz').status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
