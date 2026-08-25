import os
import time
import sqlite3
import threading
import telebot
import pandas as pd
import yfinance as yf
from flask import Flask, request
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN غير موجود!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# --- قاعدة البيانات ---
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

# --- جلب الشمعات والسعر اللحظي عن طريق yfinance ---
def fetch_candles_yf(interval='30m', period='5d'):
    try:
        ticker = yf.Ticker("GC=F") # العقود الآجلة للذهب
        df = ticker.history(period=period, interval=interval)
        if not df.empty:
            df = df[['Open', 'High', 'Low', 'Close']].astype(float)
            return df
    except Exception as e:
        print(f"Error fetching data: {e}")
    return pd.DataFrame()

def get_live_price():
    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="1d", interval="1m")
        if not df.empty:
            return round(df['Close'].iloc[-1], 2)
    except Exception as e:
        print(f"Error getting live price: {e}")
    return None

def analyze_timeframe(df):
    if df.empty or len(df) < 5:
        return {
            "trend": "غير معروف ⚪", "demand": "غير محدد", "supply": "غير محدد", 
            "demand_low": 0, "demand_high": 0, "supply_low": 0, "supply_high": 0,
            "fvg": "لا توجد ⚪", "high": 0, "low": 0
        }

    current = df['Close'].iloc[-1]
    ema = df['Close'].ewm(span=min(len(df), 20), adjust=False).mean().iloc[-1]
    trend = "BULLISH 🟢" if current >= ema else "BEARISH 🔴"

    high_val = round(df['High'].max(), 2)
    low_val = round(df['Low'].min(), 2)

    d_low, d_high = low_val, round(low_val + 2.5, 2)
    s_low, s_high = round(high_val - 2.5, 2), high_val

    for i in range(len(df)-2, 1, -1):
        if df['Close'].iloc[i] < df['Open'].iloc[i] and df['Close'].iloc[i+1] > df['High'].iloc[i]:
            d_low, d_high = round(df['Low'].iloc[i], 1), round(df['High'].iloc[i], 1)
            break

    for i in range(len(df)-2, 1, -1):
        if df['Close'].iloc[i] > df['Open'].iloc[i] and df['Close'].iloc[i+1] < df['Low'].iloc[i]:
            s_low, s_high = round(df['Low'].iloc[i], 1), round(df['High'].iloc[i], 1)
            break

    return {
        "trend": trend, "demand": f"🟢 Demand ({d_low} - {d_high})", "supply": f"🔴 Supply ({s_low} - {s_high})", 
        "demand_low": d_low, "demand_high": d_high, "supply_low": s_low, "supply_high": s_high,
        "high": high_val, "low": low_val
    }

def scan_multi_timeframe_smc():
    df_30m = fetch_candles_yf('30m', '5d')
    df_1h  = fetch_candles_yf('1h', '7d')
    df_4h  = fetch_candles_yf('60m', '14d')
    df_1d  = fetch_candles_yf('1d', '30d')
    price  = get_live_price()

    if df_30m.empty or price is None:
        return None

    tf_30m = analyze_timeframe(df_30m)
    tf_1h  = analyze_timeframe(df_1h)
    tf_4h  = analyze_timeframe(df_4h)
    tf_1d  = analyze_timeframe(df_1d)

    bull_count = sum(1 for tf in [tf_30m, tf_1h, tf_4h, tf_1d] if "BULLISH" in tf['trend'])

    if bull_count >= 3:
        signal = "BUY Strong 🚀 (توافق صاعد قوي)"
    elif bull_count <= 1:
        signal = "SELL Strong 📉 (توافق هابط قوي)"
    else:
        signal = "WAIT ⏳ (تضارب الاتجاهات)"

    return {
        "price": price, "30m": tf_30m, "1h": tf_1h, "4h": tf_4h, "1d": tf_1d, "signal": signal
    }

# --- المنبه التلقائي للصفقات الناجحة ---
def auto_alert_loop():
    last_alert_key = ""
    while True:
        try:
            time.sleep(60)
            users = get_all_users()
            if not users:
                continue

            res = scan_multi_timeframe_smc()
            if res:
                p = res['price']
                tf30 = res['30m']
                
                is_high_winrate = False
                alert_type = ""
                
                if "BUY Strong" in res['signal'] and tf30['demand_low'] <= p <= (tf30['demand_high'] + 1.0):
                    is_high_winrate = True
                    alert_type = "🔥 **صفقة شراء VIP عالية النجاح!**"
                elif "SELL Strong" in res['signal'] and (tf30['supply_low'] - 1.0) <= p <= tf30['supply_high']:
                    is_high_winrate = True
                    alert_type = "🔥 **صفقة بيع VIP عالية النجاح!**"

                current_key = f"{res['signal']}_{is_high_winrate}_{round(p, 1)}"

                if is_high_winrate and current_key != last_alert_key:
                    last_alert_key = current_key
                    sl = round(tf30['demand_low'] - 3.0, 2) if "شراء" in alert_type else round(tf30['supply_high'] + 3.0, 2)
                    tp = round(tf30['supply_low'], 2) if "شراء" in alert_type else round(tf30['demand_high'], 2)

                    alert_msg = (
                        f"🚨 **تنبيه صفقة ناجحة معتمدة!**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{alert_type}\n\n"
                        f"📍 **السعر اللحظي:** `{p}` $\n"
                        f"🛑 **وقف الخسارة (SL):** `{sl}` $\n"
                        f"🎯 **الهدف (TP):** `{tp}` $\n"
                        f"━━━━━━━━━━━━━━━━━━━━━"
                    )
                    for chat_id in users:
                        try:
                            bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                        except Exception as e:
                            print(f"Failed alert: {e}")
        except Exception as e:
            print(f"Error in alert loop: {e}")

threading.Thread(target=auto_alert_loop, daemon=True).start()

# --- واجهة البوت والتنقل ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_live = types.KeyboardButton("⚡ السعر اللحظي")
    btn_vip = types.KeyboardButton("🔥 صفقات VIP (الطلب والعرض)")
    btn_sr = types.KeyboardButton("📊 الدعم والمقاومة")
    btn_gold = types.KeyboardButton("تحليل الذهب 🥇")
    markup.add(btn_live, btn_vip, btn_sr, btn_gold)
    
    bot.send_message(message.chat.id, "مرحباً بك! تم تشغيل البوت بنجاح 🔔", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⚡ السعر اللحظي")
def send_live_price(message):
    p = get_live_price()
    if p:
        bot.send_message(message.chat.id, f"⚡ **سعر الذهب المباشر:** `{p}` $", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ فشل جلب السعر المباشر.")

@bot.message_handler(func=lambda m: m.text == "🔥 صفقات VIP (الطلب والعرض)")
def send_vip_trade(message):
    res = scan_multi_timeframe_smc()
    if not res:
        bot.send_message(message.chat.id, "⚠️ يتعذر حساب صفقات VIP الآن.")
        return

    p = res['price']
    tf30 = res['30m']
    
    if "BUY" in res['signal']:
        sl, tp, trade_type = round(tf30['demand_low'] - 2.5, 2), round(tf30['supply_low'], 2), "BUY 🟢"
    else:
        sl, tp, trade_type = round(tf30['supply_high'] + 2.5, 2), round(tf30['demand_high'], 2), "SELL 🔴"

    msg = (
        f"🔥 **توصية VIP (SMC):**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **نوع الصفقة:** `{trade_type}`\n"
        f"📍 **الدخول:** `{p}` $\n"
        f"🛑 **SL:** `{sl}` $\n"
        f"🎯 **TP:** `{tp}` $\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 الدعم والمقاومة")
def send_support_resistance(message):
    df_1h = fetch_candles_yf('1h', '7d')
    p = get_live_price()
    if not df_1h.empty and p:
        r1 = round(df_1h['High'].tail(24).max(), 2)
        s1 = round(df_1h['Low'].tail(24).min(), 2)
        msg = (
            f"📊 **الدعم والمقاومة (XAU/USD):**\n"
            f"📍 **السعر الحالي:** `{p}` $\n"
            f"🔴 **المقاومة (R1):** `{r1}` $\n"
            f"🟢 **الدعم (S1):** `{s1}` $"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "تحليل الذهب 🥇")
def handle_gold_analysis(message):
    add_user(message.chat.id)
    res = scan_multi_timeframe_smc()
    if res:
        msg = (
            f"📊 **تحليل هيكل السوق (30M SMC Pro):**\n"
            f"📍 **السعر اللحظي:** `{res['price']}` $\n"
            f"⚡ **الإشارة:** `{res['signal']}`\n"
            f"🔹 **الطلب:** `{res['30m']['demand']}`\n"
            f"🔹 **العرض:** `{res['30m']['supply']}`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# --- خادم Webhook لـ Render ---
@app.route('/')
def home():
    return "Bot Online", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)