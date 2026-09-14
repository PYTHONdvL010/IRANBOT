import os
import sqlite3
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
}
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
            panel_id INTEGER,
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
        c.execute("""CREATE TABLE IF NOT EXISTS panels(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_type TEXT NOT NULL,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            status TEXT DEFAULT 'unknown',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

        # Migration for older databases created by the first version.
        cols = {r[1] for r in c.execute("PRAGMA table_info(products)").fetchall()}
        if "panel_id" not in cols:
            c.execute("ALTER TABLE products ADD COLUMN panel_id INTEGER")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def menu(user_id: int):
    buttons = [
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="products")],
        [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders"),
         InlineKeyboardButton("👤 حساب من", callback_data="profile")],
        [InlineKeyboardButton("🎁 کد تخفیف", callback_data="coupon"),
         InlineKeyboardButton("💬 پشتیبانی", callback_data="support")],
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton("🛠 پنل مدیریت", callback_data="admin")])
    return InlineKeyboardMarkup(buttons)


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن محصول", callback_data="admin_add")],
        [InlineKeyboardButton("🖥 پنل‌ها", callback_data="admin_panels")],
        [InlineKeyboardButton("📋 محصولات", callback_data="admin_products")],
        [InlineKeyboardButton("📦 سفارش‌ها", callback_data="admin_orders")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
    ])


def cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="admin")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("flow", None)
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name} 👋\n\nبه فروشگاه کانفیگ خوش اومدی.",
        reply_markup=menu(user.id)
    )


async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        rows = c.execute("""
            SELECT p.id,p.name,p.price,COALESCE(pa.name,'بدون پنل')
            FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id
            WHERE p.active=1 ORDER BY p.id
        """).fetchall()
    if not rows:
        await q.edit_message_text("🛒 فعلاً محصولی ثبت نشده.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data="home")]]))
        return
    buttons = [[InlineKeyboardButton(f"{name} — {price}", callback_data=f"product:{pid}")] for pid,name,price,panel in rows]
    buttons.append([InlineKeyboardButton("↩️ بازگشت", callback_data="home")])
    await q.edit_message_text("🛒 پلن موردنظرت رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))


async def product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("""
            SELECT p.id,p.name,p.price,p.description,COALESCE(pa.name,'بدون پنل')
            FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id
            WHERE p.id=? AND p.active=1
        """, (pid,)).fetchone()
    if not row:
        await q.edit_message_text("محصول پیدا نشد.")
        return
    _, name, price, desc, panel = row
    await q.edit_message_text(
        f"📦 {name}\n\n{desc or 'بدون توضیحات'}\n\n💰 قیمت: {price}\n🖥 پنل: {panel}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍 ثبت سفارش", callback_data=f"order:{pid}")],
            [InlineKeyboardButton("↩️ محصولات", callback_data="products")]
        ])
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
        oid = c.execute("INSERT INTO orders(user_id,product_id) VALUES(?,?)", (q.from_user.id,pid)).lastrowid
    await q.edit_message_text(
        f"✅ سفارش #{oid} ثبت شد.\n\nمحصول: {row[0]}\nمبلغ: {row[1]}\n\n💳 پرداخت را تکمیل کن؛ بعد از تأیید ادمین کانفیگ تحویل می‌شود.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]
        ])
    )


async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        rows = c.execute("""SELECT o.id,p.name,o.status FROM orders o JOIN products p ON p.id=o.product_id
                           WHERE o.user_id=? ORDER BY o.id DESC LIMIT 20""", (q.from_user.id,)).fetchall()
    text = "📦 سفارش‌های تو:\n\n" + "\n".join(f"#{oid} — {name} — {status}" for oid,name,status in rows) if rows else "📦 هنوز سفارشی نداری."
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
        f"👤 پروفایل\n\nID: {q.from_user.id}\nنام کاربری: @{q.from_user.username or '-'}\nتعداد سفارش: {count}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]])
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data.pop("flow", None)
    await q.edit_message_text("🛠 پنل مدیریت\n\nیک بخش را انتخاب کن:", reply_markup=admin_menu())


async def admin_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    context.user_data["flow"] = {"type":"product", "step":"name"}
    await q.edit_message_text("➕ افزودن محصول\n\nلطفاً نام محصول را ارسال کن:", reply_markup=cancel_keyboard())


async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    with conn() as c:
        rows = c.execute("""SELECT p.id,p.name,p.price,COALESCE(pa.name,'بدون پنل')
                           FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id ORDER BY p.id DESC""").fetchall()
    text = "📋 محصولات\n\n" + ("\n".join(f"#{i} — {n}\n💰 {pr}\n🖥 {pn}" for i,n,pr,pn in rows) if rows else "هنوز محصولی ثبت نشده.")
    await q.edit_message_text(text, reply_markup=admin_menu())


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    with conn() as c:
        rows = c.execute("""SELECT o.id,o.user_id,p.name,o.status FROM orders o JOIN products p ON p.id=o.product_id
                           ORDER BY o.id DESC LIMIT 30""").fetchall()
    text = "📦 سفارش‌ها\n\n" + ("\n".join(f"#{oid} | user={uid} | {name} | {status}" for oid,uid,name,status in rows) if rows else "خالی")
    await q.edit_message_text(text, reply_markup=admin_menu())


# ---------------- Panels ----------------

PANEL_TYPES = {
    "marzban": "Marzban",
    "pasarguard": "Pasarguard",
    "3xui": "3x-ui",
}


def panel_type_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Marzban", callback_data="paneltype:marzban")],
        [InlineKeyboardButton("Pasarguard", callback_data="paneltype:pasarguard")],
        [InlineKeyboardButton("3x-ui", callback_data="paneltype:3xui")],
        [InlineKeyboardButton("❌ لغو", callback_data="admin")],
    ])


async def admin_panels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    context.user_data.pop("flow", None)
    with conn() as c:
        rows = c.execute("SELECT id,panel_type,name,address,status FROM panels ORDER BY id DESC").fetchall()
    text = "🖥 پنل‌ها\n\n"
    if rows:
        text += "\n\n".join(f"#{i} — {name}\nنوع: {PANEL_TYPES.get(pt,pt)}\nوضعیت: {status}" for i,pt,name,address,status in rows)
    else:
        text += "هنوز پنلی ثبت نشده."
    buttons = [[InlineKeyboardButton("➕ افزودن پنل", callback_data="add_panel")]]
    for i,pt,name,address,status in rows:
        buttons.append([InlineKeyboardButton(f"🧪 تست #{i}", callback_data=f"test_panel:{i}"), InlineKeyboardButton(f"🗑 حذف #{i}", callback_data=f"delete_panel:{i}")])
    buttons.append([InlineKeyboardButton("↩️ پنل مدیریت", callback_data="admin")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def add_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    context.user_data["flow"] = {"type":"panel", "step":"type"}
    await q.edit_message_text("🖥 چه نوع پنلی می‌خواهی اضافه کنی؟", reply_markup=panel_type_keyboard())


async def select_panel_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    pt = q.data.split(":",1)[1]
    context.user_data["flow"] = {"type":"panel", "step":"address", "panel_type":pt}
    await q.edit_message_text(
        f"🖥 نوع پنل: {PANEL_TYPES[pt]}\n\nلطفاً آدرس پنل را ارسال کن.\nمثال: https://panel.example.com",
        reply_markup=cancel_keyboard()
    )


def valid_url(value: str) -> bool:
    try:
        p = urlparse(value.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


async def finish_panel(context, message, flow):
    # Demo connection test: validates the address/credentials locally.
    # No real panel API call is made in this demo version.
    address = flow["address"]
    username = flow["username"]
    password = flow["password"]
    ok = valid_url(address) and bool(username.strip()) and bool(password.strip())
    status = "connected" if ok else "error"
    name = f"{PANEL_TYPES[flow['panel_type']]} #{flow.get('name_suffix','Panel')}"
    with conn() as c:
        pid = c.execute("""INSERT INTO panels(panel_type,name,address,username,password,status)
                          VALUES(?,?,?,?,?,?)""", (flow["panel_type"],name,address,username,password,status)).lastrowid
    if ok:
        await message.reply_text(f"✅ تست دمو موفق بود.\n\nپنل {PANEL_TYPES[flow['panel_type']]} ثبت شد.\nشناسه پنل: #{pid}\n\n⚠️ این نسخه دمو است و هنوز به API واقعی پنل وصل نمی‌شود.", reply_markup=admin_menu())
    else:
        await message.reply_text("❌ اطلاعات پنل معتبر نیست. آدرس، username یا password را بررسی کن.", reply_markup=admin_menu())


async def test_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("در حال تست دمو...")
    if not is_admin(q.from_user.id): return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("SELECT panel_type,name,address,username,password FROM panels WHERE id=?", (pid,)).fetchone()
    if not row:
        await q.edit_message_text("❌ پنل پیدا نشد.", reply_markup=admin_menu())
        return
    pt,name,address,username,password = row
    ok = valid_url(address) and bool(username) and bool(password)
    status = "connected" if ok else "error"
    with conn() as c:
        c.execute("UPDATE panels SET status=? WHERE id=?", (status,pid))
    if ok:
        text = f"🧪 تست پنل #{pid}\n\nنوع: {PANEL_TYPES.get(pt,pt)}\nنام: {name}\nآدرس: {address}\n\n🟢 Demo Test: OK\n🔐 اطلاعات ورود: موجود\n\n⚠️ تست واقعی API در این نسخه فعال نیست."
    else:
        text = f"🧪 تست پنل #{pid}\n\n🔴 Demo Test: FAILED\n\nآدرس یا اطلاعات ورود نامعتبر است."
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ پنل‌ها", callback_data="admin_panels")]]))


async def delete_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        c.execute("UPDATE products SET panel_id=NULL WHERE panel_id=?", (pid,))
        c.execute("DELETE FROM panels WHERE id=?", (pid,))
    await q.edit_message_text("🗑 پنل حذف شد.", reply_markup=admin_menu())


# ---------------- Text flow ----------------

async def text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    flow = context.user_data.get("flow")
    if not flow or not is_admin(user_id):
        return
    text = update.message.text.strip()

    if flow["type"] == "product":
        if flow["step"] == "name":
            flow["name"] = text
            flow["step"] = "price"
            await update.message.reply_text("💰 قیمت محصول را به تومان ارسال کن.\nمثال: 250000")
            return
        if flow["step"] == "price":
            digits = text.replace(",", "").replace("٬", "").replace("تومان", "").strip()
            if not digits.isdigit():
                await update.message.reply_text("❌ قیمت باید فقط عدد باشد. دوباره ارسال کن.")
                return
            flow["price"] = f"{int(digits):,} تومان"
            with conn() as c:
                panels = c.execute("SELECT id,panel_type,name,status FROM panels ORDER BY id DESC").fetchall()
            if not panels:
                await update.message.reply_text("❌ اول حداقل یک پنل از بخش 🖥 پنل‌ها اضافه کن.", reply_markup=admin_menu())
                context.user_data.pop("flow", None)
                return
            flow["step"] = "panel"
            buttons = [[InlineKeyboardButton(f"#{i} {name} ({PANEL_TYPES.get(pt,pt)})", callback_data=f"product_panel:{i}")] for i,pt,name,status in panels]
            buttons.append([InlineKeyboardButton("بدون پنل", callback_data="product_panel:0")])
            await update.message.reply_text("🖥 محصول به کدام پنل متصل باشد؟", reply_markup=InlineKeyboardMarkup(buttons))
            return

    if flow["type"] == "panel":
        if flow["step"] == "address":
            if not valid_url(text):
                await update.message.reply_text("❌ آدرس معتبر نیست. با http:// یا https:// ارسال کن.")
                return
            flow["address"] = text
            flow["step"] = "username"
            await update.message.reply_text("👤 لطفاً username پنل را ارسال کن.")
            return
        if flow["step"] == "username":
            flow["username"] = text
            flow["step"] = "password"
            await update.message.reply_text("🔑 لطفاً password پنل را ارسال کن.")
            return
        if flow["step"] == "password":
            flow["password"] = text
            await finish_panel(context, update.message, flow)
            context.user_data.pop("flow", None)
            return


async def select_product_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    flow = context.user_data.get("flow")
    if not flow or flow.get("type") != "product":
        await q.edit_message_text("فرآیند افزودن محصول منقضی شده.", reply_markup=admin_menu())
        return
    panel_id = int(q.data.split(":")[1])
    if panel_id:
        with conn() as c:
            p = c.execute("SELECT id,name FROM panels WHERE id=?", (panel_id,)).fetchone()
        if not p:
            await q.edit_message_text("❌ پنل پیدا نشد.", reply_markup=admin_menu())
            return
    with conn() as c:
        pid = c.execute("INSERT INTO products(name,price,panel_id) VALUES(?,?,?)", (flow["name"],flow["price"],panel_id or None)).lastrowid
    context.user_data.pop("flow", None)
    await q.edit_message_text(f"✅ محصول #{pid} اضافه شد.\n\nنام: {flow['name']}\nقیمت: {flow['price']}", reply_markup=admin_menu())


async def simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "home":
        context.user_data.pop("flow", None)
        await q.edit_message_text("🏠 منوی اصلی:", reply_markup=menu(q.from_user.id))
    elif q.data == "support":
        await q.edit_message_text("💬 پشتیبانی\n\nبرای پشتیبانی با ادمین فروشگاه تماس بگیر.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]]))
    elif q.data == "coupon":
        await q.edit_message_text("🎁 کد تخفیف\n\nفعلاً کد تخفیف فعال نیست.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]]))


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await update.message.reply_text("🛠 پنل مدیریت", reply_markup=admin_menu())


async def addconfig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    raw = update.message.text.removeprefix("/addconfig ").strip()
    parts = [x.strip() for x in raw.split("|", 1)]
    if len(parts) != 2 or not parts[0].isdigit():
        await update.message.reply_text("فرمت: /addconfig PRODUCT_ID | CONFIG")
        return
    with conn() as c:
        c.execute("INSERT INTO configs(product_id,config) VALUES(?,?)", (int(parts[0]),parts[1]))
    await update.message.reply_text("✅ کانفیگ به موجودی اضافه شد.")


async def list_products_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    with conn() as c:
        rows = c.execute("SELECT id,name,price,active FROM products ORDER BY id DESC").fetchall()
    await update.message.reply_text("📋 محصولات:\n" + ("\n".join(f"#{i} {n} — {p} — {'فعال' if a else 'غیرفعال'}" for i,n,p,a in rows) or "خالی"))


async def list_orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    with conn() as c:
        rows = c.execute("SELECT o.id,o.user_id,p.name,o.status FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT 30").fetchall()
    await update.message.reply_text("📦 سفارش‌ها:\n" + ("\n".join(f"#{oid} user={uid} {name} [{status}]" for oid,uid,name,status in rows) or "خالی"))


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id) or not context.args: return
    try: oid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ORDER_ID باید عدد باشد."); return
    with conn() as c:
        order = c.execute("SELECT user_id,product_id FROM orders WHERE id=?", (oid,)).fetchone()
        if not order:
            await update.message.reply_text("سفارش پیدا نشد."); return
        user_id, product_id = order
        cfg = c.execute("SELECT id,config FROM configs WHERE product_id=? AND delivered=0 LIMIT 1", (product_id,)).fetchone()
        if not cfg:
            await update.message.reply_text("❌ برای این محصول کانفیگ موجود نیست."); return
        c.execute("UPDATE orders SET status='paid' WHERE id=?", (oid,))
        c.execute("UPDATE configs SET delivered=1 WHERE id=?", (cfg[0],))
    await update.message.reply_text(f"✅ سفارش #{oid} تأیید شد.")
    try:
        await context.bot.send_message(user_id, f"🎉 سفارش #{oid} تأیید شد.\n\n🔐 کانفیگ شما:\n\n{cfg[1]}")
    except Exception:
        pass


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    if data == "admin": return await admin_panel(update, context)
    if data == "admin_add": return await admin_add_product(update, context)
    if data == "admin_panels": return await admin_panels(update, context)
    if data == "add_panel": return await add_panel_start(update, context)
    if data.startswith("paneltype:"): return await select_panel_type(update, context)
    if data.startswith("test_panel:"): return await test_panel(update, context)
    if data.startswith("delete_panel:"): return await delete_panel(update, context)
    if data.startswith("product_panel:"): return await select_product_panel(update, context)
    if data == "admin_products": return await admin_products(update, context)
    if data == "admin_orders": return await admin_orders(update, context)
    return await simple(update, context)


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("addconfig", addconfig))
    app.add_handler(CommandHandler("products", list_products_cmd))
    app.add_handler(CommandHandler("orders", list_orders_cmd))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CallbackQueryHandler(products, pattern=r"^products$"))
    app.add_handler(CallbackQueryHandler(product, pattern=r"^product:\d+$"))
    app.add_handler(CallbackQueryHandler(create_order, pattern=r"^order:\d+$"))
    app.add_handler(CallbackQueryHandler(orders, pattern=r"^orders$"))
    app.add_handler(CallbackQueryHandler(profile, pattern=r"^profile$"))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_messages))
    app.run_polling()


if __name__ == "__main__":
    main()
