"""Collect runtime evidence for the GOST audit report (no secrets)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.audit.version import get_git_commit, get_git_tag, get_version


def run_command(command: list[str], timeout: int = 120) -> dict:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": " ".join(command),
            "returncode": result.returncode,
            "output": (result.stdout + result.stderr).strip()[-2000:],
        }
    except FileNotFoundError:
        return {"command": " ".join(command), "returncode": None, "output": "not found"}
    except subprocess.TimeoutExpired:
        return {"command": " ".join(command), "returncode": None, "output": "timeout"}


def main() -> None:
    tests = run_command([sys.executable, "-m", "pytest", "-q", "tests"])
    ruff = run_command([sys.executable, "-m", "ruff", "check", "app", "bot", "eval", "tests"])
    containers = run_command(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"], timeout=20
    )
    memory = run_command(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}"],
        timeout=30,
    )

    health: dict = {"status": "not running"}
    try:
        response = httpx.get("http://127.0.0.1:8000/health", timeout=3)
        health = response.json()
    except Exception as exc:  # noqa: BLE001 - evidence may be collected without API
        health = {"status": "unavailable", "error": type(exc).__name__}

    kb = Path("data/kb")
    graph = json.loads((kb / "graph.json").read_text(encoding="utf-8"))
    terms = [
        json.loads(line)
        for line in (kb / "terms.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    outline = json.loads((kb / "outline.json").read_text(encoding="utf-8"))

    gold: dict[str, dict] = {}
    for name in ("report_v2_bge_m3.json", "report_v3_bge_m3.json", "report_kb.json"):
        path = Path("eval") / name
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        gold[name] = {
            "pass_rate": data.get("pass_rate"),
            "citation_recall": data.get("citation_recall"),
            "metrics": data.get("metrics"),
            "questions_scored": data.get("questions_scored"),
        }

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "version": get_version(),
        "git_commit": get_git_commit(),
        "git_tag": get_git_tag(),
        "tests": tests,
        "ruff": ruff,
        "health": health,
        "gosts": len(outline),
        "kb": {
            "terms": len(terms),
            "nodes": len(graph.get("nodes", [])),
            "edges": len(graph.get("edges", [])),
        },
        "gold": gold,
        "containers": containers,
        "memory": memory,
    }

    out = Path("docs/audit_evidence")
    out.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    test_line = tests["output"].splitlines()[-1] if tests["output"] else "n/a"
    ruff_line = "clean" if ruff["returncode"] == 0 else "errors"
    gold_lines = "\n".join(
        f"| `{name}` | {value.get('pass_rate')} | {value.get('citation_recall')} |"
        for name, value in gold.items()
    )
    markdown = f"""# Audit evidence

- Generated: {payload['generated_at']}
- Version: **{payload['version']}**, commit `{payload['git_commit'][:12]}`, tag `{payload['git_tag']}`
- Tests: {test_line}
- Ruff: {ruff_line}
- Health: `{json.dumps(health, ensure_ascii=False)}`
- Standards in outline: {payload['gosts']}
- KB: {payload['kb']['terms']} terms, {payload['kb']['nodes']} nodes, {payload['kb']['edges']} edges

| Gold | pass_rate | citation_recall |
|---|---|---|
{gold_lines}

## Containers

```text
{containers['output']}
```

## Memory

```text
{memory['output']}
```
"""
    out.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
