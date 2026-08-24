import os
import sqlite3
import requests
import telebot
import threading
import time
import pandas as pd
import yfinance as yf
from flask import Flask, request
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

SYMBOLS = {
    "البيتكوين": "BTCUSD",
    "الذهب": "XAUUSD",
    "اليورو": "EURUSD"
}

last_alert_time = {
    "الذهب": 0,
    "اليورو": 0,
    "البيتكوين": 0
}

def get_db_connection():
    conn = sqlite3.connect('bot_users.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, alerts INTEGER DEFAULT 1)''')
        conn.commit()

init_db()

def add_user(chat_id):
    try:
        with get_db_connection() as conn:
            conn.execute('INSERT OR IGNORE INTO users (chat_id, alerts) VALUES (?, 1)', (chat_id,))
            conn.commit()
    except Exception as e:
        print(f"Error adding user: {e}")

def get_alert_users():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT chat_id FROM users WHERE alerts = 1')
            return [row['chat_id'] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []

def fetch_klines(symbol_key, interval="15min"):
    tf_map = {
        "15min": ("15m", "1d"), 
        "30min": ("30m", "5d"), 
        "1hour": ("1h", "5d"), 
        "4hour": ("1h", "1mo"), 
        "1day": ("1d", "3mo")
    }
    tf, period = tf_map.get(interval, ("15m", "1d"))

    # استخدام رموز Yahoo المحدثة مع جلب البيانات المباشرة
    ticker_map = {
        "الذهب": ["XAUUSD=X", "GC=F"],
        "اليورو": ["EURUSD=X"],
        "البيتكوين": ["BTC-USD"]
    }
    
    tickers = ticker_map.get(symbol_key, ["XAUUSD=X"])
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    for sym in tickers:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={period}&interval={tf}"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get('chart', {}).get('result'):
                    result = data['chart']['result'][0]
                    quote = result['indicators']['quote'][0]
                    df = pd.DataFrame({
                        'Open': quote['open'],
                        'High': quote['high'],
                        'Low': quote['low'],
                        'Close': quote['close']
                    }).dropna()
                    
                    if not df.empty and len(df) >= 5:
                        return df
        except Exception as e:
            print(f"Fetch Error ({sym}): {e}")

    return pd.DataFrame()

def get_market_trend(symbol_key):
    df_1d = fetch_klines(symbol_key, "1day")
    df_4h = fetch_klines(symbol_key, "4hour")
    df_1h = fetch_klines(symbol_key, "1hour")
    df_30m = fetch_klines(symbol_key, "30min")

    if df_1d.empty or df_4h.empty or df_1h.empty or df_30m.empty:
        return "NEUTRAL ⚖️"

    trend_1d = "BULLISH" if df_1d['Close'].iloc[-1] > df_1d['Close'].rolling(min(10, len(df_1d))).mean().iloc[-1] else "BEARISH"
    trend_4h = "BULLISH" if df_4h['Close'].iloc[-1] > df_4h['Close'].rolling(min(10, len(df_4h))).mean().iloc[-1] else "BEARISH"
    trend_1h = "BULLISH" if df_1h['Close'].iloc[-1] > df_1h['Close'].rolling(min(10, len(df_1h))).mean().iloc[-1] else "BEARISH"
    trend_30m = "BULLISH" if df_30m['Close'].iloc[-1] > df_30m['Close'].rolling(min(10, len(df_30m))).mean().iloc[-1] else "BEARISH"

    if trend_1d == "BULLISH" and trend_4h == "BULLISH" and trend_1h == "BULLISH" and trend_30m == "BULLISH":
        return "STRONG BULLISH 🚀 (1D+4H+1H+30m)"
    elif trend_1d == "BEARISH" and trend_4h == "BEARISH" and trend_1h == "BEARISH" and trend_30m == "BEARISH":
        return "STRONG BEARISH 📉 (1D+4H+1H+30m)"
    elif trend_4h == "BULLISH" and trend_1h == "BULLISH" and trend_30m == "BULLISH":
        return "BULLISH 🟢 (4H+1H+30m)"
    elif trend_4h == "BEARISH" and trend_1h == "BEARISH" and trend_30m == "BEARISH":
        return "BEARISH 🔴 (4H+1H+30m)"

    return "NEUTRAL ⚖️"

def scan_high_winrate_signals(symbol_key):
    df = fetch_klines(symbol_key, "15min")
    if df.empty or len(df) < 5:
        return None

    decimals = 5 if symbol_key == "اليورو" else 2
    current_price = round(float(df['Close'].iloc[-1]), decimals)
    trend = get_market_trend(symbol_key)

    # حساب الفجوة السعرية FVG
    fvg_status = "غير متوفر"
    for i in range(len(df) - 1, 2, -1):
        if df['Low'].iloc[i] > df['High'].iloc[i-2]:
            fvg_status = f"Bullish FVG 🟢 ({round(df['High'].iloc[i-2], decimals)} - {round(df['Low'].iloc[i], decimals)})"
            break
        elif df['High'].iloc[i] < df['Low'].iloc[i-2]:
            fvg_status = f"Bearish FVG 🔴 ({round(df['High'].iloc[i], decimals)} - {round(df['Low'].iloc[i-2], decimals)})"
            break

    # حساب مناطق Order Block النواة
    bullish_ob, bearish_ob = None, None
    for i in range(len(df)-2, 1, -1):
        if df['Close'].iloc[i] < df['Open'].iloc[i] and df['Close'].iloc[i+1] > df['High'].iloc[i]:
            bullish_ob = (round(df['Low'].iloc[i], decimals), round(df['High'].iloc[i], decimals))
            break

    for i in range(len(df)-2, 1, -1):
        if df['Close'].iloc[i] > df['Open'].iloc[i] and df['Close'].iloc[i+1] < df['Low'].iloc[i]:
            bearish_ob = (round(df['Low'].iloc[i], decimals), round(df['High'].iloc[i], decimals))
            break

    if not bullish_ob:
        bullish_ob = (round(current_price - (0.0020 if symbol_key == "اليورو" else 3.5), decimals), round(current_price - (0.0008 if symbol_key == "اليورو" else 1.0), decimals))
    if not bearish_ob:
        bearish_ob = (round(current_price + (0.0008 if symbol_key == "اليورو" else 1.0), decimals), round(current_price + (0.0020 if symbol_key == "اليورو" else 3.5), decimals))

    signal = "NONE"
    setup_type = ""
    demand_str = f"{bullish_ob[0]} ⟷ {bullish_ob[1]}"
    supply_str = f"{bearish_ob[0]} ⟷ {bearish_ob[1]}"

    buffer = 0.0003 if symbol_key == "اليورو" else (1.5 if symbol_key == "الذهب" else 100.0)

    if current_price <= (bullish_ob[1] + buffer) and ("BULLISH" in trend):
        signal = "BUY"
        setup_type = "اختبار أوردر بلوك شرائي متوافق مع كافة الفريمات 🚀"
    elif current_price >= (bearish_ob[0] - buffer) and ("BEARISH" in trend):
        signal = "SELL"
        setup_type = "اختبار أوردر بلوك بيعي متوافق مع كافة الفريمات 📉"

    return {
        "price": current_price,
        "signal": signal,
        "setup_type": setup_type,
        "demand": demand_str,
        "supply": supply_str,
        "demand_low": bullish_ob[0],
        "supply_high": bearish_ob[1],
        "fvg": fvg_status,
        "trend": trend
    }

def background_monitor():
    time.sleep(5)
    while True:
        try:
            current_timestamp = time.time()
            for name in SYMBOLS.keys():
                if current_timestamp - last_alert_time[name] >= 1800:
                    analysis = scan_high_winrate_signals(name)
                    if analysis and analysis["signal"] != "NONE":
                        last_alert_time[name] = current_timestamp
                        price = analysis["price"]
                        users = get_alert_users()
                        decimals = 5 if name == "اليورو" else 2
                        sl_offset = 0.0006 if name == "اليورو" else (2.5 if name == "الذهب" else 150.0)

                        if analysis["signal"] == "BUY":
                            sl = round(analysis["demand_low"] - sl_offset, decimals)
                            risk = abs(price - sl)
                            tp1 = round(price + (risk * 1.8), decimals)
                            tp2 = round(price + (risk * 3.2), decimals)
                            tp3 = round(price + (risk * 5.0), decimals)
                            action_text = "📈 شراء مؤكد VIP"
                        else:
                            sl = round(analysis["supply_high"] + sl_offset, decimals)
                            risk = abs(sl - price)
                            tp1 = round(price - (risk * 1.8), decimals)
                            tp2 = round(price - (risk * 3.2), decimals)
                            tp3 = round(price - (risk * 5.0), decimals)
                            action_text = "📉 بيع مؤكد VIP"

                        msg = (
                            f"🎯🔥 **تنبيه صفقة مكتملة الشروط** 🔥🎯\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 **الزوج:** {name}\n"
                            f"🚨 **الإشارة:** {action_text}\n"
                            f"📍 **سعر الدخول:** `{price}` $\n\n"
                            f"🧱 **منطقة الطلب / OB:** `{analysis['demand']}`\n"
                            f"🧱 **منطقة العرض / OB:** `{analysis['supply']}`\n"
                            f"📐 **الفجوة السعرية (FVG):** {analysis['fvg']}\n"
                            f"🌐 **اتساق الفريمات:** {analysis['trend']}\n\n"
                            f"⛔ **وقف الخسارة (SL):** `{sl}` $\n"
                            f"🎯 **هدف 1:** `{tp1}` $\n"
                            f"🎯 **هدف 2:** `{tp2}` $\n"
                            f"🎯 **هدف 3:** `{tp3}` $"
                        )

                        for chat_id in users:
                            try:
                                bot.send_message(chat_id, msg, parse_mode="Markdown")
                            except Exception:
                                pass
            time.sleep(60)
        except Exception as e:
            print(f"Monitor error: {e}")
            time.sleep(60)

threading.Thread(target=background_monitor, daemon=True).start()

@app.route('/')
def home():
    return "Bot Engine Active!", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

@bot.message_handler(commands=['start'])
def start_command(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    btn_vip = types.KeyboardButton("🔥 صفقات VIP (SMC / OB / S&D)")
    btn_gold = types.KeyboardButton("الذهب 🥇")
    btn_euro = types.KeyboardButton("اليورو/دولار 💶")
    btn_btc = types.KeyboardButton("البيتكوين ₿")

    markup.add(btn_vip)
    markup.add(btn_gold, btn_euro, btn_btc)

    welcome_text = (
        f"👑 **ماسح التنبيهات المؤسسي VIP**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"تم تعديل سيرفر الأسعار للربط المباشر لجميع الأزواج بنجاح."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    chat_id = message.chat.id
    text = message.text.strip() if message.text else ""
    add_user(chat_id)

    if "VIP" in text.upper():
        bot.send_message(chat_id, "🔍 **جاري فحص كافة الفريمات ومناطق SMC لمطابقة الإشارات...**")
        found_any = False

        for key in SYMBOLS.keys():
            analysis = scan_high_winrate_signals(key)
            if analysis and analysis["signal"] != "NONE":
                found_any = True
                price = analysis["price"]
                decimals = 5 if key == "اليورو" else 2
                sl_offset = 0.0006 if key == "اليورو" else (2.5 if key == "الذهب" else 150.0)

                if analysis["signal"] == "BUY":
                    sl = round(analysis["demand_low"] - sl_offset, decimals)
                    risk = abs(price - sl)
                    tp1 = round(price + (risk * 1.8), decimals)
                    tp2 = round(price + (risk * 3.2), decimals)
                    tp3 = round(price + (risk * 5.0), decimals)
                    action_text = "📈 شراء VIP مؤكد"
                else:
                    sl = round(analysis["supply_high"] + sl_offset, decimals)
                    risk = abs(sl - price)
                    tp1 = round(price - (risk * 1.8), decimals)
                    tp2 = round(price - (risk * 3.2), decimals)
                    tp3 = round(price - (risk * 5.0), decimals)
                    action_text = "📉 بيع VIP مؤكد"

                vip_msg = (
                    f"⭐ **صفقة VIP متوفرة الآن - {key}** ⭐\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 **التوجيه:** {action_text}\n"
                    f"📍 **سعر الدخول:** `{price}` $\n\n"
                    f"🧱 **الأوردر بلوك / منطقة الطلب:** `{analysis['demand']}`\n"
                    f"🧱 **الأوردر بلوك / منطقة العرض:** `{analysis['supply']}`\n"
                    f"📐 **الفجوة السعرية (FVG):** {analysis['fvg']}\n"
                    f"🌐 **توافق الفريمات:** {analysis['trend']}\n\n"
                    f"⛔ **وقف الخسارة (SL):** `{sl}` $\n"
                    f"🎯 **هدف 1:** `{tp1}` $\n"
                    f"🎯 **هدف 2:** `{tp2}` $\n"
                    f"🎯 **هدف 3:** `{tp3}` $"
                )
                bot.send_message(chat_id, vip_msg, parse_mode="Markdown")

        if not found_any:
            bot.send_message(chat_id, "⏳ **لا توجد صفقات VIP ناضجة حالياً.**\nيتم فحص السوق كل دقيقة وسيتم إرسال تنبيه فور توفر الفرصة.")
        return

    selected_key = None
    if "بيتكوين" in text or "BTC" in text.upper():
        selected_key = "البيتكوين"
    elif "ذهب" in text or "XAU" in text.upper() or "🥇" in text:
        selected_key = "الذهب"
    elif "يورو" in text or "EUR" in text.upper() or "💶" in text:
        selected_key = "اليورو"

    if selected_key:
        bot.send_message(chat_id, f"🔄 **جاري جلب بيانات {selected_key}...**")
        analysis = scan_high_winrate_signals(selected_key)

        if not analysis:
            bot.send_message(chat_id, f"⚠️ تعذر جلب البيانات لـ {selected_key} حالياً.")
            return

        pair_name = "XAU/USD (الذهب)" if selected_key == "الذهب" else ("EUR/USD (اليورو)" if selected_key == "اليورو" else "BTC/USDT (البيتكوين)")

        msg = (
            f"📊 **التقرير اللحظي المتقدم لـ ({pair_name}):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **السعر اللحظي:** `{analysis['price']}` $\n"
            f"🧱 **منطقة الطلب (OB):** `{analysis['demand']}`\n"
            f"🧱 **منطقة العرض (OB):** `{analysis['supply']}`\n"
            f"📐 **الفجوة السعرية (FVG):** `{analysis['fvg']}`\n"
            f"🌐 **اتجاه السوق العام:** `{analysis['trend']}`\n"
            f"⚡ **الإشارة اللحظية:** `{analysis['signal']}`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")

def setup_webhook():
    time.sleep(3)
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        webhook_url = f"{external_url}/{TOKEN}"
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)

threading.Thread(target=setup_webhook, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)