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
