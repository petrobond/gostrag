"""Read-only connectivity matrix for local development.

Checks the resources that must be reachable at the same time:
Telegram (VPN), VPS SSH, Cloud.ru, GigaChat, GitHub, S3 and DeepSeek.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

CA_BUNDLE = Path("deploy/certs/ca-bundle.pem")

CHECKS = (
    ("telegram", "https://api.telegram.org", {200, 302, 404}, True),
    ("cloudru", "https://foundation-models.api.cloud.ru/v1/models", {200, 401}, True),
    ("gigachat", "https://api.giga.chat/v1/models", {200, 401}, True),
    ("sber_oauth", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth", {400, 401, 405}, False),
    ("github", "https://github.com", {200}, True),
    ("s3", "https://storage.yandexcloud.net", {200, 403}, True),
    ("deepseek", "https://api.deepseek.com/v1/models", {401}, False),
)


@dataclass(slots=True)
class Result:
    name: str
    target: str
    status: str
    ok: bool
    critical: bool


def check_url(name: str, url: str, expected: set[int], critical: bool) -> Result:
    verify: str | bool = str(CA_BUNDLE) if CA_BUNDLE.exists() else False
    try:
        response = httpx.get(url, timeout=8.0, verify=verify)
        status = str(response.status_code)
        ok = response.status_code in expected
    except Exception as exc:  # noqa: BLE001 - report connectivity, not a stack trace
        status = f"{type(exc).__name__}: {str(exc)[:80]}"
        ok = False
    return Result(name, url, status, ok, critical)


def check_tcp(name: str, host: str, port: int, critical: bool) -> Result:
    try:
        with socket.create_connection((host, port), timeout=5):
            return Result(name, f"{host}:{port}", "open", True, critical)
    except OSError as exc:
        return Result(name, f"{host}:{port}", str(exc)[:80], False, critical)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = [check_tcp("vps_ssh", "45.15.252.185", 22, True)]
    for name, url, expected, critical in CHECKS:
        results.append(check_url(name, url, expected, critical))
    results.append(check_url("local_qdrant", "http://localhost:6335/healthz", {200}, False))

    if args.json:
        print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))
    else:
        print(f"{'resource':14} {'status':8} {'target'}")
        for result in results:
            mark = "OK" if result.ok else "FAIL"
            print(f"{result.name:14} {mark:8} {result.target} [{result.status}]")

    if any(result.critical and not result.ok for result in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
