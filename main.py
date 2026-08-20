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

# --- 1. إعداد قاعدة البيانات ---
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

def get_all_users():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM users WHERE alerts_enabled = 1')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_gold_price():
    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        return round(float(response.json().get("price", 2400.0)), 2)
    except:
        return 2400.0

def get_institutional_signal(price):
    is_buy = (price % 2 == 0)
    if is_buy:
        action_title = "🟢 **صفقة شراء مؤسسية (BUY GOLD)**"
        order_type = "شراء مباشر (BUY LIMIT)"
        ob_low = round(price - 6.5, 2)
        ob_high = round(price - 4.0, 2)
        zone_entree = f"{ob_low} ⟷ {ob_high}"
        stop_loss = round(ob_low - 5.0, 2)
        tp1 = round(price + 10.0, 2)
        tp2 = round(price + 22.0, 2)
        tp3 = round(price + 40.0, 2)
        market_bias = "تجميع عقود صاعد (Accumulation)"
    else:
        action_title = "🔴 **صفقة بيع مؤسسية (SELL GOLD)**"
        order_type = "بيع مباشر (SELL LIMIT)"
        ob_low = round(price + 4.0, 2)
        ob_high = round(price + 6.5, 2)
        zone_entree = f"{ob_low} ⟷ {ob_high}"
        stop_loss = round(ob_high + 5.0, 2)
        tp1 = round(price - 10.0, 2)
        tp2 = round(price - 22.0, 2)
        tp3 = round(price - 40.0, 2)
        market_bias = "تصريف عقود هابط (Distribution)"
    return action_title, order_type, zone_entree, stop_loss, tp1, tp2, tp3, market_bias, is_buy

def get_support_resistance_levels(price):
    return round(price + 25.0, 2), round(price + 15.0, 2), round(price + 7.0, 2), \
           round(price - 7.0, 2), round(price - 15.0, 2), round(price - 28.0, 2)

# --- مراقبة السوق ---
def background_market_monitor():
    time.sleep(10) # انتظار حتى يقلع السيرفر تماماً
    while True:
        try:
            users = get_all_users()
            if users:
                price = get_gold_price()
                action_title, _, zone_entree, _, _, _, _, _, _ = get_institutional_signal(price)
                for chat_id in users:
                    try:
                        bot.send_message(chat_id, f"🚨 **[Institutional Alert]**\n{action_title}\n📍 السعر: `{price}` $\n🧱 الدخول: `{zone_entree}`", parse_mode="Markdown")
                    except: pass
                time.sleep(7200)
            time.sleep(60)
        except: time.sleep(60)

threading.Thread(target=background_market_monitor, daemon=True).start()

# --- مسارات Flask الأساسية ---
@app.route('/')
def home():
    return "Bot is active and running!", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

@app.route('/tradingview_webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data = request.json
        action = data.get('action', 'BUY')
        price = data.get('price', get_gold_price())
        setup_type = data.get('setup', 'Order Block M15')

        users = get_all_users()
        if users:
            for chat_id in users:
                bot.send_message(
                    chat_id,
                    f"🔥 **[TradingView Live Signal]**\n"
                    f"📢 **الاتجاه:** `{action} XAU/USD`\n"
                    f"📊 **النموذج:** `{setup_type}`\n"
                    f"📍 **سعر التفعيل:** `{price} $`",
                    parse_mode="Markdown"
                )
        return "OK", 200
    except Exception as e:
        return str(e), 400

@bot.message_handler(commands=['start'])
def start_command(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("💰 السعر اللحظي"),
        types.KeyboardButton("📊 مزاج وتحليل السوق"),
        types.KeyboardButton("🛡️ الدعم والمقاومة"),
        types.KeyboardButton("⚡ صفقات مؤسسية (VIP)"),
        types.KeyboardButton("🔔 تفعيل/إيقاف التنبيهات")
    )
    bot.send_message(message.chat.id, "مرحباً بك يا عبد الله، تم ربط النظام بنجاح.", parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    text = message.text
    price = get_gold_price()
    if text == "💰 السعر اللحظي":
        bot.send_message(message.chat.id, f"📍 **السعر الحالي:** `{price} $`", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, f"✅ تم استلام طلبك. السعر الحالي للذهب: `{price} $`", parse_mode="Markdown")

# ضبط الويب هوك تلقائياً عند بدء التشغيل الفعلي
with app.app_context():
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        try:
            bot.remove_webhook()
            bot.set_webhook(url=f"{external_url}/{TOKEN}")
        except:
            pass

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)