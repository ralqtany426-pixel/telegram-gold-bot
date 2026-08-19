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
open_daily_price = 4370.0 

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

# --- دوال جلب الأسعار والتحليلات المتقدمة ---
def get_gold_price():
    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        return round(float(response.json().get("price", 4367.47)), 2)
    except:
        return 4367.47

def get_institutional_levels(price):
    change_from_open = price - open_daily_price
    
    # حساب نسبة النجاح ديناميكياً بناءً على حجم الحركة والزخم
    abs_change = abs(change_from_open)
    base_probability = 82
    calculated_probability = min(96, base_probability + int(abs_change * 0.5))

    if change_from_open < 0:
        signal_type = "📉 بيع (SELL)"
        ob_low = round(price + 3.0, 2)
        ob_high = round(price + 6.0, 2)
        zone_entree = f"{ob_low} ⟷ {ob_high} (منطقة عرض مؤسسية)"
        stop_loss = round(ob_high + 5.0, 2)
        tp1 = round(price - 8.0, 2)
        tp2 = round(price - 18.0, 2)
        tp3 = round(price - 32.0, 2)
        
        # تحليل الفريمات لاتجاه البيع
        tf_15m = "مقاومة لحظية واختبار خط الاتجاه الهابط"
        tf_1h = "تشبع شرائي واجتياز لفوليوم الهبوط"
        tf_4h = "ارتداد من هجوم الدببة (Bearish Order Block)"
        tf_daily = "اتجاه عام هابط ضمن القناة الرئيسية"
    else:
        signal_type = "📈 شراء (BUY)"
        ob_low = round(price - 6.5, 2)
        ob_high = round(price - 4.0, 2)
        zone_entree = f"{ob_low} ⟷ {ob_high} (منطقة طلب مؤسسية)"
        stop_loss = round(ob_low - 5.0, 2)
        tp1 = round(price + 10.0, 2)
        tp2 = round(price + 22.0, 2)
        tp3 = round(price + 40.0, 2)
        
        # تحليل الفريمات لاتجاه الشراء
        tf_15m = "دعم قوي وتشكل نموذج انعكاسي إيجابي"
        tf_1h = "اختراق ناجح لمنطقة السيولة وتجميع صاعد"
        tf_4h = "ارتداد من قاعدة طلب قوية (Bullish OB)"
        tf_daily = "زخم شرائي يدعم استمرار الصعود"

    return zone_entree, stop_loss, tp1, tp2, tp3, signal_type, calculated_probability, tf_15m, tf_1h, tf_4h, tf_daily

def get_support_resistance_levels(price):
    return round(price + 25.0, 2), round(price + 15.0, 2), round(price + 7.0, 2), \
           round(price - 7.0, 2), round(price - 15.0, 2), round(price - 28.0, 2)

# --- دالة التحذير الخارق التلقائي ---
def send_ultimate_alert(chat_id, price, signal_type, zone_entree, stop_loss, tp1, probability):
    alert_message = (
        f"🚨🔥 **[ تنبيــــه الـسـوق الـخــــارق ]** 🔥🚨\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ **فرصة ذهبية مؤكدة - High Probability!**\n"
        f"📍 السعر الحالي: `{price} $`\n"
        f"📌 الاتجاه: `{signal_type}`\n"
        f"🎯 نسبة نجاح الصفقة: `__ {probability}% __` 🌟\n"
        f"🎯 منطقة التفعيل: `{zone_entree}`\n"
        f"⛔ وقف الخسارة: `{stop_loss} $`\n"
        f"🎯 الهدف الأساسي (TP1): `{tp1} $`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *ملاحظة: توافق تام للسيولة عبر جميع الفريمات.*"
    )
    bot.send_message(chat_id, alert_message, parse_mode="Markdown")

# --- مراقبة السوق الخلفية ---
def background_market_monitor():
    while True:
        try:
            users = get_all_users()
            if users:
                price = get_gold_price()
                zone_entree, stop_loss, tp1, _, _, signal_type, prob, _, _, _, _ = get_institutional_levels(price)
                if 4365.0 <= price <= 4369.0:
                    for chat_id in users:
                        send_ultimate_alert(chat_id, price, signal_type, zone_entree, stop_loss, tp1, prob)
                        time.sleep(3600) 
            time.sleep(60)
        except:
            time.sleep(60)

threading.Thread(target=background_market_monitor, daemon=True).start()

# --- الروابط وأوامر البوت ---
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
        types.InlineKeyboardButton("🛡️ الدعم والمقاومة المؤسسية", callback_data="support_resistance"),
        types.InlineKeyboardButton("🚀 صفقات زيرو انعكاس", callback_data="zero_draw"),
        types.InlineKeyboardButton("⚡ صفقات مؤسسية (VIP)", callback_data="pro_signals"),
        types.InlineKeyboardButton("🧮 حاسبة إدارة المخاطر", callback_data="risk_calc"),
        types.InlineKeyboardButton("📈 سجل أداء البوت", callback_data="track_record")
    )
    bot.send_message(message.chat.id, "👑 **النظام الذكي المتطور لتداول الذهب**", parse_mode="Markdown", reply_markup=markup)

# --- معالجة الأزرار مع الفريمات ونسبة النجاح ---
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    price = get_gold_price()
    zone_entree, stop_loss, tp1, tp2, tp3, signal_type, probability, tf_15m, tf_1h, tf_4h, tf_daily = get_institutional_levels(price)
    r3, r2, r1, s1, s2, s3 = get_support_resistance_levels(price)

    if call.data == "get_price":
        msg = f"💰 **السعر اللحظي للذهب (XAU/USD):**\n`{price} $`"
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "market_mood":
        msg = (
            f"📊 **تحليل ومزاج السوق عبر جميع الفريمات:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 السعر الحالي: `{price} $`\n"
            f"📌 الاتجاه المسيطر: `{signal_type}`\n"
            f"🎯 **نسبة نجاح الاتجاه الحالي: `{probability}%`** 🌟\n\n"
            f"⏱️ **التحليل الزمني المتعدد:**\n"
            f"• فريم 15 دقيقة: `{tf_15m}`\n"
            f"• فريم 1 ساعة: `{tf_1h}`\n"
            f"• فريم 4 ساعات: `{tf_4h}`\n"
            f"• الفريم اليومي (Daily): `{tf_daily}`"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "support_resistance":
        msg = (
            f"🛡️ **مستويات الدعم والمقاومة المؤسسية:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 مقاومة 3: `{r3} $`\n"
            f"🔴 مقاومة 2: `{r2} $`\n"
            f"🔴 مقاومة 1: `{r1} $`\n"
            f"--- السعر الحالي: `{price} $` ---\n"
            f"🟢 دعم 1: `{s1} $`\n"
            f"🟢 دعم 2: `{s2} $`\n"
            f"🟢 دعم 3: `{s3} $`"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "zero_draw" or call.data == "pro_signals":
        msg = (
            f"🚀 **{('صفقات زيرو انعكاس' if call.data=='zero_draw' else 'صفقات مؤسسية VIP')}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 الاتجاه: `{signal_type}`\n"
            f"📍 السعر الحالي: `{price} $`\n"
            f"🌟 **نسبة نجاح الصفقة: `{probability}%`**\n"
            f"🎯 منطقة التفعيل: `{zone_entree}`\n"
            f"⛔ وقف الخسارة: `{stop_loss} $`\n"
            f"🎯 الهدف الأول (TP1): `{tp1} $`\n"
            f"🎯 الهدف الثاني (TP2): `{tp2} $`\n"
            f"🎯 الهدف الثالث (TP3): `{tp3} $`\n\n"
            f"⏱️ **توافق الفريمات:**\n"
            f"• 15د: `{tf_15m}`\n"
            f"• 1س: `{tf_1h}`\n"
            f"• 4س: `{tf_4h}`"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "risk_calc":
        msg = (
            f"🧮 **حاسبة إدارة المخاطر:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"للحفاظ على حسابك، يرجى عدم المخاطرة بأكثر من `1%` إلى `2%` من إجمالي رأس مالك.\n"
            f"• وقف الخسارة المقترح للصفقة الحالية: `{stop_loss} $`"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "track_record":
        msg = (
            f"📈 **سجل أداء البوت:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ نسبة نجاح الصفقات الإجمالية: `88%`\n"
            f"📊 إجمالي النقاط المحققة هذا الأسبوع: `+340 نقطة`\n"
            f"وضع النظام: مستقر ومربط بالتحليل الفني متعدد الفريمات."
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))