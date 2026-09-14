# Telegram Config Shop — Railway Demo

این نسخه یک فروشگاه تلگرامی با پنل مدیریت و بخش مدیریت پنل‌هاست.

## امکانات
- شناسایی ادمین با Telegram numeric ID از `ADMIN_IDS`
- پنل مدیریت داخل بات
- افزودن محصول: نام → قیمت تومان → انتخاب پنل
- افزودن پنل با سه نوع:
  - Marzban
  - Pasarguard
  - 3x-ui
- هنگام افزودن پنل: آدرس → username → password
- Demo Test برای بررسی کامل بودن URL و credentialها
- نمایش لیست پنل‌ها
- تست دوباره پنل
- حذف پنل
- SQLite برای محصولات، سفارش‌ها، کانفیگ‌ها و پنل‌ها

## نکته مهم درباره Demo Test
در این نسخه، تست پنل **واقعاً به API پنل وصل نمی‌شود**؛ فقط فرمت آدرس و خالی نبودن username/password را بررسی می‌کند. برای تست واقعی باید API و نسخه دقیق هر پنل مشخص شود و endpoint/authentication مربوط به همان پنل پیاده‌سازی شود.

## Railway
1. این پروژه را به GitHub ببر یا فایل‌های آن را در یک Repository قرار بده.
2. در Railway پروژه را از Repository بساز.
3. Variables را تنظیم کن:
   - `BOT_TOKEN`
   - `ADMIN_IDS`
   - `DB_PATH=/app/data/shop.db`
4. برای ماندگاری SQLite یک Volume بساز و روی `/app/data` mount کن.
5. Deploy کن.

## فرمت ADMIN_IDS
برای یک ادمین:
`123456789`

برای چند ادمین:
`123456789,987654321`

توکن ربات و رمز پنل‌ها را داخل کد commit نکن.
