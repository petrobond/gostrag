from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

STATUS_LABELS = {
    "compliant": "соответствует",
    "partial": "частично",
    "non_compliant": "не соответствует",
    "not_applicable": "не применимо",
}


@dataclass(slots=True)
class Finding:
    requirement_id: str
    gost: str
    clause: str
    requirement: str
    category: str
    severity: str
    status: str
    evidence: str
    confidence: float


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_markdown(findings: list[Finding], meta: dict) -> str:
    total = len(findings) or 1
    compliant = sum(1 for f in findings if f.status == "compliant")
    partial = sum(1 for f in findings if f.status == "partial")
    non_compliant = sum(1 for f in findings if f.status == "non_compliant")
    not_applicable = sum(1 for f in findings if f.status == "not_applicable")

    lines = [
        "# Отчёт аудита соответствия ГОСТам",
        "",
        f"- Версия продукта: **{meta['product_version']}**",
        f"- Git commit: `{meta['git_commit']}`",
        f"- Git tag: `{meta['git_tag']}`",
        f"- Пользователь: `{meta['user_id']}`",
        f"- Дата: {meta['generated_at']}",
        f"- Модель judge: `{meta['judge_model']}`",
        "",
        "## Сводка",
        "",
        "| Показатель | Значение |",
        "|---|---|",
        f"| Требований | {len(findings)} |",
        f"| Соответствует | {compliant} |",
        f"| Частично | {partial} |",
        f"| Не соответствует | {non_compliant} |",
        f"| Не применимо | {not_applicable} |",
        f"| Compliance rate | {compliant / total:.2%} |",
        "",
        "## Результаты",
        "",
        "| ID | ГОСТ | Пункт | Категория | Статус | Уверенность | Доказательство |",
        "|---|---|---|---|---|---|---|",
    ]
    for finding in findings:
        evidence = finding.evidence.replace("|", "/").replace("\n", " ")[:220]
        lines.append(
            f"| {finding.requirement_id} | {finding.gost} | {finding.clause} | "
            f"{finding.category} | {STATUS_LABELS.get(finding.status, finding.status)} | "
            f"{finding.confidence:.2f} | {evidence} |"
        )
    lines += [
        "",
        "## Ограничения",
        "",
        "- Аудит внутренний, не является сертификацией.",
        "- ГОСТы добровольного применения (ст. 26 162-ФЗ).",
        "- LLM-as-a-judge не заменяет эксперта.",
        "",
    ]
    return "\n".join(lines)


def write_report(
    reports_dir: Path,
    product_version: str,
    user_id: int,
    findings: list[Finding],
    meta: dict,
) -> dict:
    report_dir = reports_dir / product_version / str(user_id)
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = report_dir / "manifest.json"

    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    markdown = render_markdown(findings, meta)
    md_path = report_dir / "audit.md"
    json_path = report_dir / "audit.json"
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(
        json.dumps([asdict(finding) for finding in findings], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total = len(findings) or 1
    manifest = {
        **meta,
        "requirements_total": len(findings),
        "compliance_rate": sum(1 for f in findings if f.status == "compliant") / total,
        "md_path": str(md_path),
        "json_path": str(json_path),
        "md_sha256": _hash(markdown),
        "json_sha256": _hash(json_path.read_text(encoding="utf-8")),
        "generated_at": meta.get("generated_at", datetime.now(UTC).isoformat()),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
