#!/usr/bin/env bash
set -euo pipefail

TAG="${1:?usage: scripts/deploy.sh v3.1.0}"
APP_VERSION="${TAG#v}"
APP_IMAGE="${APP_IMAGE:-ghcr.io/petrobond/gostrag:$TAG}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/vps_deploy_key}"
SSH_USER="${SSH_USER:-gostrag}"
SSH_HOST="${SSH_HOST:-45.15.252.185}"
DATA_VERSION="${DATA_VERSION:-}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-}"
CORPUS_VERSION="${CORPUS_VERSION:-}"

ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o ConnectTimeout=10 \
  "$SSH_USER@$SSH_HOST" 'cat > /tmp/gostrag_deploy.sh' < scripts/remote_deploy.sh
ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o ConnectTimeout=10 \
  "$SSH_USER@$SSH_HOST" \
  "TAG='$TAG' APP_IMAGE='$APP_IMAGE' APP_VERSION='$APP_VERSION' \
  DATA_VERSION='$DATA_VERSION' QDRANT_COLLECTION='$QDRANT_COLLECTION' \
  CORPUS_VERSION='$CORPUS_VERSION' bash /tmp/gostrag_deploy.sh"
