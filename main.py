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

TOKEN = '8982114650:AAH9EVAcP9bJnm_3VC72J_o7vMpfTlim2W4'
bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

SYMBOLS = {
    "الذهب 🥇": "XAUUSD=X",
    "اليورو/دولار 💶": "EURUSD=X",
    "البيتكوين ₿": "BTC-USD"
}

last_states = {
    "الذهب 🥇": "NONE",
    "اليورو/دولار 💶": "NONE",
    "البيتكوين ₿": "NONE"
}

def init_db():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, alerts INTEGER DEFAULT 1)''')
    conn.commit()
    conn.close()

init_db()

def add_user(chat_id):
    try:
        conn = sqlite3.connect('bot_users.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO users (chat_id, alerts) VALUES (?, 1)', (chat_id,))
        conn.commit()
        conn.close()
    except:
        pass

def get_alert_users():
    try:
        conn = sqlite3.connect('bot_users.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT chat_id FROM users WHERE alerts = 1')
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except:
        return []

def fetch_data(symbol, tf, period="30d"):
    try:
        # تعديل لضمان استدعاء البيانات وتحديث الشموع الأخيرة
        df = yf.download(symbol, period=period, interval=tf, progress=False, auto_adjust=True)
        if df.empty and symbol == "XAUUSD=X":
            df = yf.download("GC=F", period=period, interval=tf, progress=False, auto_adjust=True)
        return df
    except:
        return pd.DataFrame()

def get_main_trend_200(symbol):
    df_4h = fetch_data(symbol, "1h", "30d")
    if df_4h.empty or len(df_4h) < 100:
        return "NEUTRAL"
    
    close_prices = df_4h['Close'].dropna().squeeze()
    ema200 = close_prices.ewm(span=200, adjust=False).mean().iloc[-1]
    current_price = close_prices.iloc[-1]
    return "BULLISH" if current_price > ema200 else "BEARISH"

def analyze_smc_setup(symbol):
    df_15m = fetch_data(symbol, "15m", "3d")
    df_1h = fetch_data(symbol, "1h", "10d")

    if df_15m.empty or df_1h.empty:
        return None

    close_15m = df_15m['Close'].dropna().squeeze()
    
    # تحسين الخانات العشرية: 5 لليورو ليتطابق مع MT5 و 2 لباقي الأصول
    decimals = 5 if "EURUSD" in symbol else 2
    current_price = round(float(close_15m.iloc[-1]), decimals)
    main_trend = get_main_trend_200(symbol)

    # تحديد سُمك المنطقة بأسلوب دقيق لكل زوج
    if "EURUSD" in symbol:
        step = 0.0005
    elif "BTC" in symbol:
        step = 20.0
    else:
        step = 1.5

    high_1h = df_1h['High'].dropna().squeeze()
    low_1h = df_1h['Low'].dropna().squeeze()

    demand_low = round(float(low_1h.iloc[-20:].min()), decimals)
    demand_high = round(demand_low + step, decimals)

    supply_high = round(float(high_1h.iloc[-20:].max()), decimals)
    supply_low = round(supply_high - step, decimals)

    return {
        "price": current_price,
        "signal": "NONE",
        "trend": main_trend,
        "demand": f"{demand_low} ⟷ {demand_high}",
        "supply": f"{supply_low} ⟷ {supply_high}",
        "demand_low": demand_low,
        "supply_high": supply_high
    }

def background_monitor():
    time.sleep(15)
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
                        decimals = 5 if "EURUSD" in sym else 2

                        if current_state == "BUY":
                            sl = round(analysis["demand_low"] - (100.0 if "BTC" in sym else (0.00100 if "EURUSD" in sym else 2.0)), decimals)
                            risk = price - sl
                            tp1 = round(price + (risk * 1.5), decimals)
                            tp2 = round(price + (risk * 3.0), decimals)
                            direction = "شراء (BUY) 📈"
                        else:
                            sl = round(analysis["supply_high"] + (100.0 if "BTC" in sym else (0.00100 if "EURUSD" in sym else 2.0)), decimals)
                            risk = sl - price
                            tp1 = round(price - (risk * 1.5), decimals)
                            tp2 = round(price - (risk * 3.0), decimals)
                            direction = "بيع (SELL) 📉"

                        msg = (
                            f"🚨 **تنبيه SMC احترافي على {name}** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 الصفقة: {direction}\n"
                            f"📍 سعر الدخول: `{price}`\n"
                            f"🧱 المنطقة: `{analysis['demand'] if current_state == 'BUY' else analysis['supply']}`\n"
                            f"⛔ وقف الخسارة (SL): `{sl}`\n"
                            f"🎯 الهدف الأول (TP1): `{tp1}`\n"
                            f"🎯 Target الثاني (TP2): `{tp2}`"
                        )

                        for chat_id in users:
                            try:
                                bot.send_message(chat_id, msg, parse_mode="Markdown")
                            except:
                                pass
            time.sleep(120)
        except Exception:
            time.sleep(120)

threading.Thread(target=background_monitor, daemon=True).start()

@app.route('/')
def home():
    return "Bot Active!", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

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
        f"👑 **ماسح SMC المطور (BOS + OB + FVG)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر الزوج لمعاينة تحليله اللحظي."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text
    add_user(chat_id)

    if text in SYMBOLS:
        wait_msg = bot.send_message(chat_id, f"⏳ جاري فحص هيكل السوق لـ {text}...")
        symbol = SYMBOLS[text]
        analysis = analyze_smc_setup(symbol)

        if not analysis:
            bot.edit_message_text(f"⚠️ تعذر جلب البيانات لـ {text} حالياً.", chat_id, wait_msg.message_id)
            return

        trend_str = "📈 صاعد" if analysis['trend'] == "BULLISH" else "📉 هابط"
        msg = (
            f"📊 **تقرير هيكل السوق لـ ({text}):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 الاتجاه العام: `{trend_str}`\n"
            f"📍 السعر الحالي: `{analysis['price']}`\n"
            f"🧱 منطقة الطلب (Demand): `{analysis['demand']}`\n"
            f"🧱 منطقة العرض (Supply): `{analysis['supply']}`\n"
            f"⚡ الإشارة الحالية: `{analysis['signal']}`"
        )
        bot.edit_message_text(msg, chat_id, wait_msg.message_id, parse_mode="Markdown")

def setup_webhook():
    time.sleep(3)
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        webhook_url = f"{external_url}/{TOKEN}"
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)

threading.Thread(target=setup_webhook, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)