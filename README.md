# Telegram Shop Bot - PasarGuard Group Edition

## Railway Variables
BOT_TOKEN=...
ADMIN_IDS=123456789
DB_PATH=/app/data/shop.db

Mount a Railway Volume at /app/data for persistent SQLite storage.

## Flow
Admin -> Panel Management -> Add PasarGuard
1. panel name
2. base URL
3. username
4. password
5. real API login test

Then:
Panel Management -> اتصال Group
The bot logs in and reads available PasarGuard Groups. It does not require direct Xray inbound-management access.

A Group is saved with its inbound_tags metadata. The Group test only verifies API authentication and stored metadata; it does not create a real user or consume traffic.

Security note: this demo stores the panel password in SQLite. For production, encrypt credentials or use an API-key/secret-management approach.
