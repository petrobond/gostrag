#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

check() {
  local expected="$1"
  shift
  local actual
  actual="$(code "$@")"
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $* -> $actual (expected $expected)" >&2
    exit 1
  fi
}

check 200 "$BASE/login"
check 303 "$BASE/"
check 303 "$BASE/chat"
check 401 "$BASE/api/web/conversations"
check 401 -X POST "$BASE/api/web/ask"

echo "web smoke ok: $BASE"
