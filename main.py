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

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- 🎯 الفارق السعري لتطابق MT5 ---
PRICE_OFFSET = -1.14 
last_signal_state = "NONE"

# --- 1. قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        chat_id INTEGER PRIMARY KEY,
                        alerts_enabled INTEGER DEFAULT 1
                    )''')
    conn.commit()
    conn.close()

init_db()

def add_user(chat_id):
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (chat_id, alerts_enabled) VALUES (?, 1)', (chat_id,))
    conn.commit()
    conn.close()

def toggle_user_alerts(chat_id):
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT alerts_enabled FROM users WHERE chat_id = ?', (chat_id,))
    res = cursor.fetchone()
    if res is not None:
        new_status = 0 if res[0] == 1 else 1
        cursor.execute('UPDATE users SET alerts_enabled = ? WHERE chat_id = ?', (new_status, chat_id))
        conn.commit()
        conn.close()
        return new_status
    else:
        cursor.execute('INSERT INTO users (chat_id, alerts_enabled) VALUES (?, 1)', (chat_id,))
        conn.commit()
        conn.close()
        return 1

def get_alert_users():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM users WHERE alerts_enabled = 1')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# --- 2. محرك جلب وتحليل الشموع الحقيقي (SMC Engine) ---
def get_real_market_data():
    try:
        ticker = yf.Ticker("GC=F") # عقود الذهب
        df = ticker.history(period="5d", interval="15m")
        if df.empty:
            ticker = yf.Ticker("XAUUSD=X")
            df = ticker.history(period="5d", interval="15m")
        
        # تطبيق الفارق السعري
        df['Open'] += PRICE_OFFSET
        df['High'] += PRICE_OFFSET
        df['Low'] += PRICE_OFFSET
        df['Close'] += PRICE_OFFSET
        return df
    except Exception as e:
        print(f"Error fetching candles: {e}")
        return pd.DataFrame()

def analyze_smc_structure_real():
    df = get_real_market_data()
    if df.empty or len(df) < 10:
        return None

    current_price = round(df['Close'].iloc[-1], 2)
    
    # البحث عن Bullish Order Block
    bullish_ob_low = round(df['Low'].iloc[-10:-1].min(), 2)
    bullish_ob_high = round(bullish_ob_low + 2.5, 2)
    
    # البحث عن Bearish Order Block
    bearish_ob_high = round(df['High'].iloc[-10:-1].max(), 2)
    bearish_ob_low = round(bearish_ob_high - 2.5, 2)

    # فحص الفجوات السعرية (FVG)
    has_fvg = False
    if len(df) >= 3:
        if df['Low'].iloc[-1] > df['High'].iloc[-3]:
            has_fvg = True

    return {
        "price": current_price,
        "bullish_ob": f"{bullish_ob_low} ⟷ {bullish_ob_high}",
        "bearish_ob": f"{bearish_ob_low} ⟷ {bearish_ob_high}",
        "bullish_ob_low": bullish_ob_low,
        "bullish_ob_high": bullish_ob_high,
        "bearish_ob_low": bearish_ob_low,
        "bearish_ob_high": bearish_ob_high,
        "has_fvg": has_fvg
    }

# --- 3. نظام المراقبة والتنبيهات (كل 60 ثانية) ---
def background_signal_sender():
    global last_signal_state
    time.sleep(10)
    while True:
        try:
            users = get_alert_users()
            if users:
                smc = analyze_smc_structure_real()
                if smc:
                    price = smc["price"]
                    is_in_bullish = (smc["bullish_ob_low"] <= price <= smc["bullish_ob_high"])
                    is_in_bearish = (smc["bearish_ob_low"] <= price <= smc["bearish_ob_high"])

                    current_state = "NONE"
                    if is_in_bullish:
                        current_state = "BUY"
                    elif is_in_bearish:
                        current_state = "SELL"

                    if current_state != "NONE" and current_state != last_signal_state:
                        last_signal_state = current_state

                        if current_state == "BUY":
                            sl = round(smc["bullish_ob_low"] - 2.0, 2)
                            tp1 = round(price + 4.5, 2)
                            tp2 = round(price + 9.0, 2)
                            msg = (
                                f"🚀🔥 **تنبيه SMC حقيقي: شراء (BUY)** 🔥🚀\n"
                                f"━━━━━━━━━━━━━━━━━━━━━\n"
                                f"📍 السعر الحقيقي (MT5): `{price} $`\n"
                                f"📦 **Order Block الشرائي:** `{smc['bullish_ob']}`\n"
                                f"⚡ **وجود FVG:** `{'نعم ✅' if smc['has_fvg'] else 'لا ❌'}`\n\n"
                                f"⛔ **وقف الخسارة (SL):** `{sl} $`\n"
                                f"🎯 **الهدف الأول (TP1):** `{tp1} $`\n"
                                f"🎯 **الهدف الثاني (TP2):** `{tp2} $`"
                            )
                        else:
                            sl = round(smc["bearish_ob_high"] + 2.0, 2)
                            tp1 = round(price - 4.5, 2)
                            tp2 = round(price - 9.0, 2)
                            msg = (
                                f"🔻🔥 **تنبيه SMC حقيقي: بيع (SELL)** 🔥🔻\n"
                                f"━━━━━━━━━━━━━━━━━━━━━\n"
                                f"📍 السعر الحقيقي (MT5): `{price} $`\n"
                                f"📦 **Order Block البيعي:** `{smc['bearish_ob']}`\n"
                                f"⚡ **وجود FVG:** `{'نعم ✅' if smc['has_fvg'] else 'لا ❌'}`\n\n"
                                f"⛔ **وقف الخسارة (SL):** `{sl} $`\n"
                                f"🎯 **الهدف الأول (TP1):** `{tp1} $`\n"
                                f"🎯 **الهدف الثاني (TP2):** `{tp2} $`"
                            )

                        for chat_id in users:
                            try:
                                bot.send_message(chat_id, msg, parse_mode="Markdown")
                                time.sleep(0.3)
                            except:
                                pass

            time.sleep(60) # مراقبة كل 60 ثانية
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(60)

threading.Thread(target=background_signal_sender, daemon=True).start()

# --- 4. أوامر البوت ---
@app.route('/')
def home():
    return "SMC Real Candles Engine Active!", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

@bot.message_handler(commands=['start'])
def start_command(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("💰 السعر اللحظي"),
        types.KeyboardButton("📊 مناطق SMC و Order Block"),
        types.KeyboardButton("🎯 الفرصة الحالية (SMC)"),
        types.KeyboardButton("🔔 التنبيهات"),
        types.KeyboardButton("🧮 حاسبة المخاطر")
    )
    welcome_text = (
        f"👑 **النظام الذكي لتداول الذهب (Real SMC Candles)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"مرحباً يا عبد الله.\n"
        f"تم تطوير البوت ليعمل بنظام تحليل الشموع الحقيقية مع فحص كل 60 ثانية.\n\n"
        f"اختر من الأزرار بالأسفل:"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    text = message.text
    add_user(message.chat.id)
    smc = analyze_smc_structure_real()

    if not smc:
        bot.send_message(message.chat.id, "⚠️ جاري الاتصال بخادم بيانات الشموع... يرجى المحاولة بعد لحظات.")
        return

    price = smc["price"]

    if text == "💰 السعر اللحظي":
        bot.send_message(message.chat.id, f"💰 **سعر الذهب الحقيقي (مطابق لـ MT5):**\n`{price} $`", parse_mode="Markdown")

    elif text == "📊 مناطق SMC و Order Block":
        msg = (
            f"📊 **تحليل الشموع الحقيقي (SMC Structure):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 السعر الحالي: `{price} $`\n\n"
            f"📦 **Bullish Order Block:** `{smc['bullish_ob']}`\n"
            f"📦 **Bearish Order Block:** `{smc['bearish_ob']}`\n"
            f"⚡ **تأكيد الفجوة السعرية (FVG):** `{'موجودة ✅' if smc['has_fvg'] else 'غير موجودة ❌'}`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    elif text == "🎯 الفرصة الحالية (SMC)":
        is_in_bullish = (smc["bullish_ob_low"] <= price <= smc["bullish_ob_high"])
        is_in_bearish = (smc["bearish_ob_low"] <= price <= smc["bearish_ob_high"])

        if is_in_bullish:
            sl = round(smc["bullish_ob_low"] - 2.0, 2)
            tp1 = round(price + 4.5, 2)
            msg = f"🚀 **فرصة شراء ممتازة (Bullish OB)**\nالسعر داخل المنطقة الحقيقية: `{price} $`\nوقف الخسارة: `{sl} $` | الهدف: `{tp1} $`"
        elif is_in_bearish:
            sl = round(smc["bearish_ob_high"] + 2.0, 2)
            tp1 = round(price - 4.5, 2)
            msg = f"🔻 **فرصة بيع ممتازة (Bearish OB)**\nالسعر داخل المنطقة الحقيقية: `{price} $`\nوقف الخسارة: `{sl} $` | الهدف: `{tp1} $`"
        else:
            msg = (
                f"⏳ **منطقة انتظار (No Trade Zone)**\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📍 السعر الحالي: `{price} $`\n"
                f"السعر يتحرك بين المناطق. لا توجد صفقة واضحة حالياً."
            )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    elif text == "🔔 التنبيهات":
        new_status = toggle_user_alerts(message.chat.id)
        status_text = "🟢 **تم تفعيل التنبيهات الذكية مع فحص كل 60 ثانية.**" if new_status == 1 else "🔴 **تم إيقاف التنبيهات.**"
        bot.send_message(message.chat.id, status_text, parse_mode="Markdown")

    elif text == "🧮 حاسبة المخاطر":
        bot.send_message(message.chat.id, "🧮 **إدارة المخاطر:** خاطِر بـ 1% فقط من حسابك لكل صفقة.", parse_mode="Markdown")

if __name__ == '__main__':
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"{external_url}/{TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)