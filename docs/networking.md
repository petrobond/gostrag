# Сеть и раздельное туннелирование

## 1. Требование

Одновременно должны быть доступны:

| Ресурс | Зачем | Маршрут |
|---|---|---|
| `api.telegram.org` | бот на VPS / тестовый бот | VPN (`utun4`) |
| `45.15.252.185:22` | SSH и деплой | напрямую |
| `foundation-models.api.cloud.ru` | эмбеддинги BGE-M3 | напрямую (`en0`) |
| `api.giga.chat`, `ngw.devices.sberbank.ru` | GigaChat | напрямую (`en0`) |
| `github.com`, `ghcr.io` | git и CI/CD | напрямую |
| `storage.yandexcloud.net` | PDF и data-артефакты | напрямую |
| `api.deepseek.com` | fallback LLM | напрямую |

Проверка одной командой:

```bash
.venv/bin/python scripts/net_matrix.py
```

Ожидаемый результат — все строки `OK`; exit code 1, если критичный ресурс
(Telegram, VPS, Cloud.ru, GigaChat, GitHub, S3) недоступен.

## 2. Фактическая настройка (2026-11-13)

- AmneziaVPN на Mac: split tunneling, Telegram — через `utun4`.
- Cloud.ru и GigaChat — через `en0` напрямую.
- VPS SSH — напрямую; `Host ultra` в `~/.ssh/config`.
- На VPS AmneziaWG (`awg0`) уже настроен для Telegram; не трогать.

## 3. TLS GigaChat

Цепочка GigaChat подписана `Russian Trusted Sub CA` → `Russian Trusted Root CA`.
В certifi этих корней нет, поэтому:

- сертификаты лежат в `deploy/certs/`;
- локально `scripts/build_ca_bundle.py` собирает `deploy/certs/ca-bundle.pem`;
- в `deploy/.env` задан `GIGACHAT_CA_BUNDLE` на этот bundle;
- в Docker сертификаты ставятся в системный store, `GIGACHAT_CA_BUNDLE`
  указывает на `/etc/ssl/certs/ca-certificates.crt`;
- `verify=False` в GigaChat не используется.

## 4. Диагностика

| Симптом | Причина | Действие |
|---|---|---|
| Cloud.ru timeout | трафик ушёл в VPN | добавить `*.cloud.ru` в direct/exclude |
| GigaChat timeout | трафик ушёл в VPN | direct/exclude для `*.sberbank.ru`, `*.giga.chat` |
| GigaChat `CERTIFICATE_VERIFY_FAILED` | нет Russian Trusted CA | собрать `ca-bundle.pem`, проверить `GIGACHAT_CA_BUNDLE` |
| Telegram timeout | нет handshake AWG | проверить профиль AmneziaVPN, не менять VPS |
| SSH к VPS не работает | профиль завернул VPS в туннель | direct route на `45.15.252.185`, откатить профиль |
| `scripts/net_matrix.py` exit 1 | критичный ресурс недоступен | смотреть строку `FAIL`, не печатать секреты |

Секреты (ключи, токены, приватные ключи AWG) в диагностику не попадают.


## 5. Веб-интерфейс и TLS (v3.3.0)

| Ресурс | Зачем | Маршрут |
|---|---|---|
| `https://<WEB_DOMAIN>:443` | веб-интерфейс (Caddy) | напрямую |
| `http://<WEB_DOMAIN>:80` | ACME HTTP-01 и редирект на HTTPS | напрямую |

- Домен задаётся в `deploy/.env` (`WEB_DOMAIN`, `WEB_ACME_EMAIL`); DNS A-запись
  указывает на `45.15.252.185`.
- Открыть TCP 80/443 на VPS и у провайдера; SSH 22 не меняется.
- Caddy получает сертификат Let's Encrypt автоматически и продлевает его.
- `/api/ask` и `/health` снаружи отвечают 404; Qdrant/PG/Redis остаются
  на `127.0.0.1`.
- Без HTTPS `Secure`-cookie не работает, поэтому доступ по «голому» IP не
  используется. Варианты домена — в `docs/adr/001-web-ui-auth.md`.
