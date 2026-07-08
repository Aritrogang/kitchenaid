# syntax=docker/dockerfile:1
# API image: FastAPI over the Concierge, with the Postgres-backed Profile Keeper.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Only what the package + migrations need (the rest is excluded via .dockerignore).
# Editable install keeps the source tree at /app so `migrations/` resolves at runtime
# (run_migrations looks next to the package root).
COPY pyproject.toml ./
COPY kitchenaid ./kitchenaid
COPY migrations ./migrations
RUN pip install --upgrade pip && pip install -e ".[api,db]"

# Drop privileges for runtime.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Liveness: the API's own /health endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# Apply migrations only when a database is configured, then serve. Without DATABASE_URL the
# API still starts (taste falls back to JSON files) and migrate is skipped.
CMD ["sh", "-c", "if [ -n \"$DATABASE_URL\" ]; then python -m kitchenaid.store migrate; fi && exec uvicorn kitchenaid.api:app --host 0.0.0.0 --port 8000"]
