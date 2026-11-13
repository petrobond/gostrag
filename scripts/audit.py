"""Run GOST compliance audit with GigaChat judge and versioned report."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audit.report import Finding, write_report  # noqa: E402
from app.audit.version import get_git_commit, get_git_tag, get_version  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.llm.chain import LLMChain  # noqa: E402

JUDGE_PROMPT = """Ты — независимый аудитор соответствия программной системы требованиям ГОСТов.
Система: gostrag — RAG-система по российским стандартам ИИ. Отвечает на вопросы, цитирует ГОСТ/пункт/страницу,
отказывается при отсутствии контекста, имеет whitelist, квоты, версионирование отчётов.

Артефакты системы:
{artifacts}

Оцени каждое требование. Верни ТОЛЬКО JSON-массив, по одному объекту на требование:
[{{"requirement_id":"REQ-001","status":"compliant|partial|non_compliant","evidence":"...","confidence":0.0}}]

Правила:
- status только из enum: compliant, partial, non_compliant;
- evidence должен ссылаться на конкретный артефакт, файл, тест или документ;
- не ставь compliant без evidence;
- если evidence неполное или требование выполнено частично — partial;
- если требование явно не выполнено — non_compliant;
- не используй not_applicable: неприменимость уже отмечена в требованиях.

Требования:
{requirements}
"""

ARTIFACT_FILES = (
    "docs/architecture.md",
    "docs/data_quality.md",
    "docs/provenance.md",
    "docs/test_plan.md",
    "docs/trust.md",
    "docs/scope.md",
    "docs/kb.md",
    "docs/eval_results_v3.md",
    "docs/audit_evidence.md",
    "docs/networking.md",
    "docs/dev.md",
)


def load_artifacts(limit: int = 2500) -> str:
    blocks = []
    for name in ARTIFACT_FILES:
        path = Path(name)
        if path.exists():
            text = path.read_text(encoding="utf-8")[:limit]
            blocks.append(f"--- {name} ---\n{text}")
    return "\n\n".join(blocks)


def parse_json_array(text: str) -> list[dict]:
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    return []


async def run_audit(
    requirements_path: Path,
    reports_dir: Path,
    user_id: int,
    batch_size: int = 3,
) -> dict:
    settings = get_settings()
    version = get_version()
    commit = get_git_commit()
    tag = get_git_tag()

    manifest_path = reports_dir / version / str(user_id) / "manifest.json"
    if manifest_path.exists():
        print(f"report already exists: {manifest_path}")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    requirements = yaml.safe_load(requirements_path.read_text(encoding="utf-8"))
    artifacts = load_artifacts()
    chain = LLMChain(settings)
    findings: list[Finding] = []
    judged = [
        item
        for item in requirements
        if item.get("applicability", "applicable") != "not_applicable"
    ]
    for item in requirements:
        if item.get("applicability", "applicable") == "not_applicable":
            findings.append(
                Finding(
                    requirement_id=item["id"],
                    gost=item["gost"],
                    clause=str(item["clause"]),
                    requirement=item["requirement"],
                    category=item["category"],
                    severity=item["severity"],
                    status="not_applicable",
                    evidence=str(
                        item.get("applicability_reason")
                        or "Не применимо: требование вне области RAG-системы."
                    ),
                    confidence=1.0,
                )
            )

    for start in range(0, len(judged), batch_size):
        batch = judged[start : start + batch_size]
        req_text = "\n".join(
            f'{item["id"]} | {item["gost"]}, п. {item["clause"]} | {item["requirement"]}'
            for item in batch
        )
        prompt = JUDGE_PROMPT.format(artifacts=artifacts, requirements=req_text)
        result = await chain.chat(
            [{"role": "user", "content": prompt}],
            complexity="complex",
            max_tokens=1500,
            temperature=0.0,
        )
        scored = {item.get("requirement_id"): item for item in parse_json_array(result.content)}
        for item in batch:
            score = scored.get(item["id"], {})
            status = str(score.get("status", "partial"))
            if status not in {"compliant", "partial", "non_compliant"}:
                status = "partial"
            findings.append(
                Finding(
                    requirement_id=item["id"],
                    gost=item["gost"],
                    clause=str(item["clause"]),
                    requirement=item["requirement"],
                    category=item["category"],
                    severity=item["severity"],
                    status=status,
                    evidence=str(score.get("evidence", "Автоматическая оценка не дала результата")),
                    confidence=min(max(float(score.get("confidence", 0.0) or 0.0), 0.0), 1.0),
                )
            )
        print(
            f"judged {min(start + batch_size, len(judged))}/{len(judged)} "
            f"(na={len(requirements) - len(judged)})",
            flush=True,
        )
    findings.sort(key=lambda finding: finding.requirement_id)

    meta = {
        "product_version": version,
        "git_commit": commit,
        "git_tag": tag,
        "user_id": user_id,
        "judge_model": settings.gigachat_model_ultra,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return write_report(reports_dir, version, user_id, findings, meta)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", default="eval/requirements.yaml")
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--user-id", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=3)
    args = parser.parse_args()
    user_id = args.user_id or int(get_settings().telegram_user_ids.split(",")[0])
    manifest = asyncio.run(
        run_audit(Path(args.requirements), Path(args.reports), user_id, args.batch_size)
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
