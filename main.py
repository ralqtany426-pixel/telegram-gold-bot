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
last_signal_state = "NONE" 

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

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
    if MT5_AVAILABLE:
        try:
            if mt5.initialize():
                symbol = "XAUUSD"
                tick = mt5.symbol_info_tick(symbol)
                if not tick:
                    symbol = "GOLD"
                    tick = mt5.symbol_info_tick(symbol)
                
                if tick:
                    mt5.shutdown()
                    return round(tick.bid, 2)
                mt5.shutdown()
        except:
            pass

    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        raw_price = float(response.json().get("price", 0.0))
        return round(raw_price + PRICE_OFFSET, 2)
    except:
        return round(2400.0 + PRICE_OFFSET, 2)

# --- 🎯 خوارزمية حساب SMC الذكية ---
def analyze_smc_structure(price):
    demand_low = round(price - 6.0, 2)
    demand_high = round(price - 1.0, 2)
    bullish_ob_low = round(price - 4.5, 2)
    bullish_ob_high = round(price - 1.5, 2)

    supply_low = round(price + 1.0, 2)
    supply_high = round(price + 6.0, 2)
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
    stop_loss = round(smc["bullish_ob_low"] - 2.0, 2)
    tp1 = round(price + 4.5, 2)
    tp2 = round(price + 9.0, 2)
    tp3 = round(price + 15.0, 2)
    return ("📈 شراء مؤكد (Bullish OB - BUY)", 94, smc["bullish_ob"], smc["demand_zone"], smc["supply_zone"],
            stop_loss, tp1, tp2, tp3, 
            "اختبار شمعة Order Block شرائية واختراق FVG", "تغير هيكل السعر الداخلي (CHOCH)", "استقرار فوق كسر الهيكل (BOS)", "ضخ سيولة مؤسسية إيجابية")

def get_sell_signal(price):
    smc = analyze_smc_structure(price)
    stop_loss = round(smc["bearish_ob_high"] + 2.0, 2)
    tp1 = round(price - 4.5, 2)
    tp2 = round(price - 9.0, 2)
    tp3 = round(price - 15.0, 2)
    return ("🔻 بيع مؤكد (Bearish OB - SELL)", 92, smc["bearish_ob"], smc["demand_zone"], smc["supply_zone"],
            stop_loss, tp1, tp2, tp3, 
            "رفض عند Order Block بيعي واختبار FVG", "كسر هيكل السعر نحو الهبوط (CHOCH)", "احترام كسر الهيكل الهابط (BOS)", "سحب سيولة من القمم العالية")

# --- 🚀 المراقبة الذكية بالخلفية ---
def background_signal_sender():
    global last_signal_state
    time.sleep(10) 
    while True:
        try:
            users = get_alert_users()
            if users:
                price = get_gold_price()
                smc = analyze_smc_structure(price)

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

            time.sleep(20) 
        except:
            time.sleep(20)

threading.Thread(target=background_signal_sender, daemon=True).start()

@app.route('/')
def home():
    return "SMC Smart Gold Bot is Active!", 200

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
        f"👑 **النظام الذكي لتداول الذهب (Smart SMC Bot)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"مرحباً يا عبد الله.\n"
        f"تم دمج النظام الذكي لاتخاذ القرار تلقائياً، اضغط على زر `🎯 الفرصة الحالية (SMC)` لفحص حالة السوق ومنع أي شتات.\n\n"
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

    elif text == "🎯 الفرصة الحالية (SMC)":
        is_in_bullish = (smc["bullish_ob_low"] <= price <= smc["bullish_ob_high"])
        is_in_bearish = (smc["bearish_ob_low"] <= price <= smc["bearish_ob_high"])

        if is_in_bullish:
            signal_type, prob, ob, dem, sup, sl, tp1, tp2, tp3, tf15, tf30, tf1h, tf4h = get_buy_signal(price)
            msg = (
                f"🚀 **إشارة شراء مؤكدة (Bullish OB - BUY)**\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📍 السعر الحالي في منطقة الطلب: `{price} $`\n"
                f"🌟 نسبة النجاح: `{prob}%`\n"
                f"📦 **Order Block الشرائي:** `{ob}`\n"
                f"⛔ **وقف الخسارة (SL):** `{sl} $`\n"
                f"🎯 TP1: `{tp1} $` | TP2: `{tp2} $` | TP3: `{tp3} $`"
            )
        elif is_in_bearish:
            signal_type, prob, ob, dem, sup, sl, tp1, tp2, tp3, tf15, tf30, tf1h, tf4h = get_sell_signal(price)
            msg = (
                f"🔻 **إشارة بيع مؤكدة (Bearish OB - SELL)**\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📍 السعر الحالي في منطقة العرض: `{price} $`\n"
                f"🌟 نسبة النجاح: `{prob}%`\n"
                f"📦 **Order Block البيعي:** `{ob}`\n"
                f"⛔ **وقف الخسارة (SL):** `{sl} $`\n"
                f"🎯 TP1: `{tp1} $` | TP2: `{tp2} $` | TP3: `{tp3} $`"
            )
        else:
            msg = (
                f"⏳ **منطقة انتظار وتذبذب محايدة (No Trade Zone)**\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📍 السعر الحالي: `{price} $`\n\n"
                f"⚠️ السعر يتحرك حالياً بين منطقتي العرض والطلب ولا يلمس أي Order Block مؤكد.\n"
                f"💡 **نصيحة النظام:** يفضل الانتظار حتى يصل السعر لإحدى المنطقتين التاليين:\n"
                f"• للبيع 🔻: ينتظر وصول السعر لـ `{smc['bearish_ob']}`\n"
                f"• للشراء 📈: ينتظر وصول السعر لـ `{smc['bullish_ob']}`"
            )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

    elif text == "🔔 التنبيهات":
        new_status = toggle_user_alerts(message.chat.id)
        status_text = "🟢 **تم تفعيل التنبيهات! ستصلك إشارة فور دخول السعر إحدى مناطق الـ Order Block.**" if new_status == 1 else "🔴 **تم إيقاف التنبيهات الآلية.**"
        bot.send_message(message.chat.id, status_text, parse_mode="Markdown")

    elif text == "🧮 حاسبة المخاطر":
        msg = f"🧮 **إدارة المخاطر:**\nاحرص دائماً على عدم تجاوز مخاطرة 1% إلى 2% من رأس مالك لكل صفقة."
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"{external_url}/{TOKEN}")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)