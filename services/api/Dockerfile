# syntax=docker/dockerfile:1
#
# API image. The build context MUST be the repo root, because the service depends on
# packages/shared which lives outside services/api/ (Railway's Nixpacks auto-builder cannot
# express that cross-directory dependency — hence this Dockerfile).
#
#   docker build -f services/api/Dockerfile -t provenalt-api .
#
FROM python:3.12-slim

# Flush logs immediately; skip writing .pyc files into the image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy the shared package first, then the service (paths are relative to the repo root).
COPY packages/shared ./packages/shared
COPY services/api ./services/api

# Install shared first so the service's local `provenalt-shared` dependency resolves from the
# monorepo rather than PyPI (where it does not exist).
RUN pip install --no-cache-dir ./packages/shared ./services/api

# Request/response HTTP service. Railway injects $PORT at runtime; a shell-form CMD (run via
# /bin/sh -c) expands it — a JSON-array CMD would pass the literal string "$PORT". Falls back
# to 8000 for a plain `docker run` without a PORT set.
EXPOSE 8000
CMD uvicorn provenalt_api.main:app --host 0.0.0.0 --port ${PORT:-8000}
