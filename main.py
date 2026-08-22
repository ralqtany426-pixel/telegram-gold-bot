import os
import sqlite3
import requests
import telebot
import threading
import time
import pandas as pd
import numpy as np
import yfinance as yf
from flask import Flask, request
from telebot import types

# --- 1. إعدادات المفتاح والبوت ---
TOKEN = '8982114650:AAH9EVAcP9bJnm_3VC72J_o7vMpfTlim2W4'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# قائمة الأزواج المدعومة
SYMBOLS = {
    "الذهب 🥇": "GC=F",
    "اليورو/دولار 💶": "EURUSD=X",
    "البيتكوين ₿": "BTC-USD"
}

# حالات التنبيه الأخيرة لكل زوج لمنع التكرار
last_states = {
    "الذهب 🥇": "NONE",
    "اليورو/دولار 💶": "NONE",
    "البيتكوين ₿": "NONE"
}

# --- 2. قاعدة البيانات للمشتركين ---
def init_db():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, alerts INTEGER DEFAULT 1)''')
    conn.commit()
    conn.close()

init_db()

def add_user(chat_id):
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (chat_id, alerts) VALUES (?, 1)', (chat_id,))
    conn.commit()
    conn.close()

def get_alert_users():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM users WHERE alerts = 1')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# --- 3. جلب البيانات وتحليل الاتجاه بـ 200 شمعة ---
def fetch_data(symbol, tf, period="60d"):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=tf)
        if df.empty and symbol == "GC=F":
            ticker = yf.Ticker("XAUUSD=X")
            df = ticker.history(period=period, interval=tf)
        return df
    except:
        return pd.DataFrame()

def get_main_trend_200(symbol):
    df_4h = fetch_data(symbol, "1h", "60d")
    if df_4h.empty or len(df_4h) < 200:
        return "NEUTRAL"
    
    ema200 = df_4h['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
    current_price = df_4h['Close'].iloc[-1]

    return "BULLISH" if current_price > ema200 else "BEARISH"

# --- 4. محرك التحليل الشامل (SMC + EMA 200) ---
def analyze_smc_setup(symbol):
    df_15m = fetch_data(symbol, "15m", "5d")
    df_1h = fetch_data(symbol, "1h", "20d")

    if df_15m.empty or df_1h.empty:
        return None

    current_price = round(df_15m['Close'].iloc[-1], 4 if "EURUSD" in symbol else 2)
    main_trend = get_main_trend_200(symbol)

    df_1h['highest_high'] = df_1h['High'].shift(1).rolling(20).max()
    df_1h['lowest_low'] = df_1h['Low'].shift(1).rolling(20).min()

    bullish_ob = (df_1h['Close'] < df_1h['Open']) & (df_1h['High'].shift(-1) > df_1h['highest_high'])
    bearish_ob = (df_1h['Close'] > df_1h['Open']) & (df_1h['Low'].shift(-1) < df_1h['lowest_low'])

    df_demand = df_1h[bullish_ob]
    df_supply = df_1h[bearish_ob]

    step = 0.0010 if "EURUSD" in symbol else 3.5

    if not df_demand.empty:
        demand_low = round(df_demand.iloc[-1]['Low'], 4 if "EURUSD" in symbol else 2)
        demand_high = round(df_demand.iloc[-1]['High'], 4 if "EURUSD" in symbol else 2)
    else:
        demand_low = round(df_1h['Low'].iloc[-30:-1].min(), 4 if "EURUSD" in symbol else 2)
        demand_high = round(demand_low + step, 4 if "EURUSD" in symbol else 2)

    if not df_supply.empty:
        supply_high = round(df_supply.iloc[-1]['High'], 4 if "EURUSD" in symbol else 2)
        supply_low = round(df_supply.iloc[-1]['Low'], 4 if "EURUSD" in symbol else 2)
    else:
        supply_high = round(df_1h['High'].iloc[-30:-1].max(), 4 if "EURUSD" in symbol else 2)
        supply_low = round(supply_high - step, 4 if "EURUSD" in symbol else 2)

    has_fvg_buy = df_15m['Low'].iloc[-1] > df_15m['High'].iloc[-3]
    has_fvg_sell = df_15m['High'].iloc[-1] < df_15m['Low'].iloc[-3]

    signal_type = "NONE"
    if (demand_low <= current_price <= demand_high) and has_fvg_buy and (main_trend == "BULLISH"):
        signal_type = "BUY"
    elif (supply_low <= current_price <= supply_high) and has_fvg_sell and (main_trend == "BEARISH"):
        signal_type = "SELL"

    return {
        "price": current_price,
        "signal": signal_type,
        "trend": main_trend,
        "demand": f"{demand_low} ⟷ {demand_high}",
        "supply": f"{supply_low} ⟷ {supply_high}",
        "demand_low": demand_low,
        "supply_high": supply_high
    }

# --- 5. نظام التنبيه الخلفي لجميع الأزواج ---
def background_monitor():
    time.sleep(10)
    while True:
        try:
            for name, sym in SYMBOLS.items():
                analysis = analyze_smc_setup(sym)
                if analysis and analysis["signal"] != "NONE":
                    current_state = analysis["signal"]
                    if current_state != last_states[name]:
                        last_states[name] = current_state
                        price = analysis["price"]
                        users = get_alert_users()

                        is_forex = "EURUSD" in sym
                        sl_offset = 0.0015 if is_forex else 2.5
                        tp1_offset = 0.0030 if is_forex else 5.0
                        tp2_offset = 0.0070 if is_forex else 12.0

                        if current_state == "BUY":
                            sl = round(analysis["demand_low"] - sl_offset, 4 if is_forex else 2)
                            tp1 = round(price + tp1_offset, 4 if is_forex else 2)
                            tp2 = round(price + tp2_offset, 4 if is_forex else 2)
                            direction = "شراء (BUY) 📈"
                        else:
                            sl = round(analysis["supply_high"] + sl_offset, 4 if is_forex else 2)
                            tp1 = round(price - tp1_offset, 4 if is_forex else 2)
                            tp2 = round(price - tp2_offset, 4 if is_forex else 2)
                            direction = "بيع (SELL) 📉"

                        msg = (
                            f"🚨 **تنبيه SMC مؤكد على {name}** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 الصفقة: {direction}\n"
                            f"📍 سعر الدخول: `{price}`\n"
                            f"🧱 المنطقة المفعلة: `{analysis['demand'] if current_state == 'BUY' else analysis['supply']}`\n"
                            f"⛔ وقف الخسارة (SL): `{sl}`\n"
                            f"🎯 الهدف الأول (TP1): `{tp1}`\n"
                            f"🎯 الهدف الثاني (TP2): `{tp2}`\n\n"
                            f"💡 *نفذ الصفقة يدوياً من تطبيق MT5.*"
                        )

                        for chat_id in users:
                            try:
                                bot.send_message(chat_id, msg, parse_mode="Markdown")
                            except:
                                pass
            time.sleep(60)
        except Exception:
            time.sleep(60)

threading.Thread(target=background_monitor, daemon=True).start()

# --- 6. التشغيل عبر Flask و Webhook ---
@app.route('/')
def home():
    return "Multi-Asset SMC Bot Active!", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

@bot.message_handler(commands=['start'])
def start_command(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(
        types.KeyboardButton("الذهب 🥇"),
        types.KeyboardButton("اليورو/دولار 💶"),
        types.KeyboardButton("البيتكوين ₿")
    )
    welcome_text = (
        f"👑 **ماسح SMC الشامل للأسواق**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"البوت يراقب حالياً: الذهب، اليورو/دولار، والبيتكوين.\n"
        f"اختر الزوج من الأزرار بالأسفل لمعاينة تحليله اللحظي."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text
    add_user(chat_id)

    if text in SYMBOLS:
        symbol = SYMBOLS[text]
        analysis = analyze_smc_setup(symbol)
        
        if not analysis:
            bot.send_message(chat_id, f"⚠️ جاري الاتصال وتحديث بيانات {text}...")
            return

        trend_str = "📈 صاعد" if analysis['trend'] == "BULLISH" else "📉 هابط"
        msg = (
            f"📊 **تقرير هيكل السوق لـ ({text}):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 الاتجاه العام (200 شمعة): `{trend_str}`\n"
            f"📍 السعر الحالي: `{analysis['price']}`\n"
            f"🧱 منطقة الطلب (Demand OB): `{analysis['demand']}`\n"
            f"🧱 منطقة العرض (Supply OB): `{analysis['supply']}`\n"
            f"⚡ الإشارة الحالية: `{analysis['signal']}`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"{external_url}/{TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)