# syntax=docker/dockerfile:1.7

# ============================================================================
# Stage 1: build the React frontend
# ============================================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci

COPY frontend/ ./
COPY docs/help /build/docs/help
RUN npm run build
# Output: /build/frontend/dist/{index.html, assets/*}


# ============================================================================
# Stage 2: install Python dependencies and pre-cache the embedding model
# ============================================================================
FROM python:3.10-slim AS python-builder
WORKDIR /build

# Build deps for psycopg2-binary wheels + torch + sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the multilingual-e5-base model so the runtime image does not
# need outbound HuggingFace access. ~470 MB.
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('intfloat/multilingual-e5-base')"


# ============================================================================
# Stage 3: runtime
# ============================================================================
FROM python:3.10-slim AS runtime

# Runtime deps:
#   curl    — used by HEALTHCHECK
#   libpq5  — runtime library for psycopg2
#   libgomp1 — OpenMP runtime needed by torch
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libpq5 \
        libgomp1 \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

# Copy installed Python packages + scripts (uvicorn, alembic, etc.)
COPY --from=python-builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# Cached HF model
COPY --from=python-builder /opt/hf-cache /opt/hf-cache

# Application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/
RUN chmod +x /app/scripts/entrypoint.sh

# Built frontend
COPY --from=frontend-builder /build/frontend/dist ./app/static/

# Mutable data directory for exports / generated artifacts
RUN mkdir -p /app/data && chown -R app:app /app /opt/hf-cache

ENV HF_HOME=/opt/hf-cache
ENV TZ=Europe/Moscow
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ready || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/entrypoint.sh"]
