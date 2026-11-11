from app.audit.report import Finding, render_markdown, write_report


def make_finding(status: str = "compliant") -> Finding:
    return Finding(
        requirement_id="REQ-001",
        gost="ГОСТ Р 71476—2024",
        clause="3.6.4",
        requirement="Определять извлечение информации",
        category="терминология",
        severity="low",
        status=status,
        evidence="Глоссарий содержит определение",
        confidence=0.9,
    )


def test_render_markdown_contains_summary():
    text = render_markdown([make_finding()], {
        "product_version": "0.1.0",
        "git_commit": "abc",
        "git_tag": "v0.1.0",
        "user_id": 1,
        "generated_at": "2026-11-11T00:00:00Z",
        "judge_model": "GigaChat-3-Ultra",
    })
    assert "Отчёт аудита" in text
    assert "REQ-001" in text
    assert "соответствует" in text
    assert "0.1.0" in text


def test_write_report_is_idempotent(tmp_path):
    meta = {
        "product_version": "0.1.0",
        "git_commit": "abc",
        "git_tag": "v0.1.0",
        "user_id": 1,
        "generated_at": "2026-11-11T00:00:00Z",
        "judge_model": "GigaChat-3-Ultra",
    }
    first = write_report(tmp_path, "0.1.0", 1, [make_finding()], meta)
    second = write_report(tmp_path, "0.1.0", 1, [make_finding("non_compliant")], meta)
    assert first["md_sha256"] == second["md_sha256"]
    assert second["requirements_total"] == 1
