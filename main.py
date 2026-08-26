import os
import time
import sqlite3
import threading
import requests
import telebot
import pandas as pd
import yfinance as yf
from telebot import types
from flask import Flask, request

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN غير موجود في متغيرات البيئة!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

DB_NAME = "users.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY)")
        conn.commit()

def add_user(chat_id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR IGNORE INTO users (chat_id) VALUES (?)", (chat_id,))
        conn.commit()

def get_all_users():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM users")
        return [row[0] for row in cursor.fetchall()]

init_db()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# متغيرات التخزين المؤقت (Cache) لمنع بطء الاتصال بالإنترنت عند الضغط المتكرر
cached_price = 2650.00
last_fetch_time = 0

def get_live_price():
    global cached_price, last_fetch_time
    # إذا مر أقل من 30 ثانية، استخدم السعر المخزن مؤقتاً لتكون الاستجابة فورية 100%
    if time.time() - last_fetch_time < 30 and cached_price > 0:
        return cached_price

    try:
        url = "https://api.gold-api.com/price/XAU"
        res = requests.get(url, headers=HEADERS, timeout=2).json()
        if 'price' in res and res['price']:
            cached_price = round(float(res['price']), 2)
            last_fetch_time = time.time()
            return cached_price
    except Exception:
        pass

    return cached_price if cached_price > 0 else 2650.00

def fetch_candles(interval='30m', period='3d'):
    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period=period, interval=interval)
        if not df.empty and len(df) >= 5:
            df = df[['Open', 'High', 'Low', 'Close']].astype(float)
            return df
    except Exception:
        pass
    return pd.DataFrame()

def check_triple_bottom(df):
    if df.empty or len(df) < 10:
        return False, 0
    lows = df['Low'].values
    local_bottoms = []
    for i in range(2, len(lows) - 2):
        if lows[i] <= lows[i-1] and lows[i] <= lows[i-2] and lows[i] <= lows[i+1] and lows[i] <= lows[i+2]:
            local_bottoms.append((i, lows[i]))
            
    if len(local_bottoms) >= 3:
        b1, b2, b3 = local_bottoms[-3][1], local_bottoms[-2][1], local_bottoms[-1][1]
        if abs(b1 - b2) <= 6.0 and abs(b2 - b3) <= 6.0:
            return True, round(b3, 2)
    return False, 0

def analyze_market_structure(df):
    if df.empty or len(df) < 5:
        return {
            "demand_low": 2640, "demand_high": 2650, "fvg": "لا توجد ⚪", "triple_bottom": False
        }

    high_val = round(df['High'].max(), 2)
    low_val = round(df['Low'].min(), 2)
    d_low, d_high = low_val, round(low_val + 10.0, 2)
    
    for i in range(len(df)-2, 0, -1):
        if df['Close'].iloc[i] < df['Open'].iloc[i] and df['Close'].iloc[i+1] > df['High'].iloc[i]:
            d_low, d_high = round(df['Low'].iloc[i], 2), round(df['High'].iloc[i], 2)
            break

    has_tb, tb_price = check_triple_bottom(df)
    return {
        "demand": f"🟢 منطقة طلب / أوردر بلوك ({d_low} - {d_high})",
        "demand_low": d_low, "demand_high": d_high,
        "triple_bottom": has_tb, "tb_price": tb_price
    }

def calculate_targets(price):
    entry = price
    sl = round(entry - 10.0, 2)  
    risk = abs(entry - sl)
    tp1 = round(entry + (risk * 1.5), 2)  
    tp2 = round(entry + (risk * 2.5), 2)  
    tp3 = round(entry + (risk * 3.5), 2)  
    rr_ratio = "1 : 3.5"
    return "BUY 🟢 (شراء فقط)", entry, sl, tp1, tp2, tp3, rr_ratio

def auto_alert_loop():
    time.sleep(15)
    last_alert_type = ""
    while True:
        try:
            users = get_all_users()
            if users:
                p = get_live_price()
                df = fetch_candles('30m', '3d')
                tf30 = analyze_market_structure(df)
                
                d_low = tf30['demand_low']
                d_high = tf30['demand_high']
                has_triple_bottom = tf30['triple_bottom']
                is_at_order_block = (d_low - 3.0) <= p <= (d_high + 5.0)

                alert_msg = ""
                current_state = ""

                if has_triple_bottom:
                    current_state = f"TRIPLE_BOTTOM_{round(p, -1)}"
                    if current_state != last_alert_type:
                        last_alert_type = current_state
                        t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p)
                        alert_msg = (
                            f"🚀🔥 **[ نموذج انعكاسي إيجابي: تكوّن ثلاث قيعان (Triple Bottom) ]** 🔥🚀\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📈 **السوق يشكل نموذج القيعان الثلاثة الصاعد!**\n"
                            f"📍 **سعر الدخول المقترح:** `{entry}` $\n"
                            f"🛑 **وقف الخسارة:** `{sl}` $\n"
                            f"🎯 **الأهداف:** TP1: `{tp1}` | TP2: `{tp2}` | TP3: `{tp3}`\n"
                            f"━━━━━━━━━━━━━━━━━━━━━"
                        )
                elif is_at_order_block:
                    current_state = f"ORDER_BLOCK_{round(p, -1)}"
                    if current_state != last_alert_type:
                        last_alert_type = current_state
                        t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p)
                        alert_msg = (
                            f"🚨 **[ تنبيه هام: وصول الذهب لمنطقة الأوردر بلوك ]** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📍 **السعر الحالي:** `{p}` $\n"
                            f"🧱 **نطاق الطلب:** `{d_low} - {d_high}` $\n"
                            f"🛑 **وقف الخسارة:** `{sl}` $\n"
                            f"🎯 **الأهداف:** TP1: `{tp1}` | TP2: `{tp2}` | TP3: `{tp3}`\n"
                            f"━━━━━━━━━━━━━━━━━━━━━"
                        )

                if alert_msg:
                    for chat_id in users:
                        try:
                            bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                        except Exception:
                            pass
        except Exception:
            pass
        
        time.sleep(300)

threading.Thread(target=auto_alert_loop, daemon=True).start()

@bot.message_handler(commands=['start'])
def start_cmd(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("⚡ السعر اللحظي"),
        types.KeyboardButton("🔥 صفقة شراء VIP حالية"),
        types.KeyboardButton("📊 الدعم والمقاومة"),
        types.KeyboardButton("تحليل الذهب 🥇"),
        types.KeyboardButton("🔔 اختبار إرسال تنبيه الآن")
    )
    bot.send_message(message.chat.id, "👑 أهلاً بك. تم تحسين سرعة استجابة الأزرار لتكون فورية 🚀", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⚡ السعر اللحظي")
def send_live_price(message):
    p = get_live_price()
    bot.send_message(message.chat.id, f"⚡ **سعر الذهب العالمي المباشر (Spot XAU/USD):** `{p}` $ 🏆", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔥 صفقة شراء VIP حالية")
def send_vip_trade(message):
    p = get_live_price()
    t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p)
    msg = (
        f"💎 **[ توصية شراء VIP الاحترافية - SMC ]** 💎\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **الصفقة المقترحة:** `{t_type}`\n"
        f"📍 **سعر الدخول الموصى به:** `{entry}` $\n"
        f"🛑 **وقف الخسارة:** `{sl}` $\n"
        f"🎯 **الهدف 1:** `{tp1}` $\n"
        f"🎯 **الهدف 2:** `{tp2}` $\n"
        f"🎯 **الهدف 3:** `{tp3}` $\n"
        f"⚖️ **نسبة المخاطرة للأرباح:** `{rr}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 الدعم والمقاومة")
def send_support_resistance(message):
    p = get_live_price()
    msg = (
        f"📊 **مستويات السيولة والدعم والمقاومة:**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 **السعر الحالي:** `{p}` $\n"
        f"🔴 **مقاومة رئيسية (R1):** `{round(p + 15, 2)}` $\n"
        f"🟢 **دعم رئيسي / أوردر بلوك (S1):** `{round(p - 15, 2)}` $\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "تحليل الذهب 🥇")
def handle_gold_analysis(message):
    add_user(message.chat.id)
    p = get_live_price()
    df = fetch_candles('30m', '3d')
    tf30 = analyze_market_structure(df)
    tb_status = "مكوّن ورصد بنجاح 🚀" if tf30['triple_bottom'] else "غير متكون حالياً ⚪"
    msg = (
        f"👑 **التقرير الفني الشامل (أسرع وأدق)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 **السعر اللحظي:** `{p}` $\n"
        f"⚡ **الاتجاه العام:** `BUY Only (صاعد)`\n"
        f"🔹 **نموذج القيعان الثلاثة:** `{tb_status}`\n"
        f"🔹 **30 دقيقة:** {tf30['demand']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔔 اختبار إرسال تنبيه الآن")
def test_alert_btn(message):
    add_user(message.chat.id)
    p = get_live_price()
    t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p)
    msg = (
        f"🧪 **[ اختبار نظام التنبيهات الفوري ]** 🧪\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 **تنبيه تجريبي ناجح:**\n"
        f"📍 **السعر الحالي:** `{entry}` $\n"
        f"🛑 **وقف الخسارة:** `{sl}` $\n"
        f"🎯 **الأهداف:** TP1: `{tp1}` | TP2: `{tp2}` | TP3: `{tp3}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    else:
        return "Invalid Data", 403

@app.route('/')
def index():
    return "Bot is running fast with Cache & Webhook!", 200

if __name__ == '__main__':
    bot.remove_webhook()
    render_url = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if render_url:
        webhook_url = f"https://{render_url}/{TOKEN}"
        bot.set_webhook(url=webhook_url)
        print(f"Webhook successfully set to: {webhook_url}")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)