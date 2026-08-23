import os
import sqlite3
import requests
import telebot
import threading
import time
import pandas as pd
from flask import Flask, request
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN", '8982114650:AAH9EVAcP9bJnm_3VC72J_o7vMpfTlim2W4')
bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
})

# ربط الأزواج بأسماء KuCoin
SYMBOLS = {
    "البيتكوين ₿": "BTC-USDT",
    "الذهب 🥇": "PAXG-USDT",
    "اليورو/دولار 💶": "EUR-USDT"
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
    except Exception as e:
        print(f"Error adding user: {e}")

def get_alert_users():
    try:
        conn = sqlite3.connect('bot_users.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT chat_id FROM users WHERE alerts = 1')
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []

# جلب الشموع عبر KuCoin API بدلاً من Binance المكتومة في Render
def fetch_klines(symbol_ticker, interval="15min"):
    try:
        url = f"https://api.kucoin.com/api/v1/market/candles?symbol={symbol_ticker}&type={interval}"
        res = session.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json().get('data', [])
            if data and len(data) > 0:
                # KuCoin Structure: [time, open, close, high, low, volume, turnover]
                df = pd.DataFrame(data, columns=['time', 'Open', 'Close', 'High', 'Low', 'Volume', 'Turnover'])
                df['Open'] = df['Open'].astype(float)
                df['Close'] = df['Close'].astype(float)
                df['High'] = df['High'].astype(float)
                df['Low'] = df['Low'].astype(float)
                # ترتيب البيانات من القديم إلى الحديث
                df = df.iloc[::-1].reset_index(drop=True)
                return df
    except Exception as e:
        print(f"Fetch KuCoin Error ({symbol_ticker}): {e}")
            
    return pd.DataFrame()

# تحليل SMC
def analyze_smc_setup(symbol_key):
    ticker = SYMBOLS.get(symbol_key)
    if not ticker:
        return None

    df = fetch_klines(ticker, "15min")

    if df.empty or len(df) < 20:
        return None

    decimals = 5 if "اليورو" in symbol_key else 2
    current_price = round(float(df['Close'].iloc[-1]), decimals)

    bullish_ob, bearish_ob = None, None
    for i in range(len(df) - 3, len(df) - 15, -1):
        if df['Low'].iloc[i] > df['High'].iloc[i-2]:
            bullish_ob = (df['Low'].iloc[i-2], df['High'].iloc[i-1])
            break
        if df['High'].iloc[i] < df['Low'].iloc[i-2]:
            bearish_ob = (df['Low'].iloc[i-1], df['High'].iloc[i-2])
            break

    signal = "NONE"
    demand_str, supply_str = "غير محددة", "غير محددة"
    demand_low, supply_high = 0.0, 0.0
    buffer = 0.0005 if "اليورو" in symbol_key else (2.0 if "الذهب" in symbol_key else 100.0)

    if bullish_ob:
        demand_low, demand_high = round(float(bullish_ob[0]), decimals), round(float(bullish_ob[1]), decimals)
        demand_str = f"{demand_low} ⟷ {demand_high}"
        if current_price <= demand_high and current_price >= (demand_low - buffer):
            signal = "BUY"

    if bearish_ob:
        supply_low, supply_high = round(float(bearish_ob[0]), decimals), round(float(bearish_ob[1]), decimals)
        supply_str = f"{supply_low} ⟷ {supply_high}"
        if current_price >= supply_low and current_price <= (supply_high + buffer):
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
                        decimals = 5 if "اليورو" in name else 2
                        sl_offset = 0.0008 if "اليورو" in name else (3.0 if "الذهب" in name else 250.0)

                        if current_state == "BUY":
                            sl = round(analysis["demand_low"] - sl_offset, decimals)
                            risk = abs(price - sl)
                            tp1 = round(price + (risk * 2.0), decimals)
                            tp2 = round(price + (risk * 3.5), decimals)
                            direction = "شراء (BUY) 📈"
                            zone_text = analysis['demand']
                        else:
                            sl = round(analysis["supply_high"] + sl_offset, decimals)
                            risk = abs(sl - price)
                            tp1 = round(price - (risk * 2.0), decimals)
                            tp2 = round(price - (risk * 3.5), decimals)
                            direction = "بيع (SELL) 📉"
                            zone_text = analysis['supply']

                        msg = (
                            f"🚨 **تنبيه SMC محترف على {name}** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 الصفقة: {direction}\n"
                            f"📍 سعر الدخول: `{price}`\n"
                            f"🧱 كتلة الأوامر (OB Zone): `{zone_text}`\n"
                            f"⛔ وقف الخسارة (SL): `{sl}`\n"
                            f"🎯 الهدف الأول (TP1): `{tp1}`\n"
                            f"🎯 الهدف الثاني (TP2): `{tp2}`"
                        )

                        for chat_id in users:
                            try:
                                bot.send_message(chat_id, msg, parse_mode="Markdown")
                            except Exception:
                                pass
            time.sleep(60)
        except Exception as e:
            print(f"Monitor error: {e}")
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
        f"👑 **ماسح SMC المطور (Real-Time)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر الزوج لمعاينة تحليله اللحظي."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip() if message.text else ""
    add_user(chat_id)

    selected_key = None
    if "البيتكوين" in text:
        selected_key = "البيتكوين ₿"
    elif "الذهب" in text or "XAU" in text.upper():
        selected_key = "الذهب 🥇"
    elif "اليورو" in text or "EUR" in text.upper():
        selected_key = "اليورو/دولار 💶"

    if selected_key:
        analysis = analyze_smc_setup(selected_key)

        if not analysis:
            bot.send_message(chat_id, f"⚠️ تعذر جلب البيانات لـ {text} حالياً. حاول مرة أخرى بعد لحظات.")
            return

        pair_name = "XAU/USD (الذهب)" if selected_key == "الذهب 🥇" else selected_key

        msg = (
            f"📊 **تقرير SMC اللحظي لـ ({pair_name}):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 السعر اللحظي: `{analysis['price']}`\n"
            f"🧱 منطقة الطلب (Demand/OB): `{analysis['demand']}`\n"
            f"🧱 منطقة العرض (Supply/OB): `{analysis['supply']}`\n"
            f"⚡ الإشارة الحالية: `{analysis['signal']}`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")

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