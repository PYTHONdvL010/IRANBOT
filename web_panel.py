import os
import re
import json
import sqlite3
import secrets
import tempfile
from datetime import datetime, timedelta
from functools import wraps

import httpx
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, redirect, url_for, session, render_template_string, flash, send_file

DB_PATH = os.getenv('DB_PATH', 'shop.db')
ADMIN_IDS = {int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()}
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
WEB_SECRET = os.getenv('WEB_SECRET') or secrets.token_hex(32)
VERSION = '1.0.7'

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
.light-theme{--bg:#f3f6fa;--panel:#ffffff;--panel2:#f8fafc;--line:#d6dee8;--text:#172333;--muted:#5d6d7e;--shadow:0 12px 35px rgba(20,40,60,.12)}
.light-theme body{background:linear-gradient(135deg,#f7f9fc,#edf2f7);color:var(--text)}
.light-theme .nav,.light-theme .card,.light-theme .statcard{background:#fff;border-color:var(--line)}
.light-theme .nav a{background:#f4f7fa;color:#25384c}.light-theme .nav a:hover{background:#e9f0f6}
.light-theme input,.light-theme textarea,.light-theme select{background:#fff;color:#172333;border-color:#b9c8d7}.light-theme .switch,.light-theme .check{background:#f7f9fb;border-color:#cbd7e3}.light-theme .table th{background:#f1f5f9}.light-theme .logout{background:#f4f7fa;color:#24384d;border-color:#cbd7e3}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% -10%,rgba(56,168,255,.15),transparent 30%),radial-gradient(circle at 5% 10%,rgba(56,217,150,.11),transparent 25%),var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;min-height:100vh}
.wrap{max-width:1280px;margin:0 auto;padding:24px 18px 45px}.top{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:18px}.brand{display:flex;align-items:center;gap:12px}.logo{width:48px;height:48px;border-radius:15px;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent2),var(--accent));box-shadow:0 10px 30px rgba(56,168,255,.2);font-size:24px}.brand h1{margin:0;font-size:25px}.version{color:var(--muted);font-size:12px}.logout{color:#dce9f7;text-decoration:none;background:#14263d;border:1px solid var(--line);padding:9px 13px;border-radius:11px}
.nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;padding:10px;background:rgba(13,27,45,.82);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);backdrop-filter:blur(12px);margin-bottom:20px}.nav a{color:#dbe9f7;text-decoration:none;text-align:center;background:#12243a;border:1px solid transparent;padding:11px 9px;border-radius:12px;transition:.18s}.nav a:hover{border-color:#2d5578;transform:translateY(-1px);background:#172d47}
.hero{background:linear-gradient(135deg,rgba(56,168,255,.16),rgba(56,217,150,.10));border:1px solid #254664;border-radius:22px;padding:24px;box-shadow:var(--shadow);margin-bottom:18px}.hero h2{margin:0 0 7px;font-size:24px}.hero p{margin:0;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:13px}.statcard{background:linear-gradient(180deg,#10223a,#0c192b);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:var(--shadow)}.staticon{font-size:24px}.statlabel{color:var(--muted);font-size:13px;margin-top:9px}.stat{font-size:28px;font-weight:800;margin-top:3px}
.card{background:rgba(13,27,45,.94);border:1px solid var(--line);border-radius:18px;padding:20px;margin:14px 0;box-shadow:var(--shadow)}.card h2,.card h3{margin-top:0}.muted{color:var(--muted)}.ok{color:var(--accent)}.bad{color:#ff9bab}.warn{color:var(--warn)}
input,textarea,select{width:100%;box-sizing:border-box;background:#081525;color:#fff;border:1px solid #2a425d;border-radius:12px;padding:12px 13px;margin:7px 0 14px;outline:none}input:focus,textarea:focus,select:focus{border-color:var(--accent2);box-shadow:0 0 0 3px rgba(56,168,255,.08)}label{font-size:13px;color:#b8c9da}button,.btn{display:inline-block;background:linear-gradient(135deg,var(--accent),#23bd86);color:#03130d;border:0;border-radius:11px;padding:11px 15px;font-weight:800;cursor:pointer;text-decoration:none}.btn.blue{background:linear-gradient(135deg,var(--accent2),#4385ff);color:white}.btn.dark{background:#152a42;color:#e6f0fa;border:1px solid #29435e}.danger{background:linear-gradient(135deg,#ff6679,#e83e58)!important;color:#fff!important}.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.actions{display:flex;gap:8px;flex-wrap:wrap}.small{font-size:12px}.table-wrap{overflow:auto}.table{width:100%;border-collapse:separate;border-spacing:0;min-width:720px}.table td,.table th{border-bottom:1px solid #20344d;padding:12px;text-align:right;vertical-align:middle}.table th{color:#9fb5cb;font-size:12px;background:#0d1a2b}.table tr:hover td{background:rgba(255,255,255,.018)}.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:#172b43;font-size:12px}.badge.ok{background:rgba(56,217,150,.12);color:#72efb7}.badge.bad{background:rgba(255,93,114,.12);color:#ff9bab}.badge.warn{background:rgba(255,189,89,.12);color:#ffd18a}
.login{max-width:440px;margin:12vh auto}.login .logo{margin:auto}.flash{background:#11263a;border:1px solid #284763;padding:11px 13px;margin-bottom:10px;border-radius:12px}.empty{text-align:center;padding:35px;color:var(--muted)}.mini{font-size:11px;color:#7890a9;word-break:break-all}.switch{display:flex;align-items:center;justify-content:space-between;padding:14px;background:#0a1829;border:1px solid var(--line);border-radius:13px;margin:10px 0}.checkgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}.check{padding:13px;border:1px solid #29425c;border-radius:13px;background:#0a1829}.check input{width:auto;margin:0 7px 0 0}.kpi{font-size:12px;color:var(--muted)}
@media(max-width:700px){.wrap{padding:14px 10px 30px}.top{align-items:flex-start}.brand h1{font-size:20px}.nav{grid-template-columns:repeat(2,1fr)}.hero{padding:18px}.card{padding:15px}.table{min-width:650px}}
</style></head><body class="{{'light-theme' if theme=='light' else ''}}"><div class="wrap">
<div class="top"><div class="brand"><div class="logo">⚡</div><div><h1>IRANBOT <span class="version">v{{version}}</span></h1><div class="muted small">داشبورد مدیریت فروش و سرویس</div></div></div>{% if session.get('admin_id') %}<a class="logout" href="{{url_for('logout')}}">خروج ↪</a>{% endif %}</div>
{% if session.get('admin_id') %}<div class="nav">
<a href="{{url_for('dashboard')}}">🏠 داشبورد</a><a href="{{url_for('users')}}">👥 کاربران</a><a href="{{url_for('welcome')}}">👋 خوش‌آمد</a><a href="{{url_for('mandatory')}}">📢 عضویت</a><a href="{{url_for('finance')}}">💳 مالی</a><a href="{{url_for('finance_report_web')}}">📊 گزارش مالی</a><a href="{{url_for('panels')}}">🖥 پنل‌ها</a><a href="{{url_for('products')}}">🛒 محصولات</a><a href="{{url_for('orders')}}">📦 سفارش‌ها</a><a href="{{url_for('free_tests')}}">🎁 تست رایگان</a><a href="{{url_for('raffle')}}">🎟 قرعه‌کشی</a><a href="{{url_for('discount')}}">🏷 تخفیف</a><a href="{{url_for('backup')}}">💾 پشتیبان‌گیری</a><a href="{{url_for('settings_web')}}">⚙️ تنظیمات</a>
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
        c.execute("CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,product_id INTEGER NOT NULL,status TEXT DEFAULT 'pending',created_at DATETIME DEFAULT CURRENT_TIMESTAMP,subscription TEXT DEFAULT '',panel_username TEXT DEFAULT '')")
        c.execute("CREATE TABLE IF NOT EXISTS coupons(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT NOT NULL UNIQUE,discount_type TEXT NOT NULL,value INTEGER NOT NULL,duration_days INTEGER NOT NULL,created_at DATETIME DEFAULT CURRENT_TIMESTAMP,expires_at DATETIME NOT NULL,active INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS configs(id INTEGER PRIMARY KEY AUTOINCREMENT,product_id INTEGER NOT NULL,config TEXT NOT NULL,delivered INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,kind TEXT NOT NULL,order_id INTEGER,amount INTEGER NOT NULL,status TEXT DEFAULT 'pending',photo_file_id TEXT,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS renewals(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,order_id INTEGER NOT NULL,full_price INTEGER NOT NULL,remaining_gb REAL DEFAULT 0,charge_gb REAL DEFAULT 0,amount INTEGER NOT NULL,status TEXT DEFAULT 'pending',created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS free_test_settings(panel_id INTEGER PRIMARY KEY,max_tests INTEGER DEFAULT 1,data_limit_mb INTEGER DEFAULT 100,expire_hours INTEGER DEFAULT 1,enabled INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS raffles(id INTEGER PRIMARY KEY AUTOINCREMENT,prize_type TEXT NOT NULL,prize_name TEXT DEFAULT '',prize_amount INTEGER DEFAULT 0,entry_fee INTEGER DEFAULT 0,max_participants INTEGER DEFAULT 30,status TEXT DEFAULT 'active',created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS raffle_participants(raffle_id INTEGER NOT NULL,user_id INTEGER NOT NULL,created_at DATETIME DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(raffle_id,user_id))")
        for table, columns in {
            'users': [('username',"TEXT DEFAULT ''"),('first_name',"TEXT DEFAULT ''"),('is_blocked','INTEGER DEFAULT 0'),('last_seen',"TEXT DEFAULT ''")],
            'products': [('panel_id','INTEGER'),('data_limit_gb','INTEGER DEFAULT 1'),('expire_days','INTEGER DEFAULT 1'),('active','INTEGER DEFAULT 1')],
            'orders': [('subscription',"TEXT DEFAULT ''"),('panel_username',"TEXT DEFAULT ''"),('discount_code',"TEXT DEFAULT ''"),('discount_amount','INTEGER DEFAULT 0'),('final_amount','INTEGER DEFAULT 0')],
        }.items():
            existing={r[1] for r in c.execute(f'PRAGMA table_info({table})').fetchall()}
            for name, definition in columns:
                if name not in existing:
                    c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
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
        allowed_ids=set(ADMIN_IDS)
        configured=configured_web_admin_id()
        if configured is not None:
            allowed_ids.add(configured)
        if current not in allowed_ids:
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
        allowed=set(ADMIN_IDS);
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
                flash('❌ آیدی عددی معتبر نیست.')
                return redirect(url_for('settings_web'))
            enabled=request.form.get('two_factor')=='1'
            password=request.form.get('password','')
            confirm=request.form.get('password_confirm','')
            old_enabled=setting('web_2fa')=='1'
            if enabled and not old_enabled and not password:
                flash('❌ برای فعال‌سازی ورود دو مرحله‌ای، رمز عبور را وارد کن.')
                return redirect(url_for('settings_web'))
            if password or confirm:
                if len(password)<8:
                    flash('❌ رمز عبور باید حداقل 8 کاراکتر باشد.')
                    return redirect(url_for('settings_web'))
                if password!=confirm:
                    flash('❌ تکرار رمز عبور با رمز اصلی یکسان نیست.')
                    return redirect(url_for('settings_web'))
                set_setting('web_password_hash',generate_password_hash(password))
            if enabled and not setting('web_password_hash'):
                flash('❌ ابتدا رمز عبور را تنظیم کن.')
                return redirect(url_for('settings_web'))
            set_setting('web_admin_id',new_id)
            set_setting('web_2fa','1' if enabled else '0')
            session['admin_id']=new_id
            flash('✅ تنظیمات ورود با موفقیت ذخیره شد.')
            return redirect(url_for('settings_web'))
    current_id=configured_web_admin_id() or ''
    two_factor=setting('web_2fa')=='1'
    theme=setting('web_theme') or 'dark'
    b='''<div class="hero"><h2>⚙️ تنظیمات</h2><p>تنظیمات ظاهر Web Panel و امنیت ورود را از این بخش مدیریت کن.</p></div>
<div class="card"><h3>🎨 تغییر Theme</h3><p class="muted">ظاهر پنل را به حالت سفید یا مشکی تغییر بده.</p><div class="actions"><form method="post"><input type="hidden" name="action" value="theme"><button name="theme" value="light">⚪ سفید</button></form><form method="post"><input type="hidden" name="action" value="theme"><button class="btn dark" name="theme" value="dark">⚫ مشکی</button></form></div><p class="small muted">Theme فعلی: {{'سفید' if theme=='light' else 'مشکی'}}</p></div>
<div class="card"><h3>🔐 ورود دو مرحله‌ای</h3><form method="post" id="securityForm"><input type="hidden" name="action" value="security"><label>آیدی عددی Web Panel</label><input name="admin_id" type="number" min="1" value="{{current_id}}" required><div class="switch"><span><b>فعال‌سازی ورود دو مرحله‌ای</b><br><span class="muted small">بعد از فعال‌سازی، ورود با آیدی عددی + رمز انجام می‌شود.</span></span><input id="twoFactor" name="two_factor" value="1" type="checkbox" style="width:auto" {% if two_factor %}checked{% endif %} onchange="document.getElementById('passFields').style.display=this.checked?'block':'none'"></div><div id="passFields" style="display:{{'block' if two_factor else 'none'}}"><label>رمز عبور جدید</label><input name="password" type="password" minlength="8" placeholder="حداقل 8 کاراکتر"><label>تکرار رمز عبور</label><input name="password_confirm" type="password" minlength="8" placeholder="تکرار رمز"></div><button>💾 ذخیره تنظیمات</button></form></div>'''
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

@app.route('/raffle',methods=['GET','POST'])
@admin_required
def raffle():
    if request.method=='POST':
        action=request.form.get('action','create')
        if action=='delete':
            rid=int(request.form.get('id','0') or 0)
            with db() as c: c.execute('DELETE FROM raffle_participants WHERE raffle_id=?',(rid,)); c.execute('DELETE FROM raffles WHERE id=?',(rid,))
            flash('🗑 قرعه‌کشی حذف شد.'); return redirect(url_for('raffle'))
        if action=='draw':
            import random
            rid=int(request.form.get('id','0') or 0)
            with db() as c: r=c.execute("SELECT prize_type,prize_name,prize_amount,status FROM raffles WHERE id=?",(rid,)).fetchone(); rows=c.execute('SELECT user_id FROM raffle_participants WHERE raffle_id=?',(rid,)).fetchall()
            if not r or r[3]!='active' or not rows: flash('❌ قرعه‌کشی فعال نیست یا شرکت‌کننده ندارد.'); return redirect(url_for('raffle'))
            winner=random.choice(rows)[0]
            with db() as c: c.execute("UPDATE raffles SET status='drawn' WHERE id=?",(rid,)); c.execute('DELETE FROM raffle_participants WHERE raffle_id=?',(rid,))
            prize=f"{r[2]:,} تومان" if r[0]=='money' else r[1]
            if BOT_TOKEN: telegram_notify(winner,f"🎉 برنده شدی!\n\n🎟 قرعه‌کشی #{rid}\n🎁 جایزه: {prize}\n\nبرووووو تو PV ادمین 😄")
            flash(f'🎉 برنده قرعه‌کشی #{rid}: {winner} — جایزه: {prize}'); return redirect(url_for('raffle'))
        pt=request.form.get('prize_type','item'); name=request.form.get('prize_name','').strip()
        try: amount=int(request.form.get('prize_amount','0') or 0); fee=int(request.form.get('entry_fee','0') or 0); limit=int(request.form.get('max_participants','30') or 30)
        except Exception: amount=fee=-1; limit=0
        if pt not in ('money','item') or amount<0 or fee<0 or not 1<=limit<=30 or (pt=='item' and not name): flash('❌ اطلاعات قرعه‌کشی نامعتبر است.')
        else:
            with db() as c: c.execute("UPDATE raffles SET status='closed' WHERE status='active'"); c.execute('INSERT INTO raffles(prize_type,prize_name,prize_amount,entry_fee,max_participants,status) VALUES(?,?,?,?,?,?)',(pt,name,amount,fee,limit,'active'))
            flash('🎉 قرعه‌کشی ساخته و فعال شد.')
        return redirect(url_for('raffle'))
    with db() as c: rows=c.execute("SELECT r.id,r.prize_type,r.prize_name,r.prize_amount,r.entry_fee,r.max_participants,r.status,r.created_at,(SELECT COUNT(*) FROM raffle_participants p WHERE p.raffle_id=r.id) FROM raffles r ORDER BY r.id DESC").fetchall()
    b="""<div class='hero'><h2>🎟 قرعه‌کشی</h2><p>ساخت، ویرایش، حذف و شروع قرعه‌کشی. ظرفیت حداکثر 30 نفر است.</p></div><div class='card'><h3>➕ ساخت قرعه‌کشی</h3><form method='post'><label>نوع جایزه</label><select name='prize_type'><option value='money'>💰 نقدی</option><option value='item'>🎁 غیرنقدی</option></select><label>اسم جایزه (برای غیرنقدی)</label><input name='prize_name' placeholder='مثلاً اشتراک VIP'><label>مبلغ / ارزش جایزه (تومان)</label><input name='prize_amount' type='number' min='0' required><label>هزینه ثبت‌نام (تومان) — 0 یعنی رایگان</label><input name='entry_fee' type='number' min='0' value='0' required><label>حداکثر شرکت‌کننده</label><input name='max_participants' type='number' min='1' max='30' value='30' required><button>🎟 ساخت قرعه‌کشی</button></form></div><div class='card'><h3>📋 قرعه‌کشی‌ها</h3>{% if rows %}<div class='table-wrap'><table class='table'><tr><th>#</th><th>جایزه</th><th>ورودی</th><th>ظرفیت</th><th>وضعیت</th><th>ساخت</th><th>عملیات</th></tr>{% for r in rows %}<tr><td>{{r[0]}}</td><td>{% if r[1]=='money' %}💰 {{r[3]|money}} تومان{% else %}🎁 {{r[2]}}<br><span class='small'>ارزش: {{r[3]|money}} تومان</span>{% endif %}</td><td>{{r[4]|money}} تومان</td><td>{{r[8]}} / {{r[5]}}</td><td>{{'🟢 فعال' if r[6]=='active' else '🏁 انجام‌شده' if r[6]=='drawn' else '⚪ بسته'}}</td><td>{{r[7]}}</td><td><div class='actions'>{% if r[6]=='active' %}<a class='btn blue' href='{{url_for('raffle_edit_web',rid=r[0])}}'>✏️ ویرایش</a><form method='post'><input type='hidden' name='action' value='draw'><input type='hidden' name='id' value='{{r[0]}}'><button>▶️ شروع</button></form>{% endif %}<form method='post'><input type='hidden' name='action' value='delete'><input type='hidden' name='id' value='{{r[0]}}'><button class='danger'>🗑 حذف</button></form></div></td></tr>{% endfor %}</table></div>{% else %}<div class='empty'>هنوز قرعه‌کشی ساخته نشده.</div>{% endif %}</div>"""
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
    <div class='card'><h3>📋 کدهای ثبت‌شده</h3>{% if rows %}<div class='table-wrap'><table class='table'><tr><th>نام / کد</th><th>نوع</th><th>مقدار</th><th>مدت</th><th>تاریخ ساخت</th><th>انقضا</th><th>وضعیت</th><th></th></tr>{% for r in rows %}<tr><td><b>{{r[1]}}</b></td><td>{{'درصدی' if r[2]=='percent' else 'مبلغی'}}</td><td>{{r[3]}}{% if r[2]=='percent' %}٪{% else %} تومان{% endif %}</td><td>{{r[4]}} روز</td><td>{{r[5]}}</td><td>{{r[6]}}</td><td><span class='badge {{'ok' if r[7] and r[6]>now else 'bad'}}'>{{'🟢 فعال' if r[7] and r[6]>now else '🔴 منقضی/غیرفعال'}}</span></td><td><a class='btn blue' href='{{url_for('discount_edit_web',rid=r[0])}}'>✏️ ویرایش</a><form method='post' action='{{url_for('discount_delete_web')}}'><input type='hidden' name='id' value='{{r[0]}}'><button class='danger'>🗑 حذف</button></form></td></tr>{% endfor %}</table></div>{% else %}<div class='empty'>هنوز کد تخفیفی ساخته نشده.</div>{% endif %}</div>"""
    return page(b,rows=rows,now=now)

@app.route('/discount/edit/<int:rid>',methods=['GET','POST'])
@admin_required
def discount_edit_web(rid):
    with db() as c: row=c.execute('SELECT id,code,discount_type,value,duration_days FROM coupons WHERE id=?',(rid,)).fetchone()
    if not row: flash('❌ کد تخفیف پیدا نشد.'); return redirect(url_for('discount'))
    if request.method=='POST':
        code=re.sub(r'\s+','',request.form.get('code','')).upper(); dtype=request.form.get('discount_type','percent')
        try: value=int(request.form.get('value','0') or 0); days=int(request.form.get('duration_days','0') or 0)
        except Exception: value=days=0
        if not re.fullmatch(r'[A-Z0-9_-]{2,40}',code): flash('❌ کد نامعتبر است.')
        elif dtype not in ('percent','amount') or value<=0 or (dtype=='percent' and value>100): flash('❌ مقدار تخفیف نامعتبر است.')
        elif days<=0: flash('❌ مدت اعتبار باید مثبت باشد.')
        else:
            expires=(datetime.utcnow()+timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            try:
                with db() as c: c.execute('UPDATE coupons SET code=?,discount_type=?,value=?,duration_days=?,expires_at=?,active=1 WHERE id=?',(code,dtype,value,days,expires,rid))
                flash('✅ کد تخفیف ویرایش شد.'); return redirect(url_for('discount'))
            except sqlite3.IntegrityError: flash('❌ این کد قبلاً ثبت شده است.')
    b='''<div class='card'><h2>✏️ ویرایش کد تخفیف #{{row[0]}}</h2><form method='post'><label>نام / کد</label><input name='code' value='{{row[1]}}' required><label>نوع</label><select name='discount_type'><option value='percent' {% if row[2]=='percent' %}selected{% endif %}>٪ درصدی</option><option value='amount' {% if row[2]=='amount' %}selected{% endif %}>💰 مبلغی</option></select><label>مقدار</label><input name='value' type='number' min='1' value='{{row[3]}}' required><label>مدت اعتبار (روز)</label><input name='duration_days' type='number' min='1' value='{{row[4]}}' required><button>💾 ذخیره تغییرات</button> <a class='btn dark' href='{{url_for('discount')}}'>لغو</a></form></div>'''
    return page(b,row=row)

@app.route('/discount/delete',methods=['POST'])
@admin_required
def discount_delete_web():
    try: rid=int(request.form.get('id','0') or 0)
    except Exception: rid=0
    with db() as c: c.execute('DELETE FROM coupons WHERE id=?',(rid,))
    flash('🗑 کد تخفیف حذف شد.')
    return redirect(url_for('discount'))

def start_web_server():
    port=int(os.getenv('PORT','8080'))
    app.run(host='0.0.0.0',port=port,debug=False,use_reloader=False)
