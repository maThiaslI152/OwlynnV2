# ── Stage 1: Build Frontend ─────────────────────────
FROM node:22-alpine AS frontend-builder
WORKDIR /app

COPY frontend-v2/package.json frontend-v2/package-lock.json* ./frontend-v2/
WORKDIR /app/frontend-v2
RUN npm install

COPY frontend-v2/ ./
RUN npx vite build


# ── Stage 2: Build Backend ──────────────────────────
FROM python:3.12-slim-bookworm AS backend

RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml .
COPY docs/ /app/docs/

# Install CPU-only version of PyTorch to avoid massive 8GB CUDA downloads
RUN uv pip install --system torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN uv pip install --system -e .

COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY browser-extension/ /app/browser-extension/
COPY alembic.ini /app/
COPY alembic/ /app/alembic/

# Copy the built frontend into the expected directory structure for FastAPI to serve
COPY --from=frontend-builder /app/frontend-v2/dist /app/frontend-v2/dist

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV OWLYNN_DATA_DIR=/app/data
ENV OWLYNN_WORKSPACE_DIR=/app/workspace
# Don't preload models in container start to avoid blocking if LM studio is down
ENV OWLYNN_NO_PRELOAD=1

CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
