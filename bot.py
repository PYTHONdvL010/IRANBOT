import os
import re
import sqlite3
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}
DB_PATH = os.getenv("DB_PATH", "shop.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

PANEL_TYPES = {"marzban": "Marzban", "pasarguard": "Pasarguard", "3xui": "3x-ui"}


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
        c.execute("""CREATE TABLE IF NOT EXISTS panel_inbounds(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_id INTEGER NOT NULL,
            inbound_id TEXT,
            inbound_tag TEXT NOT NULL,
            inbound_name TEXT NOT NULL,
            UNIQUE(panel_id, inbound_tag)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS wallets(
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )""")
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
        [InlineKeyboardButton("💰 کیف پول", callback_data="wallet"),
         InlineKeyboardButton("🎁 کد تخفیف", callback_data="coupon")],
        [InlineKeyboardButton("💬 پشتیبانی", callback_data="support")],
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
        reply_markup=menu(user.id),
    )


async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        rows = c.execute("""SELECT p.id,p.name,p.price,COALESCE(pa.name,'بدون پنل')
            FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id
            WHERE p.active=1 ORDER BY p.id""").fetchall()
    if not rows:
        await q.edit_message_text("🛒 فعلاً محصولی ثبت نشده.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data="home")]]))
        return
    buttons = [[InlineKeyboardButton(f"{name} — {price}", callback_data=f"product:{pid}")] for pid, name, price, panel in rows]
    buttons.append([InlineKeyboardButton("↩️ بازگشت", callback_data="home")])
    await q.edit_message_text("🛒 پلن موردنظرت رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))


async def product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("""SELECT p.id,p.name,p.price,p.description,COALESCE(pa.name,'بدون پنل')
            FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id
            WHERE p.id=? AND p.active=1""", (pid,)).fetchone()
    if not row:
        await q.edit_message_text("محصول پیدا نشد.")
        return
    _, name, price, desc, panel = row
    await q.edit_message_text(
        f"📦 {name}\n\n{desc or 'بدون توضیحات'}\n\n💰 قیمت: {price}\n🖥 پنل: {panel}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍 ثبت سفارش", callback_data=f"order:{pid}")],
            [InlineKeyboardButton("↩️ محصولات", callback_data="products")],
        ]),
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
        oid = c.execute("INSERT INTO orders(user_id,product_id) VALUES(?,?)", (q.from_user.id, pid)).lastrowid
    await q.edit_message_text(
        f"✅ سفارش #{oid} ثبت شد.\n\nمحصول: {row[0]}\nمبلغ: {row[1]}\n\n💳 پرداخت را تکمیل کن؛ بعد از تأیید ادمین سرویس تحویل می‌شود.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
        ]),
    )


async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        rows = c.execute("""SELECT o.id,p.name,o.status FROM orders o JOIN products p ON p.id=o.product_id
            WHERE o.user_id=? ORDER BY o.id DESC LIMIT 20""", (q.from_user.id,)).fetchall()
    text = "📦 سفارش‌های تو:\n\n" + "\n".join(f"#{oid} — {name} — {status}" for oid, name, status in rows) if rows else "📦 هنوز سفارشی نداری."
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="products")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
    ]))


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        count = c.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (q.from_user.id,)).fetchone()[0]
    await q.edit_message_text(
        f"👤 پروفایل\n\nID: {q.from_user.id}\nنام کاربری: @{q.from_user.username or '-'}\nتعداد سفارش: {count}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]]),
    )


async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        row = c.execute("SELECT balance FROM wallets WHERE user_id=?", (q.from_user.id,)).fetchone()
        if not row:
            c.execute("INSERT OR IGNORE INTO wallets(user_id,balance) VALUES(?,0)", (q.from_user.id,))
            balance = 0
        else:
            balance = row[0]
    await q.edit_message_text(
        f"💰 کیف پول\n\nموجودی فعلی: {balance:,} تومان\n\n🧪 این بخش فعلاً Demo است.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]]),
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
    if not is_admin(q.from_user.id):
        return
    context.user_data["flow"] = {"type": "product", "step": "name"}
    await q.edit_message_text("➕ افزودن محصول\n\nلطفاً نام محصول را ارسال کن:", reply_markup=cancel_keyboard())


async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    with conn() as c:
        rows = c.execute("""SELECT p.id,p.name,p.price,COALESCE(pa.name,'بدون پنل')
            FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id ORDER BY p.id DESC""").fetchall()
    text = "📋 محصولات\n\n" + ("\n".join(f"#{i} — {n}\n💰 {pr}\n🖥 {pn}" for i, n, pr, pn in rows) if rows else "هنوز محصولی ثبت نشده.")
    await q.edit_message_text(text, reply_markup=admin_menu())


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    with conn() as c:
        rows = c.execute("""SELECT o.id,o.user_id,p.name,o.status FROM orders o JOIN products p ON p.id=o.product_id
            ORDER BY o.id DESC LIMIT 30""").fetchall()
    text = "📦 سفارش‌ها\n\n" + ("\n".join(f"#{oid} | user={uid} | {name} | {status}" for oid, uid, name, status in rows) if rows else "خالی")
    await q.edit_message_text(text, reply_markup=admin_menu())


# ---------------- Panel API ----------------

def panel_type_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Marzban", callback_data="paneltype:marzban")],
        [InlineKeyboardButton("Pasarguard", callback_data="paneltype:pasarguard")],
        [InlineKeyboardButton("3x-ui", callback_data="paneltype:3xui")],
        [InlineKeyboardButton("❌ لغو", callback_data="admin")],
    ])


def valid_url(value: str) -> bool:
    try:
        p = urlparse(value.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def clean_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    value = re.sub(r"/dashboard/?(?:#.*)?$", "", value, flags=re.I)
    value = re.sub(r"/#.*$", "", value)
    return value.rstrip("/")


async def panel_api_login(panel_type: str, address: str, username: str, password: str):
    base = clean_base_url(address)
    timeout = httpx.Timeout(20.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=True) as client:
        try:
            if panel_type in ("marzban", "pasarguard"):
                r = await client.post(f"{base}/api/admin/token", data={"username": username, "password": password, "grant_type": "password"})
                if r.status_code in (401, 403):
                    return False, "credentials", None
                if r.status_code >= 400:
                    return False, f"http_{r.status_code}", None
                data = r.json()
                token = data.get("access_token")
                if not token:
                    return False, "bad_response", None
                me = await client.get(f"{base}/api/admin", headers={"Authorization": f"Bearer {token}"})
                if me.status_code in (401, 403):
                    return False, "credentials", None
                if me.status_code >= 400:
                    return False, f"http_{me.status_code}", None
                return True, "ok", token

            if panel_type == "3xui":
                r = await client.post(f"{base}/login", json={"username": username, "password": password})
                if r.status_code >= 400 and r.status_code not in (401, 403):
                    r = await client.post(f"{base}/login", data={"username": username, "password": password})
                if r.status_code in (401, 403):
                    return False, "credentials", None
                if r.status_code >= 400:
                    return False, f"http_{r.status_code}", None
                if not client.cookies:
                    return False, "no_session", None
                status = await client.get(f"{base}/panel/api/server/status")
                if status.status_code in (401, 403):
                    return False, "credentials", None
                if status.status_code >= 400:
                    return False, f"http_{status.status_code}", None
                return True, "ok", client
            return False, "unsupported", None
        except httpx.ConnectError:
            return False, "connection", None
        except httpx.TimeoutException:
            return False, "timeout", None
        except (httpx.HTTPError, ValueError):
            return False, "bad_response", None


def panel_error_text(reason: str) -> str:
    return {
        "credentials": "❌ نام کاربری یا رمز عبور اشتباه است.",
        "connection": "❌ اتصال به پنل برقرار نشد. آدرس یا دسترسی شبکه را بررسی کن.",
        "timeout": "❌ زمان اتصال به پنل تمام شد.",
        "no_session": "❌ ورود انجام شد ولی session پنل دریافت نشد.",
        "bad_response": "❌ پاسخ API پنل معتبر نبود یا نسخه پنل سازگار نیست.",
        "unsupported": "❌ نوع پنل پشتیبانی نمی‌شود.",
    }.get(reason, f"❌ خطا در API پنل ({reason}).")


async def admin_panels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data.pop("flow", None)
    with conn() as c:
        rows = c.execute("SELECT id,panel_type,name,address,status FROM panels ORDER BY id DESC").fetchall()
    text = "🖥 پنل‌ها\n\n"
    if rows:
        text += "\n\n".join(f"#{i} — {name}\nنوع: {PANEL_TYPES.get(pt, pt)}\nوضعیت: {status}" for i, pt, name, address, status in rows)
    else:
        text += "هنوز پنلی ثبت نشده."
    buttons = [[InlineKeyboardButton("➕ افزودن پنل", callback_data="add_panel")]]
    for i, pt, name, address, status in rows:
        buttons.append([InlineKeyboardButton(f"📌 {PANEL_TYPES.get(pt, pt)} #{i}", callback_data=f"panel_detail:{i}")])
    buttons.append([InlineKeyboardButton("↩️ پنل مدیریت", callback_data="admin")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def add_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data["flow"] = {"type": "panel", "step": "type"}
    await q.edit_message_text("🖥 چه نوع پنلی می‌خواهی اضافه کنی؟", reply_markup=panel_type_keyboard())


async def select_panel_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pt = q.data.split(":", 1)[1]
    context.user_data["flow"] = {"type": "panel", "step": "address", "panel_type": pt}
    await q.edit_message_text(f"🖥 نوع پنل: {PANEL_TYPES[pt]}\n\nلطفاً آدرس پنل را ارسال کن.\nمثال: https://panel.example.com", reply_markup=cancel_keyboard())


async def save_panel_after_test(message, flow):
    ok, reason, _ = await panel_api_login(flow["panel_type"], flow["address"], flow["username"], flow["password"])
    if not ok:
        await message.reply_text(panel_error_text(reason), reply_markup=cancel_keyboard())
        return False
    name = f"{PANEL_TYPES[flow['panel_type']]} Panel"
    with conn() as c:
        pid = c.execute("INSERT INTO panels(panel_type,name,address,username,password,status) VALUES(?,?,?,?,?,?)",
                        (flow["panel_type"], name, clean_base_url(flow["address"]), flow["username"], flow["password"], "connected")).lastrowid
    await message.reply_text(f"✅ پنل با موفقیت ثبت شد.\n\nنوع: {PANEL_TYPES[flow['panel_type']]}\nآدرس: {clean_base_url(flow['address'])}\nوضعیت: 🟢 Connected\nشناسه: #{pid}", reply_markup=admin_menu())
    return True


async def panel_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("SELECT panel_type,name,address,status FROM panels WHERE id=?", (pid,)).fetchone()
        inbounds = c.execute("SELECT inbound_id,inbound_tag,inbound_name FROM panel_inbounds WHERE panel_id=? ORDER BY id", (pid,)).fetchall()
    if not row:
        await q.edit_message_text("❌ پنل پیدا نشد.", reply_markup=admin_menu())
        return
    pt, name, address, status = row
    text = f"🖥 {PANEL_TYPES.get(pt, pt)}\n\nنام: {name}\nآدرس: {address}\nوضعیت: {status}\n\n"
    if inbounds:
        text += "🔗 Inboundهای متصل:\n" + "\n".join(f"• {n}  [{t}]" for _, t, n in inbounds)
    else:
        text += "🔗 هنوز Inboundای ثبت نشده."
    buttons = []
    if pt == "pasarguard":
        buttons.append([InlineKeyboardButton("🔗 اتصال Inbound", callback_data=f"connect_inbound:{pid}")])
        buttons.append([InlineKeyboardButton("👤 ساخت کاربر / کانفیگ", callback_data=f"create_pg_user:{pid}")])
        buttons.append([InlineKeyboardButton("🧪 Pasarguard — تست Inbound", callback_data=f"test_inbound:{pid}")])
        buttons.append([InlineKeyboardButton("🔄 بروزرسانی Inboundها", callback_data=f"refresh_inbounds:{pid}")])
    buttons += [[InlineKeyboardButton("🧪 تست API Pasarguard" if pt == "pasarguard" else "🧪 تست اتصال", callback_data=f"test_panel:{pid}")],
                [InlineKeyboardButton("🗑 حذف پنل", callback_data=f"delete_panel:{pid}")],
                [InlineKeyboardButton("↩️ پنل‌ها", callback_data="admin_panels")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def test_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("در حال تست API...")
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("SELECT panel_type,name,address,username,password FROM panels WHERE id=?", (pid,)).fetchone()
    if not row:
        await q.edit_message_text("❌ پنل پیدا نشد.", reply_markup=admin_menu())
        return
    pt, name, address, username, password = row
    ok, reason, _ = await panel_api_login(pt, address, username, password)
    with conn() as c:
        c.execute("UPDATE panels SET status=? WHERE id=?", ("connected" if ok else "error", pid))
    if ok:
        text = f"🧪 {PANEL_TYPES.get(pt, pt)}\n\nنام: {name}\nآدرس: {address}\n\n🟢 API Login: موفق\n🔐 احراز هویت: موفق"
    else:
        text = f"🧪 {PANEL_TYPES.get(pt, pt)}\n\n{panel_error_text(reason)}"
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ جزئیات پنل", callback_data=f"panel_detail:{pid}")]]))


async def delete_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        c.execute("UPDATE products SET panel_id=NULL WHERE panel_id=?", (pid,))
        c.execute("DELETE FROM panel_inbounds WHERE panel_id=?", (pid,))
        c.execute("DELETE FROM panels WHERE id=?", (pid,))
    await q.edit_message_text("🗑 پنل حذف شد.", reply_markup=admin_menu())


# ---------------- PasarGuard inbound/user helpers ----------------
async def pg_client(panel_id: int):
    with conn() as c:
        row = c.execute("SELECT address,username,password FROM panels WHERE id=? AND panel_type='pasarguard'", (panel_id,)).fetchone()
    if not row:
        raise RuntimeError("panel_not_found")
    address, username, password = row
    base = clean_base_url(address)
    timeout = httpx.Timeout(25.0, connect=8.0)
    client = httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=True)
    try:
        r = await client.post(f"{base}/api/admin/token", data={"username": username, "password": password, "grant_type": "password"})
        r.raise_for_status()
        token = r.json().get("access_token")
        if not token:
            raise RuntimeError("bad_token")
        return client, base, {"Authorization": f"Bearer {token}"}
    except Exception:
        await client.aclose()
        raise


def extract_list(data, keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def inbound_fields(item):
    if not isinstance(item, dict):
        return None
    tag = item.get("tag") or item.get("inbound_tag") or item.get("name") or item.get("remark")
    name = item.get("name") or item.get("remark") or item.get("tag") or str(item.get("id", ""))
    iid = item.get("id")
    if tag is None:
        return None
    return str(iid) if iid is not None else "", str(tag), str(name)


async def pasarguard_inbounds(panel_id: int):
    client, base, headers = await pg_client(panel_id)
    try:
        r = await client.get(f"{base}/api/inbounds", headers=headers)
        if r.status_code in (401, 403):
            raise RuntimeError("credentials")
        r.raise_for_status()
        items = extract_list(r.json(), ["inbounds", "items", "data"])
        result = []
        for item in items:
            fields = inbound_fields(item)
            if fields:
                result.append(fields)
        return result
    finally:
        await client.aclose()


async def find_inbound(panel_id: int, query: str):
    items = await pasarguard_inbounds(panel_id)
    q = query.strip().casefold()
    exact = [x for x in items if q in (x[1].casefold(), x[2].casefold(), x[0].casefold())]
    return exact, items


async def ensure_panel_group(panel_id: int):
    """PasarGuard uses groups as the gateway to inbound tags."""
    with conn() as c:
        tags = [r[0] for r in c.execute("SELECT inbound_tag FROM panel_inbounds WHERE panel_id=? ORDER BY id", (panel_id,)).fetchall()]
    if not tags:
        raise RuntimeError("no_inbounds")
    client, base, headers = await pg_client(panel_id)
    try:
        group_name = f"botpanel{panel_id}"
        r = await client.get(f"{base}/api/groups/simple", headers=headers)
        if r.status_code in (401, 403):
            r = await client.get(f"{base}/api/groups", headers=headers)
        r.raise_for_status()
        groups = extract_list(r.json(), ["groups", "items", "data"])
        group = next((g for g in groups if str(g.get("name", "")) == group_name), None)
        payload = {"name": group_name, "inbound_tags": sorted(set(tags)), "is_disabled": False}
        if group:
            gid = group.get("id")
            ur = await client.put(f"{base}/api/group/{gid}", headers=headers, json={"inbound_tags": payload["inbound_tags"], "is_disabled": False})
            ur.raise_for_status()
            return int(gid)
        cr = await client.post(f"{base}/api/group", headers=headers, json=payload)
        cr.raise_for_status()
        data = cr.json()
        gid = data.get("id") if isinstance(data, dict) else None
        if gid is None and isinstance(data, dict) and isinstance(data.get("group"), dict):
            gid = data["group"].get("id")
        if gid is None:
            # Re-read simple groups and locate by name.
            rr = await client.get(f"{base}/api/groups/simple", headers=headers)
            rr.raise_for_status()
            groups = extract_list(rr.json(), ["groups", "items", "data"])
            group = next((g for g in groups if str(g.get("name", "")) == group_name), None)
            if not group:
                raise RuntimeError("group_create_response")
            gid = group.get("id")
        return int(gid)
    finally:
        await client.aclose()


async def pasarguard_create_user(panel_id: int, username: str, data_limit: int, expire_days: int = 1):
    group_id = await ensure_panel_group(panel_id)
    client, base, headers = await pg_client(panel_id)
    try:
        expire = (datetime.now(timezone.utc) + timedelta(days=expire_days)).replace(microsecond=0).isoformat()
        payload = {
            "username": username,
            "proxy_settings": {},
            "expire": expire,
            "data_limit": data_limit,
            "data_limit_reset_strategy": "no_reset",
            "status": "active",
            "group_ids": [group_id],
        }
        r = await client.post(f"{base}/api/user", headers=headers, json=payload)
        if r.status_code in (400, 422):
            detail = r.text[:500]
            raise RuntimeError(f"create_user:{detail}")
        r.raise_for_status()
        data = r.json()
        user = data.get("user") if isinstance(data, dict) and isinstance(data.get("user"), dict) else data
        if not isinstance(user, dict):
            raise RuntimeError("bad_user_response")
        return user, group_id
    finally:
        await client.aclose()


async def connect_inbound_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("SELECT name FROM panels WHERE id=? AND panel_type='pasarguard'", (pid,)).fetchone()
    if not row:
        await q.edit_message_text("❌ پنل Pasarguard پیدا نشد.", reply_markup=admin_menu())
        return
    context.user_data["flow"] = {"type": "connect_inbound", "step": "name", "panel_id": pid}
    await q.edit_message_text("🔗 اتصال Inbound\n\nلطفاً اسم یا Tag اینباند را ارسال کن.\nمثال: VLESS-TCP-REALITY", reply_markup=cancel_keyboard())


async def save_inbound_flow(message, context):
    flow = context.user_data.get("flow", {})
    pid = flow["panel_id"]
    query = message.text.strip()
    try:
        matches, all_items = await find_inbound(pid, query)
    except RuntimeError as e:
        reason = str(e)
        await message.reply_text("❌ دریافت Inboundها از Pasarguard ناموفق بود.\n\n" + ("احراز هویت ناموفق است." if reason == "credentials" else f"خطا: {reason}"), reply_markup=cancel_keyboard())
        return False
    if not matches:
        await message.reply_text("❌ چنین Inboundای در پنل پیدا نشد. اسم/Tag را دقیق‌تر بفرست.", reply_markup=cancel_keyboard())
        return False
    if len(matches) > 1:
        buttons = []
        for iid, tag, name in matches[:15]:
            buttons.append([InlineKeyboardButton(f"{name} [{tag}]", callback_data=f"choose_inbound:{pid}:{iid}")])
        await message.reply_text("چند Inbound پیدا شد؛ یکی را انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))
        return None
    iid, tag, name = matches[0]
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO panel_inbounds(panel_id,inbound_id,inbound_tag,inbound_name) VALUES(?,?,?,?)", (pid, iid, tag, name))
    await message.reply_text(f"✅ Inbound متصل شد.\n\nنام: {name}\nTag: {tag}\nID: {iid or '-'}\n\nاز این به بعد کاربرانی که برای این پنل ساخته شوند به Inboundهای ثبت‌شده متصل می‌شوند.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard", callback_data=f"panel_detail:{pid}")]]))
    return True


async def choose_inbound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    parts = q.data.split(":", 2)
    pid = int(parts[1])
    iid = parts[2]
    try:
        items = await pasarguard_inbounds(pid)
        found = next((x for x in items if x[0] == iid), None)
        if not found:
            await q.edit_message_text("❌ Inbound دیگر در پنل پیدا نشد.", reply_markup=admin_menu())
            return
        iid2, tag, name = found
        with conn() as c:
            c.execute("INSERT OR REPLACE INTO panel_inbounds(panel_id,inbound_id,inbound_tag,inbound_name) VALUES(?,?,?,?)", (pid, iid2, tag, name))
        await q.edit_message_text(f"✅ Inbound متصل شد.\n\nنام: {name}\nTag: {tag}\nID: {iid2 or '-'}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard", callback_data=f"panel_detail:{pid}")]]))
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در ثبت Inbound: {str(e)[:300]}", reply_markup=admin_menu())


async def refresh_inbounds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("در حال بررسی Inboundها...")
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split(":")[1])
    try:
        items = await pasarguard_inbounds(pid)
        with conn() as c:
            saved = {r[1] for r in c.execute("SELECT id,inbound_tag FROM panel_inbounds WHERE panel_id=?", (pid,)).fetchall()}
        available = {tag for _, tag, _ in items}
        stale = saved - available
        if stale:
            with conn() as c:
                for tag in stale:
                    c.execute("DELETE FROM panel_inbounds WHERE panel_id=? AND inbound_tag=?", (pid, tag))
        await q.edit_message_text(f"🔄 Inboundها بررسی شدند.\n\nتعداد موجود در پنل: {len(items)}\nتعداد ثبت‌شده: {len(saved & available)}\nموارد حذف‌شده از پنل: {len(stale)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard", callback_data=f"panel_detail:{pid}")]]))
    except Exception as e:
        await q.edit_message_text(f"❌ بروزرسانی ناموفق بود: {str(e)[:300]}", reply_markup=admin_menu())


async def create_pg_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("SELECT name FROM panels WHERE id=? AND panel_type='pasarguard'", (pid,)).fetchone()
        inbounds = c.execute("SELECT inbound_tag,inbound_name FROM panel_inbounds WHERE panel_id=? ORDER BY id", (pid,)).fetchall()
    if not row:
        await q.edit_message_text("❌ پنل Pasarguard پیدا نشد.", reply_markup=admin_menu())
        return
    if not inbounds:
        await q.edit_message_text("❌ اول حداقل یک Inbound را ثبت کن.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard", callback_data=f"panel_detail:{pid}")]]))
        return
    context.user_data["flow"] = {"type": "pg_user", "step": "username", "panel_id": pid}
    inbound_text = "\n".join(f"• {n} [{t}]" for t, n in inbounds)
    await q.edit_message_text(
        f"👤 ساخت کاربر / کانفیگ\n\nInboundهای ثبت‌شده برای این پنل:\n{inbound_text}\n\nلطفاً اسم کاربر را ارسال کن.\nمثال: test001",
        reply_markup=cancel_keyboard(),
    )


async def create_pg_user_flow(message, context):
    flow = context.user_data.get("flow", {})
    pid = flow["panel_id"]
    username = message.text.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username):
        await message.reply_text("❌ نام کاربر باید ۳ تا ۶۴ کاراکتر و فقط شامل حروف انگلیسی، عدد، _، - یا . باشد.")
        return False
    with conn() as c:
        inbounds = c.execute("SELECT inbound_tag,inbound_name FROM panel_inbounds WHERE panel_id=? ORDER BY id", (pid,)).fetchall()
    if not inbounds:
        await message.reply_text("❌ هیچ Inbound ثبت‌شده‌ای برای این پنل وجود ندارد.", reply_markup=admin_menu())
        return False
    try:
        user, group_id = await pasarguard_create_user(pid, username, 0, 30)
        sub = user.get("subscription_url") or user.get("sub_url") or user.get("subscription")
        inbound_text = "\n".join(f"• {n} [{t}]" for t, n in inbounds)
        text = f"✅ کاربر ساخته شد.\n\n👤 Username: {user.get('username', username)}\n⏳ اعتبار: ۳۰ روز\n🔗 Group ID: {group_id}\n\n🔗 Inboundهای متصل:\n{inbound_text}\n\n"
        if sub:
            text += f"🔗 Subscription:\n{sub}"
        else:
            text += "⚠️ کاربر ساخته شد ولی subscription_url در پاسخ API برنگشت."
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard", callback_data=f"panel_detail:{pid}")]]))
        return True
    except Exception as e:
        await message.reply_text(f"❌ ساخت کاربر ناموفق بود.\n\n{str(e)[:700]}", reply_markup=cancel_keyboard())
        return False


async def test_inbound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("در حال ساخت تست 1MB...")
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("SELECT name FROM panels WHERE id=? AND panel_type='pasarguard'", (pid,)).fetchone()
        inbounds = c.execute("SELECT inbound_tag,inbound_name FROM panel_inbounds WHERE panel_id=? ORDER BY id", (pid,)).fetchall()
    if not row:
        await q.edit_message_text("❌ پنل Pasarguard پیدا نشد.", reply_markup=admin_menu())
        return
    if not inbounds:
        await q.edit_message_text("❌ اول حداقل یک Inbound را با «اتصال Inbound» ثبت کن.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard", callback_data=f"panel_detail:{pid}")]]))
        return
    username = "test_" + datetime.now().strftime("%m%d%H%M%S")
    try:
        user, group_id = await pasarguard_create_user(pid, username, 1024 * 1024, 1)
        sub = user.get("subscription_url") or user.get("sub_url") or user.get("subscription")
        inbound_text = "\n".join(f"• {n} [{t}]" for t, n in inbounds)
        text = f"🧪 Pasarguard — تست Inbound\n\n👤 User: {user.get('username', username)}\n📦 حجم: 1 MB\n⏳ اعتبار: 1 روز\n🔗 Group ID: {group_id}\n\n🔗 Inboundها:\n{inbound_text}\n\n"
        if sub:
            text += f"🔗 Subscription:\n{sub}"
        else:
            text += "⚠️ کاربر ساخته شد ولی subscription_url در پاسخ API برنگشت."
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard", callback_data=f"panel_detail:{pid}")]]))
    except Exception as e:
        await q.edit_message_text(f"❌ ساخت تست 1MB ناموفق بود.\n\n{str(e)[:700]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard", callback_data=f"panel_detail:{pid}")]]))


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
            buttons = [[InlineKeyboardButton(f"#{i} {name} ({PANEL_TYPES.get(pt, pt)})", callback_data=f"product_panel:{i}")] for i, pt, name, status in panels]
            buttons.append([InlineKeyboardButton("بدون پنل", callback_data="product_panel:0")])
            await update.message.reply_text("🖥 محصول به کدام پنل متصل باشد؟", reply_markup=InlineKeyboardMarkup(buttons))
            return

    if flow["type"] == "panel":
        if flow["step"] == "address":
            if not valid_url(text):
                await update.message.reply_text("❌ آدرس معتبر نیست. با http:// یا https:// ارسال کن.")
                return
            flow["address"] = clean_base_url(text)
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
            ok = await save_panel_after_test(update.message, flow)
            if ok:
                context.user_data.pop("flow", None)
            return

    if flow["type"] == "connect_inbound" and flow["step"] == "name":
        result = await save_inbound_flow(update.message, context)
        if result is True:
            context.user_data.pop("flow", None)
        return

    if flow["type"] == "pg_user" and flow["step"] == "username":
        result = await create_pg_user_flow(update.message, context)
        if result is True:
            context.user_data.pop("flow", None)
        return


async def select_product_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
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
        pid = c.execute("INSERT INTO products(name,price,panel_id) VALUES(?,?,?)", (flow["name"], flow["price"], panel_id or None)).lastrowid
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
    if not is_admin(update.effective_user.id):
        return
    raw = update.message.text.removeprefix("/addconfig ").strip()
    parts = [x.strip() for x in raw.split("|", 1)]
    if len(parts) != 2 or not parts[0].isdigit():
        await update.message.reply_text("فرمت: /addconfig PRODUCT_ID | CONFIG")
        return
    with conn() as c:
        c.execute("INSERT INTO configs(product_id,config) VALUES(?,?)", (int(parts[0]), parts[1]))
    await update.message.reply_text("✅ کانفیگ به موجودی اضافه شد.")


async def list_products_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    with conn() as c:
        rows = c.execute("SELECT id,name,price,active FROM products ORDER BY id DESC").fetchall()
    await update.message.reply_text("📋 محصولات:\n" + ("\n".join(f"#{i} {n} — {p} — {'فعال' if a else 'غیرفعال'}" for i, n, p, a in rows) or "خالی"))


async def list_orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    with conn() as c:
        rows = c.execute("SELECT o.id,o.user_id,p.name,o.status FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT 30").fetchall()
    await update.message.reply_text("📦 سفارش‌ها:\n" + ("\n".join(f"#{oid} user={uid} {name} [{status}]" for oid, uid, name, status in rows) or "خالی"))


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id) or not context.args:
        return
    try:
        oid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ORDER_ID باید عدد باشد.")
        return
    with conn() as c:
        order = c.execute("SELECT user_id,product_id FROM orders WHERE id=?", (oid,)).fetchone()
        if not order:
            await update.message.reply_text("سفارش پیدا نشد.")
            return
        user_id, product_id = order
        cfg = c.execute("SELECT id,config FROM configs WHERE product_id=? AND delivered=0 LIMIT 1", (product_id,)).fetchone()
        if not cfg:
            await update.message.reply_text("❌ برای این محصول کانفیگ موجود نیست.")
            return
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
    if data.startswith("panel_detail:"): return await panel_detail(update, context)
    if data.startswith("test_panel:"): return await test_panel(update, context)
    if data.startswith("delete_panel:"): return await delete_panel(update, context)
    if data.startswith("connect_inbound:"): return await connect_inbound_start(update, context)
    if data.startswith("create_pg_user:"): return await create_pg_user_start(update, context)
    if data.startswith("choose_inbound:"): return await choose_inbound(update, context)
    if data.startswith("refresh_inbounds:"): return await refresh_inbounds(update, context)
    if data.startswith("test_inbound:"): return await test_inbound(update, context)
    if data.startswith("product_panel:"): return await select_product_panel(update, context)
    if data == "admin_products": return await admin_products(update, context)
    if data == "admin_orders": return await admin_orders(update, context)
    if data == "wallet": return await wallet(update, context)
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
