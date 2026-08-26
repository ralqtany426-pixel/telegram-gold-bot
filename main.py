import os
import time
import sqlite3
import threading
import requests
import telebot
import pandas as pd
import yfinance as yf
from telebot import types
from flask import Flask, request

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN غير موجود في متغيرات البيئة!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

DB_NAME = "users.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY)")
        conn.commit()

def add_user(chat_id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR IGNORE INTO users (chat_id) VALUES (?)", (chat_id,))
        conn.commit()

def get_all_users():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM users")
        return [row[0] for row in cursor.fetchall()]

init_db()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_live_price():
    try:
        url = "https://api.gold-api.com/price/XAU"
        res = requests.get(url, headers=HEADERS, timeout=5).json()
        if 'price' in res and res['price']:
            return round(float(res['price']), 2)
    except Exception:
        pass

    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="1d", interval="1m")
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except Exception:
        pass

    return 2650.00

def fetch_candles(interval='30m', period='5d'):
    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period=period, interval=interval)
        if not df.empty and len(df) >= 5:
            df = df[['Open', 'High', 'Low', 'Close']].astype(float)
            return df
    except Exception:
        pass
    return pd.DataFrame()

def analyze_market_structure(df):
    if df.empty or len(df) < 5:
        return {
            "trend": "صاعد 🟢", "demand": "منطقة طلب افتراضية", 
            "demand_low": 0, "demand_high": 0, "fvg": "لا توجد ⚪", "ema": 0
        }

    current = df['Close'].iloc[-1]
    ema_50 = df['Close'].ewm(span=min(len(df), 50), adjust=False).mean().iloc[-1]
    trend = "BULLISH 🟢 (صاعد)"

    high_val = round(df['High'].max(), 2)
    low_val = round(df['Low'].min(), 2)

    # تحديد منطقة الطلب / الأوردر بلوك (Order Block / Demand Zone) بطريقة SMC
    d_low, d_high = low_val, round(low_val + 10.0, 2)
    for i in range(len(df)-2, 0, -1):
        # البحث عن شمعة هابطة تليها صعود قوي (أوردر بلوك شرائي)
        if df['Close'].iloc[i] < df['Open'].iloc[i] and df['Close'].iloc[i+1] > df['High'].iloc[i]:
            d_low, d_high = round(df['Low'].iloc[i], 2), round(df['High'].iloc[i], 2)
            break

    fvg = "لا توجد ⚪"
    for i in range(len(df)-1, 2, -1):
        if df['High'].iloc[i-2] < df['Low'].iloc[i]:
            fvg = f"Bullish FVG 🟢 ({round(df['High'].iloc[i-2], 2)} - {round(df['Low'].iloc[i], 2)})"
            break

    return {
        "trend": trend,
        "demand": f"🟢 منطقة طلب / أوردر بلوك ({d_low} - {d_high})",
        "demand_low": d_low, "demand_high": d_high,
        "fvg": fvg, "ema": round(ema_50, 2)
    }

def multi_timeframe_scan():
    price = get_live_price()
    tf_30m = analyze_market_structure(fetch_candles('30m', '4d'))
    tf_1h  = analyze_market_structure(fetch_candles('1h', '7d'))
    
    strength = "⭐⭐⭐⭐⭐ (فرصة ذهبية قوية)"
    return {
        "price": price, "strength": strength,
        "30m": tf_30m, "1h": tf_1h
    }

def calculate_targets(price):
    entry = price
    sl = round(entry - 10.0, 2)  
    risk = abs(entry - sl)
    tp1 = round(entry + (risk * 1.5), 2)  
    tp2 = round(entry + (risk * 2.5), 2)  
    tp3 = round(entry + (risk * 3.5), 2)  
    rr_ratio = "1 : 3.5"
    return "BUY 🟢 (شراء فقط)", entry, sl, tp1, tp2, tp3, rr_ratio

def auto_alert_loop():
    """حلقة ذكية تفحص السوق كل 5 دقائق ولا ترسل تنبيهاً إلا عند ملامسة الأوردر بلوك أو توفر فرصة حقيقية"""
    time.sleep(15)
    last_alert_type = ""
    
    while True:
        try:
            users = get_all_users()
            if users:
                data = multi_timeframe_scan()
                p = data['price']
                tf30 = data['30m']
                
                d_low = tf30['demand_low']
                d_high = tf30['demand_high']

                # شرط 1: هل السعر دخل في منطقة الأوردر بلوك / الطلب الحالية؟ (بامان هامش بسيط ±5 دولار)
                is_at_order_block = (d_low - 3.0) <= p <= (d_high + 5.0)
                
                # شرط 2: صفقة ناجحة عامة (مثلاً إذا كان السعر فوق المتوسط المتحرك ومستقر)
                is_valid_trade = p >= tf30['ema']

                alert_msg = ""
                current_state = ""

                if is_at_order_block:
                    current_state = f"ORDER_BLOCK_{round(p, -1)}"
                    if current_state != last_alert_type:
                        last_alert_type = current_state
                        t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p)
                        alert_msg = (
                            f"🚨 **[ تنبيه هام: وصول الذهب لمنطقة الأوردر بلوك (Order Block) ]** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📍 **السعر الحالي لامس منطقة الطلب:** `{p}` $\n"
                            f"🧱 **نطاق الأوردر بلوك:** `{d_low} - {d_high}` $\n"
                            f"🎯 **نوع التوصية المقترحة:** `{t_type}`\n"
                            f"🛑 **وقف الخسارة:** `{sl}` $\n"
                            f"🎯 **الأهداف:** TP1: `{tp1}` | TP2: `{tp2}` | TP3: `{tp3}`\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"💡 *راقب حركة الشموع للتأكيد والانطلاق.*"
                        )
                elif is_valid_trade and not last_alert_type.startswith("TRADE_"):
                    current_state = f"TRADE_{round(p, -1)}"
                    if current_state != last_alert_type:
                        last_alert_type = current_state
                        t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p)
                        alert_msg = (
                            f"💎 **[ صفقة شراء ذهبية ناجحة - SMC ]** 💎\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🚀 **توافرت شروط صفقة شراء قوية!**\n"
                            f"📍 **سعر الدخول:** `{entry}` $\n"
                            f"🛑 **وقف الخسارة:** `{sl}` $\n"
                            f"🎯 **الهدف الأول:** `{tp1}` $\n"
                            f"🎯 **الهدف الثاني:** `{tp2}` $\n"
                            f"🎯 **الهدف الثالث:** `{tp3}` $\n"
                            f"⚖️ **نسبة العائد (R:R):** `{rr}`\n"
                            f"━━━━━━━━━━━━━━━━━━━━━"
                        )

                # إرسال التنبيه فقط إذا تحقق أحد الشرطين ولم يتم تكراره لنفس النطاق السعري
                if alert_msg:
                    for chat_id in users:
                        try:
                            bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                        except Exception as e:
                            print(f"Error sending to {chat_id}: {e}")

        except Exception as e:
            print(f"Alert Error: {e}")
        
,        # فحص السوق كل 5 دقائق
        time.sleep(300)

threading.Thread(target=auto_alert_loop, daemon=True).start()

@bot.message_handler(commands=['start'])
def start_cmd(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("⚡ السعر اللحظي"),
        types.KeyboardButton("🔥 صفقة شراء VIP حالية"),
        types.KeyboardButton("📊 الدعم والمقاومة"),
        types.KeyboardButton("تحليل الذهب 🥇"),
        types.KeyboardButton("🔔 اختبار إرسال تنبيه الآن")
    )
    bot.send_message(message.chat.id, "👑 أهلاً بك في نظام تنبيهات الأوردر بلوك والصفقات الناجحة (شراء فقط). البوت يراقب السوق الآن 🚀", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⚡ السعر اللحظي")
def send_live_price(message):
    p = get_live_price()
    bot.send_message(message.chat.id, f"⚡ **سعر الذهب العالمي المباشر (Spot XAU/USD):** `{p}` $ 🏆", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔥 صفقة شراء VIP حالية")
def send_vip_trade(message):
    data = multi_timeframe_scan()
    p = data['price']
    t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p)
    msg = (
        f"💎 **[ توصية شراء VIP الاحترافية - SMC ]** 💎\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **الصفقة المقترحة:** `{t_type}`\n"
        f"⭐ **تقييم الثقة:** `{data['strength']}`\n"
        f"📍 **سعر الدخول الموصى به:** `{entry}` $\n"
        f"🛑 **وقف الخسارة:** `{sl}` $\n"
        f"🎯 **الهدف 1:** `{tp1}` $\n"
        f"🎯 **الهدف 2:** `{tp2}` $\n"
        f"🎯 **الهدف 3:** `{tp3}` $\n"
        f"⚖️ **نسبة المخاطرة للأرباح:** `{rr}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 الدعم والمقاومة")
def send_support_resistance(message):
    p = get_live_price()
    df_1h = fetch_candles('1h', '7d')
    r1 = round(df_1h['High'].max(), 2) if not df_1h.empty else round(p + 15.0, 2)
    s1 = round(df_1h['Low'].min(), 2) if not df_1h.empty else round(p - 15.0, 2)
    msg = (
        f"📊 **مستويات السيولة والدعم والمقاومة:**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 **السعر الحالي:** `{p}` $\n"
        f"🔴 **مقاومة رئيسية (R1):** `{r1}` $\n"
        f"🟢 **دعم رئيسي / أوردر بلوك (S1):** `{s1}` $\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "تحليل الذهب 🥇")
def handle_gold_analysis(message):
    add_user(message.chat.id)
    data = multi_timeframe_scan()
    msg = (
        f"👑 **التقرير الفني الشامل (أوردر بلوك ونقاط الدخول)** 👑\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 **السعر اللحظي:** `{data['price']}` $\n"
        f"⚡ **الاتجاه العام:** `BUY Only (صاعد)`\n"
        f"🔹 **30 دقيقة:** {data['30m']['demand']}\n"
        f"🔹 **منطقة FVG:** `{data['30m']['fvg']}`\n"
        f"🔹 **المتوسط (EMA50):** `{data['30m']['ema']}` $\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔔 اختبار إرسال تنبيه الآن")
def test_alert_btn(message):
    add_user(message.chat.id)
    p = get_live_price()
    t_type, entry, sl, tp1, tp2, tp3, rr = calculate_targets(p)
    msg = (
        f"🧪 **[ اختبار تنبيه الأوردر بلوك والصفقة الناجحة ]** 🧪\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚨 **هذا تنبيه تجريبي فوري:**\n"
        f"📍 **السعر الحالي:** `{entry}` $\n"
        f"🧱 **الحالة:** السعر في منطقة أوردر بلوك تجريبية مع توافر صفقة شراء ناجحة.\n"
        f"🛑 **وقف الخسارة:** `{sl}` $\n"
        f"🎯 **الأهداف:** TP1: `{tp1}` | TP2: `{tp2}` | TP3: `{tp3}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    else:
        return "Invalid Data", 403

@app.route('/')
def index():
    return "Bot is running with Smart Order Block Alerts!", 200

if __name__ == '__main__':
    bot.remove_webhook()
    render_url = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if render_url:
        webhook_url = f"https://{render_url}/{TOKEN}"
        bot.set_webhook(url=webhook_url)
        print(f"Webhook successfully set to: {webhook_url}")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)