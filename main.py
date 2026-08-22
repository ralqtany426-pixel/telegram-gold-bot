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

SYMBOL = "GC=F"  # رمز عقود الذهب العالمية
last_vip_state = "NONE"

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

# --- 3. جلب البيانات وتحليل الاتجاه بـ 200 شمعة (EMA 200) ---
def fetch_data(tf, period="60d"):
    try:
        ticker = yf.Ticker(SYMBOL)
        df = ticker.history(period=period, interval=tf)
        if df.empty:
            ticker = yf.Ticker("XAUUSD=X")
            df = ticker.history(period=period, interval=tf)
        return df
    except:
        return pd.DataFrame()

# 🔹 فحص الاتجاه العام (200 شمعة على فريم 4 ساعات)
def get_main_trend_200():
    df_4h = fetch_data("1h", "60d") # جلب بيانات كافية للحساب
    if df_4h.empty or len(df_4h) < 200:
        return "NEUTRAL"
    
    # حساب المتوسط المتحرك الأسّي لـ 200 شمعة (EMA 200)
    ema200 = df_4h['Close'].ewm(span=200, adjust=False).mean().iloc[-1]
    current_price = df_4h['Close'].iloc[-1]

    if current_price > ema200:
        return "BULLISH" # الاتجاه صاعد (مسموح بالشراء فقط)
    else:
        return "BEARISH" # الاتجاه هابط (مسموح بالبيع فقط)

# --- 4. محرك التحليل الشامل (SMC + EMA 200) ---
def analyze_smc_setup():
    df_15m = fetch_data("15m", "5d")
    df_1h = fetch_data("1h", "20d")

    if df_15m.empty or df_1h.empty:
        return None

    current_price = round(df_15m['Close'].iloc[-1], 2)
    main_trend = get_main_trend_200() # الاتجاه من 200 شمعة

    # تحديد قمم وقيعان الهيكل (BOS)
    df_1h['highest_high'] = df_1h['High'].shift(1).rolling(20).max()
    df_1h['lowest_low'] = df_1h['Low'].shift(1).rolling(20).min()

    # تحديد كتل الأوامر (Order Blocks)
    bullish_ob = (df_1h['Close'] < df_1h['Open']) & (df_1h['High'].shift(-1) > df_1h['highest_high'])
    bearish_ob = (df_1h['Close'] > df_1h['Open']) & (df_1h['Low'].shift(-1) < df_1h['lowest_low'])

    df_demand = df_1h[bullish_ob]
    df_supply = df_1h[bearish_ob]

    if not df_demand.empty:
        demand_low = round(df_demand.iloc[-1]['Low'], 2)
        demand_high = round(df_demand.iloc[-1]['High'], 2)
    else:
        demand_low = round(df_1h['Low'].iloc[-30:-1].min(), 2)
        demand_high = round(demand_low + 3.5, 2)

    if not df_supply.empty:
        supply_high = round(df_supply.iloc[-1]['High'], 2)
        supply_low = round(df_supply.iloc[-1]['Low'], 2)
    else:
        supply_high = round(df_1h['High'].iloc[-30:-1].max(), 2)
        supply_low = round(supply_high - 3.5, 2)

    # الفجوات السعرية (FVG)
    has_fvg_buy = df_15m['Low'].iloc[-1] > df_15m['High'].iloc[-3]
    has_fvg_sell = df_15m['High'].iloc[-1] < df_15m['Low'].iloc[-3]

    # 🎯 اتخاذ القرار: الشراء والبيع محمي ومفلتر بحسب اتجاه الـ 200 شمعة
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

# --- 5. نظام التنبيه الخلفي المباشر ---
def background_monitor():
    global last_vip_state
    time.sleep(10)
    while True:
        try:
            analysis = analyze_smc_setup()
            if analysis and analysis["signal"] != "NONE":
                current_state = analysis["signal"]
                if current_state != last_vip_state:
                    last_vip_state = current_state
                    price = analysis["price"]
                    users = get_alert_users()

                    if current_state == "BUY":
                        sl = round(analysis["demand_low"] - 2.5, 2)
                        tp1 = round(price + 5.0, 2)
                        tp2 = round(price + 12.0, 2)
                        msg = (
                            f"🚨 **تنبيه صفقة SMC مؤكدة (BUY)** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📈 الاتجاه العام (200 شمعة): صاعد (BULLISH)\n"
                            f"📌 الاتجاه: 📈 شراء (BUY)\n"
                            f"📍 سعر الدخول: `{price} $`\n"
                            f"🧱 منطقة الطلب (OB): `{analysis['demand']}`\n"
                            f"⛔ وقف الخسارة (SL): `{sl} $`\n"
                            f"🎯 الهدف الأول (TP1): `{tp1} $`\n"
                            f"🎯 الهدف الثاني (TP2): `{tp2} $`\n\n"
                            f"💡 *ادخل الصفقة يدوياً على تطبيق MT5 بالهاتف.*"
                        )
                    else:
                        sl = round(analysis["supply_high"] + 2.5, 2)
                        tp1 = round(price - 5.0, 2)
                        tp2 = round(price - 12.0, 2)
                        msg = (
                            f"🚨 **تنبيه صفقة SMC مؤكدة (SELL)** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📉 الاتجاه العام (200 شمعة): هابط (BEARISH)\n"
                            f"📌 الاتجاه: 📉 بيع (SELL)\n"
                            f"📍 سعر الدخول: `{price} $`\n"
                            f"🧱 منطقة العرض (OB): `{analysis['supply']}`\n"
                            f"⛔ وقف الخسارة (SL): `{sl} $`\n"
                            f"🎯 الهدف الأول (TP1): `{tp1} $`\n"
                            f"🎯 الهدف الثاني (TP2): `{tp2} $`\n\n"
                            f"💡 *ادخل الصفقة يدوياً على تطبيق MT5 بالهاتف.*"
                        )

                    for chat_id in users:
                        try:
                            bot.send_message(chat_id, msg, parse_mode="Markdown")
                        except:
                            pass
            time.sleep(60)
        except Exception as e:
            time.sleep(60)

threading.Thread(target=background_monitor, daemon=True).start()

# --- 6. التشغيل عبر Flask و Webhook منصة Render ---
@app.route('/')
def home():
    return "Render SMC Bot Active!", 200

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
        types.KeyboardButton("🎯 فحص الشارت الحقيقي (SMC)")
    )
    welcome_text = (
        f"👑 **نظام SMC للتنبيهات الذكية (مفلتر بـ 200 شمعة)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"مرحباً بك.\n"
        f"البوت مفلتر بـ EMA 200 وسيرسل لك الصفقات المتوافقة مع الاتجاه العام فقط."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text
    add_user(chat_id)

    analysis = analyze_smc_setup()
    if not analysis:
        bot.send_message(chat_id, "⚠️ جاري الاتصال وتحديث البيانات...")
        return

    if text == "💰 السعر اللحظي":
        bot.send_message(chat_id, f"💰 **سعر الذهب المباشر:**\n`{analysis['price']} $`", parse_mode="Markdown")

    elif text == "🎯 فحص الشارت الحقيقي (SMC)":
        trend_str = "📈 صاعد" if analysis['trend'] == "BULLISH" else "📉 هابط"
        msg = (
            f"📊 **تقرير هيكل السوق (SMC + EMA 200):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 الاتجاه العام (200 شمعة): `{trend_str}`\n"
            f"📍 السعر الحالي: `{analysis['price']} $`\n"
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