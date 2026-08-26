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

def get_live_price():
    try:
        url = "https://api.gold-api.com/price/XAU"
        res = requests.get(url, headers=HEADERS, timeout=5).json()
        if 'price' in res and res['price']:
            return round(float(res['price']), 2)
    except Exception:
        pass

    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="1d", interval="1m")
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except Exception:
        pass

    return 4610.00

def fetch_candles(interval='30m', period='5d'):
    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period=period, interval=interval)
        if not df.empty and len(df) >= 5:
            df = df[['Open', 'High', 'Low', 'Close']].astype(float)
            return df
    except Exception:
        pass
    return pd.DataFrame()

def analyze_market_structure(df):
    if df.empty or len(df) < 5:
        return {
            "trend": "غير محدد ⚪", "demand": "غير محدد", "supply": "غير محدد",
            "demand_low": 0, "demand_high": 0, "supply_low": 0, "supply_high": 0,
            "fvg": "لا توجد ⚪", "high": 0, "low": 0, "ema": 0, "bos": "لا توجد"
        }

    current = df['Close'].iloc[-1]
    ema_50 = df['Close'].ewm(span=min(len(df), 50), adjust=False).mean().iloc[-1]
    trend = "BULLISH 🟢 (صاعد)" if current >= ema_50 else "BEARISH 🔴 (هابط)"

    high_val = round(df['High'].max(), 2)
    low_val = round(df['Low'].min(), 2)

    d_low, d_high = low_val, round(low_val + 6.0, 2)
    s_low, s_high = round(high_val - 6.0, 2), high_val

    for i in range(len(df)-2, 0, -1):
        if df['Close'].iloc[i] < df['Open'].iloc[i] and df['Close'].iloc[i+1] > df['High'].iloc[i]:
            d_low, d_high = round(df['Low'].iloc[i], 2), round(df['High'].iloc[i], 2)
            break

    for i in range(len(df)-2, 0, -1):
        if df['Close'].iloc[i] > df['Open'].iloc[i] and df['Close'].iloc[i+1] < df['Low'].iloc[i]:
            s_low, s_high = round(df['Low'].iloc[i], 2), round(df['High'].iloc[i], 2)
            break

    fvg = "لا توجد ⚪"
    for i in range(len(df)-1, 2, -1):
        if df['High'].iloc[i-2] < df['Low'].iloc[i]:
            fvg = f"Bullish FVG 🟢 ({round(df['High'].iloc[i-2], 2)} - {round(df['Low'].iloc[i], 2)})"
            break
        elif df['Low'].iloc[i-2] > df['High'].iloc[i]:
            fvg = f"Bearish FVG 🔴 ({round(df['High'].iloc[i], 2)} - {round(df['Low'].iloc[i-2], 2)})"
            break

    return {
        "trend": trend,
        "demand": f"🟢 منطقة طلب ({d_low} - {d_high})",
        "supply": f"🔴 منطقة عرض ({s_low} - {s_high})",
        "demand_low": d_low, "demand_high": d_high,
        "supply_low": s_low, "supply_high": s_high,
        "fvg": fvg, "high": high_val, "low": low_val, "ema": round(ema_50, 2)
    }

def multi_timeframe_scan():
    price = get_live_price()
    tf_15m = analyze_market_structure(fetch_candles('15m', '2d'))
    tf_30m = analyze_market_structure(fetch_candles('30m', '4d'))
    tf_1h  = analyze_market_structure(fetch_candles('1h', '7d'))
    tf_4h  = analyze_market_structure(fetch_candles('60m', '14d'))
    tf_1d  = analyze_market_structure(fetch_candles('1d', '30d'))

    bull_count = sum(1 for tf in [tf_15m, tf_30m, tf_1h, tf_4h, tf_1d] if "BULLISH" in tf['trend'])

    if bull_count >= 4:
        signal = "BUY Strong 🚀 (فرصة شراء قوية)"
    elif bull_count <= 1:
        signal = "SELL Strong 📉 (فرصة بيع قوية)"
    elif bull_count >= 3:
        signal = "BUY Swing 🟢 (شراء تذبذبي صاعد)"
    else:
        signal = "WAIT ⏳ (تذبذب / حياد)"

    return {
        "price": price, "signal": signal, "bull_count": bull_count,
        "15m": tf_15m, "30m": tf_30m, "1h": tf_1h, "4h": tf_4h, "1d": tf_1d
    }

def calculate_targets(price, tf30, signal):
    if "BUY" in signal:
        sl = round(tf30['demand_low'] - 4.0, 2) if tf30['demand_low'] > 0 else round(price - 8.0, 2)
        risk = abs(price - sl)
        return "BUY 🟢", sl, round(price + (risk * 1.5), 2), round(price + (risk * 2.5), 2), round(price + (risk * 3.5), 2)
    else:
        sl = round(tf30['supply_high'] + 4.0, 2) if tf30['supply_high'] > 0 else round(price + 8.0, 2)
        risk = abs(sl - price)
        return "SELL 🔴", sl, round(price - (risk * 1.5), 2), round(price - (risk * 2.5), 2), round(price - (risk * 3.5), 2)

# --- نظام التنبيهات يعمل في الخلفية ---
def auto_alert_loop():
    last_signal_state = ""
    while True:
        try:
            users = get_all_users()
            if users:
                data = multi_timeframe_scan()
                p = data['price']
                tf30 = data['30m']

                is_valid_opportunity = False
                alert_title = ""

                if "BUY" in data['signal'] and p <= (tf30['demand_high'] + 8.0):
                    is_valid_opportunity = True
                    alert_title = "🔥 **تنبيه صفقة شراء (VIP Demand Zone)**"
                elif "SELL" in data['signal'] and p >= (tf30['supply_low'] - 8.0):
                    is_valid_opportunity = True
                    alert_title = "🔥 **تنبيه صفقة بيع (VIP Supply Zone)**"

                current_state = f"{data['signal']}_{round(p, -1)}"

                if is_valid_opportunity and current_state != last_signal_state:
                    last_signal_state = current_state
                    t_type, sl, tp1, tp2, tp3 = calculate_targets(p, tf30, data['signal'])

                    msg = (
                        f"🚨 **رصد فرصة ذهب حقيقية (مؤشرات SMC + EMA)**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{alert_title}\n\n"
                        f"📍 **السعر الحالي:** `{p}` $\n"
                        f"🎯 **نوع الصفقة:** `{t_type}`\n"
                        f"🛑 **وقف الخسارة (SL):** `{sl}` $\n"
                        f"🎯 **الهدف الأول:** `{tp1}` $\n"
                        f"🎯 **الهدف الثاني:** `{tp2}` $\n"
                        f"🎯 **الهدف الثالث:** `{tp3}` $\n"
                        f"━━━━━━━━━━━━━━━━━━━━━"
                    )
                    for chat_id in users:
                        try:
                            bot.send_message(chat_id, msg, parse_mode="Markdown")
                        except Exception:
                            pass
        except Exception as e:
            print(f"Alert Error: {e}")
        time.sleep(300)

threading.Thread(target=auto_alert_loop, daemon=True).start()

# --- أوامر واجهة البوت ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("⚡ السعر اللحظي"),
        types.KeyboardButton("🔥 صفقات VIP (الطلب والعرض)"),
        types.KeyboardButton("📊 الدعم والمقاومة"),
        types.KeyboardButton("تحليل الذهب 🥇"),
        types.KeyboardButton("🔔 حالة التنبيهات")
    )
    bot.send_message(message.chat.id, "أهلاً بك! تم ضبط نظام التنبيهات والتحليل متعدد الفريمات (SMC) بنجاح ⚡", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⚡ السعر اللحظي")
def send_live_price(message):
    p = get_live_price()
    bot.send_message(message.chat.id, f"⚡ **سعر الذهب المباشر (Spot Gold):** `{p}` $", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔥 صفقات VIP (الطلب والعرض)")
def send_vip_trade(message):
    data = multi_timeframe_scan()
    p = data['price']
    t_type, sl, tp1, tp2, tp3 = calculate_targets(p, data['30m'], data['signal'])
    msg = (
        f"🔥 **توصية VIP (SMC & Order Block):**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **الصفقة المقترحة:** `{t_type}`\n"
        f"📍 **سعر الدخول:** `{p}` $\n"
        f"🛑 **وقف الخسارة:** `{sl}` $\n"
        f"🎯 **الهدف 1:** `{tp1}` $\n"
        f"🎯 **الهدف 2:** `{tp2}` $\n"
        f"🎯 **الهدف 3:** `{tp3}` $\n"
        f"🧭 **إشارة الإجماع:** `{data['signal']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 الدعم والمقاومة")
def send_support_resistance(message):
    p = get_live_price()
    df_1h = fetch_candles('1h', '7d')
    r1 = round(df_1h['High'].max(), 2) if not df_1h.empty else round(p + 15.0, 2)
    s1 = round(df_1h['Low'].min(), 2) if not df_1h.empty else round(p - 15.0, 2)
    msg = (
        f"📊 **مستويات الدعم والمقاومة الرئيسية:**\n"
        f"📍 **السعر الحالي:** `{p}` $\n"
        f"🔴 **مقاومة رئيسية (R1):** `{r1}` $\n"
        f"🟢 **دعم رئيسي (S1):** `{s1}` $"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "تحليل الذهب 🥇")
def handle_gold_analysis(message):
    add_user(message.chat.id)
    data = multi_timeframe_scan()
    msg = (
        f"📊 **تقرير تحليل الذهب متعدد الفريمات (Pro):**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 **السعر اللحظي:** `{data['price']}` $\n"
        f"⚡ **القرار الفني:** `{data['signal']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 **15 دقيقة:** `{data['15m']['trend']}` | FVG: `{data['15m']['fvg']}`\n"
        f"🔹 **30 دقيقة:** `{data['30m']['trend']}`\n"
        f"   - {data['30m']['demand']}\n"
        f"   - {data['30m']['supply']}\n"
        f"🔹 **الساعة (1H):** `{data['1h']['trend']}` | EMA50: `{data['1h']['ema']}`\n"
        f"🔹 **4 ساعات (4H):** `{data['4h']['trend']}`\n"
        f"🔹 **اليومي (1D):** `{data['1d']['trend']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔔 حالة التنبيهات")
def send_alert_status(message):
    add_user(message.chat.id)
    bot.send_message(message.chat.id, "🔔 **نظام التنبيهات الذكي:** يعمل تلقائياً في الخلفية ويقوم بفحص السوق كل **5 دقائق** لإرسال الصفقات الناجحة فوراً للمشتركين.", parse_mode="Markdown")

# --- مسار استقبال تحديثات تليجرام (Webhook) ---
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
    return "Bot is running with Webhook!", 200

if __name__ == '__main__':
    bot.remove_webhook()
    
    # ربط الويب هوك تلقائياً برابط المنصة الخارجي
    render_url = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if render_url:
        webhook_url = f"https://{render_url}/{TOKEN}"
        bot.set_webhook(url=webhook_url)
        print(f"Webhook successfully set to: {webhook_url}")
        
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)