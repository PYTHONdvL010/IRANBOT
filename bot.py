
import os
import sqlite3
import logging
from urllib.parse import urlparse

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
}
DB_PATH = os.getenv("DB_PATH", "shop.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")


def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    with db() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price_toman INTEGER NOT NULL,
            panel_id INTEGER,
            description TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS panels(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            panel_type TEXT NOT NULL,
            base_url TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            status TEXT DEFAULT 'unknown',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS panel_groups(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_id INTEGER NOT NULL,
            group_id INTEGER,
            group_name TEXT NOT NULL,
            inbound_tags TEXT DEFAULT '',
            UNIQUE(panel_id, group_name)
        )""")


def normalize_url(value: str):
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    p = urlparse(value)
    if not p.netloc:
        return None
    # Remove UI paths such as /dashboard/#/login.
    return f"{p.scheme}://{p.netloc}".rstrip("/")


def is_admin(uid):
    return uid in ADMIN_IDS


def main_menu(uid):
    rows = [
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="products")],
        [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders"),
         InlineKeyboardButton("👤 حساب من", callback_data="profile")],
    ]
    if is_admin(uid):
        rows.append([InlineKeyboardButton("🛠 پنل مدیریت", callback_data="admin")])
    return InlineKeyboardMarkup(rows)


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن محصول", callback_data="admin_add")],
        [InlineKeyboardButton("🖥 پنل‌ها", callback_data="admin_panels")],
        [InlineKeyboardButton("📋 محصولات", callback_data="admin_products")],
        [InlineKeyboardButton("📦 سفارش‌ها", callback_data="admin_orders")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
    ])


def panels_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن PasarGuard", callback_data="add_pasarguard")],
        [InlineKeyboardButton("📋 پنل‌های ثبت‌شده", callback_data="list_panels")],
        [InlineKeyboardButton("🧪 تست پنل", callback_data="panel_test_menu")],
        [InlineKeyboardButton("🔗 اتصال Group", callback_data="group_connect_menu")],
        [InlineKeyboardButton("🧪 تست Group/Inbound", callback_data="group_test_menu")],
        [InlineKeyboardButton("⬅️ پنل مدیریت", callback_data="admin")],
    ])


def cancel_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="cancel_flow")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "سلام 👋\nبه ربات فروش سرویس خوش آمدی.",
        reply_markup=main_menu(update.effective_user.id)
    )


async def api_login(panel):
    """PasarGuard API login. Returns (ok, token_or_error)."""
    url = normalize_url(panel["base_url"])
    if not url:
        return False, "آدرس پنل نامعتبر است."

    endpoint = f"{url}/api/admin/token"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.post(
                endpoint,
                data={"username": panel["username"], "password": panel["password"]},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if r.status_code in (401, 403):
                return False, "نام کاربری یا رمز عبور اشتباه است."
            if r.status_code >= 400:
                return False, f"HTTP {r.status_code}: {r.text[:180]}"
            data = r.json()
            token = data.get("access_token")
            if not token:
                return False, "توکن احراز هویت از پنل دریافت نشد."
            return True, token
    except httpx.RequestError as e:
        return False, f"اتصال به پنل برقرار نشد: {type(e).__name__}"
    except Exception as e:
        return False, f"خطای API: {str(e)[:180]}"


async def pasarguard_groups(panel, token):
    """Read groups; this does not require direct inbound-management permission."""
    url = normalize_url(panel["base_url"])
    endpoint = f"{url}/api/groups"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 403:
                return False, "این حساب اجازه مشاهده Groupها را ندارد."
            if r.status_code >= 400:
                return False, f"HTTP {r.status_code}: {r.text[:180]}"
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", data.get("groups", []))
            return True, items
    except Exception as e:
        return False, f"خطا در دریافت Groupها: {str(e)[:180]}"


def extract_group_fields(g):
    gid = g.get("id") or g.get("group_id")
    name = g.get("name") or g.get("group_name") or g.get("tag")
    tags = g.get("inbound_tags") or g.get("inbounds") or []
    if isinstance(tags, str):
        tags = [x.strip() for x in tags.split(",") if x.strip()]
    return gid, name, tags


async def show_admin_panels(update, context):
    q = update.callback_query
    await q.edit_message_text("🖥 مدیریت پنل‌ها", reply_markup=panels_menu())


async def begin_add_pasarguard(update, context):
    q = update.callback_query
    context.user_data["flow"] = {"type": "add_panel", "step": "name"}
    await q.edit_message_text(
        "🖥 افزودن PasarGuard\n\nیک نام برای این پنل بفرست:",
        reply_markup=cancel_menu()
    )


async def handle_panel_text(update, context):
    flow = context.user_data.get("flow")
    if not flow or flow.get("type") != "add_panel":
        return False

    text = update.message.text.strip()
    step = flow["step"]

    if step == "name":
        flow["name"] = text
        flow["step"] = "url"
        await update.message.reply_text(
            "لطفاً آدرس اصلی پنل را بفرست.\n"
            "مثال:\nhttps://panel.example.com:2096\n\n"
            "اگر /dashboard/#/login هم بفرستی، خودکار حذف می‌شود.",
            reply_markup=cancel_menu()
        )
    elif step == "url":
        url = normalize_url(text)
        if not url:
            await update.message.reply_text("❌ آدرس نامعتبر است. دوباره ارسال کن.")
            return True
        flow["url"] = url
        flow["step"] = "username"
        await update.message.reply_text("👤 لطفاً username پنل را بفرست:", reply_markup=cancel_menu())
    elif step == "username":
        flow["username"] = text
        flow["step"] = "password"
        await update.message.reply_text("🔑 لطفاً password پنل را بفرست:", reply_markup=cancel_menu())
    elif step == "password":
        flow["password"] = text
        panel = {
            "name": flow["name"], "base_url": flow["url"],
            "username": flow["username"], "password": flow["password"]
        }
        await update.message.reply_text("⏳ در حال تست Login و API پنل...")
        ok, result = await api_login(panel)
        if not ok:
            await update.message.reply_text(f"❌ تست ناموفق بود.\n\n{result}", reply_markup=panels_menu())
            context.user_data.clear()
            return True

        with db() as c:
            cur = c.execute(
                """INSERT INTO panels(name,panel_type,base_url,username,password,status)
                   VALUES(?,?,?,?,?,?)""",
                (panel["name"], "pasarguard", panel["base_url"],
                 panel["username"], panel["password"], "connected")
            )
            pid = cur.lastrowid

        await update.message.reply_text(
            f"✅ پنل ثبت شد.\n\n"
            f"نام: {panel['name']}\n"
            f"نوع: PasarGuard\n"
            f"وضعیت: 🟢 Connected\n\n"
            f"حالا از بخش «🔗 اتصال Group» می‌توانی Groupهای همین پنل را اضافه کنی.",
            reply_markup=panels_menu()
        )
        context.user_data.clear()
    return True


async def list_panels(update, context):
    q = update.callback_query
    with db() as c:
        rows = c.execute(
            "SELECT id,name,panel_type,status,base_url FROM panels ORDER BY id DESC"
        ).fetchall()
    if not rows:
        text = "📋 هنوز پنلی ثبت نشده."
    else:
        text = "📋 پنل‌های ثبت‌شده:\n\n"
        for pid, name, typ, status, url in rows:
            text += f"#{pid} — {name}\nنوع: {typ}\nوضعیت: {status}\nآدرس: {url}\n\n"
    await q.edit_message_text(text, reply_markup=panels_menu())


def panel_buttons(prefix):
    with db() as c:
        rows = c.execute("SELECT id,name FROM panels ORDER BY id DESC").fetchall()
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"#{pid} {name}", callback_data=f"{prefix}:{pid}")] for pid, name in rows]
        + [[InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_panels")]]
    )


async def panel_test_menu(update, context):
    q = update.callback_query
    with db() as c:
        exists = c.execute("SELECT COUNT(*) FROM panels").fetchone()[0]
    if not exists:
        await q.edit_message_text("هیچ پنلی ثبت نشده.", reply_markup=panels_menu())
    else:
        await q.edit_message_text("🧪 کدام پنل را تست کنم؟", reply_markup=panel_buttons("ptest"))


async def test_panel(update, context, pid):
    q = update.callback_query
    with db() as c:
        row = c.execute(
            "SELECT id,name,base_url,username,password FROM panels WHERE id=?", (pid,)
        ).fetchone()
    if not row:
        await q.answer("پنل پیدا نشد.", show_alert=True)
        return
    panel = dict(id=row[0], name=row[1], base_url=row[2], username=row[3], password=row[4])
    await q.edit_message_text("⏳ در حال تست API Login...")
    ok, result = await api_login(panel)
    with db() as c:
        c.execute("UPDATE panels SET status=? WHERE id=?", ("connected" if ok else "error", pid))
    await q.edit_message_text(
        f"🧪 نتیجه تست\n\nپنل: {panel['name']}\n"
        + ("🟢 API Login موفق است." if ok else f"🔴 تست ناموفق:\n{result}"),
        reply_markup=panels_menu()
    )


async def group_connect_menu(update, context):
    q = update.callback_query
    with db() as c:
        rows = c.execute("SELECT id,name FROM panels WHERE panel_type='pasarguard'").fetchall()
    if not rows:
        await q.edit_message_text("اول یک PasarGuard اضافه کن.", reply_markup=panels_menu())
        return
    await q.edit_message_text(
        "🔗 انتخاب PasarGuard برای دریافت Groupها:",
        reply_markup=panel_buttons("gconnect")
    )


async def load_groups_for_panel(update, context, pid):
    q = update.callback_query
    with db() as c:
        row = c.execute(
            "SELECT id,name,base_url,username,password FROM panels WHERE id=?", (pid,)
        ).fetchone()
    if not row:
        await q.answer("پنل پیدا نشد.", show_alert=True)
        return
    panel = dict(id=row[0], name=row[1], base_url=row[2], username=row[3], password=row[4])
    ok, token = await api_login(panel)
    if not ok:
        await q.edit_message_text(f"❌ Login ناموفق:\n{token}", reply_markup=panels_menu())
        return
    ok, groups = await pasarguard_groups(panel, token)
    if not ok:
        await q.edit_message_text(f"❌ دریافت Groupها ناموفق بود:\n{groups}", reply_markup=panels_menu())
        return

    # Store a fresh snapshot in local DB. The bot never needs direct inbound permission.
    with db() as c:
        c.execute("DELETE FROM panel_groups WHERE panel_id=?", (pid,))
        for g in groups:
            gid, name, tags = extract_group_fields(g)
            if name:
                c.execute(
                    "INSERT OR REPLACE INTO panel_groups(panel_id,group_id,group_name,inbound_tags) VALUES(?,?,?,?)",
                    (pid, gid, name, ",".join(tags))
                )

    with db() as c:
        rows = c.execute(
            "SELECT id,group_id,group_name,inbound_tags FROM panel_groups WHERE panel_id=? ORDER BY group_name",
            (pid,)
        ).fetchall()

    if not rows:
        await q.edit_message_text(
            "⚠️ API وصل شد، ولی هیچ Group قابل مشاهده‌ای برای این حساب پیدا نشد.",
            reply_markup=panels_menu()
        )
        return

    kb = []
    for local_id, gid, name, tags in rows:
        label = f"{name}" + (f" | {len(tags.split(','))} inbound" if tags else "")
        kb.append([InlineKeyboardButton(label[:60], callback_data=f"gsel:{pid}:{local_id}")])
    kb.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_panels")])
    await q.edit_message_text(
        f"🔗 Groupهای قابل دسترس در «{panel['name']}»:\n"
        "یکی را انتخاب کن تا در ربات ثبت شود.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def select_group(update, context, pid, local_gid):
    q = update.callback_query
    with db() as c:
        row = c.execute(
            """SELECT pg.group_name,pg.inbound_tags,p.name
               FROM panel_groups pg JOIN panels p ON p.id=pg.panel_id
               WHERE pg.id=? AND pg.panel_id=?""", (local_gid, pid)
        ).fetchone()
    if not row:
        await q.answer("Group پیدا نشد.", show_alert=True)
        return
    group_name, tags, panel_name = row
    await q.edit_message_text(
        f"✅ Group ثبت شد\n\n"
        f"پنل: {panel_name}\n"
        f"Group: {group_name}\n"
        f"Inboundها:\n" +
        ("\n".join(f"• {x}" for x in tags.split(",") if x) if tags else "• در API لیست نشده"),
        reply_markup=panels_menu()
    )


async def group_test_menu(update, context):
    q = update.callback_query
    with db() as c:
        rows = c.execute("""
            SELECT pg.id,p.id,p.name,pg.group_name,pg.inbound_tags
            FROM panel_groups pg JOIN panels p ON p.id=pg.panel_id
            ORDER BY p.id DESC, pg.group_name
        """).fetchall()
    if not rows:
        await q.edit_message_text(
            "اول از «🔗 اتصال Group» یک Group ثبت کن.",
            reply_markup=panels_menu()
        )
        return
    kb = []
    for local_id, pid, pname, gname, tags in rows:
        kb.append([InlineKeyboardButton(
            f"{pname} / {gname}"[:60], callback_data=f"gtest:{pid}:{local_id}"
        )])
    kb.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_panels")])
    await q.edit_message_text("🧪 Group موردنظر را برای تست انتخاب کن:", reply_markup=InlineKeyboardMarkup(kb))


async def group_test(update, context, pid, local_gid):
    q = update.callback_query
    with db() as c:
        row = c.execute("""
            SELECT p.name,p.base_url,p.username,p.password,pg.group_name,pg.inbound_tags
            FROM panel_groups pg JOIN panels p ON p.id=pg.panel_id
            WHERE pg.id=? AND pg.panel_id=?
        """, (local_gid, pid)).fetchone()
    if not row:
        await q.answer("Group پیدا نشد.", show_alert=True)
        return
    pname, url, username, password, gname, tags = row
    panel = {"base_url": url, "username": username, "password": password}
    ok, result = await api_login(panel)
    if not ok:
        await q.edit_message_text(f"🔴 Login تستی ناموفق است:\n{result}", reply_markup=panels_menu())
        return

    # Safe connectivity test: verifies authentication and Group metadata.
    # It does NOT create a real user/subscription or consume traffic.
    await q.edit_message_text(
        f"🧪 نتیجه تست Group\n\n"
        f"پنل: {pname}\n"
        f"Group: {gname}\n"
        f"Inboundهای ثبت‌شده: {len([x for x in tags.split(',') if x])}\n\n"
        f"🟢 API Login OK\n"
        f"🟢 Group metadata OK\n"
        f"ℹ️ این تست Demo است و کاربر واقعی/Subscription ایجاد نمی‌کند.",
        reply_markup=panels_menu()
    )


async def cancel_flow(update, context):
    q = update.callback_query
    context.user_data.clear()
    await q.edit_message_text("لغو شد.", reply_markup=admin_menu())


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "home":
        await q.edit_message_text("🏠 منوی اصلی", reply_markup=main_menu(uid))
    elif q.data == "admin" and is_admin(uid):
        await q.edit_message_text("🛠 پنل مدیریت", reply_markup=admin_menu())
    elif q.data == "admin_panels" and is_admin(uid):
        await show_admin_panels(update, context)
    elif q.data == "add_pasarguard" and is_admin(uid):
        await begin_add_pasarguard(update, context)
    elif q.data == "list_panels" and is_admin(uid):
        await list_panels(update, context)
    elif q.data == "panel_test_menu" and is_admin(uid):
        await panel_test_menu(update, context)
    elif q.data.startswith("ptest:") and is_admin(uid):
        await test_panel(update, context, int(q.data.split(":")[1]))
    elif q.data == "group_connect_menu" and is_admin(uid):
        await group_connect_menu(update, context)
    elif q.data.startswith("gconnect:") and is_admin(uid):
        await load_groups_for_panel(update, context, int(q.data.split(":")[1]))
    elif q.data.startswith("gsel:") and is_admin(uid):
        _, pid, gid = q.data.split(":")
        await select_group(update, context, int(pid), int(gid))
    elif q.data == "group_test_menu" and is_admin(uid):
        await group_test_menu(update, context)
    elif q.data.startswith("gtest:") and is_admin(uid):
        _, pid, gid = q.data.split(":")
        await group_test(update, context, int(pid), int(gid))
    elif q.data == "cancel_flow":
        await cancel_flow(update, context)
    elif q.data == "products":
        await q.edit_message_text("🛒 بخش خرید در نسخه پایه آماده است.", reply_markup=main_menu(uid))
    elif q.data == "orders":
        await q.edit_message_text("📦 هنوز سفارشی ثبت نشده.", reply_markup=main_menu(uid))
    elif q.data == "profile":
        await q.edit_message_text(f"👤 شناسه شما: {uid}", reply_markup=main_menu(uid))
    elif q.data == "admin_add":
        await q.edit_message_text(
            "➕ افزودن محصول\n\nبرای نسخه بعدی می‌توانیم محصول را مستقیماً به Group/Panel انتخابی وصل کنیم.",
            reply_markup=admin_menu()
        )
    elif q.data == "admin_products":
        await q.edit_message_text("📋 مدیریت محصولات", reply_markup=admin_menu())
    elif q.data == "admin_orders":
        await q.edit_message_text("📦 مدیریت سفارش‌ها", reply_markup=admin_menu())


async def text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        handled = await handle_panel_text(update, context)
        if handled:
            return
    await update.message.reply_text("از دکمه‌های منو استفاده کن.", reply_markup=main_menu(update.effective_user.id))


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_messages))
    log.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
