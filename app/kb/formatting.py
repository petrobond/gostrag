def format_outline(outline: dict) -> str:
    """Format a KB outline without counting split chunks as separate clauses."""
    lines = [f"{outline['gost']}: разделы"]
    for section in outline.get("sections", [])[:20]:
        clauses = section.get("clauses", [])
        numbers = {item["clause"] for item in clauses}
        leaves = [
            item
            for item in clauses
            if item["clause"] != section["section"]
            and not any(
                other.startswith(f"{item['clause']}.")
                for other in numbers
                if other != item["clause"]
            )
        ]
        if not leaves:
            leaves = [item for item in clauses if item["clause"] == section["section"]]
        if not leaves and clauses:
            leaves = clauses[:1]
        title = (section.get("title") or "").strip()
        label = section.get("section") or "—"
        suffix = f" {title}" if title else ""
        lines.append(f"• {label}{suffix} — {len(leaves)} п.")
    return "\n".join(lines)
