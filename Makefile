SHELL := /bin/sh

COMPOSE := docker compose -f deploy/docker-compose.local.yml
PY := .venv/bin/python
ROOT := $(CURDIR)

export APP_VERSION := 3.1.0
export CORPUS_VERSION := 2026.11.11
export QDRANT_URL := http://localhost:6335
export QDRANT_COLLECTION := gost_chunks_bge_m3
export EMBEDDING_PROVIDER := cloudru
export DATA_SOURCE_DIR := $(ROOT)/data/source
export DATA_CORPUS_DIR := $(ROOT)/data/corpus
export DATA_KB_DIR := $(ROOT)/data/kb
export INDEX_DIR := $(ROOT)/data/index
export REPORTS_DIR := $(ROOT)/reports

.PHONY: dev-up dev-down dev-status api test lint eval-retrieval judge audit seed-qdrant snapshot

dev-up:
	mkdir -p .local/qdrant .local/postgres .local/redis
	$(COMPOSE) up -d

dev-down:
	$(COMPOSE) down

dev-status:
	$(COMPOSE) ps
	@curl -s http://localhost:6333/healthz || true
	@echo

api:
	$(PY) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	$(PY) -m pytest -q tests

lint:
	$(PY) -m ruff check app bot eval tests

eval-retrieval:
	$(PY) scripts/eval_retrieval.py --gold eval/gold_set_v3.yaml --top-k 8

judge:
	$(PY) eval/judge.py --gold eval/gold_set_v3.yaml --out eval/report_v3_local.json

audit:
	$(PY) scripts/audit.py --reports reports

seed-qdrant:
	$(PY) scripts/qdrant_snapshot.py restore \
		--collection gost_chunks_bge_m3 \
		--file backups/2026-11-13/qdrant-gost_chunks_bge_m3.snapshot

snapshot:
	$(PY) scripts/qdrant_snapshot.py download \
		--collection gost_chunks_bge_m3 \
		--out dist/qdrant-gost_chunks_bge_m3.snapshot
