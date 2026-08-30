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

EXPOSE 8000

# Migrations run at boot so a fresh managed Postgres comes up ready.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
