FROM python:3.12-slim AS builder

ARG INSTALL_LOCAL_EMBEDDINGS=false

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY app ./app
COPY bot ./bot
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels . \
    && if [ "$INSTALL_LOCAL_EMBEDDINGS" = "true" ]; then \
        pip wheel --no-cache-dir --wheel-dir /wheels '.[local]'; \
    fi

FROM python:3.12-slim AS runtime

ARG INSTALL_LOCAL_EMBEDDINGS=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    EMBEDDING_CACHE_DIR=/app/.cache/fastembed

ARG APP_VERSION=3.2.1
ARG GIT_COMMIT=""
ARG GIT_TAG=""
ENV APP_VERSION=${APP_VERSION} \
    GIT_COMMIT=${GIT_COMMIT} \
    GIT_TAG=${GIT_TAG}

WORKDIR /app
COPY deploy/certs/*.crt /usr/local/share/ca-certificates/
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    GIGACHAT_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

COPY --from=builder /wheels /wheels
RUN if [ "$INSTALL_LOCAL_EMBEDDINGS" = "true" ]; then \
        pip install --no-cache-dir --no-index --find-links=/wheels 'gostrag[local]'; \
    else \
        pip install --no-cache-dir --no-index --find-links=/wheels gostrag; \
    fi \
    && rm -rf /wheels

COPY app ./app
COPY bot ./bot
COPY scripts ./scripts
COPY eval/requirements.yaml ./eval/requirements.yaml
COPY docs ./docs

RUN mkdir -p /app/reports /data/source /data/corpus /data/index /data/kb /app/.cache/fastembed

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

