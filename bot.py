import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
DB_PATH = os.getenv("DB_PATH", "shop.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

def conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price TEXT NOT NULL,
            description TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS configs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            config TEXT NOT NULL,
            delivered INTEGER DEFAULT 0
        )""")

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="products")],
        [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders"),
         InlineKeyboardButton("👤 حساب من", callback_data="profile")],
        [InlineKeyboardButton("🎁 کد تخفیف", callback_data="coupon"),
         InlineKeyboardButton("💬 پشتیبانی", callback_data="support")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n\n"
        "به فروشگاه کانفیگ خوش اومدی.\n"
        "از منوی زیر سرویس موردنظرت رو انتخاب کن:",
        reply_markup=menu()
    )

async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        rows = c.execute(
            "SELECT id,name,price,description FROM products WHERE active=1 ORDER BY id"
        ).fetchall()

    if not rows:
        await q.edit_message_text(
            "🛒 فعلاً محصولی برای فروش ثبت نشده.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data="home")]])
        )
        return

    buttons = [
        [InlineKeyboardButton(f"{name} — {price}", callback_data=f"product:{pid}")]
        for pid, name, price, desc in rows
    ]
    buttons.append([InlineKeyboardButton("↩️ بازگشت", callback_data="home")])
    await q.edit_message_text("🛒 پلن موردنظرت رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))

async def product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split(":")[1])

    with conn() as c:
        row = c.execute(
            "SELECT id,name,price,description FROM products WHERE id=? AND active=1", (pid,)
        ).fetchone()

    if not row:
        await q.edit_message_text("محصول پیدا نشد.")
        return

    _, name, price, desc = row
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 ثبت سفارش", callback_data=f"order:{pid}")],
        [InlineKeyboardButton("↩️ محصولات", callback_data="products")]
    ])
    await q.edit_message_text(
        f"📦 {name}\n\n{desc}\n\n💰 قیمت: {price}\n\n"
        "بعد از ثبت سفارش، وضعیت پرداخت توسط ادمین بررسی می‌شود.",
        reply_markup=kb
    )

async def create_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split(":")[1])

    with conn() as c:
        row = c.execute("SELECT name,price FROM products WHERE id=? AND active=1", (pid,)).fetchone()
        if not row:
            await q.edit_message_text("محصول دیگر موجود نیست.")
            return
        oid = c.execute(
            "INSERT INTO orders(user_id,product_id) VALUES(?,?)",
            (q.from_user.id, pid)
        ).lastrowid

    await q.edit_message_text(
        f"✅ سفارش #{oid} ثبت شد.\n\n"
        f"محصول: {row[0]}\n"
        f"مبلغ: {row[1]}\n\n"
        "💳 روش پرداخت را با ادمین/درگاه فروشگاه تکمیل کن.\n"
        "پس از تأیید پرداخت، کانفیگ تحویل می‌شود.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]
        ])
    )

async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        rows = c.execute("""
            SELECT o.id,p.name,o.status,o.created_at
            FROM orders o JOIN products p ON p.id=o.product_id
            WHERE o.user_id=? ORDER BY o.id DESC LIMIT 20
        """, (q.from_user.id,)).fetchall()

    if not rows:
        text = "📦 هنوز سفارشی نداری."
    else:
        text = "📦 سفارش‌های تو:\n\n" + "\n".join(
            f"#{oid} — {name} — {status}" for oid,name,status,created in rows
        )

    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="products")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]
    ]))

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        count = c.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (q.from_user.id,)).fetchone()[0]
    await q.edit_message_text(
        f"👤 پروفایل\n\n"
        f"ID: {q.from_user.id}\n"
        f"نام کاربری: @{q.from_user.username or '-'}\n"
        f"تعداد سفارش: {count}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]])
    )

async def simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "home":
        await q.edit_message_text("🏠 منوی اصلی:", reply_markup=menu())
    elif q.data == "support":
        await q.edit_message_text(
            "💬 پشتیبانی\n\nبرای پشتیبانی با ادمین فروشگاه تماس بگیر.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]])
        )
    elif q.data == "coupon":
        await q.edit_message_text(
            "🎁 کد تخفیف\n\nفعلاً کد تخفیف فعال نیست.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]])
        )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text(
        "🛠 پنل ادمین\n\n"
        "/addproduct NAME | PRICE | DESCRIPTION\n"
        "/addconfig PRODUCT_ID | CONFIG\n"
        "/products — لیست محصولات\n"
        "/orders — سفارش‌ها\n"
        "/approve ORDER_ID — تأیید سفارش"
    )

async def addproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    raw = update.message.text.removeprefix("/addproduct ").strip()
    parts = [x.strip() for x in raw.split("|", 2)]
    if len(parts) != 3:
        await update.message.reply_text("فرمت:\n/addproduct NAME | PRICE | DESCRIPTION")
        return
    with conn() as c:
        pid = c.execute(
            "INSERT INTO products(name,price,description) VALUES(?,?,?)", parts
        ).lastrowid
    await update.message.reply_text(f"✅ محصول #{pid} اضافه شد.")

async def addconfig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    raw = update.message.text.removeprefix("/addconfig ").strip()
    parts = [x.strip() for x in raw.split("|", 1)]
    if len(parts) != 2:
        await update.message.reply_text("فرمت:\n/addconfig PRODUCT_ID | CONFIG")
        return
    with conn() as c:
        c.execute("INSERT INTO configs(product_id,config) VALUES(?,?)", (int(parts[0]), parts[1]))
    await update.message.reply_text("✅ کانفیگ به موجودی اضافه شد.")

async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    with conn() as c:
        rows = c.execute("SELECT id,name,price,active FROM products").fetchall()
    await update.message.reply_text(
        "🛒 محصولات:\n" + ("\n".join(f"#{x} {n} — {p} — {'فعال' if a else 'غیرفعال'}" for x,n,p,a in rows) or "خالی")
    )

async def list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    with conn() as c:
        rows = c.execute("""
            SELECT o.id,o.user_id,p.name,o.status
            FROM orders o JOIN products p ON p.id=o.product_id
            ORDER BY o.id DESC LIMIT 30
        """).fetchall()
    await update.message.reply_text(
        "📦 سفارش‌ها:\n" + ("\n".join(f"#{oid} user={uid} {name} [{status}]" for oid,uid,name,status in rows) or "خالی")
    )

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS or not context.args:
        return
    oid = int(context.args[0])
    with conn() as c:
        order = c.execute(
            "SELECT user_id,product_id FROM orders WHERE id=?", (oid,)
        ).fetchone()
        if not order:
            await update.message.reply_text("سفارش پیدا نشد.")
            return

        user_id, product_id = order
        cfg = c.execute(
            "SELECT id,config FROM configs WHERE product_id=? AND delivered=0 LIMIT 1",
            (product_id,)
        ).fetchone()

        if not cfg:
            await update.message.reply_text("❌ برای این محصول کانفیگ موجود نیست.")
            return

        c.execute("UPDATE orders SET status='paid' WHERE id=?", (oid,))
        c.execute("UPDATE configs SET delivered=1 WHERE id=?", (cfg[0],))

    await update.message.reply_text(f"✅ سفارش #{oid} تأیید شد.")
    try:
        await context.bot.send_message(
            user_id,
            f"🎉 پرداخت سفارش #{oid} تأیید شد.\n\n"
            f"🔐 کانفیگ شما:\n\n{cfg[1]}"
        )
    except Exception:
        pass

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("addproduct", addproduct))
    app.add_handler(CommandHandler("addconfig", addconfig))
    app.add_handler(CommandHandler("products", list_products))
    app.add_handler(CommandHandler("orders", list_orders))
    app.add_handler(CommandHandler("approve", approve))

    app.add_handler(CallbackQueryHandler(products, pattern=r"^products$"))
    app.add_handler(CallbackQueryHandler(product, pattern=r"^product:\d+$"))
    app.add_handler(CallbackQueryHandler(create_order, pattern=r"^order:\d+$"))
    app.add_handler(CallbackQueryHandler(orders, pattern=r"^orders$"))
    app.add_handler(CallbackQueryHandler(profile, pattern=r"^profile$"))
    app.add_handler(CallbackQueryHandler(simple, pattern=r"^(home|support|coupon)$"))

    app.run_polling()

if __name__ == "__main__":
    main()
