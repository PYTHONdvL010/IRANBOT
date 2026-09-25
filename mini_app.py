import os, sqlite3, json, hmac, hashlib, urllib.parse
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

DB_PATH = os.getenv('DB_PATH', 'shop.db')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
MINI_APP_PORT = 8081
VERSION = '1.0.9'

app = Flask(__name__)


def db():
    return sqlite3.connect(DB_PATH)


def setting(key, default=''):
    try:
        with db() as c:
            row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default
    except Exception:
        return default


def telegram_init_data_valid(init_data: str) -> bool:
    if not BOT_TOKEN or not init_data:
        return False
    try:
        data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received = data.pop('hash', '')
        if not received:
            return False
        pairs = [f'{k}={data[k]}' for k in sorted(data)]
        check_string = '\n'.join(pairs)
        secret = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(calculated, received)
    except Exception:
        return False


HTML = r'''<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>IRANBOT</title>
<style>
:root{--bg:#06111f;--card:#0c1b2d;--card2:#10253b;--line:#20415e;--text:#f4f8ff;--muted:#8ea7c0;--a:#38a9ff;--b:#38e0a0;--danger:#ff617c;--shadow:0 18px 55px rgba(0,0,0,.35)}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% 0%,rgba(56,169,255,.2),transparent 32%),radial-gradient(circle at 0% 20%,rgba(56,224,160,.12),transparent 30%),var(--bg);color:var(--text);font-family:Tahoma,Arial,sans-serif;min-height:100vh}.wrap{max-width:760px;margin:auto;padding:18px 15px 92px}.brand{display:flex;align-items:center;justify-content:space-between;margin:5px 0 18px}.logo{width:50px;height:50px;border-radius:17px;display:grid;place-items:center;font-size:24px;background:linear-gradient(135deg,var(--a),var(--b));box-shadow:0 10px 35px rgba(56,169,255,.25)}.title{font-weight:900;font-size:23px}.sub{color:var(--muted);font-size:11px;margin-top:4px}.hero{padding:22px;border:1px solid #285171;border-radius:25px;background:linear-gradient(135deg,rgba(56,169,255,.18),rgba(56,224,160,.11));box-shadow:var(--shadow);overflow:hidden;position:relative}.hero h1{margin:0 0 8px;font-size:26px}.hero p{margin:0;color:#bdd0e2;line-height:1.8}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}.card{background:rgba(12,27,45,.93);border:1px solid var(--line);border-radius:20px;padding:15px;box-shadow:var(--shadow)}.card h3{margin:0 0 8px}.price{font-weight:900;font-size:20px;margin:8px 0}.muted{color:var(--muted);font-size:12px;line-height:1.7}.btn{border:0;border-radius:13px;padding:11px 14px;color:#06111f;background:linear-gradient(135deg,var(--b),var(--a));font-weight:900;cursor:pointer;width:100%}.nav{position:fixed;bottom:0;left:0;right:0;background:rgba(6,17,31,.94);backdrop-filter:blur(18px);border-top:1px solid var(--line);display:grid;grid-template-columns:repeat(4,1fr);padding:9px max(10px,env(safe-area-inset-left)) calc(9px + env(safe-area-inset-bottom));z-index:20}.nav button{background:none;border:0;color:var(--muted);font-size:11px}.nav button.active{color:#fff}.pill{display:inline-block;padding:6px 9px;border-radius:99px;background:#122d46;color:#a9c7df;font-size:10px}.empty{text-align:center;padding:25px;color:var(--muted)}#status{margin-top:10px}.loading{opacity:.6}@media(max-width:420px){.grid{grid-template-columns:1fr}.hero h1{font-size:23px}}
</style></head>
<body><div class="wrap">
<div class="brand"><div style="display:flex;gap:11px;align-items:center"><div class="logo">⚡</div><div><div class="title">IRANBOT</div><div class="sub">VPN & Config Store</div></div></div><span class="pill">v{{version}}</span></div>
<section class="hero"><h1>فروشگاه IRANBOT</h1><p>خرید سرویس، مشاهده سفارش‌ها و مدیریت سرویس‌های شما در یک Mini App سریع و گرافیکی.</p><div id="status" class="muted"></div></section>
<div id="content" class="grid"></div>
</div>
<nav class="nav"><button class="active" onclick="showTab('home',this)">🏠<br>خانه</button><button onclick="showTab('products',this)">🛒<br>محصولات</button><button onclick="showTab('services',this)">🔐<br>سرویس‌ها</button><button onclick="showTab('profile',this)">👤<br>پروفایل</button></nav>
<script>
const tg=window.Telegram&&Telegram.WebApp?Telegram.WebApp:null;if(tg){tg.ready();tg.expand();document.documentElement.style.setProperty('--a',tg.themeParams.button_color||'#38a9ff')}
let current='home';
async function api(path){const r=await fetch(path,{headers:{'X-Telegram-Init-Data':tg?tg.initData:''}});return r.json()}
function showTab(tab,el){current=tab;document.querySelectorAll('.nav button').forEach(x=>x.classList.remove('active'));el.classList.add('active');render()}
async function render(){const c=document.getElementById('content');c.classList.add('loading');try{if(current==='products'){const d=await api('/api/products');c.innerHTML=d.products.length?d.products.map(p=>`<article class="card"><h3>🛒 ${esc(p.name)}</h3><div class="muted">${esc(p.description||'')}</div><div class="price">${Number(p.price||0).toLocaleString()} تومان</div><button class="btn" onclick="buy(${p.id})">مشاهده محصول</button></article>`).join(''):'<div class="card empty">محصولی موجود نیست.</div>'}else if(current==='services'){const d=await api('/api/me');c.innerHTML=`<div class="card"><h3>🔐 سرویس‌های من</h3><div class="muted">${d.user?'کاربر متصل: '+esc(d.user.first_name||d.user.username||d.user.id):'برای مشاهده سرویس‌ها Mini App را از داخل Telegram باز کنید.'}</div></div>`}else if(current==='profile'){const d=await api('/api/me');c.innerHTML=`<div class="card"><h3>👤 پروفایل</h3><div class="muted">${d.user?'ID: '+d.user.id:'احراز هویت Telegram انجام نشده است.'}</div></div><div class="card"><h3>💰 کیف پول</h3><div class="price">${Number(d.balance||0).toLocaleString()} تومان</div></div>`}else{c.innerHTML='<article class="card"><h3>🛒 فروشگاه</h3><div class="muted">از بخش محصولات سرویس موردنظر خود را انتخاب کنید.</div><button class="btn" onclick="document.querySelectorAll(\'.nav button\')[1].click()">مشاهده محصولات</button></article><article class="card"><h3>⚡ سریع و گرافیکی</h3><div class="muted">این Mini App برای استفاده مستقیم داخل Telegram طراحی شده است.</div></article>'}}catch(e){c.innerHTML='<div class="card empty">خطا در دریافت اطلاعات.</div>'}finally{c.classList.remove('loading')}}
function esc(s){return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
async function buy(id){
 try{
 const r=await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json','X-Telegram-Init-Data':tg?tg.initData:''},body:JSON.stringify({product_id:id})});
 const d=await r.json();
 alert(d.message||'سفارش ثبت شد');
 }catch(e){alert('خطا در ثبت سفارش')}
}
render();
</script></body></html>'''


@app.get('/')
def home():
    if setting('mini_app_enabled', '1') != '1':
        return '<h2 style="font-family:Arial;text-align:center;margin-top:20vh">Mini App غیرفعال است.</h2>', 503
    return render_template_string(HTML, version=VERSION)


@app.get('/health')
def health():
    return jsonify({'ok': True, 'service': 'iranbot-mini-app', 'port': MINI_APP_PORT, 'version': VERSION})


@app.get('/api/products')
def products():
    try:
        with db() as c:
            rows=c.execute('SELECT id,name,price,description,active FROM products WHERE active=1 ORDER BY id DESC').fetchall()
        return jsonify({'products':[{'id':r[0],'name':r[1],'price':r[2],'description':r[3],'active':bool(r[4])} for r in rows]})
    except Exception as e:
        return jsonify({'products':[], 'error':str(e)[:200]})


@app.get('/api/me')
def me():
    init_data=request.headers.get('X-Telegram-Init-Data','')
    if not telegram_init_data_valid(init_data):
        return jsonify({'user':None,'balance':0,'authenticated':False})
    try:
        data=dict(urllib.parse.parse_qsl(init_data,keep_blank_values=True)); user=json.loads(data.get('user','{}')); uid=int(user['id'])
        with db() as c:
            row=c.execute('SELECT balance FROM wallets WHERE user_id=?',(uid,)).fetchone()
        return jsonify({'user':{'id':uid,'username':user.get('username',''),'first_name':user.get('first_name','')},'balance':row[0] if row else 0,'authenticated':True})
    except Exception:
        return jsonify({'user':None,'balance':0,'authenticated':False})


@app.get('/api/categories')
def categories():
    try:
        with db() as c:
            rows=c.execute("SELECT id,name FROM categories ORDER BY id DESC").fetchall()
        return jsonify({'categories':[{'id':r[0],'name':r[1]} for r in rows]})
    except Exception:
        return jsonify({'categories':[]})

@app.post('/api/order')
def create_order_mini():
    try:
        init_data=request.headers.get('X-Telegram-Init-Data','')
        if not telegram_init_data_valid(init_data):
            return jsonify({'message':'لطفاً Mini App را از داخل Telegram باز کنید.'}),401
        data=dict(urllib.parse.parse_qsl(init_data,keep_blank_values=True))
        user=json.loads(data.get('user','{}')); uid=int(user['id'])
        body=request.get_json(silent=True) or {}
        pid=int(body.get('product_id',0))
        with db() as c:
            product=c.execute('SELECT name,price FROM products WHERE id=? AND active=1',(pid,)).fetchone()
            if not product:
                return jsonify({'message':'محصول پیدا نشد'}),404
            cols=[x[1] for x in c.execute('PRAGMA table_info(orders)').fetchall()]
            if 'status' in cols:
                c.execute("INSERT INTO orders(user_id,product_id,status) VALUES(?,?,?)",(uid,pid,'pending'))
            else:
                c.execute("INSERT INTO orders(user_id,product_id) VALUES(?,?)",(uid,pid))
        return jsonify({'ok':True,'message':'سفارش ثبت شد. ادامه پرداخت از طریق ربات انجام می‌شود.'})
    except Exception as e:
        return jsonify({'message':'خطا در ثبت سفارش','error':str(e)[:100]}),500


def start_mini_app_server():
    app.run(host='0.0.0.0', port=MINI_APP_PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    start_mini_app_server()
