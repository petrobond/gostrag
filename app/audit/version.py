from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path


def get_version(root: Path | None = None) -> str:
    env_version = os.getenv("APP_VERSION", "").strip()
    if env_version:
        return env_version
    root = root or Path.cwd()
    with (root / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    return str(data["project"]["version"])


def _git(args: list[str], root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=root, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def get_git_commit(root: Path | None = None) -> str:
    return os.getenv("GIT_COMMIT", "") or _git(["rev-parse", "HEAD"], root or Path.cwd())


def get_git_tag(root: Path | None = None) -> str:
    return os.getenv("GIT_TAG", "") or _git(
        ["describe", "--tags", "--always"], root or Path.cwd()
    )
