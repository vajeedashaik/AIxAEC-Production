# Build from the repo root: docker build -f services/geometry/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY packages/contracts packages/contracts
COPY services/geometry/pyproject.toml services/geometry/uv.lock services/geometry/
RUN cd services/geometry && uv sync --frozen --no-dev
COPY services/geometry services/geometry
RUN useradd --create-home --uid 10001 app
USER app
WORKDIR /src/services/geometry
ENV PATH="/opt/venv/bin:$PATH"
EXPOSE 8002
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/healthz').status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
