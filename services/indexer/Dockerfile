# syntax=docker/dockerfile:1
#
# Indexer image. The build context MUST be the repo root, because the service depends on
# packages/shared which lives outside services/indexer/ (Railway's Nixpacks auto-builder
# cannot express that cross-directory dependency — hence this Dockerfile).
#
#   docker build -f services/indexer/Dockerfile -t provenalt-indexer .
#
FROM python:3.12-slim

# Flush stdout/stderr immediately so the long-running worker's logs show up in Railway,
# and don't litter the image with .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy the shared package first, then the service (paths are relative to the repo root).
COPY packages/shared ./packages/shared
COPY services/indexer ./services/indexer

# Install shared first so the service's local `provenalt-shared` dependency resolves from the
# monorepo rather than PyPI (where it does not exist). Non-editable install bakes in the
# package data (ABIs, card schemas) declared in each pyproject.
RUN pip install --no-cache-dir ./packages/shared ./services/indexer

# Long-running worker — no HTTP port. Resumes from its DB cursor on restart.
CMD ["python", "-m", "provenalt_indexer.worker"]
