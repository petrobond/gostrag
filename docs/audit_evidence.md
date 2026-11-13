# Audit evidence

- Generated: 2026-11-13T12:50:52.905916+00:00
- Version: **3.2.0**, commit `82e0c8f641a8`, tag `v3.1.0-1-g82e0c8f`
- Tests: sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute
- Ruff: clean
- Health: `{"status": "ok", "version": "3.1.0", "commit": "82e0c8f641a84421ff89d9794b8dec99db06628a", "corpus_version": "2026.11.13", "collection": "gost_chunks_bge_m3", "index_ready": true, "kb_ready": true}`
- Standards in outline: 37
- KB: 400 terms, 97 nodes, 116 edges

| Gold | pass_rate | citation_recall |
|---|---|---|
| `report_v2_bge_m3.json` | 0.9459459459459459 | None |
| `report_v3_bge_m3.json` | 0.98 | 1.0 |
| `report_kb.json` | 0.9 | 1.0 |

## Containers

```text
gostrag-local-postgres-1	Up 37 minutes (healthy)	postgres:16-alpine
gostrag-local-redis-1	Up 37 minutes (healthy)	redis:7-alpine
gostrag-local-qdrant-1	Up 37 minutes	qdrant/qdrant:v1.12.4
gostrag-qdrant-1	Up 3 hours	qdrant/qdrant:v1.12.4
```

## Memory

```text
gostrag-local-postgres-1	25.67MiB / 7.748GiB
gostrag-local-redis-1	10.12MiB / 7.748GiB
gostrag-local-qdrant-1	253.8MiB / 7.748GiB
gostrag-qdrant-1	613.8MiB / 7.748GiB
```
