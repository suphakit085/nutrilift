FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY ingest ./ingest
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --upgrade pip && pip install .

# Run as an unprivileged user: a bug in the app or a dependency should not
# hand out root inside the container. Nothing at runtime writes under /app.
RUN useradd --system --uid 10001 --user-group --no-create-home nutrilift \
    && chown -R nutrilift:nutrilift /app
USER nutrilift

EXPOSE 8000

# Migrations run at boot so a fresh managed Postgres comes up ready.
# NOTE: `python -m ingest` is NOT runnable from this image - knowledge/ is
# deliberately not copied in; run it from a checkout against the same
# DATABASE_URL (see ingest/__main__.py).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
