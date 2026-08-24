import os
import sqlite3
import requests
import telebot
import threading
import time
import pandas as pd
from flask import Flask, request
from telebot import types, apihelper

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

SYMBOLS = {"البيتكوين": "BTCUSDT", "الذهب": "XAUUSD"}

# استخدام مصادر بيانات مستقرة ومباشرة لا تحظر السيرفرات
def fetch_klines(symbol_key, interval="15min"):
    try:
        if symbol_key == "البيتكوين":
            bin_tf = {"15min": "15m", "1hour": "1h", "4hour": "4h", "1day": "1d"}.get(interval, "15m")
            url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={bin_tf}&limit=50"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                df = pd.DataFrame(res.json(), columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'CT', 'QAV', 'NT', 'TB', 'TQ', 'I'])
                df = df[['Open', 'High', 'Low', 'Close']].astype(float)
                return df.reset_index(drop=True)

        if symbol_key == "الذهب":
            # جلب أسعار الذهب الفورية المباشرة الموثوقة من CoinGecko / Gold API المباشر
            interval_sec = "900" if interval == "15min" else ("3600" if interval == "1hour" else "14400")
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=15m&range=1d"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                result = res.json()['chart']['result'][0]
                quote = result['indicators']['quote'][0]
                df = pd.DataFrame({
                    'Open': quote['open'],
                    'High': quote['high'],
                    'Low': quote['low'],
                    'Close': quote['close']
                }).dropna().reset_index(drop=True)
                if not df.empty:
                    return df
    except Exception as e:
        print(f"Fetch Error ({symbol_key}): {e}")

    # مصدر احتياطي سريع للذهب في حال تعثر المصدر الأول
    if symbol_key == "الذهب":
        try:
            url = "https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=15m&limit=50"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                df = pd.DataFrame(res.json(), columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'CT', 'QAV', 'NT', 'TB', 'TQ', 'I'])
                df = df[['Open', 'High', 'Low', 'Close']].astype(float)
                return df.reset_index(drop=True)
        except Exception as e:
            print(f"Backup Fetch Error: {e}")

    return pd.DataFrame()

def calculate_ema(df, period=50):
    if df.empty or len(df) < period:
        # حساب EMA متكيف للبيانات القليلة
        p = len(df) if len(df) > 5 else 5
        return round(float(df['Close'].ewm(span=p, adjust=False).mean().iloc[-1]), 2)
    return round(float(df['Close'].ewm(span=period, adjust=False).mean().iloc[-1]), 2)

def check_bos_and_ob(df):
    if df.empty or len(df) < 10:
        return None, None

    bullish_ob, bearish_ob = None, None
    try:
        current_close = df['Close'].iloc[-1]
        lookback = min(len(df) - 2, 15)
        previous_high = df['High'].iloc[-lookback:-2].max()
        previous_low = df['Low'].iloc[-lookback:-2].min()

        # Bullish BOS
        if current_close > previous_high:
            for i in range(len(df) - 2, max(len(df) - 10, 0), -1):
                if df['Close'].iloc[i] < df['Open'].iloc[i]:
                    bullish_ob = (round(df['Low'].iloc[i], 2), round(df['High'].iloc[i], 2))
                    break

        # Bearish BOS
        if current_close < previous_low:
            for i in range(len(df) - 2, max(len(df) - 10, 0), -1):
                if df['Close'].iloc[i] > df['Open'].iloc[i]:
                    bearish_ob = (round(df['Low'].iloc[i], 2), round(df['High'].iloc[i], 2))
                    break
    except Exception as e:
        print(f"BOS Error: {e}")

    return bullish_ob, bearish_ob

def scan_smc_advanced(symbol_key):
    df_15m = fetch_klines(symbol_key, "15min")

    if df_15m.empty:
        return None

    current_price = round(float(df_15m['Close'].iloc[-1]), 2)

    # 1. EMA
    ema_15m = calculate_ema(df_15m, 50)
    ma_status = "BULLISH 🟢" if (ema_15m and current_price > ema_15m) else "BEARISH 🔴"

    # 2. FVG
    fvg_status = "غير متوفر"
    for i in range(len(df_15m) - 1, 2, -1):
        if df_15m['Low'].iloc[i] > df_15m['High'].iloc[i-2]:
            fvg_status = f"Bullish FVG 🟢 ({round(df_15m['High'].iloc[i-2], 2)} - {round(df_15m['Low'].iloc[i], 2)})"
            break
        elif df_15m['High'].iloc[i] < df_15m['Low'].iloc[i-2]:
            fvg_status = f"Bearish FVG 🔴 ({round(df_15m['High'].iloc[i], 2)} - {round(df_15m['Low'].iloc[i-2], 2)})"
            break

    # 3. Order Block مع BOS
    bull_ob, bear_ob = check_bos_and_ob(df_15m)
    demand_str = f"{bull_ob[0]} ⟷ {bull_ob[1]}" if bull_ob else "غير متوفر (لم يحدث BOS صاعد)"
    supply_str = f"{bear_ob[0]} ⟷ {bear_ob[1]}" if bear_ob else "غير متوفر (لم يحدث BOS هابط)"

    # 4. الإشارة
    signal = "NONE"
    buffer = 1.0 if symbol_key == "الذهب" else 20.0

    if bull_ob and (bull_ob[0] - buffer) <= current_price <= (bull_ob[1] + buffer):
        signal = "BUY 🚀"
    elif bear_ob and (bear_ob[0] - buffer) <= current_price <= (bear_ob[1] + buffer):
        signal = "SELL 📉"

    return {
        "price": current_price,
        "signal": signal,
        "demand": demand_str,
        "supply": supply_str,
        "fvg": fvg_status,
        "ma_status": ma_status,
        "trend": "STRONG BULLISH 🚀" if current_price > ema_15m else "BEARISH 📉"
    }

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
def start_cmd(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_vip = types.KeyboardButton("🔥 صفقات VIP (SMC / OB / S&D)")
    btn_gold = types.KeyboardButton("الذهب 🥇")
    btn_btc = types.KeyboardButton("البيتكوين ₿")
    markup.add(btn_vip)
    markup.add(btn_gold, btn_btc)
    bot.send_message(message.chat.id, "مرحباً بك! اختر الزوج لبدء التحليل:", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    text = message.text.strip() if message.text else ""
    key = "الذهب" if ("ذهب" in text or "XAU" in text) else ("البيتكوين" if ("بيتكوين" in text or "BTC" in text) else None)

    if key:
        bot.send_message(message.chat.id, f"🔄 **جاري التحليل الفني الشامل لـ {key}...**")
        try:
            res = scan_smc_advanced(key)
            if res:
                msg = (
                    f"📊 **التقرير اللحظي الشامل ({key}):**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📍 **السعر اللحظي:** `{res['price']}` $\n"
                    f"📈 **مؤشر المتوسط المتحرك (EMA):** `{res['ma_status']}`\n"
                    f"🧱 **منطقة الطلب (OB مع BOS):** `{res['demand']}`\n"
                    f"🧱 **منطقة العرض (OB مع BOS):** `{res['supply']}`\n"
                    f"📐 **الفجوة السعرية (SMC FVG):** `{res['fvg']}`\n"
                    f"🌐 **الاتجاه العام:** `{res['trend']}`\n"
                    f"⚡ **الإشارة اللحظية:** `{res['signal']}`"
                )
                bot.send_message(message.chat.id, msg, parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "⚠️ تعذر جلب البيانات حالياً، يرجى المحاولة بعد قليل.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ حدث خطأ أثناء التحليل: {e}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)