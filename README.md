# Config Shop Bot — Railway

This is the full merged version of the Telegram config shop bot.

## Included
- Telegram shop, products, orders, profile, wallet, coupon/support placeholders
- Admin panel visible only to IDs in `ADMIN_IDS`
- Panel registration for Marzban / Pasarguard / 3x-ui with API login test
- Pasarguard Group selection and user creation
- Pasarguard test user (1 MB / 1 day)
- Subscription URL fix: relative `/sub/...` responses are converted to an absolute URL using the registered panel address
- Product creation from registered panels
- Product data limit in GB and expiry in days
- Financial admin section
- Store card number + card owner name
- Direct payment by receipt photo -> admin approve/reject
- Wallet top-up by receipt photo -> admin approve/reject
- Wallet payment: if balance is enough, service is created immediately without admin approval
- If wallet balance is insufficient, bot guides the user to card payment and receipt upload
- On payment approval, Pasarguard service is created automatically with the product's GB/day settings and the subscription link is sent to the buyer
- Delivered subscription is saved in the user's Orders section
- SQLite persistence

## Railway Variables
```text
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
ADMIN_IDS=123456789
DB_PATH=/app/data/shop.db
```

Mount a Railway Volume at `/app/data` so the SQLite database survives redeploys.

## Important
For automatic delivery, the product must be connected to a registered Pasarguard panel with at least one selected Group.
