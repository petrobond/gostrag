from bot.commands import ADMIN_COMMANDS, PUBLIC_COMMANDS


def test_public_command_menu_is_valid():
    commands = [item.command for item in PUBLIC_COMMANDS]
    assert commands == ["start", "help", "gosts", "ask", "kb", "term", "links"]
    assert len(set(commands)) == len(commands)
    for item in PUBLIC_COMMANDS:
        assert item.command.islower()
        assert item.command.isalnum() or "_" in item.command
        assert not item.command.startswith("/")
        assert 1 <= len(item.description) <= 256


def test_admin_menu_extends_public_menu():
    public = {item.command for item in PUBLIC_COMMANDS}
    admin = {item.command for item in ADMIN_COMMANDS}
    assert public < admin
    assert {"stats", "audit", "audit_status"} <= admin
    assert len(admin) == len(ADMIN_COMMANDS)
