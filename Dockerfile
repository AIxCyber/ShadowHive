# ── Stage 1: Build ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir --user -e .

COPY backend/ backend/
COPY configs/ configs/

# ── Stage 2: Production ──────────────────────────────────────────────────────
FROM python:3.12-slim AS prod

WORKDIR /app

RUN groupadd -r shadowhive && useradd -r -g shadowhive shadowhive

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY --from=builder /app/backend/ backend/
COPY --from=builder /app/configs/ configs/

USER shadowhive

EXPOSE 8000

ARG UVICORN_WORKERS=2
ENV UVICORN_WORKERS=$UVICORN_WORKERS

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD uvicorn backend.main:app \
  --host 0.0.0.0 --port 8000 \
  --workers "$UVICORN_WORKERS" \
  --timeout-graceful-shutdown 30 \
  --log-level warning

# ── Stage 3: Development ─────────────────────────────────────────────────────
FROM python:3.12-slim AS dev

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY backend/ backend/
COPY configs/ configs/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
