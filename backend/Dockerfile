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
# hand out root inside the container.
#
# pythainlp (the Thai tokeniser BM25 uses) creates a data directory under $HOME
# the first time it is imported, so the user needs a home it owns. Without one
# the import raised PermissionError, retrieval caught it, logged "BM25 scoring
# failed; falling back to dense order" and answered anyway - hybrid retrieval
# silently off in production, which is the regression the hybrid ranker exists
# to prevent. PYTHAINLP_DATA pins the location instead of trusting $HOME.
ENV PYTHAINLP_DATA=/app/.pythainlp
RUN useradd --system --uid 10001 --user-group --create-home nutrilift \
    && mkdir -p /app/.pythainlp \
    && chown -R nutrilift:nutrilift /app
USER nutrilift

# Fail the build, not a user's question, if the tokeniser cannot start as this
# user. The newmm dictionary ships inside the wheel, so this needs no network.
RUN python -c "from app.services.bm25 import tokenize; assert len(tokenize('เวย์โปรตีนกินตอนไหนดี')) > 1, 'Thai tokenizer returned nothing'"

EXPOSE 8000

# Migrations run at boot so a fresh managed Postgres comes up ready.
# NOTE: `python -m ingest` is NOT runnable from this image - knowledge/ is
# deliberately not copied in; run it from a checkout against the same
# DATABASE_URL (see ingest/__main__.py).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
