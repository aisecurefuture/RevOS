# RevOS backend image — FastAPI + Celery share one image.
FROM python:3.12-slim AS base

# Avoid .pyc files, unbuffered logs, no pip cache.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps: libpq for psycopg/asyncpg build, curl for healthcheck,
# ffmpeg for the media pipeline's video renditions.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application source.
COPY . .

# Run as a non-root user (least privilege).
RUN useradd --create-home --uid 10001 revos \
    && mkdir -p /app/storage \
    && chown -R revos:revos /app
USER revos

EXPOSE 8000

# Container-level healthcheck hits the liveness endpoint.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
