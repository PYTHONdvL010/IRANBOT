# Config Shop Bot v3 — Railway

## Features
- Telegram config shop MVP
- Numeric Telegram admin allow-list via `ADMIN_IDS`
- Admin product creation
- Panel registration: Marzban / Pasarguard / 3x-ui
- Real API login test for the three panel types
- Pasarguard inbound discovery and inbound connection by name/tag
- Pasarguard groups automatically used to grant users access to registered inbound tags
- Pasarguard 1 MB / 1 day test user creation with subscription URL
- Demo wallet
- SQLite persistence

## Railway variables
```text
BOT_TOKEN=...
ADMIN_IDS=123456789,987654321
DB_PATH=/app/data/shop.db
```

Mount a Railway Volume at `/app/data` so SQLite survives redeploy/restart.

## Pasarguard flow
1. Admin → 🖥 پنل‌ها → add Pasarguard.
2. Send the base URL, username, password.
3. After API login succeeds, open the Pasarguard panel card.
4. `🔗 اتصال Inbound` → send the inbound name/tag. The bot checks `/api/inbounds` and stores the matching inbound tag.
5. The bot uses a dedicated group (`botpanel<ID>`) whose `inbound_tags` are the saved inbounds. PasarGuard's group system is the access layer for subscriptions.
6. `🧪 Pasarguard — تست Inbound` creates a 1 MB, 1-day test user with the registered inbound group and shows the subscription URL.

## Important
- This version targets current PasarGuard v5-style APIs. PasarGuard documents groups as the mechanism connecting users to inbound tags, and the user API accepts `group_ids`.
- The bot stores panel credentials in SQLite so it can retest the panel later. For production, encrypt these credentials or move them to a secret store.
- Do not paste real panel credentials into public chats or screenshots.
