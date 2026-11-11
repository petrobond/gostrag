FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_CACHE_DIR=/app/.cache/fastembed

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY bot ./bot

RUN pip install --upgrade pip && pip install .

# Preload local embedding model so the container works offline after build.
RUN python -c "from app.embeddings.local_e5 import LocalE5Embedder; LocalE5Embedder(cache_dir='/app/.cache/fastembed')"

RUN mkdir -p /app/reports /data/corpus

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
