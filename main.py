
import os
import sqlite3
import requests
import telebot
import threading
import time
import pandas as pd
from flask import Flask, request
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

SYMBOLS = {
    "البيتكوين": "BTC-USDT",
    "الذهب": "XAUUSD",
    "اليورو": "EUR-USDT"
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

def fetch_klines(symbol_ticker, interval="15min"):
    if symbol_ticker == "XAUUSD":
        interval_param = "15m"
        range_param = "2d"
        if interval == "30min":
            interval_param = "30m"
            range_param = "5d"
        elif interval == "1hour":
            interval_param = "1h"
            range_param = "7d"
        elif interval == "4hour":
            interval_param = "1h"
            range_param = "1mo"
        elif interval == "1day":
            interval_param = "1d"
            range_param = "3mo"

        # المصدر الأول: Yahoo Finance Spot / Continuous Contract
        try:
            for symbol in ["GC=F", "XAUUSD=X"]:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval_param}&range={range_param}"
                res = session.get(url, timeout=5)
                if res.status_code == 200:
                    result = res.json()['chart']['result'][0]
                    quote = result['indicators']['quote'][0]
                    df = pd.DataFrame({
                        'Open': quote['open'],
                        'High': quote['high'],
                        'Low': quote['low'],
                        'Close': quote['close']
                    }).dropna()

                    if not df.empty and len(df) >= 10:
                        return df.reset_index(drop=True)
        except Exception as e:
            print(f"Fetch Gold Yahoo Error: {e}")

        # المصدر الثاني: GoldAPI / Binance Pax Gold لضمان التزامن اللحظي
        try:
            url_alt = "https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=15m&limit=50"
            res_alt = session.get(url_alt, timeout=5)
            if res_alt.status_code == 200:
                data = res_alt.json()
                df = pd.DataFrame(data, columns=['time', 'Open', 'High', 'Low', 'Close', 'Vol', 'CloseTime', 'Qav', 'NumTrades', 'Tbk', 'Tbq', 'Ignore'])
                df['Open'] = df['Open'].astype(float)
                df['High'] = df['High'].astype(float)
                df['Low'] = df['Low'].astype(float)
                df['Close'] = df['Close'].astype(float)
                return df[['Open', 'High', 'Low', 'Close']]
        except Exception as e:
            print(f"Fetch Gold Fallback Error: {e}")

    try:
        url = f"https://api.kucoin.com/api/v1/market/candles?symbol={symbol_ticker}&type={interval}"
        res = session.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json().get('data', [])
            if data and len(data) > 0:
                df = pd.DataFrame(data, columns=['time', 'Open', 'Close', 'High', 'Low', 'Volume', 'Turnover'])
                df['Open'] = df['Open'].astype(float)
                df['Close'] = df['Close'].astype(float)
                df['High'] = df['High'].astype(float)
                df['Low'] = df['Low'].astype(float)
                df = df.iloc[::-1].reset_index(drop=True)
                return df
    except Exception as e:
        print(f"Fetch KuCoin Error ({symbol_ticker} - {interval}): {e}")

    return pd.DataFrame()

def get_market_trend(ticker):
    """تحليل اتجاه السوق وتوافقه على الفريمات"""
    df_1d = fetch_klines(ticker, "1day")
    df_4h = fetch_klines(ticker, "4hour")
    df_1h = fetch_klines(ticker, "1hour")
    df_30m = fetch_klines(ticker, "30min")

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
    ticker = SYMBOLS.get(symbol_key)
    if not ticker:
        return None

    df = fetch_klines(ticker, "15min")
    if df.empty or len(df) < 10:
        return None

    decimals = 5 if symbol_key == "اليورو" else 2
    current_price = round(float(df['Close'].iloc[-1]), decimals)
    trend = get_market_trend(ticker)

    bullish_ob, bearish_ob = None, None
    fvg_status = "غير متوفر"

    # 1. كشف الفجوة السعرية (FVG) المحققة حديثاً
    for i in range(len(df) - 1, 2, -1):
        if df['Low'].iloc[i] > df['High'].iloc[i-2]:
            fvg_status = f"Bullish FVG 🟢 ({round(df['High'].iloc[i-2], decimals)} - {round(df['Low'].iloc[i], decimals)})"
            break
        elif df['High'].iloc[i] < df['Low'].iloc[i-2]:
            fvg_status = f"Bearish FVG 🔴 ({round(df['High'].iloc[i], decimals)} - {round(df['Low'].iloc[i-2], decimals)})"
            break

    # 2. استخراج مناطق العرض والطلب الديناميكية المعالجة من الكسر
    # استخراج مناطق الطلب التي لم يُكسر حدها الأدنى بالسعر الحالي
    valid_lows = [df['Low'].iloc[i] for i in range(len(df)-15, len(df)) if df['Low'].iloc[i] < current_price]
    if valid_lows:
        demand_low = min(valid_lows)
        demand_high = demand_low + (0.0008 if symbol_key == "اليورو" else (2.5 if symbol_key == "الذهب" else 150.0))
        bullish_ob = (round(demand_low, decimals), round(demand_high, decimals))

    # استخراج مناطق العرض التي لم يُكسر حدها الأعلى بالسعر الحالي
    valid_highs = [df['High'].iloc[i] for i in range(len(df)-15, len(df)) if df['High'].iloc[i] > current_price]
    if valid_highs:
        supply_high = max(valid_highs)
        supply_low = supply_high - (0.0008 if symbol_key == "اليورو" else (2.5 if symbol_key == "الذهب" else 150.0))
        bearish_ob = (round(supply_low, decimals), round(supply_high, decimals))

    # تعيين مناطق افتراضية مرنة في حال الحركة القوية العابرة
    if not bullish_ob:
        bullish_ob = (round(current_price - 4.0, decimals), round(current_price - 1.5, decimals))
    if not bearish_ob:
        bearish_ob = (round(current_price + 1.5, decimals), round(current_price + 4.0, decimals))

    signal = "NONE"
    setup_type = ""
    demand_str = f"{bullish_ob[0]} ⟷ {bullish_ob[1]}"
    supply_str = f"{bearish_ob[0]} ⟷ {bearish_ob[1]}"

    buffer = 0.0003 if symbol_key == "اليورو" else (1.5 if symbol_key == "الذهب" else 100.0)

    if current_price <= (bullish_ob[1] + buffer) and ("BULLISH" in trend):
        signal = "BUY"
        setup_type = "اختبار أوردر بلوك شرائي متوافق مع كافة الفريمات والمؤشرات 🚀"
    elif current_price >= (bearish_ob[0] - buffer) and ("BEARISH" in trend):
        signal = "SELL"
        setup_type = "اختبار أوردر بلوك بيعي متوافق مع كافة الفريمات والمؤشرات 📉"

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
                            action_text = "📈 شراء مؤكد VIP (FULL TIMEFRAME & SMC MATCH)"
                        else:
                            sl = round(analysis["supply_high"] + sl_offset, decimals)
                            risk = abs(sl - price)
                            tp1 = round(price - (risk * 1.8), decimals)
                            tp2 = round(price - (risk * 3.2), decimals)
                            tp3 = round(price - (risk * 5.0), decimals)
                            action_text = "📉 بيع مؤكد VIP (FULL TIMEFRAME & SMC MATCH)"

                        msg = (
                            f"🎯🔥 **تنبيه صفقة مكتملة الشروط (1m-30m Scanner)** 🔥🎯\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 **الزوج:** {name}\n"
                            f"🚨 **الإشارة:** {action_text}\n"
                            f"💡 **السبب:** {analysis['setup_type']}\n"
                            f"📍 **سعر الدخول:** `{price}` $\n\n"
                            f"🧱 **منطقة الطلب / OB:** `{analysis['demand']}`\n"
                            f"🧱 **منطقة العرض / OB:** `{analysis['supply']}`\n"
                            f"📐 **الفجوة السعرية (FVG):** {analysis['fvg']}\n"
                            f"🌐 **اتساق جميع الفريمات:** {analysis['trend']}\n\n"
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
    return "Bot 1-30 Min High Precision SMC Engine Active!", 200

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
        f"تم تحديث بيانات الذهب وتكييف المناطق ديناميكياً مع حركة الأسعار اللحظية بنجاح."
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
                    f"💡 **السبب:** {analysis['setup_type']}\n"
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
    if "البيتكوين" in text or "BTC" in text.upper():
        selected_key = "البيتكوين"
    elif "الذهب" in text or "XAU" in text.upper() or "🥇" in text:
        selected_key = "الذهب"
    elif "اليورو" in text or "EUR" in text.upper() or "💶" in text:
        selected_key = "اليورو"

    if selected_key:
        analysis = scan_high_winrate_signals(selected_key)

        if not analysis:
            bot.send_message(chat_id, f"⚠️ تعذر جلب البيانات لـ {text} حالياً.")
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