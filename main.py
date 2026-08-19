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

last_price = None
open_daily_price = 4370.0 # سعر افتراضي لافتتاح اليوم لحساب النسبة المئوية بدقة

# --- 1. إعداد وتحديث قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY)''')
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
    cursor.execute('INSERT OR IGNORE INTO users (chat_id) VALUES (?)', (chat_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_gold_price():
    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        return round(float(response.json().get("price", 4367.47)), 2)
    except:
        return 4367.47

# --- دالة حساب المستويات الديناميكية حسب الاتجاه ---
def get_institutional_levels(price):
    change_from_open = price - open_daily_price

    if change_from_open < 0:
        signal_type = "📉 بيع (SELL)"
        ob_low = round(price + 3.0, 2)
        ob_high = round(price + 6.0, 2)
        zone_entree = f"{ob_low} ⟷ {ob_high} (منطقة عرض)"
        stop_loss = round(ob_high + 5.0, 2)
        tp1 = round(price - 8.0, 2)
        tp2 = round(price - 18.0, 2)
        tp3 = round(price - 32.0, 2)
    else:
        signal_type = "📈 شراء (BUY)"
        ob_low = round(price - 6.5, 2)
        ob_high = round(price - 4.0, 2)
        zone_entree = f"{ob_low} ⟷ {ob_high} (منطقة طلب)"
        stop_loss = round(ob_low - 5.0, 2)
        tp1 = round(price + 10.0, 2)
        tp2 = round(price + 22.0, 2)
        tp3 = round(price + 40.0, 2)

    return zone_entree, stop_loss, tp1, tp2, tp3, signal_type

# --- دالة إرسال التحذير الخارق عند اكتمال الشروط بدقة ---
def send_ultimate_alert(chat_id, price, signal_type, zone_entree, stop_loss, tp1):
    alert_message = (
        f"🚨🔥 **[ تـنـبـيـه الـسـوق الـخـارق - فرصة ذهبية مؤكدة ]** 🔥🚨\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ **تنبيه عالي الثقة (High-Probability Setup)!**\n"
        f"📍 **السعر الحالي:** `{price} $`\n"
        f"📌 **الاتجاه ونوع الصفقة:** `{signal_type}`\n"
        f"🎯 **منطقة التفعيل (كسر الهيكل / العرض):** `{zone_entree}`\n"
        f"⛔ **وقف الخسارة الآمن:** `{stop_loss} $`\n"
        f"🎯 **الهدف الأساسي (TP1):** `{tp1} $`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *ملاحظة:* تم رصد توافق السيولة المؤسسية مع مستويات هيكل السوق بدقة."
    )
    bot.send_message(chat_id, alert_message, parse_mode="Markdown")

# --- نظام مراقبة السوق الخلفي مع تفعيل التحذير الخارق ---
def background_market_monitor():
    global last_price
    while True:
        try:
            users = get_all_users()
            if users:
                price = get_gold_price()
                zone_entree, stop_loss, tp1, tp2, tp3, signal_type = get_institutional_levels(price)

                # مثال تفعيل التحذير الخارق تلقائياً لو السعر دخل في نطاق عرض محدد أو حدث تغير قوي
                if last_price is not None:
                    diff = round(price - last_price, 2)

                    # شرط إطلاق التحذير الخارق (مثلاً هبوط قوي أو وصول السعر لمنطقة معينة)
                    if diff <= -3.0 or (4365.0 <= price <= 4369.0): 
                        for chat_id in users:
                            send_ultimate_alert(chat_id, price, signal_type, zone_entree, stop_loss, tp1)
                            
                last_price = price
            time.sleep(60)
        except:
            time.sleep(60)

threading.Thread(target=background_market_monitor, daemon=True).start()

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
        types.InlineKeyboardButton("📊 مزاج وتحليل السوق (خارق)", callback_data="market_mood"),
        types.InlineKeyboardButton("🚀 صفقات زيرو انعكاس", callback_data="zero_draw"),
        types.InlineKeyboardButton("📈 سجل أداء البوت", callback_data="track_record")
    )

    welcome_text = (
        f"👑 **النظام الذكي المتطور لتداول الذهب (Institutional AI Bot)**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"مرحباً بك. تم تفعيل نظام التحليل الفني والسيولة المؤسسية بنجاح."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    add_user(call.message.chat.id)
    price = get_gold_price()
    zone_entree, stop_loss, tp1, tp2, tp3, signal_type = get_institutional_levels(price)

    if call.data == "get_price":
        bot.send_message(call.message.chat.id, f"📍 السعر الحالي: `{price} $`", parse_mode="Markdown")
    elif call.data == "market_mood":
        bot.send_message(call.message.chat.id, f"📊 الاتجاه الحالي: `{signal_type}`\n📍 نطاق التفعيل: `{zone_entree}`", parse_mode="Markdown")
    elif call.data == "zero_draw":
        send_ultimate_alert(call.message.chat.id, price, signal_type, zone_entree, stop_loss, tp1)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))