# ⚡ IRANBOT v1.0.5
### Telegram VPN / Config Shop — Railway Ready

> فروشگاه حرفه‌ای سرویس VPN و کانفیگ در Telegram با پنل مدیریت Web، پرداخت، کیف پول، تست رایگان و اتصال به Marzban / Pasarguard / 3x-ui.

---

## ✨ درباره پروژه

**IRANBOT** یک Telegram Bot فروش سرویس VPN است که برای اجرای ساده روی **Railway** آماده شده.

ساختار پروژه به شکل زیر است:

```text
Telegram Bot
│
├── 🛒 محصولات
├── 📦 سفارش‌ها
├── 💳 پرداخت
├── 💰 کیف پول
├── 🎁 تست رایگان
├── 📢 عضویت اجباری
├── 🎫 پشتیبانی
├── 👥 مدیریت کاربران
│
└── 🌐 Web Admin Panel
       │
       ├── کاربران
       ├── محصولات
       ├── سفارش‌ها
       ├── پنل‌ها
       ├── Group ها
       ├── امور مالی
       ├── تست رایگان
       ├── خوش‌آمدگویی
       └── عضویت اجباری
```

---

# 🚀 امکانات

## 🤖 Telegram Bot

### 👤 بخش کاربر

- 🏠 منوی اصلی
- 🛒 مشاهده محصولات
- 📦 خرید سرویس
- 💳 پرداخت با رسید
- 💰 پرداخت از کیف پول
- ➕ شارژ کیف پول
- 📋 مشاهده سفارش‌ها
- 🔐 سرویس‌های من
- 🔗 دریافت Subscription
- 👤 پروفایل
- 🎫 پشتیبانی متنی و تصویری
- 🎁 دریافت تست رایگان
- 📢 بررسی عضویت در کانال‌های اجباری

### 🛠 بخش مدیریت

- ➕ افزودن محصول
- 🖥 مدیریت پنل‌ها
- 🔌 تست اتصال پنل
- 🔗 مدیریت Group های Pasarguard
- 👥 مدیریت کاربران
- 🚫 مسدود / رفع مسدودی کاربران
- 💰 افزایش / کاهش موجودی
- 💳 مدیریت پرداخت‌ها
- 💵 تنظیم اطلاعات کارت
- 🎁 تنظیم تست رایگان
- 📢 مدیریت عضویت اجباری
- 👋 تنظیم پیام خوش‌آمد
- 📦 مدیریت سفارش‌ها

---

# 🌐 Web Admin Panel

پنل مدیریت تحت وب با Flask اجرا می‌شود.

بخش‌های اصلی:

```text
🏠 Dashboard
👥 Users
👋 Welcome
📢 Mandatory Membership
💳 Finance
🖥 Panels
📦 Products
🧾 Orders
🎁 Free Tests
🏷 Discount
```

### Dashboard

نمایش آمار مهم:

- تعداد کاربران
- تعداد محصولات
- تعداد سفارش‌ها
- پرداخت‌های تأییدشده
- پرداخت‌های در انتظار
- تعداد پنل‌ها

---

# 🔗 Pasarguard Groups

یکی از بخش‌های مهم پروژه، مدیریت Group های Pasarguard است.

ساختار Pasarguard:

```text
User
 ↓
Group
 ↓
Inbound Tags
 ↓
Hosts
```

در Web Panel می‌توانید:

- Group ها را دریافت کنید
- Group های موردنظر را انتخاب کنید
- چند Group را همزمان انتخاب کنید
- Group های انتخاب‌شده را ذخیره کنید
- Group ها را بروزرسانی کنید

پس از انتخاب Group، هنگام ساخت سرویس از Group های تنظیم‌شده استفاده می‌شود.

---

# 🖥 پنل‌های پشتیبانی‌شده

| پنل | وضعیت |
|---|---|
| Marzban | ✅ |
| Pasarguard | ✅ |
| 3x-ui | ✅ |

### Marzban / Pasarguard

ورود API با Endpoint مربوط به Admin Token انجام می‌شود.

### 3x-ui

ورود با Login API و Session انجام می‌شود و وضعیت اتصال پنل بررسی می‌شود.

---

# 💳 سیستم پرداخت

## پرداخت مستقیم

روند خرید:

```text
انتخاب محصول
     ↓
نمایش قیمت
     ↓
نمایش شماره کارت و نام صاحب کارت
     ↓
ارسال رسید
     ↓
بررسی ادمین
     ↓
تأیید پرداخت
     ↓
ساخت سرویس
     ↓
ارسال Subscription
```

## 💰 کیف پول

کاربر می‌تواند کیف پول خود را شارژ کند.

اطلاعات کارت در صفحه اصلی کیف پول نمایش داده نمی‌شود.

اطلاعات کارت فقط در مرحله پرداخت نمایش داده می‌شود:

```text
💳 شماره کارت
👤 نام صاحب کارت
```

پس از تأیید پرداخت، موجودی کیف پول افزایش پیدا می‌کند.

اگر موجودی کافی باشد، کاربر می‌تواند سرویس را مستقیماً با موجودی خود خریداری کند.

---

# 🎁 تست رایگان

ادمین می‌تواند برای هر پنل تست رایگان تنظیم کند.

پارامترها:

```text
Panel
Max Tests
Volume (MB)
Expire Time (Hours)
Enabled / Disabled
```

مثال:

```text
Max Tests: 2
Volume: 500 MB
Expire: 6 Hours
```

کاربر مقدار حجم و زمان را انتخاب نمی‌کند؛ تنظیمات توسط ادمین تعیین می‌شود.

---

# 📢 عضویت اجباری

امکان اضافه کردن چند کانال اجباری وجود دارد.

کاربر باید در تمام کانال‌های فعال عضو باشد.

```text
کانال 1 ─┐
کانال 2 ─┼──> بررسی عضویت ──> ورود به Bot
کانال 3 ─┘
```

ادمین‌ها از محدودیت عضویت اجباری مستثنی هستند.

---

# 👥 مدیریت کاربران

مدیریت کاربران هم از داخل Bot و هم Web Panel انجام می‌شود.

امکانات:

- 🔎 جستجوی کاربر
- 👤 مشاهده اطلاعات کاربر
- 💰 مشاهده موجودی
- ➕ افزایش موجودی
- ➖ کاهش موجودی
- 🚫 Block
- ✅ Unblock
- 📦 مشاهده وضعیت سفارش‌ها

اطلاعات پایه کاربران در دیتابیس ذخیره می‌شود:

```text
user_id
username
first_name
is_blocked
created_at
last_seen
```

---

# 🗄 Database

پروژه از **SQLite** استفاده می‌کند.

جداول اصلی شامل:

```text
users
wallets
panels
panel_groups
products
orders
configs
payments
settings
support_tickets
free_test_settings
free_test_usage
```

برای Railway پیشنهاد می‌شود SQLite روی Volume قرار بگیرد.

مسیر پیشنهادی:

```text
/app/data/shop.db
```

---

# 🔐 متغیرهای Environment

برای این پروژه فقط همین سه متغیر اصلی را تنظیم کنید:

```env
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
ADMIN_IDS=123456789
DB_PATH=/app/data/shop.db
```

## 1️⃣ BOT_TOKEN

توکن ربات Telegram که از BotFather دریافت می‌کنید.

مثال:

```env
BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxx
```

⚠️ توکن واقعی خودتان را داخل GitHub یا README قرار ندهید.

---

## 2️⃣ ADMIN_IDS

Telegram ID ادمین‌ها.

یک ادمین:

```env
ADMIN_IDS=123456789
```

چند ادمین:

```env
ADMIN_IDS=123456789,987654321
```

---

## 3️⃣ DB_PATH

مسیر دیتابیس SQLite:

```env
DB_PATH=/app/data/shop.db
```

اگر Railway Volume را روی:

```text
/app/data
```

قرار دهید، اطلاعات دیتابیس بعد از Restart و Deployهای معمولی پایدارتر می‌ماند.

---

# ☁️ نصب روی Railway

## مرحله 1 — Fork کردن پروژه

اگر پروژه روی GitHub قرار دارد:

1. وارد Repository شوید.
2. بالای صفحه روی **Fork** کلیک کنید.
3. حساب GitHub خودتان را انتخاب کنید.
4. یک Repository جدید برای پروژه ساخته می‌شود.

ساختار ساده:

```text
Original Repository
       │
       └── Fork
             ↓
       Your GitHub Repository
```

### چرا Fork؟

با Fork یک کپی از پروژه داخل حساب GitHub خودتان دارید و می‌توانید آن را مستقل تغییر دهید و به Railway متصل کنید.

---

# 🚂 مرحله 2 — اتصال Fork به Railway

در Railway:

```text
New Project
   ↓
Deploy from GitHub Repo
   ↓
انتخاب Repository خودتان
   ↓
Deploy
```

Railway پروژه را از GitHub دریافت و Build می‌کند.

بعد از هر Push جدید به Repository، در صورت فعال بودن اتصال GitHub، می‌توانید پروژه را دوباره Deploy کنید.

---

# 🔧 مرحله 3 — Variables

داخل Railway وارد:

```text
Service
→ Variables
```

شوید و این سه مقدار را قرار دهید:

```env
BOT_TOKEN=توکن_ربات
ADMIN_IDS=آیدی_تلگرام_ادمین
DB_PATH=/app/data/shop.db
```

### مثال

```env
BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxx
ADMIN_IDS=123456789
DB_PATH=/app/data/shop.db
```

---

# 💾 مرحله 4 — Volume

برای SQLite بهتر است Volume بسازید.

در Railway:

```text
Service
→ Volumes
→ Add Volume
```

Mount Path:

```text
/app/data
```

و Variable:

```env
DB_PATH=/app/data/shop.db
```

---

# 🌍 مرحله 5 — Public Domain

برای Web Panel باید برای Service یک Public Domain ایجاد کنید.

بعد از Deploy:

```text
Networking
→ Public Networking
→ Generate Domain
```

سپس آدرس Web Panel را باز کنید.

---

# 🔑 ورود به Web Panel

Web Panel برای مدیریت طراحی شده و دسترسی آن باید فقط در اختیار ادمین باشد.

بعد از Deploy، Domain ساخته‌شده توسط Railway را باز کنید.

مثال:

```text
https://your-project.up.railway.app
```

---

# ⚙️ تنظیمات اولیه

بعد از اولین اجرای موفق:

### 1. پنل VPN را اضافه کنید

مثلاً:

```text
Name: PG-01
Type: Pasarguard
Address: https://panel.example.com
Username: admin
Password: ********
```

### 2. تست اتصال

اتصال پنل را تست کنید.

### 3. Group ها

برای Pasarguard:

```text
Panels
→ Groups
→ دریافت Group ها
→ انتخاب Group
→ ذخیره
```

### 4. کارت بانکی

در Finance شماره کارت و نام صاحب کارت را تنظیم کنید.

### 5. محصول

محصول ایجاد کنید و آن را به پنل موردنظر متصل کنید.

### 6. تست خرید

یک محصول ارزان یا تستی بسازید و کل فرآیند را بررسی کنید.

---

# 🐞 Bug Fix — نسخه 1.0.5

این نسخه شامل اصلاحات مربوط به **Bug**های نسخه 1.0.5 است و شماره نسخه پروژه همچنان **1.0.5** باقی می‌ماند.

## 🔧 مشکل Group ها

مشکل مشاهده‌شده:

```text
pid is undefined
```

در صفحه Group های Web Panel باعث می‌شد صفحه مدیریت Group به‌درستی کامل نشود.

این مشکل اصلاح شده است.

### نتیجه

اکنون صفحه Group باید بتواند:

```text
✓ پنل را شناسایی کند
✓ Group ها را نمایش دهد
✓ چند Group را انتخاب کند
✓ Group ها را ذخیره کند
✓ Group ها را بروزرسانی کند
✓ خطای API را به شکل کنترل‌شده نمایش دهد
```

به‌جای اینکه صفحه با:

```text
500 Internal Server Error
```

از کار بیفتد.

---

# 🩺 اگر بعد از Deploy هنوز Group ها نمایش داده نشدند

این موارد را بررسی کنید:

```text
[1] Panel Address صحیح است
[2] Username صحیح است
[3] Password صحیح است
[4] پنل واقعاً Pasarguard است
[5] API پنل از Railway قابل دسترسی است
[6] اکانت پنل دسترسی لازم را دارد
[7] Railway Logs بررسی شده است
```

اگر صفحه باز می‌شود ولی Groupی نمایش داده نمی‌شود، ممکن است مشکل از API یا Permission خود Pasarguard باشد، نه Web Panel.

---

# 🧪 چک‌لیست تست بعد از Deploy

بعد از Deploy این موارد را یکی‌یکی تست کنید:

```text
[ ] Bot /start
[ ] ثبت کاربر
[ ] منوی اصلی
[ ] عضویت اجباری
[ ] محصولات
[ ] افزودن محصول
[ ] اتصال پنل
[ ] Test Connection
[ ] دریافت Group های Pasarguard
[ ] انتخاب Group
[ ] ذخیره Group
[ ] تست رایگان
[ ] شارژ کیف پول
[ ] پرداخت
[ ] تأیید پرداخت
[ ] ساخت سرویس
[ ] دریافت Subscription
[ ] سرویس‌های من
[ ] پشتیبانی
[ ] مدیریت کاربران
[ ] Block / Unblock
[ ] افزایش / کاهش موجودی
```

---

# 🔒 نکات امنیتی مهم

هرگز این موارد را داخل Repository عمومی قرار ندهید:

```text
BOT_TOKEN
رمز پنل VPN
اطلاعات حساس کاربران
Database
```

توکن Bot را فقط در Railway Variables قرار دهید.

همچنین:

```text
.env
*.db
*.sqlite
*.sqlite3
```

را بهتر است در `.gitignore` قرار دهید.

اگر Token ربات به‌صورت عمومی منتشر شد، آن را فوراً از طریق BotFather تعویض کنید.

---

# 📁 ساختار پروژه

```text
IRANBOT/
│
├── bot.py
├── web_panel.py
├── requirements.txt
├── Dockerfile
├── railway.toml
├── .env.example
└── README.md
```

### `bot.py`

هسته Telegram Bot:

```text
Users
Products
Orders
Wallet
Payments
Support
Free Test
Mandatory Membership
Panel API
```

### `web_panel.py`

پنل مدیریت تحت وب.

### `requirements.txt`

کتابخانه‌های موردنیاز Python.

### `Dockerfile`

تعریف محیط اجرای پروژه.

### `railway.toml`

تنظیمات Deploy پروژه روی Railway.

---

# 🏁 خلاصه نصب سریع

اگر بخواهید سریع راه‌اندازی کنید:

```text
1. Fork Repository
        ↓
2. Deploy Fork در Railway
        ↓
3. ساخت Volume
        ↓
4. تنظیم /app/data
        ↓
5. تنظیم BOT_TOKEN
        ↓
6. تنظیم ADMIN_IDS
        ↓
7. تنظیم DB_PATH
        ↓
8. Deploy
        ↓
9. ساخت Public Domain
        ↓
10. ورود به Web Panel
        ↓
11. افزودن Panel
        ↓
12. تست Connection
        ↓
13. تنظیم Group
        ↓
14. ساخت Product
        ↓
15. تست خرید
```

---

# ❤️ IRANBOT

یک فروشگاه کامل Telegram برای فروش سرویس VPN با:

```text
🤖 Telegram Bot
🌐 Web Admin
🛒 Shop
💳 Payment
💰 Wallet
🖥 VPN Panels
🔗 Pasarguard Groups
🎁 Free Test
📢 Mandatory Membership
👥 User Management
🎫 Support
🗄 SQLite
☁️ Railway
```

**Version: 1.0.5**

> این README مربوط به **نسخه 1.0.5** است و Bug Fix مربوط به Group های Web Panel در همین نسخه اعمال شده است.
