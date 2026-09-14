import os
import re
import json
from urllib.parse import urljoin
import sqlite3
import threading
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
        c.execute("""CREATE TABLE IF NOT EXISTS panel_groups(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_id INTEGER NOT NULL,
            group_id INTEGER,
            group_name TEXT NOT NULL,
            inbound_tags TEXT DEFAULT '',
            UNIQUE(panel_id, group_id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS wallets(
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '', first_name TEXT DEFAULT '',
            is_blocked INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            order_id INTEGER,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            photo_file_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS support_tickets(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, admin_id INTEGER,
            message TEXT DEFAULT '', photo_file_id TEXT DEFAULT '', status TEXT DEFAULT 'open',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS free_test_settings(
            panel_id INTEGER PRIMARY KEY, max_tests INTEGER DEFAULT 1, data_limit_mb INTEGER DEFAULT 100,
            expire_hours INTEGER DEFAULT 1, enabled INTEGER DEFAULT 1
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS free_test_usage(
            user_id INTEGER NOT NULL, panel_id INTEGER NOT NULL, used_count INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, panel_id)
        )""")
        cols = {r[1] for r in c.execute("PRAGMA table_info(products)").fetchall()}
        if "panel_id" not in cols:
            c.execute("ALTER TABLE products ADD COLUMN panel_id INTEGER")
        cols = {r[1] for r in c.execute("PRAGMA table_info(products)").fetchall()}
        if "data_limit_gb" not in cols:
            c.execute("ALTER TABLE products ADD COLUMN data_limit_gb INTEGER DEFAULT 1")
        if "expire_days" not in cols:
            c.execute("ALTER TABLE products ADD COLUMN expire_days INTEGER DEFAULT 1")
        order_cols = {r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()}
        if "subscription" not in order_cols:
            c.execute("ALTER TABLE orders ADD COLUMN subscription TEXT DEFAULT ''")
        if "panel_username" not in order_cols:
            c.execute("ALTER TABLE orders ADD COLUMN panel_username TEXT DEFAULT ''")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def menu(user_id: int):
    buttons = [
        [InlineKeyboardButton("🛒 خرید سرویس", callback_data="products")],
        [InlineKeyboardButton("📦 سفارش‌های من", callback_data="orders"),
         InlineKeyboardButton("👤 حساب من", callback_data="profile")],
        [InlineKeyboardButton("💰 کیف پول", callback_data="wallet"),
         InlineKeyboardButton("🎁 کد تخفیف", callback_data="coupon")],
        [InlineKeyboardButton("🎁 تست رایگان", callback_data="free_test")],
        [InlineKeyboardButton("💬 پشتیبانی", callback_data="support")],
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton("🛠 پنل مدیریت", callback_data="admin")])
    return InlineKeyboardMarkup(buttons)


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن محصول", callback_data="admin_add")],
        [InlineKeyboardButton("👋 پیام خوش‌آمد", callback_data="admin_welcome")],
        [InlineKeyboardButton("📢 عضویت اجباری", callback_data="admin_mandatory")],
        [InlineKeyboardButton("💳 بخش مالی", callback_data="admin_finance")],
        [InlineKeyboardButton("🖥 پنل‌ها", callback_data="admin_panels")],
        [InlineKeyboardButton("📋 محصولات", callback_data="admin_products")],
        [InlineKeyboardButton("📦 سفارش‌ها", callback_data="admin_orders")],
        [InlineKeyboardButton("👥 کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
    ])


def cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="admin")]])

def user_cancel_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="cancel_user")]])


def render_welcome(user):
    template = get_setting_sync("welcome_message") or "سلام {username} 👋\n\nبه IRANBOT خوش اومدی."
    values = {
        "username": user.first_name or user.username or str(user.id),
        "first_name": user.first_name or "",
        "user_id": user.id,
    }
    try:
        return template.format(**values)
    except Exception:
        return template

def get_setting_sync(key):
    with conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else ""

def get_mandatory_channels():
    raw=get_setting_sync("mandatory_channels")
    if raw:
        try:
            data=json.loads(raw)
            if isinstance(data,list): return data
        except Exception: pass
    cid=get_setting_sync("mandatory_channel_id")
    if cid:
        return [{"id":cid,"title":get_setting_sync("mandatory_channel_title") or "کانال ما","link":get_setting_sync("mandatory_channel_link") or ""}]
    return []

def save_mandatory_channels(channels):
    payload=json.dumps(channels,ensure_ascii=False)
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('mandatory_channels',?)",(payload,))
        if channels:
            first=channels[0]
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('mandatory_channel_id',?)",(str(first.get("id","")),))
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('mandatory_channel_title',?)",(str(first.get("title","کانال ما")),))
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('mandatory_channel_link',?)",(str(first.get("link","")),))

async def mandatory_status(context,user_id:int):
    if is_admin(user_id): return True
    if get_setting_sync("mandatory_enabled")!="1": return True
    channels=get_mandatory_channels()
    if not channels: return True
    for channel in channels:
        try:
            member=await context.bot.get_chat_member(chat_id=channel.get("id"),user_id=user_id)
            if member.status not in ("member","administrator","creator"): return False
        except Exception: return False
    return True

async def membership_gate(update:Update,context:ContextTypes.DEFAULT_TYPE):
    user=update.effective_user
    if not user or await mandatory_status(context,user.id): return True
    channels=get_mandatory_channels(); buttons=[]
    for i,ch in enumerate(channels,1):
        link=ch.get("link") or ""; title=ch.get("title") or f"کانال {i}"
        if link: buttons.append([InlineKeyboardButton(f"📢 عضویت در {title}",url=link)])
    buttons.append([InlineKeyboardButton("✅ عضو شدم / بررسی همه کانال‌ها",callback_data="check_membership")])
    titles="\n".join(f"• {c.get('title') or 'کانال'}" for c in channels)
    text=f"⛔️ برای استفاده از ربات ابتدا باید در همه کانال‌های زیر عضو شوی:\n\n{titles}\n\nبعد از عضویت در همه، روی «عضو شدم / بررسی همه کانال‌ها» بزن."
    if update.callback_query:
        await update.callback_query.answer(); await update.callback_query.edit_message_text(text,reply_markup=InlineKeyboardMarkup(buttons))
    elif update.message:
        await update.message.reply_text(text,reply_markup=InlineKeyboardMarkup(buttons))
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("flow", None)
    if not await membership_gate(update, context):
        return
    user = update.effective_user
    with conn() as c:
        c.execute("INSERT INTO users(user_id,username,first_name,last_seen) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name, last_seen=CURRENT_TIMESTAMP", (user.id, user.username or "", user.first_name or ""))
    if with_block := False:
        return
    with conn() as c:
        blocked=c.execute("SELECT is_blocked FROM users WHERE user_id=?",(user.id,)).fetchone()
    if blocked and blocked[0]:
        return
    await update.message.reply_text(render_welcome(user), reply_markup=menu(user.id))


async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        rows = c.execute("""SELECT p.id,p.name,p.price,p.data_limit_gb,p.expire_days,COALESCE(pa.name,'بدون پنل')
            FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id
            WHERE p.active=1 ORDER BY p.id""").fetchall()
    if not rows:
        await q.edit_message_text("🛒 فعلاً محصولی ثبت نشده.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بازگشت", callback_data="home")]]))
        return
    buttons = [[InlineKeyboardButton(f"{name} — {price} | {gb or 1}GB/{days or 1}روز", callback_data=f"product:{pid}")] for pid, name, price, gb, days, panel in rows]
    buttons.append([InlineKeyboardButton("↩️ بازگشت", callback_data="home")])
    await q.edit_message_text("🛒 پلن موردنظرت رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))


async def product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("""SELECT p.id,p.name,p.price,p.description,p.data_limit_gb,p.expire_days,COALESCE(pa.name,'بدون پنل')
            FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id
            WHERE p.id=? AND p.active=1""", (pid,)).fetchone()
    if not row:
        await q.edit_message_text("محصول پیدا نشد.")
        return
    _, name, price, desc, gb, days, panel = row
    await q.edit_message_text(
        f"📦 {name}\n\n{desc or 'بدون توضیحات'}\n\n💰 قیمت: {price}\n📦 حجم: {gb or 1} GB\n⏳ اعتبار: {days or 1} روز\n🖥 پنل: {panel}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍 ثبت سفارش", callback_data=f"order:{pid}")],
            [InlineKeyboardButton("↩️ محصولات", callback_data="products")],
        ]),
    )


async def create_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); pid=int(q.data.split(":")[1])
    with conn() as c:
        row=c.execute("SELECT id,name,price,panel_id,data_limit_gb,expire_days FROM products WHERE id=? AND active=1",(pid,)).fetchone()
        if not row: await q.edit_message_text("محصول دیگر موجود نیست."); return
        oid=c.execute("INSERT INTO orders(user_id,product_id,status) VALUES(?,?,?)",(q.from_user.id,pid,"awaiting_payment")).lastrowid
        w=c.execute("SELECT balance FROM wallets WHERE user_id=?",(q.from_user.id,)).fetchone()
    name,price,gb,days=row[1],row[2],row[4] or 1,row[5] or 1; amount=int(re.sub(r"\D","",str(price)) or 0); balance=w[0] if w else 0
    await q.edit_message_text(f"📦 سفارش #{oid}\n\nمحصول: {name}\n📦 حجم: {gb} GB\n⏳ اعتبار: {days} روز\n💰 مبلغ: {price}\n\nروش پرداخت را انتخاب کن:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 پرداخت مستقیم",callback_data=f"pay_direct:{oid}")],[InlineKeyboardButton(f"💰 پرداخت از کیف پول (موجودی {balance:,})",callback_data=f"pay_wallet:{oid}")],[InlineKeyboardButton("↩️ محصولات",callback_data="products")]]))


async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    with conn() as c:
        rows=c.execute("""SELECT o.id,p.name,o.status,o.subscription,p.data_limit_gb,p.expire_days
            FROM orders o JOIN products p ON p.id=o.product_id
            WHERE o.user_id=? AND o.status='paid' ORDER BY o.id DESC LIMIT 20""",(q.from_user.id,)).fetchall()
    if not rows:
        text="📦 هنوز سرویس فعالی در سفارش‌های تو ثبت نشده."
        buttons=[[InlineKeyboardButton("🛒 خرید سرویس",callback_data="products")],[InlineKeyboardButton("🏠 منوی اصلی",callback_data="home")]]
    else:
        text="📦 سرویس‌های من:\n\nهر سرویس را برای دیدن لینک و مشخصات بزن:"
        buttons=[[InlineKeyboardButton(f"📦 #{oid} — {name} | {gb or 1}GB/{days or 1}روز",callback_data=f"service:{oid}")] for oid,name,status,sub,gb,days in rows]
        buttons += [[InlineKeyboardButton("🛒 خرید سرویس",callback_data="products")],[InlineKeyboardButton("🏠 منوی اصلی",callback_data="home")]]
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup(buttons))

async def service_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); oid=int(q.data.split(":")[1])
    with conn() as c:
        row=c.execute("""SELECT o.id,p.name,o.status,o.subscription,o.panel_username,p.price,p.data_limit_gb,p.expire_days
            FROM orders o JOIN products p ON p.id=o.product_id WHERE o.id=? AND o.user_id=? AND o.status='paid'""",(oid,q.from_user.id)).fetchone()
    if not row:
        await q.edit_message_text("❌ سرویس پیدا نشد.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 سرویس‌های من",callback_data="orders")]])); return
    oid,name,status,sub,username,price,gb,days=row
    text=f"📦 سرویس #{oid}\n\nنام: {name}\n📦 حجم: {gb or 1} GB\n⏳ اعتبار: {days or 1} روز\n💰 مبلغ: {price}\n👤 Username: {username or '-'}\n\n🔗 Subscription:\n{sub or 'لینک موجود نیست.'}"
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 سرویس‌های من",callback_data="orders")],[InlineKeyboardButton("🏠 منوی اصلی",callback_data="home")]]))


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with conn() as c:
        count = c.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (q.from_user.id,)).fetchone()[0]
    await q.edit_message_text(
        f"👤 پروفایل\n\nID: {q.from_user.id}\nنام کاربری: @{q.from_user.username or '-'}\nتعداد سفارش: {count}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]]),
    )


async def get_setting(key):
    with conn() as c: row=c.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
    return row[0] if row else ""


async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    with conn() as c:
        row=c.execute("SELECT balance FROM wallets WHERE user_id=?",(q.from_user.id,)).fetchone()
        if not row: c.execute("INSERT OR IGNORE INTO wallets(user_id,balance) VALUES(?,0)",(q.from_user.id,)); balance=0
        else: balance=row[0]
    card=await get_setting("card_number"); owner=await get_setting("card_owner")
    card_text=f"\n\n💳 کارت شارژ: {card}\n👤 به نام: {owner}" if card and owner else ""
    await q.edit_message_text(f"💰 کیف پول\n\nموجودی فعلی: {balance:,} تومان{card_text}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ افزایش موجودی",callback_data="wallet_topup")],[InlineKeyboardButton("🏠 منوی اصلی",callback_data="home")]]))


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    context.user_data.pop("flow", None)
    await q.edit_message_text("🛠 پنل مدیریت\n\nیک بخش را انتخاب کن:", reply_markup=admin_menu())


async def admin_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    context.user_data["flow"]={"type":"product","step":"name"}
    await q.edit_message_text("➕ افزودن محصول\n\nلطفاً نام محصول را ارسال کن:",reply_markup=cancel_keyboard())


async def admin_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    cur=get_setting_sync("welcome_message") or "سلام {username} 👋\n\nبه IRANBOT خوش اومدی."
    context.user_data["flow"]={"type":"welcome_admin"}
    await q.edit_message_text(f"👋 پیام خوش‌آمد\n\nپیام خوش‌آمدت را بنویس.\n\nمتغیرها:\n{{username}} = نام خوانده‌شده کاربر\n{{first_name}} = نام\n{{user_id}} = آیدی عددی\n\nپیام فعلی:\n{cur}",reply_markup=cancel_keyboard())

async def admin_mandatory(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    channels=get_mandatory_channels(); lines=["📢 عضویت اجباری","","کانال‌های فعلی:"]
    if channels:
        for i,ch in enumerate(channels,1): lines.append(f"{i}. {ch.get('title') or 'بدون عنوان'} — {ch.get('id')}")
    else: lines.append("هنوز کانالی ثبت نشده.")
    buttons=[[InlineKeyboardButton("➕ افزودن کانال",callback_data="mandatory_add")]]
    for i,ch in enumerate(channels): buttons.append([InlineKeyboardButton(f"🗑 حذف {ch.get('title') or ch.get('id')}",callback_data=f"mandatory_del:{i}")])
    buttons.append([InlineKeyboardButton("🔛 فعال" if get_setting_sync("mandatory_enabled")=="1" else "🔴 خاموش",callback_data="mandatory_toggle")])
    buttons.append([InlineKeyboardButton("↩️ بازگشت",callback_data="admin")])
    await q.edit_message_text("\n".join(lines)+"\n\nاول ربات را با دسترسی‌های لازم ادمین همه کانال‌ها کن.",reply_markup=InlineKeyboardMarkup(buttons))

async def mandatory_add_start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    context.user_data["flow"]={"type":"mandatory_admin","step":"channel_id"}
    await q.edit_message_text("➕ افزودن کانال عضویت اجباری\n\nاول ربات را با دسترسی‌های لازم ادمین کانال کن، سپس ID عددی یا @username کانال را بفرست.",reply_markup=cancel_keyboard())

async def mandatory_delete(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    try: idx=int(q.data.split(":")[1])
    except Exception: return
    channels=get_mandatory_channels()
    if 0<=idx<len(channels):
        removed=channels.pop(idx); save_mandatory_channels(channels)
        if not channels:
            with conn() as c: c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('mandatory_enabled','0')")
        await q.answer(f"{removed.get('title') or 'کانال'} حذف شد.",show_alert=True)
    await admin_mandatory(update,context)

async def mandatory_toggle(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    enabled=get_setting_sync("mandatory_enabled")=="1"
    with conn() as c: c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('mandatory_enabled',?)",("0" if enabled else "1",))
    await admin_mandatory(update,context)

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer("در حال بررسی...")
    if await mandatory_status(context,q.from_user.id):
        await q.edit_message_text(render_welcome(q.from_user),reply_markup=menu(q.from_user.id))
    else:
        await membership_gate(update,context)

async def admin_finance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    card=await get_setting("card_number"); owner=await get_setting("card_owner")
    with conn() as c: pending=c.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0]
    await q.edit_message_text(f"💳 بخش مالی\n\n💳 شماره کارت: {card or 'ثبت نشده'}\n👤 صاحب کارت: {owner or 'ثبت نشده'}\n\n⏳ پرداخت‌های در انتظار: {pending}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ ثبت/تغییر شماره کارت",callback_data="finance_card")],[InlineKeyboardButton("📋 پرداخت‌های در انتظار",callback_data="finance_pending")],[InlineKeyboardButton("↩️ پنل مدیریت",callback_data="admin")]]))


async def finance_card_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    context.user_data["flow"]={"type":"finance_card","step":"card"}
    await q.edit_message_text("💳 شماره کارتت را ارسال کن:",reply_markup=cancel_keyboard())


async def finance_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    with conn() as c: rows=c.execute("SELECT id,user_id,kind,order_id,amount FROM payments WHERE status='pending' ORDER BY id DESC LIMIT 30").fetchall()
    text="📋 پرداخت‌های در انتظار:\n\n"+"\n".join(f"#{i} | user={uid} | {'خرید' if kind=='order' else 'شارژ'} | {amount:,} تومان | order={oid or '-'}" for i,uid,kind,oid,amount in rows) if rows else "📋 پرداخت در انتظاری وجود ندارد."
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ بخش مالی",callback_data="admin_finance")]]))


async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    with conn() as c:
        rows=c.execute("SELECT p.id,p.name,p.price,p.data_limit_gb,p.expire_days,COALESCE(pa.name,'بدون پنل') FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id ORDER BY p.id DESC").fetchall()
    buttons=[]
    for i,n,pr,gb,days,pn in rows:
        buttons.append([InlineKeyboardButton(f"🗑 حذف #{i} {n}"[:60],callback_data=f"delete_product:{i}")])
    buttons.append([InlineKeyboardButton("↩️ پنل مدیریت",callback_data="admin")])
    text="📋 محصولات\n\n"+("\n".join(f"#{i} — {n}\n💰 {pr}\n📦 {gb or 1} GB | ⏳ {days or 1} روز\n🖥 {pn}" for i,n,pr,gb,days,pn in rows) if rows else "هنوز محصولی ثبت نشده.")
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup(buttons))

async def delete_product(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    pid=int(q.data.split(':')[1])
    with conn() as c:
        used=c.execute("SELECT COUNT(*) FROM orders WHERE product_id=?",(pid,)).fetchone()[0]
        if used:
            c.execute("UPDATE products SET active=0 WHERE id=?",(pid,))
            msg="⚠️ محصول سفارش داشته؛ به‌جای حذف کامل غیرفعال شد."
        else:
            c.execute("DELETE FROM products WHERE id=?",(pid,)); c.execute("DELETE FROM configs WHERE product_id=?",(pid,)); msg="✅ محصول حذف شد."
    await q.answer(msg,show_alert=True); await admin_products(update,context)

async def admin_users(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    with conn() as c: rows=c.execute("SELECT user_id,username,first_name,is_blocked FROM users ORDER BY last_seen DESC LIMIT 100").fetchall()
    buttons=[]
    for uid,un,fn,blocked in rows:
        label=f"👤 {fn or '-'} @{un}" if un else f"👤 {fn or uid}"
        buttons.append([InlineKeyboardButton(label[:55],callback_data=f"user_manage:{uid}")])
    buttons.append([InlineKeyboardButton("↩️ پنل مدیریت",callback_data="admin")])
    text="👥 کاربران\n\n"+ ("\n".join(f"• {uid} | @{un or '-'} | {fn or '-'} | {'🚫' if blocked else '✅'}" for uid,un,fn,blocked in rows) if rows else "کاربری ثبت نشده.")
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup(buttons))

async def user_manage(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    uid=int(q.data.split(':')[1])
    with conn() as c:
        u=c.execute("SELECT user_id,username,first_name,is_blocked FROM users WHERE user_id=?",(uid,)).fetchone()
        bal=c.execute("SELECT balance FROM wallets WHERE user_id=?",(uid,)).fetchone()
        orders_count=c.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='paid'",(uid,)).fetchone()[0]
    if not u: await q.edit_message_text("❌ کاربر پیدا نشد.",reply_markup=admin_menu()); return
    text=f"👤 مدیریت کاربر\n\nID: {u[0]}\nUsername: @{u[1] or '-'}\nنام: {u[2] or '-'}\n💰 موجودی: {(bal[0] if bal else 0):,} تومان\n📦 سفارش‌های تأییدشده: {orders_count}\nوضعیت: {'🚫 مسدود' if u[3] else '✅ فعال'}"
    kb=[[InlineKeyboardButton("➕ افزایش موجودی",callback_data=f"user_add_balance:{uid}"),InlineKeyboardButton("➖ کاهش موجودی",callback_data=f"user_sub_balance:{uid}")],[InlineKeyboardButton("📦 مشاهده سفارش‌ها",callback_data=f"user_orders:{uid}")],[InlineKeyboardButton("🚫 حذف/مسدود کاربر" if not u[3] else "✅ رفع مسدودی",callback_data=f"user_block:{uid}")],[InlineKeyboardButton("↩️ کاربران",callback_data="admin_users")]]
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup(kb))

async def user_balance_start(update,context):
    q=update.callback_query; await q.answer(); uid=int(q.data.split(':')[1]); action=q.data.split(':')[0]
    if not is_admin(q.from_user.id): return
    context.user_data['flow']={'type':'user_balance','user_id':uid,'action':'add' if action.endswith('add_balance') else 'sub'}
    await q.edit_message_text(("➕" if action.endswith('add_balance') else "➖")+" مبلغ را به تومان وارد کن:",reply_markup=cancel_keyboard())

async def user_block(update,context):
    q=update.callback_query; await q.answer(); uid=int(q.data.split(':')[1])
    if not is_admin(q.from_user.id): return
    with conn() as c:
        row=c.execute("SELECT is_blocked FROM users WHERE user_id=?",(uid,)).fetchone(); val=0 if row and row[0] else 1
        c.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(uid,)); c.execute("UPDATE users SET is_blocked=? WHERE user_id=?",(val,uid))
    await user_manage(update,context)

async def user_orders(update,context):
    q=update.callback_query; await q.answer(); uid=int(q.data.split(':')[1])
    if not is_admin(q.from_user.id): return
    with conn() as c: rows=c.execute("SELECT o.id,p.name,o.status,o.subscription,o.created_at FROM orders o JOIN products p ON p.id=o.product_id WHERE o.user_id=? AND o.status='paid' ORDER BY o.id DESC",(uid,)).fetchall()
    text="📦 سفارش‌های تأییدشده\n\n"+ ("\n".join(f"#{oid} | {name} | {status}\n{sub or '-'}" for oid,name,status,sub,dt in rows) if rows else "سفارشی وجود ندارد.")
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ مدیریت کاربر",callback_data=f"user_manage:{uid}")]]))


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
        groups = c.execute("SELECT group_id,group_name,inbound_tags FROM panel_groups WHERE panel_id=? ORDER BY id", (pid,)).fetchall()
    if not row:
        await q.edit_message_text("❌ پنل پیدا نشد.", reply_markup=admin_menu())
        return
    pt, name, address, status = row
    text = f"🖥 {PANEL_TYPES.get(pt, pt)}\n\nنام: {name}\nآدرس: {address}\nوضعیت: {status}\n\n"
    if groups:
        text += "🔗 Groupهای ثبت‌شده:\n"
        for gid, gname, tags in groups:
            tags_list = [x for x in tags.split(",") if x]
            text += f"• {gname} [ID: {gid or '-'}]"
            if tags_list:
                text += "\n  Inboundها: " + ", ".join(tags_list)
            text += "\n"
    else:
        text += "🔗 هنوز Groupای ثبت نشده.\n"
    buttons = []
    for gid, gname, tags in groups:
        if gid is not None:
            buttons.append([InlineKeyboardButton(f"🗑 حذف Group: {gname}"[:60], callback_data=f"delete_group:{pid}:{gid}")])
    if pt == "pasarguard":
        buttons.append([InlineKeyboardButton("🔗 اتصال Group", callback_data=f"connect_group:{pid}")])
        buttons.append([InlineKeyboardButton("👤 ساخت کاربر / کانفیگ", callback_data=f"create_pg_user:{pid}")])
        buttons.append([InlineKeyboardButton("🧪 Pasarguard — تست Group", callback_data=f"test_group:{pid}")])
        buttons.append([InlineKeyboardButton("🎁 تنظیم تست رایگان کاربران", callback_data=f"free_test_settings:{pid}")])
        buttons.append([InlineKeyboardButton("🔄 بروزرسانی Groupها", callback_data=f"refresh_groups:{pid}")])
    buttons += [
        [InlineKeyboardButton("🧪 تست API Pasarguard" if pt == "pasarguard" else "🧪 تست اتصال", callback_data=f"test_panel:{pid}")],
        [InlineKeyboardButton("🗑 حذف پنل", callback_data=f"delete_panel:{pid}")],
        [InlineKeyboardButton("↩️ پنل‌ها", callback_data="admin_panels")]
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def delete_group(update, context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    _,pid,gid=q.data.split(":",2); pid=int(pid)
    with conn() as c: c.execute("DELETE FROM panel_groups WHERE panel_id=? AND group_id=?",(pid,int(gid)))
    await q.answer("✅ Group حذف شد.",show_alert=True); await panel_detail(update,context)

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
    text = (f"🧪 {PANEL_TYPES.get(pt, pt)}\n\nنام: {name}\nآدرس: {address}\n\n🟢 API Login: موفق\n🔐 احراز هویت: موفق"
            if ok else f"🧪 {PANEL_TYPES.get(pt, pt)}\n\n{panel_error_text(reason)}")
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ جزئیات پنل", callback_data=f"panel_detail:{pid}")]]))


async def delete_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        c.execute("UPDATE products SET panel_id=NULL WHERE panel_id=?", (pid,))
        c.execute("DELETE FROM panel_groups WHERE panel_id=?", (pid,))
        c.execute("DELETE FROM panels WHERE id=?", (pid,))
    await q.edit_message_text("🗑 پنل حذف شد.", reply_markup=admin_menu())


# ---------------- PasarGuard Group helpers ----------------
async def pg_client(panel_id: int):
    with conn() as c:
        row = c.execute("SELECT address,username,password FROM panels WHERE id=? AND panel_type='pasarguard'", (panel_id,)).fetchone()
    if not row:
        raise RuntimeError("panel_not_found")
    address, username, password = row
    base = clean_base_url(address)
    client = httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=8.0), follow_redirects=True, verify=True)
    try:
        r = await client.post(f"{base}/api/admin/token", data={"username": username, "password": password, "grant_type": "password"})
        if r.status_code in (401,403):
            raise RuntimeError("credentials")
        r.raise_for_status()
        token = r.json().get("access_token")
        if not token:
            raise RuntimeError("bad_token")
        return client, base, {"Authorization": f"Bearer {token}"}
    except Exception:
        await client.aclose()
        raise


def full_subscription_url(base_url: str, subscription: str):
    """Return a usable absolute subscription URL.

    PasarGuard may return only a relative path such as /sub/<token>.
    In that case the panel base URL must be prepended so Telegram users
    receive a directly usable link.
    """
    if not subscription:
        return subscription
    value = str(subscription).strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    base = clean_base_url(base_url).rstrip("/") + "/"
    return urljoin(base, value.lstrip("/"))


def extract_list(data, keys):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list): return value
    return []


def group_fields(item):
    if not isinstance(item, dict): return None
    gid = item.get("id") or item.get("group_id")
    name = item.get("name") or item.get("group_name") or item.get("tag")
    tags = item.get("inbound_tags") or []
    if isinstance(tags, str): tags = [x.strip() for x in tags.split(",") if x.strip()]
    if not name: return None
    return (int(gid) if str(gid).isdigit() else gid, str(name), [str(x) for x in tags])


async def pasarguard_groups(panel_id: int):
    client, base, headers = await pg_client(panel_id)
    try:
        # Operators may only have access to /simple; sudo admins can use /groups.
        r = await client.get(f"{base}/api/groups", headers=headers)
        if r.status_code in (401,403):
            r = await client.get(f"{base}/api/groups/simple", headers=headers)
        if r.status_code in (401,403):
            raise RuntimeError("groups_permission")
        r.raise_for_status()
        return [x for x in (group_fields(i) for i in extract_list(r.json(), ["groups","items","data"])) if x]
    finally:
        await client.aclose()


async def refresh_group_snapshot(panel_id: int):
    groups = await pasarguard_groups(panel_id)
    with conn() as c:
        # Keep groups that were saved even if simple API does not return tags.
        existing = {r[0]: r[1:] for r in c.execute("SELECT group_id,group_name,inbound_tags FROM panel_groups WHERE panel_id=?", (panel_id,)).fetchall()}
        for gid, name, tags in groups:
            old = existing.get(gid)
            saved_tags = ",".join(tags) if tags else (old[1] if old else "")
            c.execute("INSERT OR REPLACE INTO panel_groups(panel_id,group_id,group_name,inbound_tags) VALUES(?,?,?,?)", (panel_id, gid, name, saved_tags))
    return groups


async def connect_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("در حال دریافت Groupها...")
    if not is_admin(q.from_user.id): return
    pid = int(q.data.split(":")[1])
    with conn() as c:
        row = c.execute("SELECT name FROM panels WHERE id=? AND panel_type='pasarguard'", (pid,)).fetchone()
    if not row:
        await q.edit_message_text("❌ پنل Pasarguard پیدا نشد.", reply_markup=admin_menu()); return
    try:
        groups = await refresh_group_snapshot(pid)
    except Exception as e:
        msg = str(e)
        friendly = "این حساب اجازه مشاهده Groupها را ندارد." if msg == "groups_permission" else f"خطا در دریافت Groupها: {msg[:300]}"
        await q.edit_message_text("❌ " + friendly, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ جزئیات پنل", callback_data=f"panel_detail:{pid}")]])); return
    if not groups:
        await q.edit_message_text("⚠️ هیچ Group قابل دسترسی پیدا نشد.", reply_markup=admin_menu()); return
    buttons=[]
    for gid,name,tags in groups:
        label=f"{name} [ID:{gid}]" if gid is not None else name
        buttons.append([InlineKeyboardButton(label[:60], callback_data=f"choose_group:{pid}:{gid}")])
    buttons.append([InlineKeyboardButton("↩️ جزئیات پنل", callback_data=f"panel_detail:{pid}")])
    await q.edit_message_text(f"🔗 Groupهای قابل دسترس در {row[0]}:\nیکی را انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))


async def choose_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    _, pid_s, gid_s = q.data.split(":", 2)
    pid=int(pid_s)
    try: gid=int(gid_s)
    except ValueError: gid=gid_s
    try:
        groups=await pasarguard_groups(pid)
        found=next((g for g in groups if str(g[0])==str(gid)), None)
        if not found:
            await q.edit_message_text("❌ Group دیگر در API پیدا نشد.", reply_markup=admin_menu()); return
        gid2,name,tags=found
        with conn() as c:
            c.execute("INSERT OR REPLACE INTO panel_groups(panel_id,group_id,group_name,inbound_tags) VALUES(?,?,?,?)", (pid,gid2,name,",".join(tags)))
        tag_text="\n".join(f"• {x}" for x in tags) if tags else "• جزئیات inbound برای این API client قابل مشاهده نیست."
        await q.edit_message_text(f"✅ Group ثبت شد.\n\nنام: {name}\nID: {gid2}\n\nInboundهای قابل مشاهده:\n{tag_text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard", callback_data=f"panel_detail:{pid}")]]))
    except Exception as e:
        await q.edit_message_text(f"❌ خطا در ثبت Group: {str(e)[:400]}", reply_markup=admin_menu())


async def refresh_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    await q.answer("در حال بروزرسانی...")
    if not is_admin(q.from_user.id): return
    pid=int(q.data.split(":")[1])
    try:
        groups=await refresh_group_snapshot(pid)
        await q.edit_message_text(f"🔄 Groupها بروزرسانی شدند.\n\nتعداد Groupهای قابل دسترس: {len(groups)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ جزئیات پنل", callback_data=f"panel_detail:{pid}")]]))
    except Exception as e:
        await q.edit_message_text(f"❌ بروزرسانی ناموفق: {str(e)[:400]}", reply_markup=admin_menu())


async def selected_groups_for_panel(pid):
    with conn() as c:
        return c.execute("SELECT group_id,group_name,inbound_tags FROM panel_groups WHERE panel_id=? ORDER BY id", (pid,)).fetchall()


async def pasarguard_create_user(panel_id: int, username: str, data_limit: int, expire_days: int = 30):
    groups=await selected_groups_for_panel(panel_id)
    group_ids=[g[0] for g in groups if g[0] is not None]
    if not group_ids: raise RuntimeError("no_groups")
    client,base,headers=await pg_client(panel_id)
    try:
        expire=(datetime.now(timezone.utc)+timedelta(days=expire_days)).replace(microsecond=0).isoformat()
        payload={"username":username,"proxy_settings":{},"expire":expire,"data_limit":data_limit,"data_limit_reset_strategy":"no_reset","status":"active","group_ids":group_ids}
        r=await client.post(f"{base}/api/user",headers=headers,json=payload)
        if r.status_code in (400,422): raise RuntimeError(f"create_user:{r.text[:500]}")
        r.raise_for_status()
        data=r.json(); user=data.get("user") if isinstance(data,dict) and isinstance(data.get("user"),dict) else data
        if not isinstance(user,dict): raise RuntimeError("bad_user_response")
        return user,group_ids
    finally:
        await client.aclose()


async def create_pg_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    pid=int(q.data.split(":")[1]); groups=await selected_groups_for_panel(pid)
    if not groups:
        await q.edit_message_text("❌ اول حداقل یک Group را از «اتصال Group» ثبت کن.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard",callback_data=f"panel_detail:{pid}")]])); return
    context.user_data["flow"]={"type":"pg_user","step":"username","panel_id":pid}
    names="\n".join(f"• {n} [ID:{gid}]" for gid,n,_ in groups)
    await q.edit_message_text(f"👤 ساخت کاربر / کانفیگ\n\nGroupهای انتخاب‌شده:\n{names}\n\nاسم کاربر را بفرست.\nمثال: test001",reply_markup=cancel_keyboard())


async def create_pg_user_flow(message,context):
    flow=context.user_data.get("flow",{}); pid=flow["panel_id"]; username=message.text.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}",username):
        await message.reply_text("❌ نام کاربر باید ۳ تا ۶۴ کاراکتر و فقط شامل حروف انگلیسی، عدد، _، - یا . باشد."); return False
    try:
        user,group_ids=await pasarguard_create_user(pid,username,0,30)
        sub=user.get("subscription_url") or user.get("sub_url") or user.get("subscription")
        with conn() as c:
            panel_row=c.execute("SELECT address FROM panels WHERE id=?", (pid,)).fetchone()
        if sub and panel_row:
            sub=full_subscription_url(panel_row[0], sub)
        groups=await selected_groups_for_panel(pid)
        gtext="\n".join(f"• {n} [ID:{gid}]" for gid,n,_ in groups)
        text=f"✅ کاربر ساخته شد.\n\n👤 Username: {user.get('username',username)}\n⏳ اعتبار: ۳۰ روز\n\n🔗 Groupها:\n{gtext}\n\n"
        text += f"🔗 Subscription:\n{sub}" if sub else "⚠️ subscription_url در پاسخ API برنگشت."
        await message.reply_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard",callback_data=f"panel_detail:{pid}")]])); return True
    except Exception as e:
        msg=str(e)
        if msg=="no_groups": msg="هیچ Groupی برای این پنل ثبت نشده."
        await message.reply_text(f"❌ ساخت کاربر ناموفق بود.\n\n{msg[:700]}",reply_markup=cancel_keyboard()); return False


async def free_test_settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    pid=int(q.data.split(":")[1])
    with conn() as c:
        row=c.execute("SELECT name FROM panels WHERE id=? AND panel_type='pasarguard'",(pid,)).fetchone()
        st=c.execute("SELECT max_tests,data_limit_mb,expire_hours FROM free_test_settings WHERE panel_id=?",(pid,)).fetchone()
    if not row: await q.edit_message_text("❌ پنل پیدا نشد.",reply_markup=admin_menu()); return
    current=f"\n\nتنظیم فعلی: هر کاربر {st[0]} تست | {st[1]} MB | {st[2]} ساعت" if st else ""
    context.user_data["flow"]={"type":"free_test_admin","step":"max_tests","panel_id":pid}
    await q.edit_message_text(f"🎁 تنظیم تست رایگان\n\nپنل: {row[0]}{current}\n\nهر کاربر چند بار بتواند تست بگیرد؟ فقط عدد بفرست.\nمثال: 2",reply_markup=cancel_keyboard())

async def free_test_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    with conn() as c:
        rows=c.execute("""SELECT p.id,p.name,s.max_tests,s.data_limit_mb,s.expire_hours FROM panels p JOIN free_test_settings s ON s.panel_id=p.id
            WHERE p.panel_type='pasarguard' AND p.status='connected' AND s.enabled=1 ORDER BY p.id""").fetchall()
    if not rows: await q.edit_message_text("❌ فعلاً تست رایگان فعال نشده.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی",callback_data="home")]])); return
    buttons=[[InlineKeyboardButton(f"🎁 {name} — {mb}MB/{hrs}ساعت",callback_data=f"free_test_panel:{pid}")] for pid,name,mt,mb,hrs in rows]
    buttons.append([InlineKeyboardButton("🏠 منوی اصلی",callback_data="home")])
    await q.edit_message_text("🎁 تست رایگان\n\nپنل تست را انتخاب کن:",reply_markup=InlineKeyboardMarkup(buttons))

async def free_test_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); pid=int(q.data.split(":")[1]); uid=q.from_user.id
    with conn() as c:
        st=c.execute("SELECT max_tests,data_limit_mb,expire_hours FROM free_test_settings WHERE panel_id=? AND enabled=1",(pid,)).fetchone()
        used=c.execute("SELECT used_count FROM free_test_usage WHERE user_id=? AND panel_id=?",(uid,pid)).fetchone()
        groups=c.execute("SELECT group_id,group_name FROM panel_groups WHERE panel_id=? ORDER BY id",(pid,)).fetchall()
        prow=c.execute("SELECT name FROM panels WHERE id=? AND panel_type='pasarguard'",(pid,)).fetchone()
    if not st or not prow: await q.edit_message_text("❌ تست برای این پنل فعال نیست.",reply_markup=menu(uid)); return
    used_n=used[0] if used else 0
    if used_n>=st[0]:
        await q.edit_message_text(f"⛔️ محدودیت ساخت تست شما تمام شد.\n\nتعداد مجاز: {st[0]} بار\nتعداد استفاده‌شده: {used_n} بار",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی",callback_data="home")]])); return
    if not groups: await q.edit_message_text("❌ برای این پنل Group ثبت نشده.",reply_markup=menu(uid)); return
    # حجم و زمان تست از تنظیمات ادمین خوانده می‌شود؛ کاربر حق تغییر آن‌ها را ندارد.
    context.user_data["flow"]={"type":"free_test_user","step":"ready","panel_id":pid,"mb":st[1],"hours":st[2]}
    await q.edit_message_text(
        f"🎁 تست رایگان — {prow[0]}\n\nتست {used_n+1} از {st[0]}\n\n📦 حجم: {st[1]} MB\n⏳ زمان: {st[2]} ساعت\n\nدر حال ساخت تست...",
        reply_markup=user_cancel_keyboard()
    )
    result=await free_test_create(q.message, context)
    if result is True:
        context.user_data.pop("flow",None)

async def free_test_create(message, context):
    flow=context.user_data.get("flow",{}); pid=flow["panel_id"]; mb=int(flow["mb"]); hours=int(flow["hours"]); uid=message.from_user.id
    with conn() as c:
        st=c.execute("SELECT max_tests FROM free_test_settings WHERE panel_id=? AND enabled=1",(pid,)).fetchone()
        used=c.execute("SELECT used_count FROM free_test_usage WHERE user_id=? AND panel_id=?",(uid,pid)).fetchone()
    if not st: await message.reply_text("❌ تست برای این پنل فعال نیست.",reply_markup=menu(uid)); return False
    used_n=used[0] if used else 0
    if used_n>=st[0]: await message.reply_text("⛔️ محدودیت ساخت تست شما تمام شد.",reply_markup=menu(uid)); return False
    username=f"trial{uid}_{datetime.now().strftime('%m%d%H%M%S%f')}"[:64]
    try:
        groups=await selected_groups_for_panel(pid); group_ids=[g[0] for g in groups if g[0] is not None]
        if not group_ids: raise RuntimeError("no_groups")
        client,base,headers=await pg_client(pid)
        try:
            expire=(datetime.now(timezone.utc)+timedelta(hours=hours)).replace(microsecond=0).isoformat()
            payload={"username":username,"proxy_settings":{},"expire":expire,"data_limit":mb*1024*1024,"data_limit_reset_strategy":"no_reset","status":"active","group_ids":group_ids}
            r=await client.post(f"{base}/api/user",headers=headers,json=payload)
            if r.status_code in (400,422): raise RuntimeError(f"create_user:{r.text[:500]}")
            r.raise_for_status(); data=r.json(); user=data.get("user") if isinstance(data,dict) and isinstance(data.get("user"),dict) else data
        finally: await client.aclose()
        sub=user.get("subscription_url") or user.get("sub_url") or user.get("subscription")
        with conn() as c:
            c.execute("INSERT OR IGNORE INTO free_test_usage(user_id,panel_id,used_count) VALUES(?,?,0)",(uid,pid)); c.execute("UPDATE free_test_usage SET used_count=used_count+1 WHERE user_id=? AND panel_id=?",(uid,pid)); prow=c.execute("SELECT address FROM panels WHERE id=?",(pid,)).fetchone()
        sub=full_subscription_url(prow[0],sub) if sub and prow else sub
        left=st[0]-(used_n+1)
        await message.reply_text(f"🎁 تست رایگان شما ساخته شد.\n\n📦 حجم: {mb} MB\n⏳ زمان: {hours} ساعت\n👤 User: {username}\n\n🔗 Subscription:\n{sub or 'لینک دریافت نشد.'}\n\n📊 تست باقی‌مانده: {left}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 تست رایگان",callback_data="free_test")],[InlineKeyboardButton("🏠 منوی اصلی",callback_data="home")]])); return True
    except Exception as e:
        await message.reply_text(f"❌ ساخت تست ناموفق بود.\n\n{str(e)[:600]}",reply_markup=menu(uid)); return False


async def test_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer("در حال ساخت تست 1MB...")
    if not is_admin(q.from_user.id): return
    pid=int(q.data.split(":")[1]); groups=await selected_groups_for_panel(pid)
    if not groups:
        await q.edit_message_text("❌ اول حداقل یک Group ثبت کن.",reply_markup=admin_menu()); return
    username="test_"+datetime.now().strftime("%m%d%H%M%S")
    try:
        user,group_ids=await pasarguard_create_user(pid,username,1024*1024,1)
        sub=user.get("subscription_url") or user.get("sub_url") or user.get("subscription")
        with conn() as c:
            panel_row=c.execute("SELECT address FROM panels WHERE id=?", (pid,)).fetchone()
        if sub and panel_row:
            sub=full_subscription_url(panel_row[0], sub)
        gtext="\n".join(f"• {n} [ID:{gid}]" for gid,n,_ in groups)
        text=f"🧪 Pasarguard — تست Group\n\n👤 User: {user.get('username',username)}\n📦 حجم: 1 MB\n⏳ اعتبار: 1 روز\n\n🔗 Groupها:\n{gtext}\n\n"
        text += f"🔗 Subscription:\n{sub}" if sub else "⚠️ subscription_url در پاسخ API برنگشت."
        await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard",callback_data=f"panel_detail:{pid}")]]))
    except Exception as e:
        await q.edit_message_text(f"❌ ساخت تست 1MB ناموفق بود.\n\n{str(e)[:700]}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Pasarguard",callback_data=f"panel_detail:{pid}")]]))


async def text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: return
    user_id=update.effective_user.id
    flow=context.user_data.get("flow")
    if not flow: return
    if flow.get("type") not in ("wallet_amount", "payment_photo", "support") and not is_admin(user_id): return
    if flow.get("type") == "support_admin_reply" and not is_admin(user_id): return
    text=update.message.text.strip()
    if flow["type"]=="wallet_amount":
        await wallet_amount_flow(update.message,context); return
    if flow["type"]=="support":
        await support_user_message(update, context); return
    if flow["type"]=="support_admin_reply":
        await support_admin_reply(update.message, context); return
    if flow["type"]=="user_balance":
        if not text.isdigit() or int(text)<=0: await update.message.reply_text("❌ فقط مبلغ مثبت وارد کن."); return
        amount=int(text); uid=flow["user_id"]
        with conn() as c:
            c.execute("INSERT OR IGNORE INTO wallets(user_id,balance) VALUES(?,0)",(uid,))
            if flow["action"]=="add": c.execute("UPDATE wallets SET balance=balance+? WHERE user_id=?",(amount,uid))
            else: c.execute("UPDATE wallets SET balance=MAX(0,balance-?) WHERE user_id=?",(amount,uid))
        context.user_data.pop("flow",None); await update.message.reply_text("✅ موجودی کاربر به‌روزرسانی شد.",reply_markup=admin_menu()); return
    if flow["type"]=="free_test_admin":
        step=flow.get("step")
        if not text.isdigit() or int(text)<=0: await update.message.reply_text("❌ فقط عدد مثبت وارد کن."); return
        if step=="max_tests": flow["max_tests"]=int(text); flow["step"]="mb"; await update.message.reply_text("📦 حجم تست را به MB وارد کن.\nهر 1 عدد = 1 MB\nمثال: 100"); return
        if step=="mb": flow["data_limit_mb"]=int(text); flow["step"]="hours"; await update.message.reply_text("⏳ زمان تست را به ساعت وارد کن.\nهر 1 عدد = 1 ساعت\nمثال: 1"); return
        if step=="hours":
            flow["expire_hours"]=int(text)
            with conn() as c: c.execute("INSERT OR REPLACE INTO free_test_settings(panel_id,max_tests,data_limit_mb,expire_hours,enabled) VALUES(?,?,?,?,1)",(flow["panel_id"],flow["max_tests"],flow["data_limit_mb"],flow["expire_hours"]))
            context.user_data.pop("flow",None); await update.message.reply_text(f"✅ تنظیم تست رایگان ثبت شد.\n\nهر کاربر: {flow['max_tests']} بار\n📦 حجم: {flow['data_limit_mb']} MB\n⏳ زمان: {flow['expire_hours']} ساعت",reply_markup=admin_menu()); return
    # free_test_user is created immediately after panel selection using the admin settings.
    if flow["type"]=="free_test_user":
        await update.message.reply_text("ℹ️ تست رایگان با حجم و زمان تنظیم‌شده توسط مدیریت ساخته می‌شود.",reply_markup=menu(user_id))
        return
    if flow["type"]=="welcome_admin":
        with conn() as c: c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('welcome_message',?)",(text,))
        context.user_data.pop("flow",None)
        await update.message.reply_text("✅ پیام خوش‌آمد ذخیره شد.",reply_markup=admin_menu()); return
    if flow["type"]=="mandatory_admin":
        if flow.get("step")=="channel_id":
            channel=text.strip()
            try:
                chat=await context.bot.get_chat(channel)
                me=await context.bot.get_chat_member(chat_id=chat.id,user_id=context.bot.id)
                if me.status not in ("administrator","creator"):
                    await update.message.reply_text("❌ ربات هنوز ادمین این کانال نیست. اول ربات را با دسترسی‌های لازم ادمین کن و دوباره ID/username را بفرست.",reply_markup=cancel_keyboard()); return
                flow["channel_id"]=str(chat.id); flow["title"]=chat.title or channel; flow["step"]="link"
                await update.message.reply_text("🔗 لینک عضویت این کانال را بفرست (مثال: https://t.me/channel).")
                return
            except Exception as e:
                await update.message.reply_text(f"❌ کانال پیدا نشد یا دسترسی ربات کافی نیست.\n\n{str(e)[:300]}",reply_markup=cancel_keyboard()); return
        if flow.get("step")=="link":
            link=text.strip()
            if not (link.startswith("http://") or link.startswith("https://")):
                await update.message.reply_text("❌ لینک معتبر نیست. مثال: https://t.me/channel"); return
            channels=get_mandatory_channels()
            channels=[c for c in channels if str(c.get("id"))!=str(flow["channel_id"])]
            channels.append({"id":flow["channel_id"],"title":flow["title"],"link":link})
            save_mandatory_channels(channels)
            with conn() as c: c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('mandatory_enabled','1')")
            context.user_data.pop("flow",None)
            await update.message.reply_text(f"✅ عضویت اجباری برای {flow['title']} فعال شد.\n\nتعداد کانال‌های اجباری: {len(channels)}",reply_markup=admin_menu()); return
    if flow["type"]=="product":
        if flow["step"]=="name":
            flow["name"]=text; flow["step"]="price"; await update.message.reply_text("💰 قیمت محصول را به تومان ارسال کن.\nمثال: 250000"); return
        if flow["step"]=="price":
            digits=text.replace(",","").replace("٬","").replace("تومان","").strip()
            if not digits.isdigit() or int(digits)<=0: await update.message.reply_text("❌ قیمت باید عدد مثبت باشد."); return
            flow["price"]=f"{int(digits):,} تومان"
            with conn() as c: panels=c.execute("SELECT id,panel_type,name,status FROM panels ORDER BY id DESC").fetchall()
            if not panels: await update.message.reply_text("❌ اول یک پنل اضافه کن.",reply_markup=admin_menu()); context.user_data.pop("flow",None); return
            flow["step"]="panel"
            await update.message.reply_text("🖥 محصول به کدام پنل متصل باشد؟",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"#{i} {name} ({PANEL_TYPES.get(pt,pt)})",callback_data=f"product_panel:{i}")] for i,pt,name,status in panels])); return
    if flow["type"]=="finance_card":
        if flow["step"]=="card":
            card=re.sub(r"\D","",text)
            if len(card)!=16: await update.message.reply_text("❌ شماره کارت باید ۱۶ رقم باشد."); return
            flow["card_number"]=card; flow["step"]="owner"; await update.message.reply_text("👤 لطفاً نام صاحب کارت را بگو:"); return
        if flow["step"]=="owner":
            with conn() as c:
                c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('card_number',?)",(flow["card_number"],)); c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('card_owner',?)",(text,))
            context.user_data.pop("flow",None); await update.message.reply_text("✅ اطلاعات کارت ثبت شد.",reply_markup=admin_menu()); return
    if flow["type"]=="product" and flow.get("step")=="gb":
        if not text.isdigit() or int(text)<=0: await update.message.reply_text("❌ حجم را فقط به عدد مثبت وارد کن."); return
        flow["data_limit_gb"]=int(text); flow["step"]="days"; await update.message.reply_text("⏳ زمان را فقط به عدد وارد کن. هر 1 عدد = 1 روز."); return
    if flow["type"]=="product" and flow.get("step")=="days":
        if not text.isdigit() or int(text)<=0: await update.message.reply_text("❌ زمان باید عدد مثبت باشد."); return
        flow["expire_days"]=int(text)
        with conn() as c: pid=c.execute("INSERT INTO products(name,price,panel_id,data_limit_gb,expire_days) VALUES(?,?,?,?,?)",(flow["name"],flow["price"],flow["panel_id"],flow["data_limit_gb"],flow["expire_days"])).lastrowid
        context.user_data.pop("flow",None); await update.message.reply_text(f"✅ محصول #{pid} اضافه شد.\n\nنام: {flow['name']}\nقیمت: {flow['price']}\n🖥 پنل: #{flow['panel_id']}\n📦 حجم: {flow['data_limit_gb']} GB\n⏳ زمان: {flow['expire_days']} روز",reply_markup=admin_menu()); return
    if flow["type"]=="panel":
        if flow["step"]=="address":
            if not valid_url(text): await update.message.reply_text("❌ آدرس معتبر نیست. با http:// یا https:// ارسال کن."); return
            flow["address"]=clean_base_url(text); flow["step"]="username"; await update.message.reply_text("👤 لطفاً username پنل را ارسال کن."); return
        if flow["step"]=="username":
            flow["username"]=text; flow["step"]="password"; await update.message.reply_text("🔑 لطفاً password پنل را ارسال کن."); return
        if flow["step"]=="password":
            flow["password"]=text; ok=await save_panel_after_test(update.message,flow)
            if ok: context.user_data.pop("flow",None)
            return
    if flow["type"]=="pg_user" and flow["step"]=="username":
        result=await create_pg_user_flow(update.message,context)
        if result is True: context.user_data.pop("flow",None)
        return


async def select_product_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    flow=context.user_data.get("flow")
    if not flow or flow.get("type")!="product": await q.edit_message_text("فرآیند افزودن محصول منقضی شده.",reply_markup=admin_menu()); return
    panel_id=int(q.data.split(":")[1])
    with conn() as c: p=c.execute("SELECT id,panel_type,name FROM panels WHERE id=?",(panel_id,)).fetchone()
    if not p: await q.edit_message_text("❌ پنل پیدا نشد.",reply_markup=admin_menu()); return
    flow["panel_id"]=panel_id; flow["step"]="gb"
    await q.edit_message_text(f"🖥 پنل انتخاب شد: {p[2]}\n\n📦 چند گیگ باشد؟\nفقط عدد بفرست. مثال: 20",reply_markup=cancel_keyboard())


async def payment_card_info(amount,kind="order"):
    card=await get_setting("card_number"); owner=await get_setting("card_owner")
    if not card: return None
    if kind == "wallet":
        return f"💰 شارژ کیف پول\n\n💰 مبلغ: {amount:,} تومان\n\n💳 شماره کارت: {card}\n\nمبلغ بالا را واریز کن و عکس رسید را همینجا ارسال کن."
    if not owner: return None
    return f"💳 پرداخت سفارش\n\n💰 مبلغ: {amount:,} تومان\n\n💳 شماره کارت: {card}\n👤 به نام: {owner}\n\nمبلغ بالا را واریز کن و عکس رسید را همینجا ارسال کن."


async def pay_direct_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); oid=int(q.data.split(":")[1])
    with conn() as c: row=c.execute("SELECT o.id,o.user_id,o.product_id,p.name,p.price FROM orders o JOIN products p ON p.id=o.product_id WHERE o.id=? AND o.user_id=?",(oid,q.from_user.id)).fetchone()
    if not row: await q.edit_message_text("❌ سفارش پیدا نشد."); return
    amount=int(re.sub(r"\D","",str(row[4])) or 0); info=await payment_card_info(amount,"order")
    if not info: await q.edit_message_text("❌ شماره کارت فروشگاه هنوز ثبت نشده."); return
    with conn() as c: payid=c.execute("INSERT INTO payments(user_id,kind,order_id,amount) VALUES(?,?,?,?)",(q.from_user.id,"order",oid,amount)).lastrowid
    context.user_data["flow"]={"type":"payment_photo","payment_id":payid}
    await q.edit_message_text(info,reply_markup=user_cancel_keyboard())


async def wallet_topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); context.user_data["flow"]={"type":"wallet_amount"}
    await q.edit_message_text("💰 مبلغ شارژ کیف پول را به تومان فقط به عدد وارد کن. مثال: 500000",reply_markup=user_cancel_keyboard())


async def wallet_amount_flow(message,context):
    text=message.text.replace(",","").replace("٬","").replace("تومان","").strip()
    if not text.isdigit() or int(text)<=0: await message.reply_text("❌ مبلغ باید عدد مثبت باشد."); return
    amount=int(text); info=await payment_card_info(amount,"wallet")
    if not info: await message.reply_text("❌ شماره کارت فروشگاه هنوز ثبت نشده.",reply_markup=menu(message.from_user.id)); return
    with conn() as c: payid=c.execute("INSERT INTO payments(user_id,kind,amount) VALUES(?,?,?)",(message.from_user.id,"wallet_topup",amount)).lastrowid
    context.user_data["flow"]={"type":"payment_photo","payment_id":payid}
    await message.reply_text(info,reply_markup=user_cancel_keyboard())


async def pay_wallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); oid=int(q.data.split(":")[1])
    with conn() as c: row=c.execute("SELECT o.id,o.user_id,o.product_id,p.name,p.price,p.panel_id,p.data_limit_gb,p.expire_days FROM orders o JOIN products p ON p.id=o.product_id WHERE o.id=? AND o.user_id=?",(oid,q.from_user.id)).fetchone(); w=c.execute("SELECT balance FROM wallets WHERE user_id=?",(q.from_user.id,)).fetchone()
    if not row: await q.edit_message_text("❌ سفارش پیدا نشد."); return
    amount=int(re.sub(r"\D","",str(row[4])) or 0); balance=w[0] if w else 0
    if balance<amount:
        card=await get_setting("card_number"); owner=await get_setting("card_owner")
        if not card or not owner: await q.edit_message_text(f"❌ موجودی کافی نیست.\nموجودی: {balance:,} تومان\nلازم: {amount:,} تومان",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 کیف پول",callback_data="wallet")]])); return
        with conn() as c: payid=c.execute("INSERT INTO payments(user_id,kind,order_id,amount) VALUES(?,?,?,?)",(q.from_user.id,"wallet_topup_for_order",oid,amount)).lastrowid
        context.user_data["flow"]={"type":"payment_photo","payment_id":payid}
        await q.edit_message_text(f"❌ موجودی کیف پول کافی نیست.\n\n💰 مبلغ لازم: {amount:,} تومان\n💳 {card}\n👤 به نام: {owner}\n\nعکس رسید را ارسال کن.",reply_markup=user_cancel_keyboard()); return
    await deliver_order(q,oid,q.from_user.id,from_wallet=True)


async def deliver_order(q,oid,uid,from_wallet=False):
    with conn() as c: row=c.execute("SELECT o.id,o.user_id,o.product_id,p.name,p.price,p.panel_id,p.data_limit_gb,p.expire_days FROM orders o JOIN products p ON p.id=o.product_id WHERE o.id=? AND o.user_id=?",(oid,uid)).fetchone()
    if not row: await q.edit_message_text("❌ سفارش پیدا نشد."); return False, None
    _,_,_,name,price,panel_id,gb,days=row; amount=int(re.sub(r"\D","",str(price)) or 0)
    try:
        with conn() as c: pt=c.execute("SELECT panel_type,address FROM panels WHERE id=?",(panel_id,)).fetchone()
        if not pt or pt[0]!="pasarguard": raise RuntimeError("محصول باید به پنل Pasarguard متصل باشد.")
        if from_wallet:
            with conn() as c: w=c.execute("SELECT balance FROM wallets WHERE user_id=?",(uid,)).fetchone();
            if not w or w[0]<amount: raise RuntimeError("موجودی کیف پول کافی نیست.")
        username=f"tg{uid}_{oid}"[:64]; user,_=await pasarguard_create_user(panel_id,username,int(gb or 1)*1024*1024*1024,int(days or 1))
        sub=user.get("subscription_url") or user.get("sub_url") or user.get("subscription")
        if sub: sub=full_subscription_url(pt[1],sub)
        with conn() as c:
            if from_wallet: c.execute("UPDATE wallets SET balance=balance-? WHERE user_id=?",(amount,uid))
            c.execute("UPDATE orders SET status='paid',subscription=?,panel_username=? WHERE id=?",(sub or '',username,oid))
        result_text=f"🎉 سفارش #{oid} تأیید و تحویل شد.\n\n📦 {name}\n📦 حجم: {gb or 1} GB\n⏳ اعتبار: {days or 1} روز\n\n🔗 Subscription:\n{sub or '⚠️ لینک subscription دریافت نشد.'}"
        markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 سفارش‌های من",callback_data="orders")],[InlineKeyboardButton("💰 کیف پول",callback_data="wallet")]])
        if getattr(q.message, "photo", None): await q.edit_message_caption(caption=result_text,reply_markup=markup)
        else: await q.edit_message_text(result_text,reply_markup=markup)
        return True, sub
    except Exception as e:
        err=f"❌ ساخت سرویس ناموفق بود؛ مبلغ کم نشد.\n\n{str(e)[:600]}"
        if getattr(q.message, "photo", None): await q.edit_message_caption(caption=err)
        else: await q.edit_message_text(err)
        return False, None


async def handle_payment_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow=context.user_data.get("flow",{})
    if flow.get("type")=="support" and update.message and update.message.photo:
        await support_user_message(update, context); return
    if flow.get("type")!="payment_photo" or not update.message or not update.message.photo: return
    payid=flow["payment_id"]; photo=update.message.photo[-1].file_id
    with conn() as c: c.execute("UPDATE payments SET photo_file_id=? WHERE id=?",(photo,payid)); row=c.execute("SELECT id,user_id,kind,order_id,amount FROM payments WHERE id=?",(payid,)).fetchone()
    context.user_data.pop("flow",None)
    if not row: await update.message.reply_text("❌ پرداخت پیدا نشد."); return
    pid,uid,kind,oid,amount=row
    await update.message.reply_text("✅ رسید دریافت شد. بعد از تأیید ادمین نتیجه اعلام می‌شود.",reply_markup=menu(uid))
    label={"order":"🛒 خرید سرویس","wallet_topup":"💰 شارژ کیف پول","wallet_topup_for_order":"💰 شارژ برای خرید"}.get(kind,kind)
    cap=f"💳 رسید #{pid}\n\nنوع: {label}\n👤 User ID: {uid}\n💰 مبلغ: {amount:,} تومان"+(f"\n📦 سفارش: #{oid}" if oid else "")
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأیید",callback_data=f"payapprove:{pid}"),InlineKeyboardButton("❌ رد",callback_data=f"payreject:{pid}")]])
    for aid in ADMIN_IDS:
        try: await context.bot.send_photo(aid,photo=photo,caption=cap,reply_markup=kb)
        except Exception: pass


async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer("در حال پردازش...");
    if not is_admin(q.from_user.id): return
    payid=int(q.data.split(":")[1])
    with conn() as c: row=c.execute("SELECT id,user_id,kind,order_id,amount,status FROM payments WHERE id=?",(payid,)).fetchone()
    if not row: await q.edit_message_caption(caption="❌ پرداخت پیدا نشد."); return
    _,uid,kind,oid,amount,status=row
    if status!="pending": await q.edit_message_caption(caption=f"ℹ️ قبلاً پردازش شده: {status}"); return
    if kind=="wallet_topup":
        with conn() as c: c.execute("UPDATE payments SET status='approved' WHERE id=?",(payid,)); c.execute("INSERT OR IGNORE INTO wallets(user_id,balance) VALUES(?,0)",(uid,)); c.execute("UPDATE wallets SET balance=balance+? WHERE user_id=?",(amount,uid))
        await q.edit_message_caption(caption=f"✅ شارژ #{payid} تأیید شد. +{amount:,} تومان")
        try: await context.bot.send_message(uid,f"🎉 شارژ کیف پول تأیید شد.\n💰 +{amount:,} تومان",reply_markup=menu(uid))
        except Exception: pass
        return
    if kind=="wallet_topup_for_order":
        with conn() as c: c.execute("UPDATE payments SET status='approved' WHERE id=?",(payid,)); c.execute("INSERT OR IGNORE INTO wallets(user_id,balance) VALUES(?,0)",(uid,)); c.execute("UPDATE wallets SET balance=balance+? WHERE user_id=?",(amount,uid))
        ok,sub=await deliver_order(q,oid,uid,from_wallet=True)
        if ok:
            try: await context.bot.send_message(uid,f"🎉 سفارش #{oid} تأیید شد و سرویس ساخته شد.\n\n🔗 Subscription:\n{sub or '⚠️ لینک subscription دریافت نشد.'}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 سفارش‌های من",callback_data="orders")],[InlineKeyboardButton("💰 کیف پول",callback_data="wallet")]]))
            except Exception: pass
        return
    with conn() as c: c.execute("UPDATE payments SET status='approved' WHERE id=?",(payid,))
    ok,sub=await deliver_order(q,oid,uid,from_wallet=False)
    if not ok:
        with conn() as c: c.execute("UPDATE payments SET status='pending' WHERE id=?",(payid,))
        return
    try: await context.bot.send_message(uid,f"🎉 سفارش #{oid} تأیید شد و سرویس ساخته شد.\n\n🔗 Subscription:\n{sub or '⚠️ لینک subscription دریافت نشد.'}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 سفارش‌های من",callback_data="orders")]]))
    except Exception: pass


async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer();
    if not is_admin(q.from_user.id): return
    payid=int(q.data.split(":")[1])
    with conn() as c: row=c.execute("SELECT user_id,kind,order_id,amount,status FROM payments WHERE id=?",(payid,)).fetchone()
    if not row: return
    uid,kind,oid,amount,status=row
    if status!="pending": await q.edit_message_caption(caption=f"ℹ️ قبلاً پردازش شده: {status}"); return
    with conn() as c: c.execute("UPDATE payments SET status='rejected' WHERE id=?",(payid,)); c.execute("UPDATE orders SET status='payment_rejected' WHERE id=?",(oid,)) if kind=="order" and oid else None
    await q.edit_message_caption(caption=f"❌ پرداخت #{payid} رد شد.")
    try: await context.bot.send_message(uid,f"❌ رسید پرداخت رد شد.\n💰 مبلغ: {amount:,} تومان",reply_markup=menu(uid))
    except Exception: pass


async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); context.user_data["flow"]={"type":"support","step":"message"}
    await q.edit_message_text("💬 پشتیبانی\n\nلطفاً عکس یا پیام خودت را برای پشتیبانی بفرست.",reply_markup=user_cancel_keyboard())

async def support_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; msg=update.message; text=msg.text or msg.caption or ""; photo=msg.photo[-1].file_id if msg.photo else ""
    if not text and not photo: await msg.reply_text("❌ لطفاً یک پیام یا عکس بفرست."); return
    with conn() as c: tid=c.execute("INSERT INTO support_tickets(user_id,message,photo_file_id) VALUES(?,?,?)",(uid,text,photo)).lastrowid
    context.user_data.pop("flow",None); await msg.reply_text("✅ پیامت برای پشتیبانی ارسال شد. منتظر پاسخ باش.",reply_markup=menu(uid))
    cap=f"💬 درخواست پشتیبانی #{tid}\n\n👤 User ID: {uid}\n\n{text}"; kb=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ پاسخ",callback_data=f"support_reply:{tid}")]])
    for aid in ADMIN_IDS:
        try:
            if photo: await context.bot.send_photo(aid,photo=photo,caption=cap,reply_markup=kb)
            else: await context.bot.send_message(aid,cap,reply_markup=kb)
        except Exception: pass

async def support_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id): return
    tid=int(q.data.split(":")[1])
    with conn() as c: row=c.execute("SELECT user_id FROM support_tickets WHERE id=?",(tid,)).fetchone()
    if not row: await q.edit_message_text("❌ درخواست پیدا نشد."); return
    context.user_data["flow"]={"type":"support_admin_reply","ticket_id":tid,"user_id":row[0]}
    await q.edit_message_text(f"↩️ پاسخ به تیکت #{tid}\n\nمتن پاسخ را ارسال کن:",reply_markup=cancel_keyboard())

async def support_admin_reply(message, context):
    flow=context.user_data.get("flow",{}); uid=flow["user_id"]; tid=flow["ticket_id"]; text=message.text.strip()
    if not text: await message.reply_text("❌ متن پاسخ خالی است."); return
    with conn() as c: c.execute("UPDATE support_tickets SET admin_id=?,status='answered' WHERE id=?",(message.from_user.id,tid))
    context.user_data.pop("flow",None)
    try:
        await context.bot.send_message(uid,f"💬 پاسخ پشتیبانی\n\n{text}",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 پشتیبانی",callback_data="support")],[InlineKeyboardButton("🏠 منوی اصلی",callback_data="home")]]))
        await message.reply_text("✅ پاسخ برای کاربر ارسال شد.",reply_markup=admin_menu())
    except Exception as e: await message.reply_text(f"❌ ارسال پاسخ ناموفق بود: {str(e)[:200]}",reply_markup=admin_menu())


async def simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "cancel_user":
        context.user_data.pop("flow",None)
        await q.edit_message_text("❌ لغو شد.",reply_markup=menu(q.from_user.id))
    elif q.data == "home":
        context.user_data.pop("flow", None)
        await q.edit_message_text("🏠 منوی اصلی:", reply_markup=menu(q.from_user.id))
    elif q.data == "support":
        await support_start(update, context)
    elif q.data == "free_test":
        await free_test_user_start(update, context)
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
    q=update.callback_query; data=q.data
    if not is_admin(q.from_user.id):
        with conn() as c:
            row=c.execute("SELECT is_blocked FROM users WHERE user_id=?",(q.from_user.id,)).fetchone()
        if row and row[0]:
            await q.answer("🚫 دسترسی شما به ربات مسدود شده است.",show_alert=True); return
    if data=="admin": return await admin_panel(update,context)
    if data=="admin_add": return await admin_add_product(update,context)
    if data=="admin_welcome": return await admin_welcome(update,context)
    if data=="admin_mandatory": return await admin_mandatory(update,context)
    if data=="mandatory_add": return await mandatory_add_start(update,context)
    if data.startswith("mandatory_del:"): return await mandatory_delete(update,context)
    if data=="mandatory_toggle": return await mandatory_toggle(update,context)
    if data=="check_membership": return await check_membership(update,context)
    if data=="admin_panels": return await admin_panels(update,context)
    if data=="add_panel": return await add_panel_start(update,context)
    if data.startswith("paneltype:"): return await select_panel_type(update,context)
    if data.startswith("panel_detail:"): return await panel_detail(update,context)
    if data.startswith("test_panel:"): return await test_panel(update,context)
    if data.startswith("delete_panel:"): return await delete_panel(update,context)
    if data.startswith("delete_group:"): return await delete_group(update,context)
    if data.startswith("connect_group:"): return await connect_group_start(update,context)
    if data.startswith("choose_group:"): return await choose_group(update,context)
    if data.startswith("refresh_groups:"): return await refresh_groups(update,context)
    if data.startswith("create_pg_user:"): return await create_pg_user_start(update,context)
    if data.startswith("test_group:"): return await test_group(update,context)
    if data.startswith("product_panel:"): return await select_product_panel(update,context)
    if data=="admin_products": return await admin_products(update,context)
    if data=="admin_orders": return await admin_orders(update,context)
    if data=="admin_users": return await admin_users(update,context)
    if data.startswith("user_manage:"): return await user_manage(update,context)
    if data.startswith("user_add_balance:") or data.startswith("user_sub_balance:"): return await user_balance_start(update,context)
    if data.startswith("user_block:"): return await user_block(update,context)
    if data.startswith("user_orders:"): return await user_orders(update,context)
    if data.startswith("delete_product:"): return await delete_product(update,context)
    if data=="wallet": return await wallet(update,context)
    if data=="admin_finance": return await admin_finance(update,context)
    if data=="finance_card": return await finance_card_start(update,context)
    if data=="finance_pending": return await finance_pending(update,context)
    if data=="wallet_topup": return await wallet_topup_start(update,context)
    if data.startswith("pay_direct:"): return await pay_direct_start(update,context)
    if data.startswith("pay_wallet:"): return await pay_wallet_start(update,context)
    if data.startswith("payapprove:"): return await approve_payment(update,context)
    if data.startswith("payreject:"): return await reject_payment(update,context)
    if data.startswith("service:"): return await service_detail(update,context)
    if data.startswith("free_test_settings:"): return await free_test_settings_start(update,context)
    if data.startswith("free_test_panel:"): return await free_test_panel_start(update,context)
    if data.startswith("support_reply:"): return await support_reply_start(update,context)
    return await simple(update,context)



def wrap_membership(fn):
    async def wrapped(update, context):
        if not await membership_gate(update, context):
            return
        return await fn(update, context)
    return wrapped


def main():
    global products, product, create_order, orders, service_detail, profile, wallet, pay_direct_start, wallet_topup_start, pay_wallet_start, free_test_user_start, free_test_panel_start, support_start, simple
    for _name in ("products","product","create_order","orders","service_detail","profile","wallet","pay_direct_start","wallet_topup_start","pay_wallet_start","free_test_user_start","free_test_panel_start","support_start","simple"):
        globals()[_name] = wrap_membership(globals()[_name])
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
    app.add_handler(MessageHandler(filters.PHOTO, handle_payment_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_messages))
    try:
        from web_panel import start_web_server
        threading.Thread(target=start_web_server, daemon=True).start()
    except Exception as e:
        print("Web panel start failed:", e)
    app.run_polling()


if __name__ == "__main__":
    main()
