# Russian Trusted CA

Публичные сертификаты Минцифры для проверки TLS GigaChat (`api.giga.chat`,
`ngw.devices.sberbank.ru`).

| Файл | Источник | Действует до |
|---|---|---|
| `russian_trusted_root_ca.crt` | `https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt` | 2032-02-27 |
| `russian_trusted_sub_ca.crt` | `https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt` | 2027-03-06 |

Это не секреты. `scripts/build_ca_bundle.py` собирает локальный
`ca-bundle.pem` (certifi + оба сертификата); файл в `.gitignore`.

В Docker сертификаты копируются в `/usr/local/share/ca-certificates/`,
затем `update-ca-certificates`; `GIGACHAT_CA_BUNDLE` указывает на системный
bundle. `verify=False` в GigaChat больше не используется.
