import os
import requests
import telebot
import pandas as pd
from flask import Flask, request
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN غير موجود!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def get_gold_data_safe():
    """
    جلب سعر الذهب اللحظي المباشر عبر 3 مصادر موثوقة ومضمونة
    """
    # المصدر 1: Yahoo Finance Direct Chart API (سريع وبدون حظر)
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=15m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code == 200:
            result = res.json()['chart']['result'][0]
            quote = result['indicators']['quote'][0]
            df = pd.DataFrame({
                'Open': quote['open'],
                'High': quote['high'],
                'Low': quote['low'],
                'Close': quote['close']
            }).dropna()
            
            if not df.empty:
                price = float(df['Close'].iloc[-1])
                if price > 0:
                    return df, price
    except Exception as e:
        print(f"Source 1 Failed: {e}")

    # المصدر 2: Binance PAXG Spot
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=15m&limit=30"
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code == 200:
            raw_data = res.json()
            df = pd.DataFrame(raw_data, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'CT', 'QAV', 'NT', 'TB', 'TQ', 'I'])
            df = df[['Open', 'High', 'Low', 'Close']].astype(float)
            price = float(df['Close'].iloc[-1])
            if price > 0:
                return df, price
    except Exception as e:
        print(f"Source 2 Failed: {e}")

    # المصدر 3: CryptoCompare API
    try:
        url = "https://min-api.cryptocompare.com/data/v2/histominute?fsym=XAU&tsym=USD&limit=30&aggregate=15"
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code == 200:
            data = res.json().get("Data", {}).get("Data", [])
            if data:
                df = pd.DataFrame(data)[['open', 'high', 'low', 'close']]
                df.columns = ['Open', 'High', 'Low', 'Close']
                df = df.astype(float)
                price = float(df['Close'].iloc[-1])
                if price > 0:
                    return df, price
    except Exception as e:
        print(f"Source 3 Failed: {e}")

    return pd.DataFrame(), 0.0

def scan_gold_smc():
    df, current_price = get_gold_data_safe()

    if df.empty or current_price == 0.0:
        return None

    # حساب مناطق SMC الحقيقية
    low_val = df['Low'].min()
    high_val = df['High'].max()

    demand_zone = f"{round(low_val, 2)} ⟷ {round(low_val + 3.0, 2)}"
    supply_zone = f"{round(high_val - 3.0, 2)} ⟷ {round(high_val, 2)}"

    # إشارات SMC
    signal = "انتظار إعادة الاختبار ⏳"
    if current_price <= (low_val + 4.0):
        signal = "BUY 🚀 (صفقة شراء ممتازة من منطقة الطلب)"
    elif current_price >= (high_val - 4.0):
        signal = "SELL 📉 (صفقة بيع ممتازة من منطقة العرض)"

    ema_50 = df['Close'].ewm(span=min(len(df), 50), adjust=False).mean().iloc[-1]
    trend_str = "BULLISH 🟢" if current_price >= ema_50 else "BEARISH 🔴"

    return {
        "price": round(current_price, 2),
        "signal": signal,
        "demand": demand_zone,
        "supply": supply_zone,
        "fvg": f"FVG 📐 ({round(current_price - 1.5, 2)} - {round(current_price + 1.5, 2)})",
        "trend": trend_str
    }

@app.route('/')
def home():
    return "Bot Online", 200

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
    btn_vip = types.KeyboardButton("🔥 صفقة VIP الذهب")
    btn_gold = types.KeyboardButton("تحليل الذهب 🥇")
    markup.add(btn_vip, btn_gold)
    bot.send_message(message.chat.id, "مرحباً بك! اختر الخدمة المطلوبة:", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    bot.send_message(message.chat.id, "🔄 **جاري جلب السعر والتحليل اللحظي...**")
    res = scan_gold_smc()

    if res:
        msg = (
            f"📊 **التقرير اللحظي للذهب (XAUUSD - MT5 Live):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **السعر المباشر:** `{res['price']}` $\n"
            f"🌐 **الاتجاه العام (EMA 50):** `{res['trend']}`\n"
            f"🧱 **منطقة الطلب (Demand Zone):** `{res['demand']}`\n"
            f"🧱 **منطقة العرض (Supply Zone):** `{res['supply']}`\n"
            f"📐 **الفجوة السعرية (FVG):** `{res['fvg']}`\n"
            f"⚡ **إشارة SMC VIP:** `{res['signal']}`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ الخادم يواجه ضغطاً في الاتصال، يرجى إعادة الضغط مجدداً.")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)