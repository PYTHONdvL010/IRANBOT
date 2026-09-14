import os
import sqlite3
import secrets
import json
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template_string, abort

DB_PATH = os.getenv('DB_PATH', 'shop.db')
ADMIN_IDS = {int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()}
WEB_SECRET = os.getenv('WEB_SECRET') or secrets.token_hex(32)

app = Flask(__name__)
app.secret_key = WEB_SECRET

BASE = '''
<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IRANBOT — Admin</title><style>
body{margin:0;background:#0f172a;color:#e5e7eb;font-family:Tahoma,Arial,sans-serif} .wrap{max-width:1180px;margin:30px auto;padding:0 16px}.nav{display:flex;gap:8px;flex-wrap:wrap;background:#111827;padding:12px;border-radius:14px}.nav a{color:#e5e7eb;text-decoration:none;background:#1f2937;padding:9px 12px;border-radius:10px}.card{background:#111827;border:1px solid #263244;border-radius:16px;padding:18px;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.stat{font-size:26px;font-weight:bold}.muted{color:#94a3b8}.ok{color:#86efac}.bad{color:#fca5a5}input,textarea,select{width:100%;box-sizing:border-box;background:#0b1220;color:#fff;border:1px solid #334155;border-radius:10px;padding:11px;margin:7px 0 14px}button{background:#22c55e;color:#06130a;border:0;border-radius:10px;padding:11px 16px;font-weight:bold;cursor:pointer}.danger{background:#ef4444;color:#fff}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.small{font-size:13px}.table{width:100%;border-collapse:collapse}.table td,.table th{border-bottom:1px solid #263244;padding:9px;text-align:right}.badge{padding:4px 8px;border-radius:8px;background:#1e293b}.login{max-width:430px;margin:100px auto}.flash{background:#1e293b;border-right:4px solid #22c55e;padding:10px;margin-bottom:10px;border-radius:8px}
</style></head><body><div class="wrap">
<div class="row" style="justify-content:space-between"><h1>🇮🇷 IRANBOT <span class="muted small">v1.0.2</span></h1>{% if session.get('admin_id') %}<a href="{{url_for('logout')}}">خروج</a>{% endif %}</div>
{% if session.get('admin_id') %}<div class="nav">
<a href="{{url_for('dashboard')}}">داشبورد</a><a href="{{url_for('users')}}">کاربران</a><a href="{{url_for('welcome')}}">پیام خوش‌آمد</a><a href="{{url_for('mandatory')}}">عضویت اجباری</a><a href="{{url_for('finance')}}">مالی</a><a href="{{url_for('panels')}}">پنل‌ها</a><a href="{{url_for('products')}}">محصولات</a><a href="{{url_for('orders')}}">سفارش‌ها</a><a href="{{url_for('free_tests')}}">تست رایگان</a><a href="{{url_for('discount')}}">کد تخفیف</a>
</div>{% endif %}
{% with msgs=get_flashed_messages() %}{% for m in msgs %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}{{body|safe}}
<div class="muted small" style="margin:25px 0">IRANBOT — نسخه 1.0.2 — ساخته شده توسط PYTHONdvL010</div></div></body></html>
'''


def db(): return sqlite3.connect(DB_PATH)
def setting(k):
    with db() as c:
        r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone()
    return r[0] if r else ''
def set_setting(k,v):
    with db() as c: c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,str(v)))

def admin_required(fn):
    @wraps(fn)
    def w(*a,**kw):
        if session.get('admin_id') not in ADMIN_IDS: return redirect(url_for('login'))
        return fn(*a,**kw)
    return w

def page(html, **ctx): return render_template_string(BASE, body=render_template_string(html, **ctx))

LOGIN='''<div class="card login"><h2>ورود پنل مدیریت</h2><p class="muted">ID عددی ادمین را وارد کن تا دسترسی بررسی شود.</p><form method="post"><input name="admin_id" inputmode="numeric" placeholder="مثلاً 123456789" required><button>🔐 بررسی دسترسی</button></form></div>'''
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        try: aid=int(request.form.get('admin_id',''))
        except: aid=-1
        if aid in ADMIN_IDS:
            session['admin_id']=aid; return redirect(url_for('dashboard'))
        return page('<div class="card login"><h2 class="bad">❌ چنین ادمینی وجود ندارد.</h2><a href="/login">تلاش دوباره</a></div>')
    return page(LOGIN)
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/')
def root(): return redirect(url_for('dashboard') if session.get('admin_id') in ADMIN_IDS else url_for('login'))

@app.route('/dashboard')
@admin_required
def dashboard():
    with db() as c:
        counts={
          'users': c.execute("SELECT COUNT(*) FROM users").fetchone()[0] if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone() else c.execute('SELECT COUNT(DISTINCT user_id) FROM orders').fetchone()[0],
          'products': c.execute('SELECT COUNT(*) FROM products').fetchone()[0],
          'orders': c.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
          'paid': c.execute("SELECT COUNT(*) FROM orders WHERE status='paid'").fetchone()[0],
          'pending': c.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0],
          'panels': c.execute('SELECT COUNT(*) FROM panels').fetchone()[0],
        }
    b='''<div class="grid">{% for k,v in counts.items() %}<div class="card"><div class="muted">{{k}}</div><div class="stat">{{v}}</div></div>{% endfor %}</div><div class="card"><h2>وضعیت تنظیمات</h2><p>نام سیستم: <b>IRANBOT</b></p><p>نسخه: <b>1.0.2</b></p><p>سازنده: <b>PYTHONdvL010</b></p><p>پیام خوش‌آمد: {{'فعال' if welcome else 'تنظیم نشده'}}</p><p>عضویت اجباری: {{'فعال' if mandatory else 'خاموش'}}</p></div>'''
    return page(b,counts=counts,welcome=setting('welcome_message'),mandatory=setting('mandatory_channel_id'))

@app.route('/welcome',methods=['GET','POST'])
@admin_required
def welcome():
    if request.method=='POST': set_setting('welcome_message',request.form.get('message','').strip()); return redirect(url_for('welcome'))
    cur=setting('welcome_message') or 'سلام {username} 👋\n\nبه IRANBOT خوش اومدی.'
    b='''<div class="card"><h2>👋 پیام خوش‌آمد</h2><form method="post"><textarea name="message" rows="8" required>{{cur}}</textarea><p class="muted">متغیرهای قابل استفاده: <b>{username}</b> = نام کاربر، <b>{first_name}</b> = نام، <b>{user_id}</b> = آیدی</p><button>💾 ذخیره</button></form></div>'''
    return page(b,cur=cur)

@app.route('/mandatory',methods=['GET','POST'])
@admin_required
def mandatory():
    def channels():
        raw=setting('mandatory_channels')
        if raw:
            try:
                data=json.loads(raw)
                if isinstance(data,list): return data
            except Exception: pass
        cid=setting('mandatory_channel_id')
        return [{"id":cid,"title":setting('mandatory_channel_title') or 'کانال ما',"link":setting('mandatory_channel_link') or ''}] if cid else []
    if request.method=='POST':
        cid=request.form.get('channel_id','').strip(); title=request.form.get('title','').strip() or cid; link=request.form.get('link','').strip()
        if cid and link:
            cs=[c for c in channels() if str(c.get('id'))!=cid]
            cs.append({"id":cid,"title":title,"link":link})
            set_setting('mandatory_channels',json.dumps(cs,ensure_ascii=False)); set_setting('mandatory_enabled','1')
            set_setting('mandatory_channel_id',cid); set_setting('mandatory_channel_title',title); set_setting('mandatory_channel_link',link)
        return redirect(url_for('mandatory'))
    cs=channels()
    b='''<div class="card"><h2>📢 عضویت اجباری</h2><p class="muted">می‌توانی چند کانال اضافه کنی؛ کاربر باید در همه کانال‌ها عضو باشد.</p><form method="post"><label>ID / @username کانال</label><input name="channel_id" placeholder="@mychannel یا -100123..." required><label>عنوان کانال</label><input name="title" placeholder="مثلاً کانال اصلی"><label>لینک عضویت</label><input name="link" placeholder="https://t.me/mychannel" required><button>➕ افزودن کانال</button></form></div><div class="card"><h3>کانال‌های فعلی</h3>{% if channels %}<table class="table"><tr><th>#</th><th>عنوان</th><th>ID</th><th>لینک</th><th>عملیات</th></tr>{% for c in channels %}<tr><td>{{loop.index}}</td><td>{{c.title}}</td><td>{{c.id}}</td><td>{{c.link}}</td><td><form method="post" action="{{url_for('mandatory_delete_web')}}" style="margin:0"><input type="hidden" name="id" value="{{c.id}}"><button class="danger">🗑 حذف</button></form></td></tr>{% endfor %}</table>{% else %}<p class="muted">هنوز کانالی ثبت نشده.</p>{% endif %}<p>وضعیت: <b>{{'فعال' if enabled else 'خاموش'}}</b></p><form method="post" action="{{url_for('mandatory_toggle_web')}}"><button>{{'🔴 خاموش کردن' if enabled else '🟢 فعال کردن'}}</button></form></div>'''
    return page(b,channels=cs,enabled=setting('mandatory_enabled')=='1')

@app.route('/mandatory/delete',methods=['POST'])
@admin_required
def mandatory_delete_web():
    cid=request.form.get('id','').strip(); raw=setting('mandatory_channels')
    try: cs=json.loads(raw) if raw else []
    except Exception: cs=[]
    cs=[c for c in cs if str(c.get('id'))!=cid]
    set_setting('mandatory_channels',json.dumps(cs,ensure_ascii=False)); set_setting('mandatory_enabled','1' if cs else '0')
    return redirect(url_for('mandatory'))

@app.route('/mandatory/toggle',methods=['POST'])
@admin_required
def mandatory_toggle_web():
    set_setting('mandatory_enabled','0' if setting('mandatory_enabled')=='1' else '1')
    return redirect(url_for('mandatory'))

@app.route('/finance',methods=['GET','POST'])
@admin_required
def finance():
    if request.method=='POST': set_setting('card_number',request.form.get('card','').strip()); set_setting('card_owner',request.form.get('owner','').strip()); return redirect(url_for('finance'))
    with db() as c: pending=c.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0]
    b='''<div class="card"><h2>💳 بخش مالی</h2><form method="post"><label>شماره کارت</label><input name="card" value="{{card}}" maxlength="16"><label>نام صاحب کارت</label><input name="owner" value="{{owner}}"><button>💾 ذخیره</button></form><p>پرداخت‌های در انتظار: <b>{{pending}}</b></p></div>'''
    return page(b,card=setting('card_number'),owner=setting('card_owner'),pending=pending)

@app.route('/panels',methods=['GET','POST'])
@admin_required
def panels():
    if request.method=='POST':
        pt=request.form.get('panel_type','').strip(); name=request.form.get('name','').strip(); address=request.form.get('address','').strip(); user=request.form.get('username','').strip(); pw=request.form.get('password','').strip()
        if pt and name and address and user and pw:
            with db() as c: c.execute('INSERT INTO panels(panel_type,name,address,username,password,status) VALUES(?,?,?,?,?,?)',(pt,name,address.rstrip('/'),user,pw,'manual'))
        return redirect(url_for('panels'))
    with db() as c: rows=c.execute('SELECT id,panel_type,name,address,status FROM panels ORDER BY id DESC').fetchall()
    b="""<div class="card"><h2>➕ افزودن پنل</h2><form method="post"><select name="panel_type" required><option value="pasarguard">Pasarguard</option><option value="marzban">Marzban</option><option value="3xui">3x-ui</option></select><input name="name" placeholder="نام پنل" required><input name="address" placeholder="https://panel.example.com:2096" required><input name="username" placeholder="Username" required><input name="password" type="password" placeholder="Password" required><button>➕ ثبت پنل</button></form></div><div class="card"><h2>🖥 پنل‌ها</h2><table class="table"><tr><th>ID</th><th>نوع</th><th>نام</th><th>آدرس</th><th>وضعیت</th><th>عملیات</th></tr>{% for r in rows %}<tr>{% for x in r %}<td>{{x}}</td>{% endfor %}<td><form method="post" action="{{url_for('panel_delete_web')}}" style="margin:0"><input type="hidden" name="id" value="{{r[0]}}"><button class="danger">🗑 حذف</button></form></td></tr>{% endfor %}</table></div>"""
    return page(b,rows=rows)

@app.route('/panels/delete',methods=['POST'])
@admin_required
def panel_delete_web():
    pid=int(request.form.get('id','0'))
    with db() as c:
        c.execute('DELETE FROM panels WHERE id=?',(pid,)); c.execute('DELETE FROM panel_groups WHERE panel_id=?',(pid,)); c.execute('DELETE FROM free_test_settings WHERE panel_id=?',(pid,))
    return redirect(url_for('panels'))

@app.route('/products',methods=['GET','POST'])
@admin_required
def products():
    if request.method=='POST':
        try: price=int(request.form.get('price','0').replace(',','')); gb=int(request.form.get('gb','1')); days=int(request.form.get('days','1')); pid=int(request.form.get('panel_id','0'))
        except: return page('<div class="card"><p class="bad">مقادیر عددی صحیح نیست.</p></div>')
        if not request.form.get('name') or price<=0 or gb<=0 or days<=0 or pid<=0: return page('<div class="card"><p class="bad">اطلاعات محصول ناقص است.</p></div>')
        with db() as c: c.execute('INSERT INTO products(name,price,panel_id,data_limit_gb,expire_days) VALUES(?,?,?,?,?)',(request.form['name'],f'{price:,} تومان',pid,gb,days))
        return redirect(url_for('products'))
    with db() as c:
        ps=c.execute('SELECT id,name,panel_type FROM panels ORDER BY id DESC').fetchall(); rows=c.execute('SELECT p.id,p.name,p.price,p.data_limit_gb,p.expire_days,pa.name,p.active FROM products p LEFT JOIN panels pa ON pa.id=p.panel_id ORDER BY p.id DESC').fetchall()
    b="""<div class="card"><h2>➕ افزودن محصول</h2><form method="post"><input name="name" placeholder="نام محصول" required><input name="price" placeholder="قیمت تومان" required><select name="panel_id" required><option value="">انتخاب پنل</option>{% for p in ps %}<option value="{{p[0]}}">#{{p[0]}} {{p[1]}} ({{p[2]}})</option>{% endfor %}</select><input name="gb" type="number" min="1" placeholder="حجم GB" required><input name="days" type="number" min="1" placeholder="مدت روز" required><button>➕ ثبت محصول</button></form></div><div class="card"><h2>📋 محصولات</h2><table class="table"><tr><th>ID</th><th>نام</th><th>قیمت</th><th>حجم</th><th>مدت</th><th>پنل</th><th>عملیات</th></tr>{% for r in rows %}<tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3]}}GB</td><td>{{r[4]}} روز</td><td>{{r[5] or '-'}}</td><td><form method="post" action="{{url_for('product_delete_web')}}" style="margin:0"><input type="hidden" name="id" value="{{r[0]}}"><button class="danger">🗑 حذف</button></form></td></tr>{% endfor %}</table></div>"""
    return page(b,ps=ps,rows=rows)

@app.route('/products/delete',methods=['POST'])
@admin_required
def product_delete_web():
    pid=int(request.form.get('id','0'))
    with db() as c:
        used=c.execute('SELECT COUNT(*) FROM orders WHERE product_id=?',(pid,)).fetchone()[0]
        if used: c.execute('UPDATE products SET active=0 WHERE id=?',(pid,))
        else: c.execute('DELETE FROM products WHERE id=?',(pid,)); c.execute('DELETE FROM configs WHERE product_id=?',(pid,))
    return redirect(url_for('products'))

@app.route('/users')
@admin_required
def users():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '', first_name TEXT DEFAULT '', is_blocked INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, last_seen DATETIME DEFAULT CURRENT_TIMESTAMP)")
        rows=c.execute("SELECT user_id,username,first_name,is_blocked FROM users ORDER BY last_seen DESC LIMIT 200").fetchall()
    b="""<div class="card"><h2>👥 کاربران</h2><p class="muted">مدیریت کاربران ربات: موجودی، سفارش‌ها و مسدودسازی.</p><table class="table"><tr><th>ID</th><th>Username</th><th>نام</th><th>موجودی</th><th>وضعیت</th><th>عملیات</th></tr>{% for r in rows %}<tr><td>{{r[0]}}</td><td>@{{r[1] or '-'}}</td><td>{{r[2] or '-'}}</td><td>{{r[4]}}</td><td>{{'🚫 مسدود' if r[3] else '✅ فعال'}}</td><td><a href="{{url_for('user_detail_web',uid=r[0])}}">مدیریت</a></td></tr>{% endfor %}</table></div>"""
    with db() as c:
        rows2=[]
        for r in rows:
            bal=c.execute('SELECT COALESCE(balance,0) FROM wallets WHERE user_id=?',(r[0],)).fetchone(); rows2.append(r+(bal[0] if bal else 0,))
    return page(b,rows=rows2)

@app.route('/users/<int:uid>',methods=['GET','POST'])
@admin_required
def user_detail_web(uid):
    if request.method=='POST':
        action=request.form.get('action'); amount=int(request.form.get('amount','0') or 0)
        with db() as c:
            c.execute('INSERT OR IGNORE INTO wallets(user_id,balance) VALUES(?,0)',(uid,))
            if action=='add' and amount>0: c.execute('UPDATE wallets SET balance=balance+? WHERE user_id=?',(amount,uid))
            elif action=='sub' and amount>0: c.execute('UPDATE wallets SET balance=MAX(0,balance-?) WHERE user_id=?',(amount,uid))
            elif action=='block': c.execute('UPDATE users SET is_blocked=1 WHERE user_id=?',(uid,))
            elif action=='unblock': c.execute('UPDATE users SET is_blocked=0 WHERE user_id=?',(uid,))
        return redirect(url_for('user_detail_web',uid=uid))
    with db() as c:
        u=c.execute('SELECT user_id,username,first_name,is_blocked FROM users WHERE user_id=?',(uid,)).fetchone()
        bal=c.execute('SELECT COALESCE(balance,0) FROM wallets WHERE user_id=?',(uid,)).fetchone(); orders=c.execute("SELECT o.id,p.name,o.status,o.subscription,o.created_at FROM orders o JOIN products p ON p.id=o.product_id WHERE o.user_id=? AND o.status='paid' ORDER BY o.id DESC",(uid,)).fetchall()
    if not u: return page('<div class="card"><h2>❌ کاربر پیدا نشد</h2></div>')
    b="""<div class="card"><h2>👤 مدیریت کاربر #{{u[0]}}</h2><p>ID: <b>{{u[0]}}</b></p><p>Username: <b>@{{u[1] or '-'}}</b></p><p>نام: <b>{{u[2] or '-'}}</b></p><p>💰 موجودی: <b>{{bal:,}} تومان</b></p><form method="post"><input name="amount" type="number" min="1" placeholder="مبلغ"><button name="action" value="add">➕ افزایش موجودی</button> <button name="action" value="sub" class="danger">➖ کاهش موجودی</button></form><form method="post" style="margin-top:10px"><button name="action" value="{{'unblock' if u[3] else 'block'}}" class="danger">{{'✅ رفع مسدودی' if u[3] else '🚫 مسدود کردن'}}</button></form></div><div class="card"><h2>📦 سفارش‌های تأییدشده</h2>{% for o in orders %}<div class="card"><b>#{{o[0]}} — {{o[1]}}</b><br>{{o[4]}}<br><span class="small">{{o[3] or '-'}}</span></div>{% else %}<p>سفارشی ندارد.</p>{% endfor %}</div>"""
    return page(b,u=u,bal=(bal[0] if bal else 0),orders=orders)

@app.route('/orders')
@admin_required
def orders():
    with db() as c: rows=c.execute('SELECT o.id,o.user_id,p.name,o.status,o.subscription,o.created_at FROM orders o JOIN products p ON p.id=o.product_id ORDER BY o.id DESC LIMIT 100').fetchall()
    b='''<div class="card"><h2>📦 سفارش‌ها</h2><table class="table"><tr><th>ID</th><th>User</th><th>محصول</th><th>وضعیت</th><th>Subscription</th><th>تاریخ</th></tr>{% for r in rows %}<tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3]}}</td><td class="small">{{r[4] or '-'}}</td><td>{{r[5]}}</td></tr>{% endfor %}</table></div>'''
    return page(b,rows=rows)

@app.route('/free-tests')
@admin_required
def free_tests():
    with db() as c: rows=c.execute('SELECT p.id,p.name,s.max_tests,s.data_limit_mb,s.expire_hours,s.enabled FROM panels p JOIN free_test_settings s ON s.panel_id=p.id ORDER BY p.id').fetchall()
    b='''<div class="card"><h2>🎁 تست رایگان</h2><table class="table"><tr><th>پنل</th><th>تعداد</th><th>MB</th><th>ساعت</th><th>وضعیت</th></tr>{% for r in rows %}<tr><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3]}}</td><td>{{r[4]}}</td><td>{{'فعال' if r[5] else 'خاموش'}}</td></tr>{% endfor %}</table><p class="muted">تنظیم کامل تست همچنان از بخش پنل‌های ربات انجام می‌شود؛ اینجا وضعیت آن نمایش داده می‌شود.</p></div>'''
    return page(b,rows=rows)

@app.route('/discount')
@admin_required
def discount():
    return page('<div class="card"><h2>🎁 کد تخفیف</h2><p>این بخش فعلاً در سایت ایجاد شده ولی سیستم ساخت کد تخفیف هنوز در ربات ساخته نشده است.</p></div>')

def start_web_server():
    port=int(os.getenv('PORT','8080'))
    app.run(host='0.0.0.0',port=port,debug=False,use_reloader=False)
