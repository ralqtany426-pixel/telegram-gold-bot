import os
import sqlite3
import requests
import telebot
import threading
import time
import datetime
from flask import Flask, request
from telebot import types

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- 🛠️ ضبط الفارق السعري ---
PRICE_OFFSET = 0.0 

# --- متغيرات حالة الصفقة ---
active_signals = {
    "is_locked": False,
    "signal_type": None,
    "zone_entree": None,
    "stop_loss": None,
    "tp1": None,
    "tp2": None,
    "tp3": None,
    "probability": None,
    "tf_15m": None,
    "tf_30m": None,
    "tf_1h": None,
    "tf_4h": None,
    "last_alert_sent": False
}

# --- 1. إعداد وتحديث قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        chat_id INTEGER PRIMARY KEY,
                        alerts_enabled INTEGER DEFAULT 1
                    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS performance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        status TEXT, 
                        price REAL, 
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
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

# --- جلب سعر الذهب ---
def get_gold_price():
    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        raw_price = float(response.json().get("price", 0.0))
        return round(raw_price + PRICE_OFFSET, 2)
    except:
        return round(4485.0 + PRICE_OFFSET, 2)

# --- نظام التنبيهات ---
def get_upcoming_news():
    now = datetime.datetime.now()
    news_schedule = ["14:30", "16:00", "20:00"]
    for time_str in news_schedule:
        try:
            news_time = datetime.datetime.strptime(time_str, "%H:%M").time()
            if (news_time.hour == now.hour and news_time.minute - now.minute == 1):
                return "⚠️🚨 **تنبيه عاجل:** خبر اقتصادي قوي خلال دقيقة!"
        except: pass
    return None

def get_dynamic_institutional_levels(price):
    global active_signals
    # (المنطق الخاص بك كما هو)
    trend_selector = int(price // 10) % 2  
    if trend_selector == 0:
        return "4480-4490", 4500, 4470, 4460, 4450, "📉 بيع", 92, "مقاومة", "تجميع", "رفض", "ارتداد"
    else:
        return "4470-4480", 4460, 4490, 4500, 4510, "📈 شراء", 94, "دعم", "تجميع", "اختراق", "سيولة"

def get_support_resistance_levels(price):
    return round(price+25, 2), round(price+15, 2), round(price+7, 2), round(price-7, 2), round(price-15, 2), round(price-28, 2)

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

@bot.message_handler(commands=['start'])
def start_command(message):
    add_user(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 السعر اللحظي", callback_data="get_price"),
        types.InlineKeyboardButton("📊 تحليل الفريمات", callback_data="market_mood"),
        types.InlineKeyboardButton("🛡️ الدعم والمقاومة", callback_data="support_resistance"),
        types.InlineKeyboardButton("🚀 صفقات VIP", callback_data="pro_signals"),
        types.InlineKeyboardButton("🔔 التنبيهات", callback_data="toggle_alerts"),
        types.InlineKeyboardButton("🧮 حاسبة المخاطر", callback_data="risk_calc")
    )
    bot.send_message(message.chat.id, "👑 **النظام الذكي لتداول الذهب**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    price = get_gold_price()
    # (باقي كود المعالجة كما هو في ملفك الأصلي)
    bot.answer_callback_query(call.id, text="تم تنفيذ الطلب")
    # أضف هنا باقي منطق عرض الرسائل الخاص بك كما في الكود الأصلي

if __name__ == '__main__':
    # --- التعديل المضاف لضمان عمل الأزرار ---
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL") + "/" + TOKEN
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))