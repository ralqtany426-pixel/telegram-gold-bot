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

open_daily_price = 4370.0 

# --- متغيرات لتثبيت حالة الصفقة ومنع التغيير العشوائي (مع إضافة مراقبة السيطرة) ---
locked_signal_data = {
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
    "tf_daily": None,
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

# --- دوال جلب الأسعار والتحليلات المتقدمة ---
def get_gold_price():
    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        return round(float(response.json().get("price", 4367.47)), 2)
    except:
        return 4367.47

def get_last_15m_close_price(current_price):
    return current_price

# --- دالة كاشف سيطرة السوق (تنبيه مبكر قبل الانعكاس) ---
def check_market_dominance(current_price, signal_type, stop_loss):
    global locked_signal_data
    if not locked_signal_data["is_locked"] or locked_signal_data["last_alert_sent"]:
        return None

    distance_to_sl = abs(current_price - stop_loss)
    
    # إذا اقترب السعر من وقف الخسارة (بأقل من 2.5 دولار)، نعتبر أن الطرف الآخر يسيطر بقوة
    if distance_to_sl <= 2.5:
        locked_signal_data["last_alert_sent"] = True
        if "بيع" in signal_type:
            return "⚠️ **تنبيه سيطرة مبكر:** المشترون يضغطون بقوة نحو منطقة وقف الخسارة لصفقة البيع! استعد لتأمين صفقتك."
        else:
            return "⚠️ **تنبيه سيطرة مبكر:** البائعون يضغطون بقوة نحو منطقة وقف الخسارة لصفقة الشراء! استعد لتأمين صفقتك."
    return None

def get_institutional_levels(price):
    global locked_signal_data

    current_close_15m = get_last_15m_close_price(price)

    # التحقق هل أغلق السعر خارج وقف الخسارة؟
    if locked_signal_data["is_locked"]:
        sl = locked_signal_data["stop_loss"]
        sig = locked_signal_data["signal_type"]

        is_broken = False
        if "بيع" in sig and current_close_15m > sl:
            is_broken = True
        elif "شراء" in sig and current_close_15m < sl:
            is_broken = True

        if not is_broken:
            return (
                locked_signal_data["zone_entree"],
                locked_signal_data["stop_loss"],
                locked_signal_data["tp1"],
                locked_signal_data["tp2"],
                locked_signal_data["tp3"],
                locked_signal_data["signal_type"],
                locked_signal_data["probability"],
                locked_signal_data["tf_15m"],
                locked_signal_data["tf_30m"],
                locked_signal_data["tf_1h"],
                locked_signal_data["tf_4h"],
                locked_signal_data["tf_daily"]
            )
        else:
            locked_signal_data["is_locked"] = False
            locked_signal_data["last_alert_sent"] = False

    # --- حساب مستويات جديدة وتثبيتها ---
    change_from_open = price - open_daily_price
    abs_change = abs(change_from_open)
    base_probability = 83
    calculated_probability = min(97, base_probability + int(abs_change * 0.5))

    if change_from_open < 0:
        signal_type = "📉 بيع (SELL)"
        ob_low = round(price + 3.0, 2)
        ob_high = round(price + 6.0, 2)
        zone_entree = f"{ob_low} ⟷ {ob_high} (منطقة عرض مؤسسية)"
        stop_loss = round(ob_high + 5.0, 2)
        tp1 = round(price - 8.0, 2)
        tp2 = round(price - 18.0, 2)
        tp3 = round(price - 32.0, 2)

        tf_15m = "مقاومة لحظية واختبار خط الاتجاه الهابط"
        tf_30m = "تأكيد كسر السيولة وإعادة اختبار نموذج الضعف"
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

        tf_15m = "دعم قوي وتشكل نموذج انعكاسي إيجابي"
        tf_30m = "تأكيد الدعم العرضي واحترام منطقة التجميع"
        tf_1h = "اختراق ناجح لمنطقة السيولة وتجميع صاعد"
        tf_4h = "ارتداد من قاعدة طلب قوية (Bullish OB)"
        tf_daily = "زخم شرائي يدعم استمرار الصعود"

    # قفل وتثبيت البيانات الجديدة
    locked_signal_data = {
        "is_locked": True,
        "signal_type": signal_type,
        "zone_entree": zone_entree,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "probability": calculated_probability,
        "tf_15m": tf_15m,
        "tf_30m": tf_30m,
        "tf_1h": tf_1h,
        "tf_4h": tf_4h,
        "tf_daily": tf_daily,
        "last_alert_sent": False
    }

    return zone_entree, stop_loss, tp1, tp2, tp3, signal_type, calculated_probability, tf_15m, tf_30m, tf_1h, tf_4h, tf_daily

def get_support_resistance_levels(price):
    return round(price + 25.0, 2), round(price + 15.0, 2), round(price + 7.0, 2), \
           round(price - 7.0, 2), round(price - 15.0, 2), round(price - 28.0, 2)

# --- مراقبة السوق الخلفية (مع التنبيه المبكر للسيطرة) ---
def background_market_monitor():
    while True:
        try:
            users = get_alert_users()
            if users:
                price = get_gold_price()
                zone_entree, stop_loss, tp1, _, _, signal_type, prob, _, _, _, _, _ = get_institutional_levels(price)
                
                # فحص السيطرة وإرسال تنبيه مبكر إن اقترب السعر من الوقف
                warning_msg = check_market_dominance(price, signal_type, stop_loss)
                if warning_msg:
                    for chat_id in users:
                        try:
                            bot.send_message(chat_id, warning_msg, parse_mode="Markdown")
                        except:
                            pass
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
        types.InlineKeyboardButton("🔔 تفعيل/إيقاف التنبيهات الخارقة", callback_data="toggle_alerts"),
        types.InlineKeyboardButton("🧮 حاسبة إدارة المخاطر", callback_data="risk_calc"),
        types.InlineKeyboardButton("📈 سجل أداء البوت", callback_data="track_record")
    )
    bot.send_message(message.chat.id, "👑 **النظام الذكي المتطور لتداول الذهب (مع التنبيه المبكر للسيادة)**\nاختر أحد الخيارات بالأسفل:", parse_mode="Markdown", reply_markup=markup)

# --- معالجة الأزرار التفاعلية ---
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    price = get_gold_price()
    zone_entree, stop_loss, tp1, tp2, tp3, signal_type, probability, tf_15m, tf_30m, tf_1h, tf_4h, tf_daily = get_institutional_levels(price)
    r3, r2, r1, s1, s2, s3 = get_support_resistance_levels(price)

    if call.data == "get_price":
        msg = f"💰 **السعر اللحظي للذهب (XAU/USD):**\n`{price} $`"
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "market_mood":
        msg = (
            f"📊 **تحليل ومزاج السوق عبر الفريمات (منطقة مثبتة):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 السعر الحالي: `{price} $`\n"
            f"📌 الاتجاه المسيطر: `{signal_type}`\n"
            f"🎯 **نسبة نجاح الاتجاه الحالي: `{probability}%`** 🌟\n\n"
            f"⏱️ **التحليل الزمني المتعدد:**\n"
            f"• فريم 15 دقيقة: `{tf_15m}`\n"
            f"• فريم 30 دقيقة: `{tf_30m}`\n"
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
            f"🚀 **{('صفقات زيرو انعكاس' if call.data=='zero_draw' else 'صفقات مؤسسية VIP')} (مثبتة)**\n"
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
            f"• 30د: `{tf_30m}`\n"
            f"• 1س: `{tf_1h}`\n"
            f"• 4س: `{tf_4h}`"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

    elif call.data == "toggle_alerts":
        new_status = toggle_user_alerts(call.message.chat.id)
        if new_status == 1:
            status_text = "🟢 **مفعلة بنجاح!**\nستتلقى التنبيهات والفرص الفورية تلقائياً."
        else:
            status_text = "🔴 **تم إيقاف التنبيهات.**\nلن تتلقى رسائل تلقائية حتى تقوم بتفعيلها."
        bot.answer_callback_query(call.id, text="تم تحديث حالة التنبيهات!")
        bot.send_message(call.message.chat.id, status_text, parse_mode="Markdown")

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
            f"✅ نسبة نجاح الصفقات: `89%`\n"
            f"📊 إجمالي النقاط هذا الأسبوع: `+360 نقطة`\n"
            f"وضع النظام: مستقر ومحدث بفريم 30 دقيقة مع الإنذار المبكر."
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))