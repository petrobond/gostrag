"""Telegram command menu definitions."""

from aiogram.types import BotCommand

PUBLIC_COMMANDS = (
    BotCommand(command="start", description="Запуск и краткая справка"),
    BotCommand(command="help", description="Как пользоваться ботом"),
    BotCommand(command="gosts", description="Список стандартов"),
    BotCommand(command="ask", description="Задать вопрос"),
    BotCommand(command="kb", description="Разделы ГОСТа"),
    BotCommand(command="term", description="Определение термина"),
    BotCommand(command="links", description="Связи стандарта"),
)

ADMIN_COMMANDS = PUBLIC_COMMANDS + (
    BotCommand(command="stats", description="Статистика (админ)"),
    BotCommand(command="audit", description="ГОСТ-аудит (whitelist)"),
    BotCommand(command="audit_status", description="Статус аудита"),
)
