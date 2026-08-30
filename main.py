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

cached_price = 2650.00
last_fetch_time = 0

def fetch_candles(interval='30m', period='3d'):
    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period=period, interval=interval)
        if not df.empty and len(df) >= 10:
            df = df[['Open', 'High', 'Low', 'Close']].astype(float)
            return df
    except Exception:
        pass
    return pd.DataFrame()

def get_live_price():
    global cached_price, last_fetch_time
    if time.time() - last_fetch_time < 30 and cached_price > 0:
        return cached_price

    try:
        url = "https://api.gold-api.com/price/XAU"
        res = requests.get(url, headers=HEADERS, timeout=3).json()
        if 'price' in res and res['price']:
            cached_price = round(float(res['price']), 2)
            last_fetch_time = time.time()
            return cached_price
    except Exception:
        pass

    try:
        df_fallback = fetch_candles(interval='1m', period='1d')
        if not df_fallback.empty:
            cached_price = round(float(df_fallback['Close'].iloc[-1]), 2)
            last_fetch_time = time.time()
            return cached_price
    except Exception:
        pass

    return cached_price if cached_price > 0 else 2650.00

def analyze_smc_liquidity(df):
    if df.empty or len(df) < 15:
        return {
            "demand_low": 2640, "demand_high": 2650,
            "supply_low": 2660, "supply_high": 2670,
            "trend": "NEUTRAL", "sweep_status": "لا توجد سيولة مسحوبة حالياً"
        }

    # تحديد أحدث قمة وقاع للسيولة (Liquidity Pools)
    recent_high = round(df['High'].iloc[-10:-2].max(), 2)
    recent_low = round(df['Low'].iloc[-10:-2].min(), 2)
    
    current_high = df['High'].iloc[-1]
    current_low = df['Low'].iloc[-1]
    last_close = df['Close'].iloc[-1]
    prev_close = df['Close'].iloc[-2]

    low_val = round(df['Low'].min(), 2)
    high_val = round(df['High'].max(), 2)
    d_low, d_high = low_val, round(low_val + 10.0, 2)
    s_low, s_high = round(high_val - 10.0, 2), high_val

    sweep_status = "استقرار في حركة الأسعار داخل النطاق"
    trend = "NEUTRAL"

    # كشف الـ Buy-Side Liquidity Sweep (اختراق القمة ثم الرفض للهبوط)
    if current_high > recent_high and last_close < recent_high:
        sweep_status = f"🔴 تم سحب سيولة الشراء (Buy-Side Sweep) فوق القمة {recent_high}"
        trend = "SELL"
    # كشف الـ Sell-Side Liquidity Sweep (اختراق القاع ثم الصعود)
    elif current_low < recent_low and last_close > recent_low:
        sweep_status = f"🟢 تم سحب سيولة البيع (Sell-Side Sweep) تحت القاع {recent_low}"
        trend = "BUY"
    else:
        trend = "BUY" if last_close > prev_close else "SELL"

    return {
        "demand": f"🟢 منطقة طلب (Demand): ({d_low} - {d_high})",
        "supply": f"🔴 منطقة عرض (Supply): ({s_low} - {s_high})",
        "demand_low": d_low, "demand_high": d_high,
        "supply_low": s_low, "supply_high": s_high,
        "trend": trend,
        "sweep_status": sweep_status
    }

def calculate_targets(price, signal_type):
    entry = price
    if signal_type == "BUY":
        sl = round(entry - 10.0, 2)  
        risk = abs(entry - sl)
        tp1 = round(entry + (risk * 1.5), 2)  
        tp2 = round(entry + (risk * 2.5), 2)  
        tp3 = round(entry + (risk * 3.5), 2)  
        t_label = "BUY 🟢 (شراء بعد سحب السيولة)"
    else:
        sl = round(entry + 10.0, 2)  
        risk = abs(sl - entry)
        tp1 = round(entry - (risk * 1.5), 2)  
        tp2 = round(entry - (risk * 2.5), 2)  
        tp3 = round(entry - (risk * 3.5), 2)  
        t_label = "SELL 🔴 (بيع بعد سحب السيولة)"

    rr_ratio = "1 : 3.5"
    return t_label, entry, sl, tp1, tp2, tp3, rr_ratio

def auto_alert_loop():
    time.sleep(20)
    last_alert_state = ""
    while True:
        try:
            users = get_all_users()
            if users:
                p = get_live_price()
                df = fetch_candles('30m', '3d')
                market = analyze_smc_liquidity(df)

                alert_msg = ""
                current_state = ""

                if "Sweep" in market['sweep_status']:
                    current_state = f"SWEEP_{int(p // 3)}"
                    if current_state != last_alert_state:
                        last_alert_state = current_state
                        t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p, market['trend'])
                        alert_msg = (
                            f"⚡ **[ تنبيه سيولة مؤكد - SMC Sweep ]** ⚡\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🔍 **الحالة:** `{market['sweep_status']}`\n"
                            f"📍 **السعر الحالي:** `{p}` $\n"
                            f"🎯 **التوصية:** `{t_type}`\n"
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
        types.KeyboardButton("🔥 صفقة VIP حالية"),
        types.KeyboardButton("📊 حالة السيولة والـ Sweep"),
        types.KeyboardButton("تحليل الذهب 🥇"),
        types.KeyboardButton("🔔 اختبار إرسال تنبيه الآن")
    )
    bot.send_message(message.chat.id, "👑 أهلاً بك. تم تطوير البوت ليدعم تحليل سحب السيولة (Liquidity Sweep) لتعزيز دقة صفقات الذهب 🚀", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⚡ السعر اللحظي")
def send_live_price(message):
    p = get_live_price()
    bot.send_message(message.chat.id, f"⚡ **سعر الذهب العالمي المباشر (Spot XAU/USD):** `{p}` $ 🏆", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔥 صفقة VIP حالية")
def send_vip_trade(message):
    p = get_live_price()
    df = fetch_candles('30m', '3d')
    market = analyze_smc_liquidity(df)
    signal_type = market['trend']
    t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p, signal_type)

    msg = (
        f"💎 **[ توصية VIP الاحترافية - SMC ]** 💎\n"
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

@bot.message_handler(func=lambda m: m.text == "📊 حالة السيولة والـ Sweep")
def send_liquidity_status(message):
    p = get_live_price()
    df = fetch_candles('30m', '3d')
    market = analyze_smc_liquidity(df)
    msg = (
        f"📊 **مراقبة السيولة الذكية (Liquidity Map):**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 **السعر الحالي:** `{p}` $\n"
        f"🔍 **حالة الـ Sweep:** \n`{market['sweep_status']}`\n"
        f"{market['supply']}\n"
        f"{market['demand']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "تحليل الذهب 🥇")
def handle_gold_analysis(message):
    add_user(message.chat.id)
    p = get_live_price()
    df = fetch_candles('30m', '3d')
    market = analyze_smc_liquidity(df)
    msg = (
        f"👑 **التقرير الفني الشامل (SMC & Sweep)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 **السعر اللحظي:** `{p}` $\n"
        f"⚡ **الحالة الفنية:** `{market['sweep_status']}`\n"
        f"🔹 {market['supply']}\n"
        f"🔹 {market['demand']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔔 اختبار إرسال تنبيه الآن")
def test_alert_btn(message):
    add_user(message.chat.id)
    p = get_live_price()
    _, entry, sl, tp1, tp2, tp3, _ = calculate_targets(p, "BUY")
    msg = (
        f"🧪 **[ اختبار نظام التنبيهات الفوري ]** 🧪\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 **تنبيه تجريبي ناجح (Liquidity Test):**\n"
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
    return "Bot is running with Liquidity Sweep SMC logic!", 200

if __name__ == '__main__':
    bot.remove_webhook()
    render_url = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if render_url:
        webhook_url = f"https://{render_url}/{TOKEN}"
        bot.set_webhook(url=webhook_url)

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)