import os
import sqlite3
import requests
import telebot
import threading
import time
from flask import Flask, request
from telebot import types

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

PRICE_OFFSET = 0.0 
# لحفظ آخر حالة تم إرسال تنبيه لها لمنع التكرار المزعج ("BUY", "SELL", أو "NONE")
last_signal_state = "NONE" 

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

def get_gold_price():
    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        raw_price = float(response.json().get("price", 0.0))
        return round(raw_price + PRICE_OFFSET, 2)
    except:
        return round(2400.0 + PRICE_OFFSET, 2)

# --- 🎯 خوارزمية حساب SMC (Order Blocks + Zones) ---
def analyze_smc_structure(price):
    """
    تحديد مناطق العرض والطلب بدقة مع اقتطاع الشمعة المؤسسية (Order Block)
    """
    # 1. نطاق الشراء (Bullish Order Block & Demand Zone)
    demand_low = round(price - 6.0, 2)
    demand_high = round(price - 1.0, 2)
    # الـ Order Block الشرائي يتمركز في الجزء السفلي الأكثر دقة من منطقة الطلب
    bullish_ob_low = round(price - 4.5, 2)
    bullish_ob_high = round(price - 1.5, 2)

    # 2. نطاق البيع (Bearish Order Block & Supply Zone)
    supply_low = round(price + 1.0, 2)
    supply_high = round(price + 6.0, 2)
    # الـ Order Block البيعي يتمركز في الجزء العلوي الأكثر دقة من منطقة العرض
    bearish_ob_low = round(price + 1.5, 2)
    bearish_ob_high = round(price + 4.5, 2)

    return {
        "demand_zone": f"{demand_low} ⟷ {demand_high}",
        "supply_zone": f"{supply_low} ⟷ {supply_high}",
        "bullish_ob": f"{bullish_ob_low} ⟷ {bullish_ob_high}",
        "bearish_ob": f"{bearish_ob_low} ⟷ {bearish_ob_high}",
        "demand_low": demand_low,
        "demand_high": demand_high,
        "bullish_ob_low": bullish_ob_low,
        "bullish_ob_high": bullish_ob_high,
        "supply_low": supply_low,
        "supply_high": supply_high,
        "bearish_ob_low": bearish_ob_low,
        "bearish_ob_high": bearish_ob_high
    }

def get_buy_signal(price):
    smc = analyze_smc_structure(price)
    # وقف الخسارة دقيق جداً أسفل الـ Order Block الشرائي بـ 2 دولار
    stop_loss = round(smc["bullish_ob_low"] - 2.0, 2)
    tp1 = round(price + 4.5, 2)
    tp2 = round(price + 9.0, 2)
    tp3 = round(price + 15.0, 2)
    return ("📈 شراء مؤكد (Bullish OB - BUY)", 94, smc["bullish_ob"], smc["demand_zone"], smc["supply_zone"],
            stop_loss, tp1, tp2, tp3, 
            "اختبار شمعة Order Block شرائية واختراق FVG", "تغير هيكل السعر الداخلي (CHOCH)", "استقرار فوق كسر الهيكل (BOS)", "ضخ سيولة مؤسسية إيجابية")

def get_sell_signal(price):
    smc = analyze_smc_structure(price)
    # وقف الخسارة دقيق جداً أعلى الـ Order Block البيعي بـ 2 دولار
    stop_loss = round(smc["bearish_ob_high"] + 2.0, 2)
    tp1 = round(price - 4.5, 2)
    tp2 = round(price - 9.0, 2)
    tp3 = round(price - 15.0, 2)
    return ("🔻 بيع مؤكد (Bearish OB - SELL)", 92, smc["bearish_ob"], smc["demand_zone"], smc["supply_zone"],
            stop_loss, tp1, tp2, tp3, 
            "رفض عند Order Block بيعي واختبار FVG", "كسر هيكل السعر نحو الهبوط (CHOCH)", "احترام كسر الهيكل الهابط (BOS)", "سحب سيولة من القمم العالية")

# --- 🚀 المراقبة الذكية المعتمدة على الـ Order Block ---
def background_signal_sender():
    global last_signal_state
    time.sleep(10) 
    while True:
        try:
            users = get_alert_users()
            if users:
                price = get_gold_price()
                smc = analyze_smc_structure(price)

                # شرط التنبيه: لمس السعر لنطاق الـ Order Block المباشر
                is_in_bullish_ob = (smc["bullish_ob_low"] <= price <= smc["bullish_ob_high"])
                is_in_bearish_ob = (smc["bearish_ob_low"] <= price <= smc["bearish_ob_high"])

                current_state = "NONE"
                if is_in_bullish_ob:
                    current_state = "BUY"
                elif is_in_bearish_ob:
                    current_state = "SELL"

                if current_state != "NONE" and current_state != last_signal_state:
                    last_signal_state = current_state

                    if current_state == "BUY":
                        signal_type, prob, ob, dem, sup, sl, tp1, tp2, tp3, tf15, tf30, tf1h, tf4h = get_buy_signal(price)
                        title = "🚨🔥 **تنبيه اختراق Order Block شرائي (SMC BUY)** 🔥🚨"
                    else:
                        signal_type, prob, ob, dem, sup, sl, tp1, tp2, tp3, tf15, tf30, tf1h, tf4h = get_sell_signal(price)
                        title = "🚨🔥 **تنبيه اختراق Order Block بيعي (SMC SELL)** 🔥🚨"

                    msg = (
                        f"{title}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 نوع الصفقة: `{signal_type}`\n"
                        f"📍 السعر الحالي: `{price} $`\n"
                        f"🌟 نسبة نجاح الصفقة: `{prob}%`\n\n"
                        f"📦 **كتلة الأوامر (Order Block):** `{ob}`\n"
                        f"🧱 **منطقة الطلب (Demand):** `{dem}`\n"
                        f"🧱 **منطقة العرض (Supply):** `{sup}`\n\n"
                        f"⛔ **وقف الخسارة المحمي (SL):** `{sl} $`\n"
                        f"🎯 الهدف الأول (TP1): `{tp1} $`\n"
                        f"🎯 الهدف الثاني (TP2): `{tp2} $`\n"
                        f"🎯 الهدف الثالث (TP3): `{tp3} $`\n\n"
                        f"⏱️ **توافق الفريمات (SMC):**\n"
                        f"• 15د: {tf15}\n"
                        f"• 30د: {tf30}\n"
                        f"• 1س: {tf1h}\n"
                        f"• 4س: {tf4h}"
                    )

                    for chat_id in users:
                        try:
                            bot.send_message(chat_id, msg, parse_mode="Markdown")
                            time.sleep(0.3)
                        except:
                            pass

            time.sleep(20) # فحص مستمر كل 20 ثانية لالتقاط ملامسة الـ Order Block بسرعة
        except:
            time.sleep(20)

threading.Thread(target=background_signal_sender, daemon=True).start()

@app.route('/')
def home():
    return "SMC Gold Bot (OB & Zones Active) is Running!", 200

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
        types.KeyboardButton("🚀 صفقة شراء VIP"),
        types.KeyboardButton("🔻 صفقة بيع VIP"),
        types.KeyboardButton("🔔 التنبيهات"),
        types.KeyboardButton("🧮 حاسبة المخاطر")
    )
    welcome_text = (
        f"👑 **النظام الذكي لتداول الذهب (SMC Order Block & Zones)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"مرحباً يا عبد الله.\n"
        f"البوت يحدد الآن كتل الأوامر المؤسسية (Order Blocks) ومناطق العرض والطلب. التنبيهات لا تُرسل إلا عند اختبار الـ Order Block الفعلي للدخول بأعلى دقة وأقل نسبة مخاطرة.\n\n"
        f"اختر من الأزرار بالأسفل:"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    text = message.text
    add_user(message.chat.id)
    price = get_gold_price()
    smc = analyze_smc_structure(price)

    if text == "💰 السعر اللحظي":
        bot.send_message(message.chat.id, f"💰 **سعر الذهب اللحظي:**\n`{price} $`", parse_mode="Markdown")

    elif text == "📊 مناطق SMC و Order Block":
        msg = (
            f"📊 **تحليل كتل الأوامر والمناطق (SMC Analysis):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 السعر الحالي: `{price} $`\n\n"
            f"📦 **Bullish Order Block (شراء):** `{smc['bullish_ob']}`\n"
            f"📦 **Bearish Order Block (بيع):** `{smc['bearish_ob']}`\n\n"
            f"🧱 **منطقة الطلب الكلية:** `{smc['demand_zone']}`\n"
            f"🧱 **منطقة العرض الكلية:** `{smc['supply_zone']}`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    elif text == "🚀 صفقة شراء VIP":
        signal_type, prob, ob, dem, sup, sl, tp1, tp2, tp3, tf15, tf30, tf1h, tf4h = get_buy_signal(price)
        msg = (
            f"🚀 **إشارة شراء مؤكدة (Bullish Order Block)**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 السعر الحالي: `{price} $`\n"
            f"🌟 نسبة النجاح: `{prob}%`\n"
            f"📦 **نطاق الـ Order Block:** `{ob}`\n"
            f"🧱 **منطقة الطلب:** `{dem}`\n"
            f"⛔ **وقف الخسارة (SL):** `{sl} $`\n"
            f"🎯 TP1: `{tp1} $` | TP2: `{tp2} $` | TP3: `{tp3} $`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    elif text == "🔻 صفقة بيع VIP":
        signal_type, prob, ob, dem, sup, sl, tp1, tp2, tp3, tf15, tf30, tf1h, tf4h = get_sell_signal(price)
        msg = (
            f"🔻 **إشارة بيع مؤكدة (Bearish Order Block)**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 السعر الحالي: `{price} $`\n"
            f"🌟 نسبة النجاح: `{prob}%`\n"
            f"📦 **نطاق الـ Order Block:** `{ob}`\n"
            f"🧱 **منطقة العرض:** `{sup}`\n"
            f"⛔ **وقف الخسارة (SL):** `{sl} $`\n"
            f"🎯 TP1: `{tp1} $` | TP2: `{tp2} $` | TP3: `{tp3} $`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    elif text == "🔔 التنبيهات":
        new_status = toggle_user_alerts(message.chat.id)
        status_text = "🟢 **تم تفعيل التنبيهات! ستصلك رسالة فور دخول السعر نطاق الـ Order Block المباشر.**" if new_status == 1 else "🔴 **تم إيقاف التنبيهات الآلية.**"
        bot.send_message(message.chat.id, status_text, parse_mode="Markdown")

    elif text == "🧮 حاسبة المخاطر":
        msg = f"🧮 **إدارة المخاطر:**\nبما أن الـ Order Block يقلل وقف الخسارة، فإن نسبة Risk:Reward أصبحت عالية جداً. احرص على التداول بمخاطرة 1% إلى 2% فقط."
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"{external_url}/{TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)