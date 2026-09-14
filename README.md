# Config Shop Bot — previous version + PasarGuard Group

این نسخه همان امکانات نسخه قبلی را نگه می‌دارد: فروشگاه، افزودن محصول، سفارش‌ها، کیف پول Demo، پنل‌های Marzban/PasarGuard/3x-ui، تست Login واقعی و مدیریت محصولات.

## PasarGuard Group mode
به‌جای اتصال مستقیم به Inbound، داخل جزئیات PasarGuard گزینه «اتصال Group» وجود دارد. بات Groupهای قابل دسترس API را می‌گیرد و Group انتخابی را ذخیره می‌کند. این برای حساب‌هایی مناسب است که دسترسی مستقیم به Inbound ندارند.

- اتصال Group
- بروزرسانی Groupها
- ساخت کاربر با group_ids ثبت‌شده
- تست 1MB / 1 روز با همان Groupها و دریافت subscription URL

در نسخه‌های جدید PasarGuard ممکن است اپراتور فقط `/api/groups/simple` را ببیند؛ در این حالت فقط id/name قابل مشاهده است و بات ادعا نمی‌کند inbound tagها را دیده است.

## Railway Variables
```
BOT_TOKEN=...
ADMIN_IDS=123456789
DB_PATH=/app/data/shop.db
```

Railway Volume را روی `/app/data` قرار بده.

**امنیت:** این نسخه برای دمو username/password پنل را در SQLite نگه می‌دارد. برای production بهتر است credentials رمزنگاری شوند یا از secret/API-key مناسب استفاده شود.
