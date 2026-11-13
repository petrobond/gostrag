# CI/CD

## 1. Пайплайн

| Событие | Что происходит |
|---|---|
| push в `release/**` | CI: `ruff`, `pytest`, сборка образа `linux/amd64` без push |
| PR в `release/**` | CI |
| push тега `v*` | Release: сборка и push в GHCR; Deploy: approval → VPS |

Файлы:

- `.github/workflows/ci.yml` — lint/test/image;
- `.github/workflows/release.yml` — build/push + deploy;
- `scripts/deploy.sh` — локальный fallback;
- `scripts/remote_deploy.sh` — шаги на VPS (backup, pull, health, rollback).

Образ: `ghcr.io/petrobond/gostrag:<tag>` и `:sha-<commit>`.
Сборка multi-stage, runtime без `build-essential` и `curl`.

## 2. Секреты GitHub

Нужны:

| Secret | Значение |
|---|---|
| `VPS_SSH_KEY` | содержимое `/Users/Lenovo/.ssh/vps_deploy_key` (приватный ключ) |
| `VPS_HOST` | `45.15.252.185` |
| `VPS_USER` | `gostrag` |
| `GHCR_PAT` | только если пакет GHCR private (иначе не нужен) |

Секреты не коммитить и не печатать.

## 2.1. Переменные репозитория

| Variable | Значение | Назначение |
|---|---|---|
| `DATA_VERSION` | `2026.11.13` | скачать data-артефакт и переиндексировать на VPS |
| `QDRANT_COLLECTION` | `gost_chunks_bge_m3_v2` | новая коллекция после переиндексации |
| `CORPUS_VERSION` | `2026.11.13` | версия корпуса в `/health` и отчётах |

Устанавливаются владельцем:

```bash
gh variable set DATA_VERSION -R petrobond/gostrag --body 2026.11.13
gh variable set QDRANT_COLLECTION -R petrobond/gostrag --body gost_chunks_bge_m3_v2
gh variable set CORPUS_VERSION -R petrobond/gostrag --body 2026.11.13
gh variable list -R petrobond/gostrag
```

Если `DATA_VERSION` пуст, deploy не трогает данные и только обновляет образ.

## 3. Блокер 2026-11-13

`gh secret set` возвращает 403:

```text
failed to fetch public key: HTTP 403: You must have repository read permissions
or have the repository secrets fine-grained permission.
```

Причина: `gh` залогинен как `PBondarevOctaneRent`, у него только `pull`
на `petrobond/gostrag`:

```json
{"admin":false,"maintain":false,"pull":true,"push":false,"triage":false}
```

Пока это не исправлено, GitHub Actions deploy не может прочитать секреты.
CI и release-сборка образа работают (используют `GITHUB_TOKEN`).

### Что нужно сделать владельцу

**Вариант A (рекомендуется):** выдать `PBondarevOctaneRent` роль Admin:
GitHub → `petrobond/gostrag` → Settings → Collaborators and teams →
`PBondarevOctaneRent` → Role: **Admin** → Update.

После этого выполнить:

```bash
gh secret set VPS_SSH_KEY -R petrobond/gostrag < /Users/Lenovo/.ssh/vps_deploy_key
gh secret set VPS_HOST -R petrobond/gostrag --body 45.15.252.185
gh secret set VPS_USER -R petrobond/gostrag --body gostrag
gh secret list -R petrobond/gostrag
```

**Вариант B:** войти в `gh` под владельцем `petrobond` и выполнить те же
три команды:

```bash
gh auth logout
gh auth login
gh secret set VPS_SSH_KEY -R petrobond/gostrag < /Users/Lenovo/.ssh/vps_deploy_key
gh secret set VPS_HOST -R petrobond/gostrag --body 45.15.252.185
gh secret set VPS_USER -R petrobond/gostrag --body gostrag
```

**Вариант C:** GitHub UI → Settings → Secrets and variables → Actions →
New repository secret: `VPS_SSH_KEY` (вставить содержимое файла),
`VPS_HOST`, `VPS_USER`.

## 4. Environment `production`

GitHub → Settings → Environments → New environment → `production` →
Required reviewers → добавить `petrobond` → Save.

Тогда deploy-джоба будет ждать ручного подтверждения. Без reviewer
деплой по тегу выполнится автоматически.

## 5. GHCR

После первого тега пакет появится в GitHub Packages. Если он private:

- сделать public: Packages → `gostrag` → Package settings → Change visibility;
- или добавить `GHCR_PAT` с `read:packages` и использовать его в deploy.

Deploy-джоба логинится на VPS через `GITHUB_TOKEN` workflow, поэтому
private-пакет тоже работает в рамках запуска.

## 6. Deploy key

`~/.ssh/vps_deploy_key` — ed25519 без passphrase, публичная часть добавлена
в `/home/gostrag/.ssh/authorized_keys` на VPS. Проверка:

```bash
ssh -i ~/.ssh/vps_deploy_key -o IdentitiesOnly=yes gostrag@45.15.252.185 'echo OK'
```

Write-права GitHub deploy key для SSH на VPS **не важны**: доступ к VPS
определяется `authorized_keys`, а не правами ключа в GitHub.

## 7. Локальный fallback

Если GitHub Actions недоступен:

```bash
# образ должен быть уже в GHCR
scripts/deploy.sh v3.1.0
```

Скрипт использует `~/.ssh/vps_deploy_key`, делает backup, pull, health-check
и откат на предыдущий `APP_IMAGE`.

## 8. Проверка

```bash
gh api repos/petrobond/gostrag --jq '.permissions'
gh secret list -R petrobond/gostrag
gh run list -R petrobond/gostrag --limit 5
ssh ultra 'curl -s localhost:8000/health'
```
