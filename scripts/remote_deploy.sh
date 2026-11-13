#!/usr/bin/env bash
set -euo pipefail

: "${TAG:?TAG is required}"
: "${APP_IMAGE:?APP_IMAGE is required}"
: "${APP_VERSION:?APP_VERSION is required}"

cd /opt/gostrag
mkdir -p backups
STAMP="$(date +%Y%m%d-%H%M%S)"
COMPOSE=(sudo -n docker compose --env-file deploy/.env -f deploy/docker-compose.yml)

PREV_IMAGE="$(grep -E '^APP_IMAGE=' deploy/.env | cut -d= -f2- || true)"
PREV_IMAGE="${PREV_IMAGE:-gostrag:latest}"
echo "$PREV_IMAGE" | sudo -n tee deploy/.previous_image >/dev/null

sudo -n cp -p deploy/.env "backups/deploy.env.$STAMP"
sudo -n chmod 600 "backups/deploy.env.$STAMP"

"${COMPOSE[@]}" exec -T postgres \
  pg_dump -U gostrag gostrag | gzip > "backups/postgres-$STAMP.sql.gz"
curl -fsS -X POST http://localhost:6333/collections/gost_chunks_bge_m3/snapshots >/dev/null || true

git fetch --tags origin
git checkout -f "$TAG"

sudo -n sed -i "s|^APP_IMAGE=.*|APP_IMAGE=$APP_IMAGE|" deploy/.env
grep -q '^APP_IMAGE=' deploy/.env || echo "APP_IMAGE=$APP_IMAGE" | sudo -n tee -a deploy/.env >/dev/null
sudo -n sed -i "s|^APP_VERSION=.*|APP_VERSION=$APP_VERSION|" deploy/.env
grep -q '^APP_VERSION=' deploy/.env || echo "APP_VERSION=$APP_VERSION" | sudo -n tee -a deploy/.env >/dev/null

"${COMPOSE[@]}" pull app bot
"${COMPOSE[@]}" up -d --remove-orphans

ok=0
for _ in $(seq 1 30); do
  body="$(curl -fsS http://localhost:8000/health || true)"
  if echo "$body" | grep -q "\"version\":\"$APP_VERSION\""; then
    ok=1
    break
  fi
  sleep 2
done

if [ "$ok" != "1" ]; then
  echo "health check failed, rolling back to $PREV_IMAGE"
  sudo -n sed -i "s|^APP_IMAGE=.*|APP_IMAGE=$PREV_IMAGE|" deploy/.env
  "${COMPOSE[@]}" up -d
  exit 1
fi

curl -fsS -X POST http://localhost:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Что такое искусственный интеллект?","top_k":2}' \
  | grep -q '"answer"'

sudo -n docker image prune -f >/dev/null 2>&1 || true
echo "deploy ok: $TAG ($APP_VERSION)"
