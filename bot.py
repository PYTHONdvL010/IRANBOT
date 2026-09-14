import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
}
DB_PATH = os.getenv("DB_PATH", "shop.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")


def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    with db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price_toman INTEGER NOT NULL,
                panel TEXT NOT NULL,
                description TEXT DEFAULT '',
                active INTEGER DEFAULT 1
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                config TEXT NOT NULL,
                delivered INTEGER DEFAULT 0
            )
        """)


def main_menu(user_id):
    buttons = [
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="products")],
        [
            InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders"),
            InlineKeyboardButton("👤 حساب من", callback_data="profile")
        ]
    ]

    # فقط Admin این دکمه را می‌بیند
    if user_id in ADMIN_IDS:
        buttons.append([
            InlineKeyboardButton("🛠 پنل مدیریت", callback_data="admin")
        ])

    return InlineKeyboardMarkup(buttons)


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن محصول", callback_data="admin_add")],
        [InlineKeyboardButton("📋 محصولات", callback_data="admin_products")],
        [InlineKeyboardButton("📦 سفارش‌ها", callback_data="admin_orders")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n\n"
        "به فروشگاه خوش اومدی.",
        reply_markup=main_menu(user.id)
    )


async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    with db() as c:
        rows = c.execute("""
            SELECT id, name, price_toman, panel
            FROM products
            WHERE active=1
            ORDER BY id DESC
        """).fetchall()

    if not rows:
        await q.edit_message_text(
            "🛒 هنوز محصولی اضافه نشده.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ بازگشت", callback_data="home")]
            ])
        )
        return

    buttons = []

    for pid, name, price, panel in rows:
        buttons.append([
            InlineKeyboardButton(
                f"{name} — {price:,} تومان",
                callback_data=f"product:{pid}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("↩️ بازگشت", callback_data="home")
    ])

    await q.edit_message_text(
        "🛒 محصول موردنظرت رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def product_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    pid = int(q.data.split(":")[1])

    with db() as c:
        product = c.execute("""
            SELECT id, name, price_toman, panel, description
            FROM products
            WHERE id=? AND active=1
        """, (pid,)).fetchone()

    if not product:
        await q.edit_message_text("❌ محصول پیدا نشد.")
        return

    pid, name, price, panel, description = product

    text = (
        f"📦 {name}\n\n"
        f"💰 قیمت: {price:,} تومان\n"
        f"🔌 پنل: {panel}\n"
    )

    if description:
        text += f"\n📝 {description}"

    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🛍 ثبت سفارش",
                    callback_data=f"order:{pid}"
                )
            ],
            [
                InlineKeyboardButton(
                    "↩️ محصولات",
                    callback_data="products"
                )
            ]
        ])
    )


async def create_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    pid = int(q.data.split(":")[1])

    with db() as c:
        product = c.execute("""
            SELECT name, price_toman
            FROM products
            WHERE id=? AND active=1
        """, (pid,)).fetchone()

        if not product:
            await q.edit_message_text("❌ محصول موجود نیست.")
            return

        order_id = c.execute("""
            INSERT INTO orders(user_id, product_id)
            VALUES (?, ?)
        """, (q.from_user.id, pid)).lastrowid

    name, price = product

    await q.edit_message_text(
        f"✅ سفارش #{order_id} ثبت شد.\n\n"
        f"📦 محصول: {name}\n"
        f"💰 مبلغ: {price:,} تومان\n\n"
        "💳 این نسخه Demo است؛ پرداخت فعلاً توسط Admin تأیید می‌شود.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📦 سفارش‌های من",
                    callback_data="orders"
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 منوی اصلی",
                    callback_data="home"
                )
            ]
        ])
    )


async def user_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    with db() as c:
        rows = c.execute("""
            SELECT o.id, p.name, o.status
            FROM orders o
            JOIN products p ON p.id=o.product_id
            WHERE o.user_id=?
            ORDER BY o.id DESC
            LIMIT 20
        """, (q.from_user.id,)).fetchall()

    if not rows:
        text = "📦 هنوز سفارشی نداری."
    else:
        text = "📦 سفارش‌های تو:\n\n"

        for oid, name, status in rows:
            text += f"#{oid} — {name} — {status}\n"

    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🛒 خرید سرویس",
                    callback_data="products"
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 منوی اصلی",
                    callback_data="home"
                )
            ]
        ])
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    with db() as c:
        count = c.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE user_id=?
        """, (q.from_user.id,)).fetchone()[0]

    await q.edit_message_text(
        f"👤 حساب کاربری\n\n"
        f"🆔 ID: {q.from_user.id}\n"
        f"👤 Username: @{q.from_user.username or '-'}\n"
        f"📦 تعداد سفارش‌ها: {count}",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🏠 منوی اصلی",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================
# ADMIN
# =========================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.from_user.id not in ADMIN_IDS:
        await q.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    await q.edit_message_text(
        "🛠 پنل مدیریت\n\n"
        "از منوی زیر استفاده کن:",
        reply_markup=admin_menu()
    )


async def admin_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.from_user.id not in ADMIN_IDS:
        return

    # شروع مراحل افزودن محصول
    context.user_data["adding_product"] = {
        "step": "name"
    }

    await q.edit_message_text(
        "➕ افزودن محصول\n\n"
        "1️⃣ اسم محصول رو بفرست:"
    )


async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.from_user.id not in ADMIN_IDS:
        return

    with db() as c:
        rows = c.execute("""
            SELECT id, name, price_toman, panel
            FROM products
            ORDER BY id DESC
        """).fetchall()

    if not rows:
        text = "📋 هنوز محصولی وجود نداره."
    else:
        text = "📋 محصولات:\n\n"

        for pid, name, price, panel in rows:
            text += (
                f"#{pid} | {name}\n"
                f"💰 {price:,} تومان\n"
                f"🔌 {panel}\n\n"
            )

    await q.edit_message_text(
        text,
        reply_markup=admin_menu()
    )


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.from_user.id not in ADMIN_IDS:
        return

    with db() as c:
        rows = c.execute("""
            SELECT o.id, o.user_id, p.name, o.status
            FROM orders o
            JOIN products p ON p.id=o.product_id
            ORDER BY o.id DESC
            LIMIT 30
        """).fetchall()

    if not rows:
        text = "📦 سفارشی وجود نداره."
    else:
        text = "📦 سفارش‌ها:\n\n"

        for oid, uid, name, status in rows:
            text += f"#{oid} | User: {uid} | {name} | {status}\n"

    await q.edit_message_text(
        text,
        reply_markup=admin_menu()
    )


# =========================
# ADD PRODUCT FLOW
# =========================

async def text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        return

    state = context.user_data.get("adding_product")

    if not state:
        return

    text = update.message.text.strip()

    # مرحله 1: اسم
    if state["step"] == "name":
        state["name"] = text
        state["step"] = "price"

        await update.message.reply_text(
            "💰 عالی.\n\n"
            "2️⃣ قیمت محصول رو به تومان بفرست.\n"
            "فقط عدد، مثلاً:\n\n"
            "150000"
        )
        return

    # مرحله 2: قیمت
    if state["step"] == "price":

        price_text = (
            text
            .replace(",", "")
            .replace("٬", "")
            .replace(" ", "")
        )

        if not price_text.isdigit():
            await update.message.reply_text(
                "❌ قیمت باید فقط عدد باشه.\n"
                "مثلاً: 150000"
            )
            return

        state["price"] = int(price_text)
        state["step"] = "panel"

        await update.message.reply_text(
            "🔌 3️⃣ محصول به کدوم پنل وصل بشه؟\n\n"
            "در نسخه Demo فعلاً یکی از پنل‌های تستی رو انتخاب کن:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🧪 Demo Panel 1",
                        callback_data="select_panel:Demo Panel 1"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🧪 Demo Panel 2",
                        callback_data="select_panel:Demo Panel 2"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🧪 Demo Panel 3",
                        callback_data="select_panel:Demo Panel 3"
                    )
                ]
            ])
        )


async def select_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.from_user.id not in ADMIN_IDS:
        return

    state = context.user_data.get("adding_product")

    if not state or state.get("step") != "panel":
        return

    panel = q.data.split(":", 1)[1]

    with db() as c:
        product_id = c.execute("""
            INSERT INTO products(name, price_toman, panel)
            VALUES (?, ?, ?)
        """, (
            state["name"],
            state["price"],
            panel
        )).lastrowid

    name = state["name"]
    price = state["price"]

    context.user_data.pop("adding_product", None)

    await q.edit_message_text(
        "✅ محصول با موفقیت اضافه شد!\n\n"
        f"🆔 ID: {product_id}\n"
        f"📦 نام: {name}\n"
        f"💰 قیمت: {price:,} تومان\n"
        f"🔌 پنل: {panel}\n\n"
        "🧪 این اتصال فعلاً Demo است.",
        reply_markup=admin_menu()
    )


# =========================
# ROUTER
# =========================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data

    if data == "products":
        await products(update, context)

    elif data.startswith("product:"):
        await product_details(update, context)

    elif data.startswith("order:"):
        await create_order(update, context)

    elif data == "orders":
        await user_orders(update, context)

    elif data == "profile":
        await profile(update, context)

    elif data == "admin":
        await admin_panel(update, context)

    elif data == "admin_add":
        await admin_add_product(update, context)

    elif data == "admin_products":
        await admin_products(update, context)

    elif data == "admin_orders":
        await admin_orders(update, context)

    elif data.startswith("select_panel:"):
        await select_panel(update, context)

    elif data == "home":
        await q.answer()
        await q.edit_message_text(
            "🏠 منوی اصلی",
            reply_markup=main_menu(q.from_user.id)
        )


def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        CallbackQueryHandler(callbacks)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_messages
        )
    )

    print("Config Shop Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
