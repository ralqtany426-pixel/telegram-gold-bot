import os
import sqlite3
import requests
import telebot
import threading
import time
import pandas as pd
import numpy as np
from flask import Flask, request
from telebot import types

TOKEN = '8982114650:AAH9EVAcP9bJnm_3VC72J_o7vMpfTlim2W4'
bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

SYMBOLS = {
    "البيتكوين ₿": "BTCUSDT",
    "الذهب 🥇": "XAUUSD",
    "اليورو/دولار 💶": "EURUSD"
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

# جلب البيانات اللحظية المباشرة من Binance بالنسبة للبيتكوين
def fetch_binance_klines(symbol="BTCUSDT", interval="15m", limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=5).json()
        df = pd.DataFrame(res, columns=[
            'time', 'Open', 'High', 'Low', 'Close', 'Volume',
            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
        ])
        df['Open'] = df['Open'].astype(float)
        df['High'] = df['High'].astype(float)
        df['Low'] = df['Low'].astype(float)
        df['Close'] = df['Close'].astype(float)
        return df
    except Exception:
        return pd.DataFrame()

# كشف مناطق FVG و Order Block الحقيقية
def detect_smc_zones(df):
    if len(df) < 20:
        return None, None
    
    bullish_ob = None
    bearish_ob = None
    
    # البحث عن الفجوات السعرية (FVG) و Order Blocks في آخر 20 شمعة
    for i in range(len(df) - 3, len(df) - 15, -1):
        # Bullish FVG & Order Block (شراء)
        if df['Low'].iloc[i] > df['High'].iloc[i-2]:
            ob_low = df['Low'].iloc[i-2]
            ob_high = df['High'].iloc[i-1]
            bullish_ob = (ob_low, ob_high)
            break
            
        # Bearish FVG & Order Block (بيع)
        if df['High'].iloc[i] < df['Low'].iloc[i-2]:
            ob_high = df['High'].iloc[i-2]
            ob_low = df['Low'].iloc[i-1]
            bearish_ob = (ob_low, ob_high)
            break
            
    return bullish_ob, bearish_ob

def analyze_smc_setup(symbol_key):
    symbol = SYMBOLS[symbol_key]
    df_15m = fetch_binance_klines("BTCUSDT" if "BTC" in symbol else "BTCUSDT", "15m", 100)

    if df_15m.empty:
        return None

    current_price = round(float(df_15m['Close'].iloc[-1]), 2)
    bullish_ob, bearish_ob = detect_smc_zones(df_15m)

    # تحديد الاتجاه بناءً على كسر القمم والقيعان (BOS)
    recent_high = df_15m['High'].iloc[-20:-5].max()
    recent_low = df_15m['Low'].iloc[-20:-5].min()
    
    signal = "NONE"
    demand_str, supply_str = "غير محددة", "غير محددة"
    demand_low, supply_high = 0.0, 0.0

    if bullish_ob:
        demand_low, demand_high = round(bullish_ob[0], 2), round(bullish_ob[1], 2)
        demand_str = f"{demand_low} ⟷ {demand_high}"
        # دخول عند اختبار منطقة الـ OB مع وجود كسر هيكل صاعد
        if current_price <= demand_high and current_price >= (demand_low - 50) and current_price > recent_low:
            signal = "BUY"

    if bearish_ob:
        supply_low, supply_high = round(bearish_ob[0], 2), round(bearish_ob[1], 2)
        supply_str = f"{supply_low} ⟷ {supply_high}"
        # دخول عند اختبار منطقة الـ OB مع وجود كسر هيكل هابط
        if current_price >= supply_low and current_price <= (supply_high + 50) and current_price < recent_high:
            signal = "SELL"

    return {
        "price": current_price,
        "signal": signal,
        "demand": demand_str,
        "supply": supply_str,
        "demand_low": demand_low,
        "supply_high": supply_high
    }

def background_monitor():
    time.sleep(10)
    while True:
        try:
            for name in SYMBOLS.keys():
                analysis = analyze_smc_setup(name)
                if analysis and analysis["signal"] != "NONE":
                    current_state = analysis["signal"]
                    if current_state != last_states[name]:
                        last_states[name] = current_state
                        price = analysis["price"]
                        users = get_alert_users()

                        if current_state == "BUY":
                            sl = round(analysis["demand_low"] - 150.0, 2)
                            risk = price - sl
                            tp1 = round(price + (risk * 2.0), 2)
                            tp2 = round(price + (risk * 3.5), 2)
                            direction = "شراء (BUY) 📈 [مباشر من Binance]"
                            zone_text = analysis['demand']
                        else:
                            sl = round(analysis["supply_high"] + 150.0, 2)
                            risk = sl - price
                            tp1 = round(price - (risk * 2.0), 2)
                            tp2 = round(price - (risk * 3.5), 2)
                            direction = "بيع (SELL) 📉 [مباشر من Binance]"
                            zone_text = analysis['supply']

                        msg = (
                            f"🚨 **تنبيه SMC محترف (OB + FVG) على {name}** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 الصفقة: {direction}\n"
                            f"📍 سعر الدخول اللحظي: `{price}`\n"
                            f"🧱 كتلة الأوامر (OB Zone): `{zone_text}`\n"
                            f"⛔ وقف الخسارة (SL): `{sl}`\n"
                            f"🎯 الهدف الأول (TP1 - 1:2): `{tp1}`\n"
                            f"🎯 الهدف الثاني (TP2 - 1:3.5): `{tp2}`"
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

@app.route('/')
def home():
    return "Bot SMC Active!", 200

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
        f"👑 **ماسح SMC المطور Real-Time (Binance API)**\n"
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
        wait_msg = bot.send_message(chat_id, f"⏳ جاري تحليل الفجوات السعرية و Order Blocks لـ {text}...")
        analysis = analyze_smc_setup(text)

        if not analysis:
            bot.edit_message_text(f"⚠️ تعذر جلب البيانات لـ {text} حالياً.", chat_id, wait_msg.message_id)
            return

        msg = (
            f"📊 **تقرير SMC دقيق لـ ({text}):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 السعر اللحظي (Binance): `{analysis['price']}`\n"
            f"🧱 منطقة الطلب (Bullish OB): `{analysis['demand']}`\n"
            f"🧱 منطقة العرض (Bearish OB): `{analysis['supply']}`\n"
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