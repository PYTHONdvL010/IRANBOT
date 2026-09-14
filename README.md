# Config Shop Telegram Bot

بات فروشگاهی پایه برای فروش و تحویل خودکار کانفیگ‌هایی که خودت در موجودی قرار می‌دهی.

## Railway Variables

BOT_TOKEN=توکن BotFather
ADMIN_IDS=123456789
DB_PATH=/app/data/shop.db

برای ماندگاری SQLite، یک Volume روی `/app/data` قرار بده.

## دستورات ادمین

/admin
/addproduct NAME | PRICE | DESCRIPTION
/addconfig PRODUCT_ID | CONFIG
/products
/orders
/approve ORDER_ID

## جریان خرید

کاربر محصول را انتخاب می‌کند → سفارش ساخته می‌شود → پرداخت خارج از این MVP تأیید می‌شود → ادمین `/approve ORDER_ID` می‌زند → اولین کانفیگ موجود تحویل کاربر می‌شود.

این نسخه عمداً درگاه پرداخت خاصی را هاردکد نمی‌کند؛ می‌توان در مرحله بعد Stripe، درگاه محلی یا روش پرداخت موردنظر را اضافه کرد.
