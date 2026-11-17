"""Web command metadata and safe slash-command parsing."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True, slots=True)
class WebCommand:
    name: str
    description: str
    usage: str
    href: str = ""
    admin: bool = False


PUBLIC_COMMANDS = (
    WebCommand("start", "Начало и краткая справка", "/start", "/help"),
    WebCommand("help", "Как пользоваться веб-интерфейсом", "/help", "/help"),
    WebCommand("gosts", "Список стандартов", "/gosts", "/tools/gosts"),
    WebCommand("ask", "Задать вопрос", "/ask <вопрос>", "/chat"),
    WebCommand("kb", "Разделы стандарта", "/kb ГОСТ Р 71476", "/tools/gosts"),
    WebCommand("term", "Определение термина", "/term термин", "/tools/terms"),
    WebCommand("links", "Связи стандарта", "/links ГОСТ Р 71540", "/tools/gosts"),
)

ADMIN_COMMANDS = (
    WebCommand("stats", "Статистика веба и бота (админ)", "/stats", "/admin", True),
    WebCommand("audit", "Отчёты ГОСТ-аудита (админ)", "/audit", "/admin/audit", True),
    WebCommand(
        "audit_status",
        "Статус аудита (админ)",
        "/audit_status",
        "/admin/audit#status",
        True,
    ),
)

ALL_COMMANDS = PUBLIC_COMMANDS + ADMIN_COMMANDS
BY_NAME = {command.name: command for command in ALL_COMMANDS}
ADMIN_NAMES = {command.name for command in ADMIN_COMMANDS}


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: str
    argument: str
    command: WebCommand | None
    unknown: bool = False


def visible_commands(user: dict | None) -> tuple[WebCommand, ...]:
    if user and user.get("role") == "admin":
        return ALL_COMMANDS
    return PUBLIC_COMMANDS


def parse_command(text: str) -> ParsedCommand | None:
    value = (text or "").strip()
    if not value.startswith("/"):
        return None
    token, _, argument = value.partition(" ")
    name = token[1:].lower()
    if not name:
        return ParsedCommand("", "", None, unknown=True)
    return ParsedCommand(
        name=name,
        argument=argument.strip(),
        command=BY_NAME.get(name),
        unknown=name not in BY_NAME,
    )


def command_url(parsed: ParsedCommand) -> str:
    if parsed.unknown or parsed.command is None:
        return "/help?unknown=" + quote(parsed.name)
    name = parsed.name
    argument = parsed.argument
    if name in {"start", "help"}:
        return "/help"
    if name == "gosts":
        return "/tools/gosts"
    if name == "ask":
        return "/chat"
    if name == "kb":
        return (
            "/tools/gosts/" + quote(argument, safe="") + "?tab=outline"
            if argument
            else "/tools/gosts"
        )
    if name == "term":
        return "/tools/terms" + (f"?q={quote(argument)}" if argument else "")
    if name == "links":
        return (
            "/tools/gosts/" + quote(argument, safe="") + "?tab=links"
            if argument
            else "/tools/gosts"
        )
    if name == "stats":
        return "/admin"
    if name == "audit":
        return "/admin/audit"
    if name == "audit_status":
        return "/admin/audit#status"
    return parsed.command.href or "/help"
