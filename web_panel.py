import os
import re
import json
import sqlite3
import secrets
import tempfile
from datetime import datetime, timedelta
from functools import wraps

import httpx
from flask import Flask, request, redirect, url_for, session, render_template_string, flash, send_file
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = os.getenv('DB_PATH', 'shop.db')
ADMIN_IDS = {int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()}
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
WEB_SECRET = os.getenv('WEB_SECRET') or secrets.token_hex(32)
VERSION = '1.0.8'

PANEL_TYPES = {'marzban': 'Marzban', 'pasarguard': 'Pasarguard', '3xui': '3x-ui'}

app = Flask(__name__)
app.secret_key = WEB_SECRET


def money_filter(value):
    try:
        return f"{int(float(value or 0)):,}"
    except (TypeError, ValueError):
        return "0"


app.jinja_env.filters['money'] = money_filter

BASE = '''
<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IRANBOT — Admin</title>
<style>
:root{--bg:#07111f;--panel:#0d1b2d;--panel2:#10233a;--line:#20344d;--text:#edf5ff;--muted:#91a7bf;--accent:#38d996;--accent2:#38a8ff;--danger:#ff5d72;--warn:#ffbd59;--shadow:0 18px 55px rgba(0,0,0,.25)}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% -10%,rgba(56,168,255,.15),transparent 30%),radial-gradient(circle at 5% 10%,rgba(56,217,150,.11),transparent 25%),var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;min-height:100vh}
.wrap{max-width:1280px;margin:0 auto;padding:24px 18px 45px}.top{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:18px}.brand{display:flex;align-items:center;gap:12px}.logo{width:48px;height:48px;border-radius:15px;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent2),var(--accent));box-shadow:0 10px 30px rgba(56,168,255,.2);font-size:24px}.brand h1{margin:0;font-size:25px}.version{color:var(--muted);font-size:12px}.logout{color:#dce9f7;text-decoration:none;background:#14263d;border:1px solid var(--line);padding:9px 13px;border-radius:11px}
.nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;padding:10px;background:rgba(13,27,45,.82);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);backdrop-filter:blur(12px);margin-bottom:20px}.nav a{color:#dbe9f7;text-decoration:none;text-align:center;background:#12243a;border:1px solid transparent;padding:11px 9px;border-radius:12px;transition:.18s}.nav a:hover{border-color:#2d5578;transform:translateY(-1px);background:#172d47}
.hero{background:linear-gradient(135deg,rgba(56,168,255,.16),rgba(56,217,150,.10));border:1px solid #254664;border-radius:22px;padding:24px;box-shadow:var(--shadow);margin-bottom:18px}.hero h2{margin:0 0 7px;font-size:24px}.hero p{margin:0;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:13px}.statcard{background:linear-gradient(180deg,#10223a,#0c192b);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:var(--shadow)}.staticon{font-size:24px}.statlabel{color:var(--muted);font-size:13px;margin-top:9px}.stat{font-size:28px;font-weight:800;margin-top:3px}
.card{background:rgba(13,27,45,.94);border:1px solid var(--line);border-radius:18px;padding:20px;margin:14px 0;box-shadow:var(--shadow)}.card h2,.card h3{margin-top:0}.muted{color:var(--muted)}.ok{color:var(--accent)}.bad{color:#ff9bab}.warn{color:var(--warn)}
input,textarea,select{width:100%;box-sizing:border-box;background:#081525;color:#fff;border:1px solid #2a425d;border-radius:12px;padding:12px 13px;margin:7px 0 14px;outline:none}input:focus,textarea:focus,select:focus{border-color:var(--accent2);box-shadow:0 0 0 3px rgba(56,168,255,.08)}label{font-size:13px;color:#b8c9da}button,.btn{display:inline-block;background:linear-gradient(135deg,var(--accent),#23bd86);color:#03130d;border:0;border-radius:11px;padding:11px 15px;font-weight:800;cursor:pointer;text-decoration:none}.btn.blue{background:linear-gradient(135deg,var(--accent2),#4385ff);color:white}.btn.dark{background:#152a42;color:#e6f0fa;border:1px solid #29435e}.danger{background:linear-gradient(135deg,#ff6679,#e83e58)!important;color:#fff!important}.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.actions{display:flex;gap:8px;flex-wrap:wrap}.small{font-size:12px}.table-wrap{overflow:auto}.table{width:100%;border-collapse:separate;border-spacing:0;min-width:720px}.table td,.table th{border-bottom:1px solid #20344d;padding:12px;text-align:right;vertical-align:middle}.table th{color:#9fb5cb;font-size:12px;background:#0d1a2b}.table tr:hover td{background:rgba(255,255,255,.018)}.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:#172b43;font-size:12px}.badge.ok{background:rgba(56,217,150,.12);color:#72efb7}.badge.bad{background:rgba(255,93,114,.12);color:#ff9bab}.badge.warn{background:rgba(255,189,89,.12);color:#ffd18a}
.light-theme{--bg:#f3f6fa;--panel:#ffffff;--panel2:#f8fafc;--line:#d6dee8;--text:#172333;--muted:#5d6d7e;--shadow:0 12px 35px rgba(20,40,60,.12)}.light-theme .nav,.light-theme .card,.light-theme .statcard{background:#fff;border-color:var(--line)}.light-theme .nav a{background:#f4f7fa;color:#25384c}.light-theme input,.light-theme textarea,.light-theme select{background:#fff;color:#172333;border-color:#b9c8d7}.light-theme .switch{background:#f7f9fb;border-color:#cbd7e3}.login{max-width:440px;margin:12vh auto}.login .logo{margin:auto}.flash{background:#11263a;border:1px solid #284763;padding:11px 13px;margin-bottom:10px;border-radius:12px}.empty{text-align:center;padding:35px;color:var(--muted)}.mini{font-size:11px;color:#7890a9;word-break:break-all}.switch{display:flex;align-items:center;justify-content:space-between;padding:14px;background:#0a1829;border:1px solid var(--line);border-radius:13px;margin:10px 0}.checkgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}.check{padding:13px;border:1px solid #29425c;border-radius:13px;background:#0a1829}.check input{width:auto;margin:0 7px 0 0}.kpi{font-size:12px;color:var(--muted)}
@media(max-width:700px){.wrap{padding:14px 10px 30px}.top{align-items:flex-start}.brand h1{font-size:20px}.nav{grid-template-columns:repeat(2,1fr)}.hero{padding:18px}.card{padding:15px}.table{min-width:650px}}
</style></head><body class="{{'light-theme' if theme=='light' else ''}}"><div class="wrap">
<div class="top"><div class="brand"><div class="logo">⚡</div><div><h1>IRANBOT <span class="version">v{{version}}</span></h1><div class="muted small">داشبورد مدیریت فروش و سرویس</div></div></div>{% if session.get('admin_id') %}<a class="logout" href="{{url_for('logout')}}">خروج ↪</a>{% endif %}</div>
{% if session.get('admin_id') %}<div class="nav">
<a href="{{url_for('dashboard')}}">🏠 داشبورد</a><a href="{{url_for('users')}}">👥 کاربران</a><a href="{{url_for('welcome')}}">👋 خوش‌آمد</a><a href="{{url_for('mandatory')}}">📢 عضویت</a><a href="{{url_for('finance')}}">💳 مالی</a><a href="{{url_for('finance_report_web')}}">📊 گزارش مالی</a><a href="{{url_for('panels')}}">🖥 پنل‌ها</a><a href="{{url_for('products')}}">🛒 محصولات</a><a href="{{url_for('orders')}}">📦 سفارش‌ها</a><a href="{{url_for('free_tests')}}">🎁 تست رایگان</a><a href="{{url_for('discount')}}">🏷 تخفیف</a><a href="{{url_for('raffle')}}">🎟 قرعه‌کشی</a><a href="{{url_for('backup')}}">💾 پشتیبان‌گیری</a><a href="{{url_for('settings_web')}}">⚙️ تنظیمات</a>
</div>{% endif %}
{% with msgs=get_flashed_messages() %}{% for m in msgs %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}
<div class="muted small" style="margin:28px 2px 0">IRANBOT — نسخه {{version}} — ساخته شده توسط PYTHONdvL010</div></div></body></html>
'''


def db():
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute('PRAGMA busy_timeout=5000')
    return c


BACKUP_REQUIRED_TABLES = {"users", "wallets", "panels", "products", "orders", "settings"}


def create_backup_file_sync(prefix="iranbot_backup"):
    ensure_schema()
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(path)
        try:
            src.backup(dst)
            row = dst.execute("PRAGMA integrity_check").fetchone()
            if not row or row[0] != "ok":
                raise RuntimeError("Database integrity check failed")
        finally:
            dst.close(); src.close()
        return path
    except Exception:
        try: os.remove(path)
        except OSError: pass
        raise


def validate_backup_file_sync(path):
    try:
        c=sqlite3.connect(path)
        try:
            check=c.execute("PRAGMA integrity_check").fetchone()
            if not check or check[0] != "ok":
                return False,"فایل Backup سالم نیست یا Database آسیب دیده است."
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            missing=BACKUP_REQUIRED_TABLES-tables
            if missing:
                return False,"فایل Backup مربوط به IRANBOT نیست یا جدول‌های اصلی ناقص هستند."
            return True,"ok"
        finally:
            c.close()
    except sqlite3.DatabaseError:
        return False,"فایل انتخاب‌شده یک SQLite Database معتبر نیست."


def restore_backup_file_sync(path):
    ok,reason=validate_backup_file_sync(path)
    if not ok: return False,reason
    parent=os.path.dirname(DB_PATH) or "."
    os.makedirs(parent,exist_ok=True)
    fd,staged=tempfile.mkstemp(prefix="iranbot_restore_",suffix=".db",dir=parent)
    os.close(fd)
    try:
        src=sqlite3.connect(path); dst=sqlite3.connect(staged)
        try: src.backup(dst)
        finally: dst.close(); src.close()
        ok,reason=validate_backup_file_sync(staged)
        if not ok: raise RuntimeError(reason)
        os.replace(staged,DB_PATH)
        ensure_schema()
        return True,"ok"
    except Exception as e:
        try: os.remove(staged)
        except OSError: pass
        return False,str(e)[:500]


def ensure_schema():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT DEFAULT '')")
        c.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '', first_name TEXT DEFAULT '', is_blocked INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, last_seen DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS wallets(user_id INTEGER PRIMARY KEY,balance INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS panels(id INTEGER PRIMARY KEY AUTOINCREMENT,panel_type TEXT NOT NULL,name TEXT NOT NULL,address TEXT NOT NULL,username TEXT NOT NULL,password TEXT NOT NULL,status TEXT DEFAULT 'unknown',created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS panel_groups(id INTEGER PRIMARY KEY AUTOINCREMENT,panel_id INTEGER NOT NULL,group_id INTEGER,group_name TEXT NOT NULL,inbound_tags TEXT DEFAULT '',UNIQUE(panel_id,group_id))")
        c.execute("CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,price TEXT NOT NULL,description TEXT DEFAULT '',panel_id INTEGER,active INTEGER DEFAULT 1,data_limit_gb INTEGER DEFAULT 1,expire_days INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS product_categories(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,product_id INTEGER NOT NULL,status TEXT DEFAULT 'pending',created_at DATETIME DEFAULT CURRENT_TIMESTAMP,subscription TEXT DEFAULT '',panel_username TEXT DEFAULT '')")
        c.execute("CREATE TABLE IF NOT EXISTS coupons(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT NOT NULL UNIQUE,discount_type TEXT NOT NULL,value INTEGER NOT NULL,duration_days INTEGER NOT NULL,created_at DATETIME DEFAULT CURRENT_TIMESTAMP,expires_at DATETIME NOT NULL,active INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS configs(id INTEGER PRIMARY KEY AUTOINCREMENT,product_id INTEGER NOT NULL,config TEXT NOT NULL,delivered INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,kind TEXT NOT NULL,order_id INTEGER,amount INTEGER NOT NULL,status TEXT DEFAULT 'pending',photo_file_id TEXT,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS renewals(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,order_id INTEGER NOT NULL,full_price INTEGER NOT NULL,remaining_gb REAL DEFAULT 0,charge_gb REAL DEFAULT 0,amount INTEGER NOT NULL,status TEXT DEFAULT 'pending',created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS free_test_settings(panel_id INTEGER PRIMARY KEY,max_tests INTEGER DEFAULT 1,data_limit_mb INTEGER DEFAULT 100,expire_hours INTEGER DEFAULT 1,enabled INTEGER DEFAULT 1)")
        for table, columns in {
            'users': [('username',"TEXT DEFAULT ''"),('first_name',"TEXT DEFAULT ''"),('is_blocked','INTEGER DEFAULT 0'),('last_seen',"TEXT DEFAULT ''")],
            'products': [('panel_id','INTEGER'),('data_limit_gb','INTEGER DEFAULT 1'),('expire_days','INTEGER DEFAULT 1'),('active','INTEGER DEFAULT 1'),('category_id','INTEGER')],
            'orders': [('subscription',"TEXT DEFAULT ''"),('panel_username',"TEXT DEFAULT ''"),('discount_code',"TEXT DEFAULT ''"),('discount_amount','INTEGER DEFAULT 0'),('final_amount','INTEGER DEFAULT 0')],
        }.items():
            existing={r[1] for r in c.execute(f'PRAGMA table_info({table})').fetchall()}
            for name, definition in columns:
                if name not in existing:
                    c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        c.execute("CREATE TABLE IF NOT EXISTS raffles(id INTEGER PRIMARY KEY AUTOINCREMENT,prize_type TEXT NOT NULL,prize_name TEXT DEFAULT '',prize_amount INTEGER DEFAULT 0,entry_fee INTEGER DEFAULT 0,max_participants INTEGER DEFAULT 30,status TEXT DEFAULT 'active',created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS raffle_participants(raffle_id INTEGER NOT NULL,user_id INTEGER NOT NULL,created_at DATETIME DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(raffle_id,user_id))")
        c.execute("UPDATE users SET last_seen=CURRENT_TIMESTAMP WHERE last_seen IS NULL OR last_seen=''")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('web_theme','dark')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('web_2fa','0')")
        if not c.execute("SELECT 1 FROM settings WHERE key='web_admin_id'").fetchone() and ADMIN_IDS:
            c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('web_admin_id',?)",(str(next(iter(ADMIN_IDS))),))


def setting(k):
    with db() as c:
        r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone()
    return r[0] if r else ''


def set_setting(k,v):
    with db() as c:
        c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,str(v)))


def configured_web_admin_id():
    raw=setting('web_admin_id')
    try:
        return int(raw) if raw else (next(iter(ADMIN_IDS)) if ADMIN_IDS else None)
    except Exception:
        return next(iter(ADMIN_IDS)) if ADMIN_IDS else None


def admin_required(fn):
    @wraps(fn)
    def w(*a,**kw):
        current=session.get('admin_id')
        allowed=set(ADMIN_IDS)
        configured=configured_web_admin_id()
        if configured is not None:
            allowed.add(configured)
        if current not in allowed:
            return redirect(url_for('login'))
        ensure_schema()
        return fn(*a,**kw)
    return w


def page(html, **ctx):
    ctx.setdefault('version', VERSION)
    ctx.setdefault('theme', setting('web_theme') or 'dark')
    return render_template_string(BASE, body=render_template_string(html, **ctx), version=VERSION, theme=ctx['theme'])


def clean_base_url(value):
    value=value.strip().rstrip('/')
    value=re.sub(r'/dashboard/?(?:#.*)?$','',value,flags=re.I)
    value=re.sub(r'/#.*$','',value)
    return value.rstrip('/')


def extract_list(data, keys):
    if isinstance(data,list): return data
    if isinstance(data,dict):
        for key in keys:
            value=data.get(key)
            if isinstance(value,list): return value
        for value in data.values():
            if isinstance(value,list): return value
    return []


def group_fields(item):
    if not isinstance(item,dict): return None
    gid=item.get('id') or item.get('group_id')
    name=item.get('name') or item.get('group_name') or item.get('tag')
    tags=item.get('inbound_tags') or []
    if isinstance(tags,str): tags=[x.strip() for x in tags.split(',') if x.strip()]
    if not name: return None
    try: gid=int(gid) if gid is not None else None
    except Exception: pass
    return gid,str(name),[str(x) for x in tags]


def panel_login_sync(pt,address,username,password):
    base=clean_base_url(address)
    client=httpx.Client(timeout=15,follow_redirects=True)
    try:
        if pt in ('marzban','pasarguard'):
            r=client.post(f'{base}/api/admin/token',data={'username':username,'password':password})
            if r.status_code in (401,403): return False,f'احراز هویت رد شد ({r.status_code})',None,base,client
            r.raise_for_status(); data=r.json(); token=data.get('access_token') or data.get('token')
            if not token: return False,'توکن از API دریافت نشد.',None,base,client
            return True,'connected',{'Authorization':f'Bearer {token}'},base,client
        if pt=='3xui':
            r=client.post(f'{base}/login',data={'username':username,'password':password})
            if r.status_code>=400: return False,f'Login HTTP {r.status_code}',None,base,client
            s=client.get(f'{base}/panel/api/server/status')
            if s.status_code>=400: return False,f'Status HTTP {s.status_code}',None,base,client
            return True,'connected',{},base,client
        return False,'نوع پنل ناشناخته است.',None,base,client
    except Exception as e:
        client.close(); return False,str(e)[:350],None,base,None


def fetch_groups_sync(pid):
    with db() as c:
        row=c.execute('SELECT panel_type,address,username,password FROM panels WHERE id=?',(pid,)).fetchone()
        cached=[(r[0],r[1],([x for x in (r[2] or '').split(',') if x])) for r in c.execute('SELECT group_id,group_name,inbound_tags FROM panel_groups WHERE panel_id=? ORDER BY id',(pid,)).fetchall()]
    if not row or row[0]!='pasarguard': return cached,'پنل Pasarguard پیدا نشد.'
    ok,reason,headers,base,client=panel_login_sync(*row)
    if not ok: return cached,reason
    try:
        r=client.get(f'{base}/api/groups',headers=headers)
        if r.status_code in (401,403): r=client.get(f'{base}/api/groups/simple',headers=headers)
        if r.status_code in (401,403): return cached,'این حساب اجازه مشاهده Groupها را ندارد.'
        r.raise_for_status()
        groups=[x for x in (group_fields(i) for i in extract_list(r.json(),['groups','items','data'])) if x]
        if not groups and cached: return cached,'API لیست Groupها را خالی برگرداند؛ Groupهای ذخیره‌شده نمایش داده شدند.'
        with db() as c:
            for gid,name,tags in groups:
                old=c.execute('SELECT inbound_tags FROM panel_groups WHERE panel_id=? AND group_id=?',(pid,gid)).fetchone()
                saved=','.join(tags) if tags else (old[0] if old else '')
                c.execute('INSERT OR REPLACE INTO panel_groups(panel_id,group_id,group_name,inbound_tags) VALUES(?,?,?,?)',(pid,gid,name,saved))
        return groups,''
    except Exception as e:
        return cached,str(e)[:400]
    finally:
        client.close()


def telegram_notify(user_id,text):
    if not BOT_TOKEN: return False
    try:
        with httpx.Client(timeout=8) as c:
            r=c.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',json={'chat_id':int(user_id),'text':text})
            return r.is_success
    except Exception:
        return False


ensure_schema()

LOGIN='''<div class="card login"><div class="logo">⚡</div><h2 style="text-align:center">ورود به پنل مدیریت</h2><p class="muted" style="text-align:center">آیدی عددی ادمین و در صورت فعال بودن ورود دو مرحله‌ای، رمز عبور را وارد کن.</p><form method="post"><label>آیدی عددی</label><input name="admin_id" inputmode="numeric" placeholder="مثلاً 123456789" required>{% if two_factor %}<label>رمز ورود</label><input name="password" type="password" placeholder="رمز ورود" required>{% endif %}<button style="width:100%">🔐 ورود</button></form></div>'''

@app.route('/login',methods=['GET','POST'])
def login():
    ensure_schema(); configured=configured_web_admin_id(); two_factor=setting('web_2fa')=='1'
    if request.method=='POST':
        try: aid=int(request.form.get('admin_id',''))
        except Exception: aid=-1
        allowed=set(ADMIN_IDS)
        if configured is not None: allowed.add(configured)
        if aid not in allowed:
            return page('<div class="card login"><h2 class="bad">❌ آیدی ادمین صحیح نیست.</h2><a class="btn dark" href="/login">تلاش دوباره</a></div>',two_factor=two_factor)
        if two_factor:
            stored=setting('web_password_hash')
            if not stored or not check_password_hash(stored, request.form.get('password','')):
                return page('<div class="card login"><h2 class="bad">❌ رمز ورود اشتباه است.</h2><a class="btn dark" href="/login">تلاش دوباره</a></div>',two_factor=two_factor)
        session['admin_id']=aid; return redirect(url_for('dashboard'))
    return page(LOGIN,two_factor=two_factor)

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/')
def root():
    allowed=set(ADMIN_IDS); configured=configured_web_admin_id()
    if configured is not None: allowed.add(configured)
    return redirect(url_for('dashboard') if session.get('admin_id') in allowed else url_for('login'))

@app.route('/settings',methods=['GET','POST'])
@admin_required
def settings_web():
    if request.method=='POST':
        action=request.form.get('action','')
        if action=='theme':
            theme=request.form.get('theme','dark')
            if theme in ('dark','light'):
                set_setting('web_theme',theme); flash('✅ تم Web Panel تغییر کرد.')
            return redirect(url_for('settings_web'))
        if action=='security':
            try: new_id=int(request.form.get('admin_id',''))
            except Exception: new_id=0
            if new_id<=0:
                flash('❌ آیدی عددی معتبر نیست.'); return redirect(url_for('settings_web'))
            enabled=request.form.get('two_factor')=='1'
            password=request.form.get('password',''); confirm=request.form.get('password_confirm','')
            old_enabled=setting('web_2fa')=='1'
            if enabled and not old_enabled and not password:
                flash('❌ برای فعال‌سازی ورود دو مرحله‌ای، رمز عبور را وارد کن.'); return redirect(url_for('settings_web'))
            if password or confirm:
                if len(password)<8:
                    flash('❌ رمز عبور باید حداقل 8 کاراکتر باشد.'); return redirect(url_for('settings_web'))
                if password!=confirm:
                    flash('❌ تکرار رمز عبور با رمز اصلی یکسان نیست.'); return redirect(url_for('settings_web'))
                set_setting('web_password_hash',generate_password_hash(password))
            if enabled and not setting('web_password_hash'):
                flash('❌ ابتدا رمز عبور را تنظیم کن.'); return redirect(url_for('settings_web'))
            set_setting('web_admin_id',new_id); set_setting('web_2fa','1' if enabled else '0'); session['admin_id']=new_id
            flash('✅ تنظیمات ورود با موفقیت ذخیره شد.'); return redirect(url_for('settings_web'))
    current_id=configured_web_admin_id() or ''; two_factor=setting('web_2fa')=='1'; theme=setting('web_theme') or 'dark'
    b='''<div class="hero"><h2>⚙️ تنظیمات</h2><p>تنظیمات ظاهر Web Panel و امنیت ورود را از این بخش مدیریت کن.</p></div><div class="card"><h3>🎨 تغییر Theme</h3><p class="muted">ظاهر پنل را به حالت سفید یا مشکی تغییر بده.</p><div class="actions"><form method="post"><input type="hidden" name="action" value="theme"><button name="theme" value="light">⚪ سفید</button></form><form method="post"><input type="hidden" name="action" value="theme"><button class="btn dark" name="theme" value="dark">⚫ مشکی</button></form></div><p class="small muted">Theme فعلی: {{'سفید' if theme=='light' else 'مشکی'}}</p></div><div class="card"><h3>🔐 ورود دو مرحله‌ای</h3><form method="post"><input type="hidden" name="action" value="security"><label>آیدی عددی Web Panel</label><input name="admin_id" type="number" min="1" value="{{current_id}}" required><div class="switch"><span><b>فعال‌سازی ورود دو مرحله‌ای</b><br><span class="muted small">بعد از فعال‌سازی، ورود با آیدی عددی + رمز انجام می‌شود.</span></span><input name="two_factor" value="1" type="checkbox" style="width:auto" {% if two_factor %}checked{% endif %}></div><label>رمز عبور جدید</label><input name="password" type="password" minlength="8" placeholder="حداقل 8 کاراکتر"><label>تکرار رمز عبور</label><input name="password_confirm" type="password" minlength="8" placeholder="تکرار رمز"><button>💾 ذخیره تنظیمات</button></form></div>'''
    return page(b,current_id=current_id,two_factor=two_factor,theme=theme)

@app.route('/dashboard')
@admin_required
def dashboard():
    with db() as c:
        counts=[
            ('👥','کاربران',c.execute('SELECT COUNT(*) FROM users').fetchone()[0]),
            ('🛒','محصولات',c.execute('SELECT COUNT(*) FROM products WHERE active=1').fetchone()[0]),
            ('📦','سفارش‌ها',c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]),
            ('💳','پرداخت موفق',c.execute("SELECT COUNT(*) FROM orders WHERE status='paid'").fetchone()[0]),
            ('⏳','در انتظار بررسی',c.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0]),
            ('🖥','پنل‌ها',c.execute('SELECT COUNT(*) FROM panels').fetchone()[0]),
        ]
        recent=c.execute("SELECT o.id,o.user_id,p.name,o.status,o.created_at FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT 8").fetchall()
    b='''<div class="hero"><h2>خوش اومدی 👋</h2><p>همه بخش‌های فروشگاه، کاربران، پنل‌ها و تست رایگان را از همین‌جا مدیریت کن.</p></div><div class="grid">{% for icon,label,val in counts %}<div class="statcard"><div class="staticon">{{icon}}</div><div class="statlabel">{{label}}</div><div class="stat">{{val}}</div></div>{% endfor %}</div><div class="card"><div class="row" style="justify-content:space-between"><h2>📦 آخرین سفارش‌ها</h2><a class="btn dark" href="{{url_for('orders')}}">مشاهده همه</a></div>{% if recent %}<div class="table-wrap"><table class="table"><tr><th>#</th><th>User</th><th>محصول</th><th>وضعیت</th><th>تاریخ</th></tr>{% for r in recent %}<tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td><span class="badge {{'ok' if r[3]=='paid' else 'warn'}}">{{r[3]}}</span></td><td>{{r[4]}}</td></tr>{% endfor %}</table></div>{% else %}<div class="empty">هنوز سفارشی ثبت نشده.</div>{% endif %}</div>'''
    return page(b,counts=counts,recent=recent)

@app.route('/welcome',methods=['GET','POST'])
@admin_required
def welcome():
    if request.method=='POST':
        set_setting('welcome_message',request.form.get('message','').strip()); flash('✅ پیام خوش‌آمد ذخیره شد.'); return redirect(url_for('welcome'))
    cur=setting('welcome_message') or 'سلام {username} 👋\n\nبه IRANBOT خوش اومدی.'
    b='''<div class="card"><h2>👋 پیام خوش‌آمد</h2><p class="muted">پیامی که بعد از ورود کاربر به ربات نمایش داده می‌شود.</p><form method="post"><textarea name="message" rows="9" required>{{cur}}</textarea><p class="muted small">متغیرها: <b>{username}</b> نام کاربر، <b>{first_name}</b> نام، <b>{user_id}</b> آیدی عددی</p><button>💾 ذخیره تغییرات</button></form></div>'''
    return page(b,cur=cur)

@app.route('/mandatory',methods=['GET','POST'])
@admin_required
def mandatory():
    def channels():
        raw=setting('mandatory_channels')
        try:
            data=json.loads(raw) if raw else []
            if isinstance(data,list): return data
        except Exception: pass
        cid=setting('mandatory_channel_id')
        return [{'id':cid,'title':setting('mandatory_channel_title') or 'کانال ما','link':setting('mandatory_channel_link') or ''}] if cid else []
    if request.method=='POST':
        cid=request.form.get('channel_id','').strip(); title=request.form.get('title','').strip() or cid; link=request.form.get('link','').strip()
        if cid and link:
            cs=[c for c in channels() if str(c.get('id'))!=cid]; cs.append({'id':cid,'title':title,'link':link})
            set_setting('mandatory_channels',json.dumps(cs,ensure_ascii=False)); set_setting('mandatory_enabled','1'); flash('✅ کانال ذخیره شد.')
        return redirect(url_for('mandatory'))
    cs=channels()
    b='''<div class="card"><h2>📢 عضویت اجباری</h2><p class="muted">کاربر باید در همه کانال‌های فعال عضو باشد.</p><form method="post"><label>ID یا @username</label><input name="channel_id" placeholder="@mychannel یا -100123..." required><label>عنوان</label><input name="title" placeholder="کانال اصلی"><label>لینک عضویت</label><input name="link" placeholder="https://t.me/mychannel" required><button>➕ افزودن کانال</button></form></div><div class="card"><div class="row" style="justify-content:space-between"><h3>کانال‌های فعلی</h3><span class="badge {{'ok' if enabled else 'bad'}}">{{'فعال' if enabled else 'خاموش'}}</span></div>{% if channels %}<div class="table-wrap"><table class="table"><tr><th>#</th><th>عنوان</th><th>ID</th><th>لینک</th><th></th></tr>{% for c in channels %}<tr><td>{{loop.index}}</td><td>{{c.title}}</td><td>{{c.id}}</td><td class="small">{{c.link}}</td><td><form method="post" action="{{url_for('mandatory_delete_web')}}"><input type="hidden" name="id" value="{{c.id}}"><button class="danger">🗑 حذف</button></form></td></tr>{% endfor %}</table></div>{% else %}<div class="empty">هنوز کانالی ثبت نشده.</div>{% endif %}<form method="post" action="{{url_for('mandatory_toggle_web')}}"><button class="btn dark">{{'🔴 خاموش کردن' if enabled else '🟢 فعال کردن'}}</button></form></div>'''
    return page(b,channels=cs,enabled=setting('mandatory_enabled')=='1')

@app.route('/mandatory/delete',methods=['POST'])
@admin_required
def mandatory_delete_web():
    cid=request.form.get('id','').strip(); raw=setting('mandatory_channels')
    try: cs=json.loads(raw) if raw else []
    except Exception: cs=[]
    cs=[c for c in cs if str(c.get('id'))!=cid]; set_setting('mandatory_channels',json.dumps(cs,ensure_ascii=False)); set_setting('mandatory_enabled','1' if cs else '0'); flash('🗑 کانال حذف شد.')
    return redirect(url_for('mandatory'))

@app.route('/mandatory/toggle',methods=['POST'])
@admin_required
def mandatory_toggle_web():
    set_setting('mandatory_enabled','0' if setting('mandatory_enabled')=='1' else '1'); flash('🔄 وضعیت عضویت اجباری تغییر کرد.'); return redirect(url_for('mandatory'))

@app.route('/finance',methods=['GET','POST'])
@admin_required
def finance():
    if request.method=='POST':
        card=re.sub(r'\D','',request.form.get('card','')); owner=request.form.get('owner','').strip()
        if len(card)!=16: flash('❌ شماره کارت باید ۱۶ رقم باشد.')
        else: set_setting('card_number',card); set_setting('card_owner',owner); flash('✅ اطلاعات کارت ذخیره شد.')
        return redirect(url_for('finance'))
    with db() as c: pending=c.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0]
    b='''<div class="hero"><h2>💳 بخش مالی</h2><p>اطلاعات کارت فقط در مرحله پرداخت به کاربر نمایش داده می‌شود؛ داخل کیف پول نمایش داده نمی‌شود.</p></div><div class="card"><form method="post"><label>شماره کارت</label><input name="card" value="{{card}}" inputmode="numeric" maxlength="16" placeholder="16 رقم"><label>نام صاحب کارت</label><input name="owner" value="{{owner}}" placeholder="نام و نام خانوادگی"><button>💾 ذخیره</button></form></div><div class="grid"><div class="statcard"><div class="statlabel">پرداخت‌های در انتظار</div><div class="stat">{{pending}}</div></div><div class="statcard"><div class="statlabel">کارت ثبت‌شده</div><div class="stat">{{'✅' if card else '❌'}}</div></div></div>'''
    return page(b,card=setting('card_number'),owner=setting('card_owner'),pending=pending)

@app.route('/finance/report')
@admin_required
def finance_report_web():
    with db() as c:
        approved_receipts=c.execute("SELECT COALESCE(SUM(amount),0),COUNT(*) FROM payments WHERE status='approved' AND kind IN ('order','renewal','wallet_topup','wallet_topup_for_order')").fetchone()
        wallet_topups=c.execute("SELECT COALESCE(SUM(amount),0),COUNT(*) FROM payments WHERE status='approved' AND kind IN ('wallet_topup','wallet_topup_for_order')").fetchone()
        direct=c.execute("SELECT COALESCE(SUM(amount),0),COUNT(*) FROM payments WHERE status='approved' AND kind IN ('order','renewal')").fetchone()
        wallet_buy=c.execute("SELECT COALESCE(SUM(amount),0),COUNT(*) FROM payments WHERE status='approved' AND kind IN ('wallet_purchase','renewal_wallet')").fetchone()
        renew=c.execute("SELECT COALESCE(SUM(amount),0),COUNT(*) FROM payments WHERE status='approved' AND kind IN ('renewal','renewal_wallet')").fetchone()
        wallet_total=c.execute("SELECT COALESCE(SUM(balance),0) FROM wallets").fetchone()[0]
        pending=c.execute("SELECT COALESCE(SUM(amount),0),COUNT(*) FROM payments WHERE status='pending'").fetchone()
        recent=c.execute("SELECT id,user_id,kind,order_id,amount,status,created_at FROM payments ORDER BY id DESC LIMIT 30").fetchall()
    b='''<div class="hero"><h2>📊 گزارش مالی</h2><p>نمایش دقیق واریزی رسیدها، شارژ کیف پول، خرید مستقیم، خرید از کیف پول، تمدیدها و پول آماده داخل کیف پول کاربران.</p></div>
    <div class="grid">
      <div class="statcard"><div class="staticon">💰</div><div class="statlabel">کل واریزی رسیدهای تأییدشده</div><div class="stat">{{approved[0]|money}} تومان</div><div class="kpi">{{approved[1]}} رسید</div></div>
      <div class="statcard"><div class="staticon">💳</div><div class="statlabel">شارژ کیف پول</div><div class="stat">{{topups[0]|money}} تومان</div><div class="kpi">{{topups[1]}} مورد</div></div>
      <div class="statcard"><div class="staticon">🛒</div><div class="statlabel">خرید مستقیم</div><div class="stat">{{direct[0]|money}} تومان</div><div class="kpi">{{direct[1]}} مورد</div></div>
      <div class="statcard"><div class="staticon">👛</div><div class="statlabel">خرید از کیف پول</div><div class="stat">{{wallet_buy[0]|money}} تومان</div><div class="kpi">{{wallet_buy[1]}} مورد</div></div>
      <div class="statcard"><div class="staticon">🔄</div><div class="statlabel">تمدید سرویس</div><div class="stat">{{renew[0]|money}} تومان</div><div class="kpi">{{renew[1]}} مورد</div></div>
      <div class="statcard"><div class="staticon">💵</div><div class="statlabel">پول آماده در کیف پول کاربران</div><div class="stat">{{wallet_total|money}} تومان</div><div class="kpi">موجودی فعلی کاربران</div></div>
      <div class="statcard"><div class="staticon">⏳</div><div class="statlabel">پرداخت‌های در انتظار</div><div class="stat">{{pending[0]|money}} تومان</div><div class="kpi">{{pending[1]}} مورد</div></div>
    </div>
    <div class="card"><h3>🧾 آخرین تراکنش‌ها</h3><div class="table-wrap"><table class="table"><tr><th>ID</th><th>User</th><th>نوع</th><th>Order</th><th>مبلغ</th><th>وضعیت</th><th>تاریخ</th></tr>{% for r in recent %}<tr><td>#{{r[0]}}</td><td>{{r[1]}}</td><td>{{labels.get(r[2],r[2])}}</td><td>{{r[3] or '-'}}</td><td>{{r[4]|money}} تومان</td><td><span class="badge {{'ok' if r[5]=='approved' else 'warn' if r[5]=='pending' else 'bad'}}">{{r[5]}}</span></td><td>{{r[6]}}</td></tr>{% endfor %}</table></div></div>'''
    labels={'order':'🛒 خرید مستقیم','renewal':'🔄 تمدید مستقیم','wallet_topup':'💳 شارژ کیف پول','wallet_topup_for_order':'💳 شارژ برای خرید','wallet_purchase':'👛 خرید از کیف پول','renewal_wallet':'🔄 تمدید از کیف پول'}
    return page(b,approved=approved_receipts,topups=wallet_topups,direct=direct,wallet_buy=wallet_buy,renew=renew,wallet_total=wallet_total,pending=pending,recent=recent,labels=labels)


@app.route('/panels',methods=['GET','POST'])
@admin_required
def panels():
    if request.method=='POST':
        pt=request.form.get('panel_type','').strip(); name=request.form.get('name','').strip(); address=request.form.get('address','').strip(); user=request.form.get('username','').strip(); pw=request.form.get('password','').strip()
        if not (pt and name and address and user and pw): flash('❌ اطلاعات پنل ناقص است.'); return redirect(url_for('panels'))
        with db() as c: c.execute('INSERT INTO panels(panel_type,name,address,username,password,status) VALUES(?,?,?,?,?,?)',(pt,name,clean_base_url(address),user,pw,'manual'))
        flash('✅ پنل اضافه شد. حالا می‌توانی تست اتصال بگیری.'); return redirect(url_for('panels'))
    with db() as c: rows=c.execute('SELECT id,panel_type,name,address,status FROM panels ORDER BY id DESC').fetchall()
    b='''<div class="card"><h2>➕ افزودن پنل</h2><form method="post"><div class="grid"><div><label>نوع پنل</label><select name="panel_type"><option value="pasarguard">Pasarguard</option><option value="marzban">Marzban</option><option value="3xui">3x-ui</option></select></div><div><label>نام پنل</label><input name="name" placeholder="مثلاً PG اصلی" required></div></div><label>آدرس</label><input name="address" placeholder="https://panel.example.com:2096" required><div class="grid"><div><label>Username</label><input name="username" required></div><div><label>Password</label><input name="password" type="password" required></div></div><button>➕ ثبت پنل</button></form></div><div class="card"><h2>🖥 پنل‌ها</h2>{% if rows %}<div class="grid">{% for r in rows %}<div class="statcard"><div class="row" style="justify-content:space-between"><b>{{r[2]}}</b><span class="badge {{'ok' if r[4]=='connected' else 'warn' if r[4]=='manual' else 'bad'}}">{{r[4]}}</span></div><p class="muted small">#{{r[0]}} · {{r[1]}}</p><p class="mini">{{r[3]}}</p><div class="actions"><a class="btn blue" href="{{url_for('panel_test_web',pid=r[0])}}">🧪 تست اتصال</a>{% if r[1]=='pasarguard' %}<a class="btn dark" href="{{url_for('panel_groups_web',pid=r[0])}}">🔗 Groupها</a><a class="btn dark" href="{{url_for('free_test_settings_web',pid=r[0])}}">🎁 تنظیم تست</a>{% endif %}<form method="post" action="{{url_for('panel_delete_web')}}"><input type="hidden" name="id" value="{{r[0]}}"><button class="danger">🗑 حذف</button></form></div></div>{% endfor %}</div>{% else %}<div class="empty">هنوز پنلی ثبت نشده.</div>{% endif %}</div>'''
    return page(b,rows=rows)

@app.route('/panels/test/<int:pid>')
@admin_required
def panel_test_web(pid):
    with db() as c: row=c.execute('SELECT panel_type,address,username,password FROM panels WHERE id=?',(pid,)).fetchone()
    if not row: flash('❌ پنل پیدا نشد.'); return redirect(url_for('panels'))
    ok,reason,_,_,client=panel_login_sync(*row)
    if client: client.close()
    with db() as c: c.execute('UPDATE panels SET status=? WHERE id=?',('connected' if ok else 'error',pid))
    flash(('🟢 اتصال موفق بود.' if ok else '🔴 تست اتصال ناموفق: '+reason))
    return redirect(url_for('panels'))

@app.route('/panels/groups/<int:pid>',methods=['GET','POST'])
@admin_required
def panel_groups_web(pid):
    try:
        with db() as c: prow=c.execute('SELECT name,panel_type FROM panels WHERE id=?',(pid,)).fetchone()
        if not prow or prow[1]!='pasarguard':
            flash('❌ پنل Pasarguard پیدا نشد.')
            return redirect(url_for('panels'))
        groups,err=fetch_groups_sync(pid)
        if request.method=='POST':
            selected=set(request.form.getlist('group_ids'))
            with db() as c:
                for gid,name,tags in groups:
                    if str(gid) in selected:
                        c.execute('INSERT OR REPLACE INTO panel_groups(panel_id,group_id,group_name,inbound_tags) VALUES(?,?,?,?)',(pid,gid,name,','.join(tags)))
                    else:
                        c.execute('DELETE FROM panel_groups WHERE panel_id=? AND group_id=?',(pid,gid))
            flash('✅ Groupهای انتخاب‌شده ذخیره شدند.')
            return redirect(url_for('panel_groups_web',pid=pid))
        with db() as c: selected={str(r[0]) for r in c.execute('SELECT group_id FROM panel_groups WHERE panel_id=?',(pid,)).fetchall()}
        b="""<div class="card"><div class="row" style="justify-content:space-between"><div><h2>🔗 مدیریت Groupها</h2><p class="muted">پنل: {{name}} — Groupهای فعال برای ساخت سرویس از اینجا انتخاب می‌شوند.</p></div><a class="btn dark" href="{{url_for('panels')}}">↩️ پنل‌ها</a></div>{% if err %}<div class="flash bad">⚠️ {{err}}</div>{% endif %}{% if groups %}<form method="post"><div class="checkgrid">{% for g in groups %}<label class="check"><input type="checkbox" name="group_ids" value="{{g[0]}}" {% if g[0]|string in selected %}checked{% endif %}><b>{{g[1]}}</b><div class="mini">ID: {{g[0]}}{% if g[2] %}<br>Inbound: {{g[2]|join(', ')}}{% endif %}</div></label>{% endfor %}</div><div class="actions" style="margin-top:15px"><button>💾 ذخیره Groupها</button><a class="btn dark" href="{{url_for('panel_groups_web',pid=pid)}}">🔄 بروزرسانی</a></div></form>{% else %}<div class="empty">Group قابل دسترسی پیدا نشد.<br><span class="mini">اگر اتصال API موقتاً در دسترس نیست، ابتدا اتصال پنل را تست کن و دوباره وارد این بخش شو.</span></div>{% endif %}</div>"""
        return page(b,name=prow[0],groups=groups,selected=selected,err=err,pid=pid)
    except Exception as e:
        msg=str(e)[:500].replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        return page('<div class="card"><h2 class="bad">❌ خطا در بخش Groupها</h2><p class="muted">صفحه مدیریت Group نتوانست کامل اجرا شود.</p><div class="flash bad">'+msg+'</div><a class="btn dark" href="'+url_for('panels')+'">↩️ بازگشت به پنل‌ها</a></div>')

@app.route('/panels/delete',methods=['POST'])
@admin_required
def panel_delete_web():
    
    try: pid=int(request.form.get('id','0'))
    except Exception: flash('❌ شناسه نامعتبر است.'); return redirect(url_for('panels'))
    with db() as c:
        c.execute('UPDATE products SET panel_id=NULL WHERE panel_id=?',(pid,)); c.execute('DELETE FROM panel_groups WHERE panel_id=?',(pid,)); c.execute('DELETE FROM free_test_settings WHERE panel_id=?',(pid,)); c.execute('DELETE FROM panels WHERE id=?',(pid,))
    flash('🗑 پنل حذف شد.'); return redirect(url_for('panels'))

@app.route('/free-tests')
@admin_required
def free_tests():
    with db() as c: rows=c.execute('SELECT p.id,p.name,s.max_tests,s.data_limit_mb,s.expire_hours,s.enabled FROM panels p JOIN free_test_settings s ON s.panel_id=p.id ORDER BY p.id').fetchall()
    b='''<div class="hero"><h2>🎁 تست رایگان</h2><p>حجم، زمان و تعداد تست از همین وب‌پنل تنظیم می‌شود و کاربر هیچ‌کدام را انتخاب نمی‌کند.</p></div><div class="grid">{% for r in rows %}<div class="statcard"><b>{{r[1]}}</b><div class="statlabel">تعداد برای هر کاربر</div><div class="stat">{{r[2]}}</div><p>📦 {{r[3]}} MB · ⏳ {{r[4]}} ساعت</p><span class="badge {{'ok' if r[5] else 'bad'}}">{{'فعال' if r[5] else 'خاموش'}}</span><div style="margin-top:12px"><a class="btn blue" href="{{url_for('free_test_settings_web',pid=r[0])}}">⚙️ تنظیم</a></div></div>{% else %}<div class="card empty">برای پنلی تست رایگان تنظیم نشده.</div>{% endfor %}</div>'''
    return page(b,rows=rows)

@app.route('/panels/free-test/<int:pid>',methods=['GET','POST'])
@admin_required
def free_test_settings_web(pid):
    with db() as c:
        prow=c.execute("SELECT name FROM panels WHERE id=? AND panel_type='pasarguard'",(pid,)).fetchone()
        st=c.execute('SELECT max_tests,data_limit_mb,expire_hours,enabled FROM free_test_settings WHERE panel_id=?',(pid,)).fetchone()
    if not prow: flash('❌ پنل Pasarguard پیدا نشد.'); return redirect(url_for('panels'))
    if request.method=='POST':
        try:
            max_tests=int(request.form.get('max_tests','1')); mb=int(request.form.get('mb','100')); hours=int(request.form.get('hours','1')); enabled=1 if request.form.get('enabled')=='1' else 0
            if min(max_tests,mb,hours)<=0: raise ValueError
        except Exception:
            flash('❌ مقادیر تست باید عدد مثبت باشند.'); return redirect(url_for('free_test_settings_web',pid=pid))
        with db() as c: c.execute('INSERT OR REPLACE INTO free_test_settings(panel_id,max_tests,data_limit_mb,expire_hours,enabled) VALUES(?,?,?,?,?)',(pid,max_tests,mb,hours,enabled))
        flash('✅ تنظیمات تست رایگان ذخیره شد.'); return redirect(url_for('free_test_settings_web',pid=pid))
    st=st or (1,100,1,0)
    b='''<div class="card"><div class="row" style="justify-content:space-between"><div><h2>🎁 تنظیم تست رایگان</h2><p class="muted">پنل: {{name}}</p></div><a class="btn dark" href="{{url_for('panels')}}">↩️ پنل‌ها</a></div><form method="post"><div class="grid"><div><label>تعداد تست برای هر کاربر</label><input name="max_tests" type="number" min="1" value="{{st[0]}}"></div><div><label>حجم تست (MB)</label><input name="mb" type="number" min="1" value="{{st[1]}}"></div><div><label>مدت تست (ساعت)</label><input name="hours" type="number" min="1" value="{{st[2]}}"></div></div><div class="switch"><span>فعال بودن تست رایگان</span><input style="width:auto;margin:0" type="checkbox" name="enabled" value="1" {% if st[3] %}checked{% endif %}></div><button>💾 ذخیره تنظیمات</button></form></div>'''
    return page(b,name=prow[0],st=st)

@app.route('/products',methods=['GET','POST'])
@admin_required
def products():
    if request.method=='POST':
        try:
            price=int(request.form.get('price','0').replace(',','').replace('٬',''))
            gb=int(request.form.get('gb','1')); days=int(request.form.get('days','1')); pid=int(request.form.get('panel_id','0'))
            raw_cat=request.form.get('category_id','').strip(); category_id=int(raw_cat) if raw_cat else None
        except Exception:
            flash('❌ مقادیر عددی صحیح نیست.'); return redirect(url_for('products'))
        name=request.form.get('name','').strip()
        if not name or min(price,gb,days,pid)<=0:
            flash('❌ اطلاعات محصول ناقص است.'); return redirect(url_for('products'))
        with db() as c:
            if category_id is not None and not c.execute('SELECT 1 FROM product_categories WHERE id=?',(category_id,)).fetchone():
                category_id=None
            c.execute('INSERT INTO products(name,price,panel_id,data_limit_gb,expire_days,category_id,active) VALUES(?,?,?,?,?,?,1)',(name,f'{price:,} تومان',pid,gb,days,category_id))
        flash('✅ محصول اضافه شد.'); return redirect(url_for('products'))
    with db() as c:
        ps=c.execute('SELECT id,panel_type,name FROM panels ORDER BY id DESC').fetchall()
        cats=c.execute('SELECT id,name FROM product_categories ORDER BY id').fetchall()
        rows=c.execute('''SELECT p.id,p.name,p.price,p.data_limit_gb,p.expire_days,pa.name,p.active,COALESCE(pc.name,'بدون دسته‌بندی')
                          FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id LEFT JOIN product_categories pc ON pc.id=p.category_id ORDER BY p.id DESC''').fetchall()
    b='''<div class="hero"><h2>🛒 محصولات</h2><p>محصولات را بساز، ویرایش کن و در صورت نیاز به یک دسته‌بندی اختصاص بده.</p><div class="actions" style="margin-top:12px"><a class="btn blue" href="{{url_for('product_categories_web')}}">📂 مدیریت دسته‌بندی‌ها</a></div></div>
    <div class="card"><h2>➕ افزودن محصول</h2><form method="post"><div class="grid"><input name="name" placeholder="نام محصول" required><input name="price" placeholder="قیمت تومان" required><select name="panel_id" required><option value="">انتخاب پنل</option>{% for p in ps %}<option value="{{p[0]}}">#{{p[0]}} {{p[2]}} ({{p[1]}})</option>{% endfor %}</select><input name="gb" type="number" min="1" placeholder="حجم GB" required><input name="days" type="number" min="1" placeholder="مدت روز" required><select name="category_id"><option value="">🚫 بدون دسته‌بندی</option>{% for c in cats %}<option value="{{c[0]}}">📂 {{c[1]}}</option>{% endfor %}</select></div><button>➕ ثبت محصول</button></form></div>
    <div class="card"><h2>📋 محصولات</h2><div class="table-wrap"><table class="table"><tr><th>ID</th><th>نام</th><th>قیمت</th><th>حجم</th><th>مدت</th><th>پنل</th><th>دسته‌بندی</th><th>وضعیت</th><th></th></tr>{% for r in rows %}<tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3]}}GB</td><td>{{r[4]}} روز</td><td>{{r[5] or '-'}}</td><td>📂 {{r[7]}}</td><td>{{'فعال' if r[6] else 'غیرفعال'}}</td><td><div class="actions"><a class="btn blue" href="{{url_for('product_edit_web',pid=r[0])}}">✏️ ویرایش</a><form method="post" action="{{url_for('product_delete_web')}}"><input type="hidden" name="id" value="{{r[0]}}"><button class="danger">🗑 حذف</button></form></div></td></tr>{% endfor %}</table></div>{% if not rows %}<div class="empty">هنوز محصولی ثبت نشده.</div>{% endif %}</div>'''
    return page(b,ps=ps,cats=cats,rows=rows)

@app.route('/products/edit/<int:pid>',methods=['GET','POST'])
@admin_required
def product_edit_web(pid):
    with db() as c:
        row=c.execute('SELECT id,name,price,panel_id,data_limit_gb,expire_days,category_id,active FROM products WHERE id=?',(pid,)).fetchone()
        ps=c.execute('SELECT id,panel_type,name FROM panels ORDER BY id DESC').fetchall()
        cats=c.execute('SELECT id,name FROM product_categories ORDER BY id').fetchall()
    if not row:
        flash('❌ محصول پیدا نشد.'); return redirect(url_for('products'))
    if request.method=='POST':
        try:
            price=int(request.form.get('price','0').replace(',','').replace('٬','')); gb=int(request.form.get('gb','1')); days=int(request.form.get('days','1')); panel_id=int(request.form.get('panel_id','0')); active=1 if request.form.get('active')=='1' else 0
            raw_cat=request.form.get('category_id','').strip(); category_id=int(raw_cat) if raw_cat else None
        except Exception:
            flash('❌ مقادیر عددی صحیح نیست.'); return redirect(url_for('product_edit_web',pid=pid))
        name=request.form.get('name','').strip()
        if not name or min(price,gb,days,panel_id)<=0:
            flash('❌ اطلاعات محصول ناقص است.'); return redirect(url_for('product_edit_web',pid=pid))
        with db() as c:
            if category_id is not None and not c.execute('SELECT 1 FROM product_categories WHERE id=?',(category_id,)).fetchone(): category_id=None
            c.execute('UPDATE products SET name=?,price=?,panel_id=?,data_limit_gb=?,expire_days=?,category_id=?,active=? WHERE id=?',(name,f'{price:,} تومان',panel_id,gb,days,category_id,active,pid))
        flash(f'✅ محصول #{pid} ویرایش شد.'); return redirect(url_for('products'))
    b='''<div class="card"><div class="row" style="justify-content:space-between"><div><h2>✏️ ویرایش محصول #{{row[0]}}</h2><p class="muted">دسته‌بندی اختیاری است.</p></div><a class="btn dark" href="{{url_for('products')}}">↩️ محصولات</a></div><form method="post"><label>نام محصول</label><input name="name" value="{{row[1]}}" required><label>قیمت تومان</label><input name="price" value="{{row[2]|replace(' تومان','')|replace(',','')}}" required><label>پنل</label><select name="panel_id" required>{% for p in ps %}<option value="{{p[0]}}" {% if row[3]==p[0] %}selected{% endif %}>#{{p[0]}} {{p[2]}} ({{p[1]}})</option>{% endfor %}</select><div class="grid"><div><label>حجم GB</label><input name="gb" type="number" min="1" value="{{row[4] or 1}}" required></div><div><label>مدت روز</label><input name="days" type="number" min="1" value="{{row[5] or 1}}" required></div><div><label>دسته‌بندی</label><select name="category_id"><option value="">🚫 بدون دسته‌بندی</option>{% for c in cats %}<option value="{{c[0]}}" {% if row[6]==c[0] %}selected{% endif %}>📂 {{c[1]}}</option>{% endfor %}</select></div></div><div class="switch"><span>فعال بودن محصول</span><input style="width:auto;margin:0" type="checkbox" name="active" value="1" {% if row[7] %}checked{% endif %}></div><button>💾 ذخیره تغییرات</button></form></div>'''
    return page(b,row=row,ps=ps,cats=cats)

@app.route('/product-categories',methods=['GET','POST'])
@admin_required
def product_categories_web():
    if request.method=='POST':
        action=request.form.get('action','create')
        if action=='create':
            name=request.form.get('name','').strip()
            if not name: flash('❌ اسم دسته‌بندی را وارد کن.')
            elif len(name)>60: flash('❌ اسم دسته‌بندی حداکثر 60 کاراکتر باشد.')
            else:
                try:
                    with db() as c: c.execute('INSERT INTO product_categories(name) VALUES(?)',(name,))
                    flash(f'✅ دسته‌بندی «{name}» ساخته شد.')
                except sqlite3.IntegrityError: flash('❌ این دسته‌بندی قبلاً وجود دارد.')
        elif action=='delete':
            try: cid=int(request.form.get('id','0'))
            except Exception: cid=0
            with db() as c:
                row=c.execute('SELECT name FROM product_categories WHERE id=?',(cid,)).fetchone()
                if row:
                    c.execute('UPDATE products SET category_id=NULL WHERE category_id=?',(cid,)); c.execute('DELETE FROM product_categories WHERE id=?',(cid,)); flash(f'🗑 دسته‌بندی «{row[0]}» حذف شد؛ محصولات آن بدون دسته‌بندی ماندند.')
                else: flash('❌ دسته‌بندی پیدا نشد.')
        return redirect(url_for('product_categories_web'))
    with db() as c:
        rows=c.execute('SELECT c.id,c.name,(SELECT COUNT(*) FROM products p WHERE p.category_id=c.id AND p.active=1) FROM product_categories c ORDER BY c.id').fetchall()
    b='''<div class="hero"><h2>📂 دسته‌بندی محصولات</h2><p>ساخت دسته‌بندی و مشاهده تعداد محصولات هر دسته.</p><div class="actions" style="margin-top:12px"><a class="btn dark" href="{{url_for('products')}}">↩️ محصولات</a></div></div><div class="card"><h3>➕ ساخت دسته‌بندی</h3><form method="post"><input type="hidden" name="action" value="create"><label>اسم دسته‌بندی</label><input name="name" maxlength="60" placeholder="مثلاً VIP" required><button>➕ ساخت دسته‌بندی</button></form></div><div class="card"><h3>📋 دسته‌بندی‌ها</h3>{% if rows %}<div class="table-wrap"><table class="table"><tr><th>ID</th><th>نام</th><th>محصولات</th><th>عملیات</th></tr>{% for r in rows %}<tr><td>{{r[0]}}</td><td>📂 {{r[1]}}</td><td>{{r[2]}}</td><td><form method="post"><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="{{r[0]}}"><button class="danger">🗑 حذف</button></form></td></tr>{% endfor %}</table></div>{% else %}<div class="empty">هنوز دسته‌بندی‌ای ساخته نشده.</div>{% endif %}</div>'''
    return page(b,rows=rows)

@app.route('/products/delete',methods=['POST'])
@admin_required
def product_delete_web():
    pid=int(request.form.get('id','0'))
    with db() as c:
        used=c.execute('SELECT COUNT(*) FROM orders WHERE product_id=?',(pid,)).fetchone()[0]
        if used: c.execute('UPDATE products SET active=0 WHERE id=?',(pid,)); flash('⚠️ محصول سفارش داشته؛ غیرفعال شد.')
        else: c.execute('DELETE FROM products WHERE id=?',(pid,)); c.execute('DELETE FROM configs WHERE product_id=?',(pid,)); flash('🗑 محصول حذف شد.')
    return redirect(url_for('products'))

@app.route('/users')
@admin_required
def users():
    q=request.args.get('q','').strip()
    with db() as c:
        if q:
            like=f'%{q}%'; rows=c.execute("SELECT user_id,username,first_name,is_blocked FROM users WHERE CAST(user_id AS TEXT) LIKE ? OR username LIKE ? OR first_name LIKE ? ORDER BY last_seen DESC LIMIT 200",(like,like,like)).fetchall()
        else: rows=c.execute('SELECT user_id,username,first_name,is_blocked FROM users ORDER BY last_seen DESC LIMIT 200').fetchall()
        rows2=[]
        for r in rows:
            bal=c.execute('SELECT COALESCE(balance,0) FROM wallets WHERE user_id=?',(r[0],)).fetchone(); count=c.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='paid'",(r[0],)).fetchone()[0]; rows2.append(r+(bal[0] if bal else 0,count))
    b='''<div class="hero"><h2>👥 مدیریت کاربران</h2><p>مدیریت کاربران فقط از وب‌پنل انجام می‌شود: موجودی، سفارش‌ها و مسدودسازی.</p></div><div class="card"><form class="row" method="get"><input style="flex:1;min-width:220px;margin:0" name="q" value="{{q}}" placeholder="جستجو با ID، username یا نام"><button>🔎 جستجو</button></form></div><div class="card"><div class="table-wrap"><table class="table"><tr><th>ID</th><th>Username</th><th>نام</th><th>موجودی</th><th>سرویس</th><th>وضعیت</th><th></th></tr>{% for r in rows %}<tr><td>{{r[0]}}</td><td>@{{r[1] or '-'}}</td><td>{{r[2] or '-'}}</td><td>{{"{:,}".format(r[4])}} تومان</td><td>{{r[5]}}</td><td><span class="badge {{'bad' if r[3] else 'ok'}}">{{'🚫 مسدود' if r[3] else '✅ فعال'}}</span></td><td><a class="btn dark" href="{{url_for('user_detail_web',uid=r[0])}}">مدیریت</a></td></tr>{% else %}<tr><td colspan="7" class="empty">کاربری پیدا نشد.</td></tr>{% endfor %}</table></div></div>'''
    return page(b,rows=rows2,q=q)

@app.route('/users/<int:uid>',methods=['GET','POST'])
@admin_required
def user_detail_web(uid):
    if request.method=='POST':
        action=request.form.get('action')
        try: amount=int(request.form.get('amount','0') or 0)
        except Exception: amount=0
        with db() as c:
            c.execute('INSERT OR IGNORE INTO wallets(user_id,balance) VALUES(?,0)',(uid,))
            if action=='add' and amount>0:
                c.execute('UPDATE wallets SET balance=balance+? WHERE user_id=?',(amount,uid)); flash(f'✅ {amount:,} تومان به کیف پول کاربر اضافه شد.')
                notify_text=f'🎉 کیف پول شما شارژ شد.\n\n💰 مبلغ افزایش: {amount:,} تومان'
            elif action=='sub' and amount>0:
                c.execute('UPDATE wallets SET balance=MAX(0,balance-?) WHERE user_id=?',(amount,uid)); flash(f'✅ {amount:,} تومان از کیف پول کاربر کم شد.'); notify_text=f'ℹ️ موجودی کیف پول شما {amount:,} تومان کاهش یافت.'
            else: notify_text=''
            if action=='block': c.execute('UPDATE users SET is_blocked=1 WHERE user_id=?',(uid,)); flash('🚫 کاربر مسدود شد.')
            elif action=='unblock': c.execute('UPDATE users SET is_blocked=0 WHERE user_id=?',(uid,)); flash('✅ مسدودی کاربر برداشته شد.')
        if notify_text: telegram_notify(uid,notify_text)
        return redirect(url_for('user_detail_web',uid=uid))
    with db() as c:
        u=c.execute('SELECT user_id,username,first_name,is_blocked,created_at,last_seen FROM users WHERE user_id=?',(uid,)).fetchone()
        bal=c.execute('SELECT COALESCE(balance,0) FROM wallets WHERE user_id=?',(uid,)).fetchone(); orders=c.execute("SELECT o.id,p.name,o.status,o.subscription,o.panel_username,o.created_at FROM orders o JOIN products p ON p.id=o.product_id WHERE o.user_id=? AND o.status='paid' ORDER BY o.id DESC",(uid,)).fetchall()
    if not u: return page('<div class="card"><h2>❌ کاربر پیدا نشد</h2><a class="btn dark" href="{{url_for(\'users\')}}">بازگشت</a></div>')
    b='''<div class="hero"><div class="row" style="justify-content:space-between"><div><h2>👤 {{u[2] or u[1] or u[0]}}</h2><p>@{{u[1] or '-'}} · ID {{u[0]}}</p></div><span class="badge {{'bad' if u[3] else 'ok'}}">{{'🚫 مسدود' if u[3] else '✅ فعال'}}</span></div></div><div class="grid"><div class="statcard"><div class="statlabel">موجودی کیف پول</div><div class="stat">{{"{:,}".format(bal)}}</div><div class="kpi">تومان</div></div><div class="statcard"><div class="statlabel">سرویس‌های فعال/تحویل‌شده</div><div class="stat">{{orders|length}}</div></div></div><div class="card"><h3>💰 مدیریت موجودی</h3><form method="post"><input name="amount" type="number" min="1" placeholder="مبلغ به تومان"><div class="actions"><button name="action" value="add">➕ افزایش موجودی</button><button name="action" value="sub" class="danger">➖ کاهش موجودی</button></div></form><form method="post" style="margin-top:10px"><button name="action" value="{{'unblock' if u[3] else 'block'}}" class="{{'btn dark' if u[3] else 'danger'}}">{{'✅ رفع مسدودی' if u[3] else '🚫 مسدود کردن'}}</button></form></div><div class="card"><h3>📦 سفارش‌های تأییدشده</h3>{% for o in orders %}<div class="card"><div class="row" style="justify-content:space-between"><b>#{{o[0]}} — {{o[1]}}</b><span class="badge ok">paid</span></div><p class="muted small">{{o[5]}} · {{o[4] or '-'}}</p><div class="mini">{{o[3] or 'Subscription موجود نیست'}}</div></div>{% else %}<div class="empty">سفارشی ندارد.</div>{% endfor %}</div>'''
    return page(b,u=u,bal=(bal[0] if bal else 0),orders=orders)

@app.route('/orders')
@admin_required
def orders():
    with db() as c: rows=c.execute('SELECT o.id,o.user_id,p.name,o.status,o.subscription,o.created_at FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT 150').fetchall()
    b='''<div class="card"><h2>📦 سفارش‌ها</h2><div class="table-wrap"><table class="table"><tr><th>ID</th><th>User</th><th>محصول</th><th>وضعیت</th><th>Subscription</th><th>تاریخ</th></tr>{% for r in rows %}<tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td><span class="badge {{'ok' if r[3]=='paid' else 'warn'}}">{{r[3]}}</span></td><td class="mini">{{r[4] or '-'}}</td><td>{{r[5]}}</td></tr>{% endfor %}</table></div></div>'''
    return page(b,rows=rows)

@app.route('/backup',methods=['GET','POST'])
@admin_required
def backup():
    if request.method=='POST':
        action=request.form.get('action','')
        if action=='weekly_on':
            set_setting('backup_weekly_enabled','1')
            from datetime import datetime, timezone
            set_setting('backup_weekly_last_sent',datetime.now(timezone.utc).isoformat())
            flash('🟢 Backup هفتگی فعال شد؛ هر 7 روز برای ادمین‌ها ارسال می‌شود.')
        elif action=='weekly_off':
            set_setting('backup_weekly_enabled','0')
            flash('🔴 Backup هفتگی غیرفعال شد.')
        return redirect(url_for('backup'))
    enabled=setting('backup_weekly_enabled')=='1'
    last=setting('backup_weekly_last_sent') or 'هنوز ارسال نشده'
    b="""<div class='hero'><h2>💾 پشتیبان‌گیری و بازیابی</h2><p>یک فایل کامل از اطلاعات Database بساز، دانلود کن یا در صورت نیاز Backup قبلی را برگردان.</p></div><div class='card'><h3>📥 گرفتن فایل Backup</h3><p class='muted'>کل اطلاعات ذخیره‌شده در SQLite، شامل کاربران، کیف پول‌ها، پنل‌ها، Groupها، محصولات، سفارش‌ها، پرداخت‌ها، تنظیمات، تیکت‌ها و سایر جدول‌های Database در یک فایل ذخیره می‌شود.</p><a class='btn blue' href='{{url_for('backup_download')}}'>💾 ساخت و دانلود Backup</a></div><div class='card'><h3>📤 وارد کردن فایل Backup</h3><p class='muted'>فایل Backup قبلی را انتخاب کن. فایل قبل از بازیابی از نظر SQLite و جدول‌های اصلی بررسی می‌شود.</p><form method='post' action='{{url_for('backup_restore')}}' enctype='multipart/form-data'><input type='file' name='backup_file' accept='.db,.sqlite,.sqlite3' required><button class='danger'>📤 بازیابی Backup</button></form></div><div class='card'><div class='row' style='justify-content:space-between'><div><h3>📅 Backup خودکار هر 7 روز</h3><p class='muted'>وقتی فعال باشد، Bot هر 7 روز یک فایل کامل Backup برای همه ADMIN_IDS ارسال می‌کند.</p></div><span class='badge {{'ok' if enabled else 'bad'}}'>{{'🟢 فعال' if enabled else '🔴 غیرفعال'}}</span></div><p class='small muted'>آخرین ارسال: {{last}}</p><form method='post'><button name='action' value='{{'weekly_off' if enabled else 'weekly_on'}}' class='{{'danger' if enabled else ''}}'>{{'2️⃣ غیرفعال کردن' if enabled else '1️⃣ فعال کردن'}}</button></form></div>"""
    return page(b,enabled=enabled,last=last)

@app.route('/backup/download')
@admin_required
def backup_download():
    path=None
    try:
        path=create_backup_file_sync()
        response=send_file(path,as_attachment=True,download_name=os.path.basename(path),mimetype='application/octet-stream')
        response.call_on_close(lambda: os.path.exists(path) and os.remove(path))
        return response
    except Exception as e:
        flash(f'❌ ساخت Backup ناموفق بود: {str(e)[:400]}')
        return redirect(url_for('backup'))

@app.route('/backup/restore',methods=['POST'])
@admin_required
def backup_restore():
    uploaded=request.files.get('backup_file')
    if not uploaded or not uploaded.filename:
        flash('❌ فایل Backup انتخاب نشده است.')
        return redirect(url_for('backup'))
    suffix=os.path.splitext(uploaded.filename)[1].lower() or '.db'
    if suffix not in ('.db','.sqlite','.sqlite3'):
        flash('❌ فقط فایل‌های .db، .sqlite و .sqlite3 پذیرفته می‌شوند.')
        return redirect(url_for('backup'))
    fd,path=tempfile.mkstemp(prefix='iranbot_upload_',suffix=suffix)
    os.close(fd)
    try:
        uploaded.save(path)
        ok,reason=restore_backup_file_sync(path)
        if ok: flash('✅ Backup با موفقیت بازیابی شد و Database جایگزین شد.')
        else: flash(f'❌ بازیابی Backup ناموفق بود: {reason}')
    finally:
        try: os.remove(path)
        except OSError: pass
    return redirect(url_for('backup'))

@app.route('/raffle',methods=['GET','POST'])
@admin_required
def raffle():
    if request.method=='POST':
        action=request.form.get('action','')
        try: rid=int(request.form.get('id','0') or 0)
        except Exception: rid=0
        if action=='delete':
            with db() as c:
                c.execute('DELETE FROM raffle_participants WHERE raffle_id=?',(rid,)); c.execute('DELETE FROM raffles WHERE id=?',(rid,))
            flash('🗑 قرعه‌کشی حذف شد.'); return redirect(url_for('raffle'))
        if action=='draw':
            with db() as c:
                r=c.execute('SELECT prize_type,prize_name,prize_amount,status FROM raffles WHERE id=?',(rid,)).fetchone(); rows=c.execute('SELECT user_id FROM raffle_participants WHERE raffle_id=?',(rid,)).fetchall()
                if not r or r[3]!='active' or not rows:
                    flash('❌ قرعه‌کشی فعال نیست یا شرکت‌کننده ندارد.'); return redirect(url_for('raffle'))
                import random
                winner=random.choice([x[0] for x in rows])
                c.execute("UPDATE raffles SET status='drawn' WHERE id=?",(rid,)); c.execute('DELETE FROM raffle_participants WHERE raffle_id=?',(rid,))
            prize=(f'{r[2]:,} تومان' if r[0]=='money' else r[1])
            telegram_notify(winner,f'🎉 تبریک!\nشما برنده قرعه‌کشی #{rid} شدید.\n🎁 جایزه: {prize}\n\nبرای دریافت جایزه با ادمین در ارتباط باشید.')
            flash(f'🎉 برنده قرعه‌کشی #{rid}: {winner} — جایزه: {prize}'); return redirect(url_for('raffle'))
        if action=='create':
            pt=request.form.get('prize_type','item'); name=request.form.get('prize_name','').strip()
            try: amount=int(request.form.get('prize_amount','0') or 0); fee=int(request.form.get('entry_fee','0') or 0); limit=int(request.form.get('max_participants','30') or 30)
            except Exception: amount=fee=-1; limit=0
            if pt not in ('money','item') or amount<0 or fee<0 or not 1<=limit<=30 or (pt=='item' and not name):
                flash('❌ اطلاعات قرعه‌کشی نامعتبر است.')
            else:
                with db() as c:
                    c.execute("UPDATE raffles SET status='closed' WHERE status='active'")
                    c.execute("INSERT INTO raffles(prize_type,prize_name,prize_amount,entry_fee,max_participants,status) VALUES(?,?,?,?,?,'active')",(pt,name,amount,fee,limit))
                flash('✅ قرعه‌کشی ساخته شد.'); return redirect(url_for('raffle'))
    with db() as c:
        rows=c.execute("SELECT r.id,r.prize_type,r.prize_name,r.prize_amount,r.entry_fee,r.max_participants,r.status,r.created_at,(SELECT COUNT(*) FROM raffle_participants p WHERE p.raffle_id=r.id) FROM raffles r ORDER BY r.id DESC").fetchall()
    b="""<div class='hero'><h2>🎟 قرعه‌کشی</h2><p>ساخت، ویرایش، حذف و شروع قرعه‌کشی. ظرفیت حداکثر 30 نفر است.</p></div><div class='card'><h3>➕ ساخت قرعه‌کشی</h3><form method='post'><input type='hidden' name='action' value='create'><label>نوع جایزه</label><select name='prize_type'><option value='money'>💰 نقدی</option><option value='item'>🎁 غیرنقدی</option></select><label>اسم جایزه (برای غیرنقدی)</label><input name='prize_name' placeholder='مثلاً اشتراک VIP'><label>مبلغ / ارزش جایزه (تومان)</label><input name='prize_amount' type='number' min='0' required><label>هزینه ثبت‌نام (تومان) — 0 یعنی رایگان</label><input name='entry_fee' type='number' min='0' value='0' required><label>حداکثر شرکت‌کننده</label><input name='max_participants' type='number' min='1' max='30' value='30' required><button>🎟 ساخت قرعه‌کشی</button></form></div><div class='card'><h3>📋 قرعه‌کشی‌ها</h3>{% if rows %}<div class='table-wrap'><table class='table'><tr><th>#</th><th>جایزه</th><th>ورودی</th><th>ظرفیت</th><th>وضعیت</th><th>ساخت</th><th>عملیات</th></tr>{% for r in rows %}<tr><td>{{r[0]}}</td><td>{% if r[1]=='money' %}💰 {{r[3]|money}} تومان{% else %}🎁 {{r[2]}}<br><span class='small'>ارزش: {{r[3]|money}} تومان</span>{% endif %}</td><td>{{r[4]|money}} تومان</td><td>{{r[8]}} / {{r[5]}}</td><td>{{'🟢 فعال' if r[6]=='active' else '🏁 انجام‌شده' if r[6]=='drawn' else '⚪ بسته'}}</td><td>{{r[7]}}</td><td><div class='actions'>{% if r[6]=='active' %}<a class='btn blue' href='{{url_for('raffle_edit_web',rid=r[0])}}'>✏️ ویرایش</a><form method='post'><input type='hidden' name='action' value='draw'><input type='hidden' name='id' value='{{r[0]}}'><button>▶️ شروع</button></form>{% endif %}<form method='post'><input type='hidden' name='action' value='delete'><input type='hidden' name='id' value='{{r[0]}}'><button class='danger'>🗑 حذف</button></form></div></td></tr>{% endfor %}</table></div>{% else %}<div class='empty'>هنوز قرعه‌کشی ساخته نشده.</div>{% endif %}</div>"""
    return page(b,rows=rows)

@app.route('/raffle/edit/<int:rid>',methods=['GET','POST'])
@admin_required
def raffle_edit_web(rid):
    with db() as c: row=c.execute('SELECT id,prize_type,prize_name,prize_amount,entry_fee,max_participants,status FROM raffles WHERE id=?',(rid,)).fetchone()
    if not row: flash('❌ قرعه‌کشی پیدا نشد.'); return redirect(url_for('raffle'))
    if request.method=='POST':
        pt=request.form.get('prize_type','item'); name=request.form.get('prize_name','').strip()
        try: amount=int(request.form.get('prize_amount','0')); fee=int(request.form.get('entry_fee','0')); limit=int(request.form.get('max_participants','30'))
        except Exception: amount=fee=-1; limit=0
        if pt not in ('money','item') or amount<0 or fee<0 or not 1<=limit<=30 or (pt=='item' and not name): flash('❌ اطلاعات نامعتبر است.')
        else:
            with db() as c: c.execute('UPDATE raffles SET prize_type=?,prize_name=?,prize_amount=?,entry_fee=?,max_participants=? WHERE id=?',(pt,name,amount,fee,limit,rid))
            flash('✅ قرعه‌کشی ویرایش شد.'); return redirect(url_for('raffle'))
    b="""<div class='card'><h2>✏️ ویرایش قرعه‌کشی #{{row[0]}}</h2><form method='post'><label>نوع جایزه</label><select name='prize_type'><option value='money' {% if row[1]=='money' %}selected{% endif %}>💰 نقدی</option><option value='item' {% if row[1]=='item' %}selected{% endif %}>🎁 غیرنقدی</option></select><label>اسم جایزه</label><input name='prize_name' value='{{row[2]}}'><label>مبلغ / ارزش جایزه</label><input name='prize_amount' type='number' min='0' value='{{row[3]}}' required><label>هزینه ثبت‌نام</label><input name='entry_fee' type='number' min='0' value='{{row[4]}}' required><label>حداکثر شرکت‌کننده (1 تا 30)</label><input name='max_participants' type='number' min='1' max='30' value='{{row[5]}}' required><button>💾 ذخیره تغییرات</button> <a class='btn dark' href='{{url_for('raffle')}}'>لغو</a></form></div>"""
    return page(b,row=row)

@app.route('/discount',methods=['GET','POST'])
@admin_required
def discount():
    if request.method=='POST':
        code=re.sub(r'\s+','',request.form.get('code','')).upper()
        dtype=request.form.get('discount_type','percent')
        try: value=int(request.form.get('value','0') or 0)
        except Exception: value=0
        try: days=int(request.form.get('duration_days','0') or 0)
        except Exception: days=0
        if not re.fullmatch(r'[A-Z0-9_-]{2,40}',code): flash('❌ کد باید 2 تا 40 کاراکتر و فقط شامل حروف انگلیسی، عدد، _ و - باشد.')
        elif dtype not in ('percent','amount'): flash('❌ نوع تخفیف نامعتبر است.')
        elif value<=0 or (dtype=='percent' and value>100): flash('❌ مقدار تخفیف نامعتبر است.')
        elif days<=0: flash('❌ مدت اعتبار باید عدد مثبت باشد.')
        else:
            expires=(datetime.utcnow()+timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            try:
                with db() as c: c.execute('INSERT INTO coupons(code,discount_type,value,duration_days,expires_at,active) VALUES(?,?,?,?,?,1)',(code,dtype,value,days,expires))
                flash(f'✅ کد {code} ساخته شد و {days} روز اعتبار دارد.')
            except sqlite3.IntegrityError: flash('❌ این کد قبلاً ثبت شده است.')
        return redirect(url_for('discount'))
    now=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with db() as c: rows=c.execute('SELECT id,code,discount_type,value,duration_days,created_at,expires_at,active FROM coupons ORDER BY id DESC').fetchall()
    b="""<div class='hero'><h2>🏷 کدهای تخفیف</h2><p>کدهای تخفیف فقط از سمت مدیریت ساخته می‌شوند و در منوی اصلی کاربر نمایش داده نمی‌شوند؛ کاربر هنگام ثبت سفارش می‌تواند کد را وارد کند.</p></div>
    <div class='card'><h3>➕ افزودن کد تخفیف</h3><form method='post'><label>اسم / کد تخفیف</label><input name='code' placeholder='مثلاً OFF20' required maxlength='40'><label>نوع تخفیف</label><select name='discount_type'><option value='percent'>٪ درصدی</option><option value='amount'>💰 مبلغی (تومان)</option></select><label>درصد یا مبلغ تخفیف</label><input name='value' type='number' min='1' placeholder='مثلاً 20 یا 50000' required><label>مدت اعتبار</label><input name='duration_days' type='number' min='1' placeholder='مثلاً 30' required><p class='muted small'>هر 1 عدد = 1 روز</p><button>➕ ساخت کد تخفیف</button></form></div>
    <div class='card'><h3>📋 کدهای ثبت‌شده</h3>{% if rows %}<div class='table-wrap'><table class='table'><tr><th>نام / کد</th><th>نوع</th><th>مقدار</th><th>مدت</th><th>تاریخ ساخت</th><th>انقضا</th><th>وضعیت</th><th></th></tr>{% for r in rows %}<tr><td><b>{{r[1]}}</b></td><td>{{'درصدی' if r[2]=='percent' else 'مبلغی'}}</td><td>{{r[3]}}{% if r[2]=='percent' %}٪{% else %} تومان{% endif %}</td><td>{{r[4]}} روز</td><td>{{r[5]}}</td><td>{{r[6]}}</td><td><span class='badge {{'ok' if r[7] and r[6]>now else 'bad'}}'>{{'🟢 فعال' if r[7] and r[6]>now else '🔴 منقضی/غیرفعال'}}</span></td><td><form method='post' action='{{url_for('discount_delete_web')}}'><input type='hidden' name='id' value='{{r[0]}}'><button class='danger'>🗑 حذف</button></form></td></tr>{% endfor %}</table></div>{% else %}<div class='empty'>هنوز کد تخفیفی ساخته نشده.</div>{% endif %}</div>"""
    return page(b,rows=rows,now=now)

@app.route('/discount/delete',methods=['POST'])
@admin_required
def discount_delete_web():
    try: rid=int(request.form.get('id','0') or 0)
    except Exception: rid=0
    with db() as c: c.execute('DELETE FROM coupons WHERE id=?',(rid,))
    flash('🗑 کد تخفیف حذف شد.')
    return redirect(url_for('discount'))



@app.errorhandler(500)
def internal_server_error(error):
    app.logger.exception('Unhandled Web Panel error', exc_info=error)
    return '<div class="card"><h2 class="bad">❌ خطای داخلی</h2><p class="muted">خطا ثبت شد. لطفاً دوباره تلاش کنید.</p><a class="btn dark" href="/dashboard">بازگشت به داشبورد</a></div>', 500

def start_web_server():
    port=int(os.getenv('PORT','8080'))
    app.run(host='0.0.0.0',port=port,debug=False,use_reloader=False)
