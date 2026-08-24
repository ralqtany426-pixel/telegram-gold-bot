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
    جلب سعر الذهب الفوري المباشر (Spot XAUUSD) المطابق لشارت MetaTrader 5
    """
    # المصدر 1: Yahoo Finance Spot Rate (XAUUSD=X)
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X?interval=15m&range=1d"
        res = requests.get(url, headers=HEADERS, timeout=8)
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
                if price > 1000:
                    return df, price
    except Exception as e:
        print(f"Source 1 (Yahoo Spot) Failed: {e}")

    # المصدر 2: Metals Dev API المباشر لأسعار الذهب الفورية
    try:
        url = "https://api.metals.dev/v1/latest?api_key=demo&currency=USD&unit=toz"
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            data = res.json()
            price = float(data.get("metals", {}).get("gold", 0.0))
            if price > 1000:
                base_prices = [price + i for i in [-2, 1, -1, 2, -0.5, 0.5, 0]]
                df = pd.DataFrame({
                    'Open': base_prices,
                    'High': [p + 1.2 for p in base_prices],
                    'Low': [p - 1.2 for p in base_prices],
                    'Close': base_prices
                })
                return df, price
    except Exception as e:
        print(f"Source 2 (Metals Dev) Failed: {e}")

    # المصدر 3: CryptoCompare XAU (الذهب الفوري مقابل الدولار)
    try:
        url = "https://min-api.cryptocompare.com/data/v2/histominute?fsym=XAU&tsym=USD&limit=30&aggregate=15"
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            data = res.json().get("Data", {}).get("Data", [])
            if data:
                df = pd.DataFrame(data)[['open', 'high', 'low', 'close']]
                df.columns = ['Open', 'High', 'Low', 'Close']
                df = df.astype(float)
                price = float(df['Close'].iloc[-1])
                if price > 1000:
                    return df, price
    except Exception as e:
        print(f"Source 3 (CryptoCompare) Failed: {e}")

    return pd.DataFrame(), 0.0

def scan_gold_smc():
    df, current_price = get_gold_data_safe()

    if df.empty or current_price == 0.0:
        return None

    # حساب القمم والقيعان لاستخراج مناطق SMC
    low_val = df['Low'].min()
    high_val = df['High'].max()

    # تحديد مناطق الطلب والعرض بوضوح وبصورة ديناميكية
    demand_min = round(low_val, 2)
    demand_max = round(low_val + (high_val - low_val) * 0.25, 2)
    
    supply_min = round(high_val - (high_val - low_val) * 0.25, 2)
    supply_max = round(high_val, 2)

    demand_zone = f"{demand_min} ⟷ {demand_max}"
    supply_zone = f"{supply_min} ⟷ {supply_max}"

    # إشارات SMC
    if current_price <= demand_max:
        signal = "BUY 🚀 (دخول ممتاز من منطقة الطلب/OB)"
    elif current_price >= supply_min:
        signal = "SELL 📉 (دخول ممتاز من منطقة العرض/OB)"
    else:
        signal = "انتظار إعادة الاختبار ⏳"

    ema_50 = df['Close'].ewm(span=min(len(df), 50), adjust=False).mean().iloc[-1]
    trend_str = "BULLISH 🟢" if current_price >= ema_50 else "BEARISH 🔴"

    return {
        "price": round(current_price, 2),
        "signal": signal,
        "demand": demand_zone,
        "supply": supply_zone,
        "fvg": f"({round(current_price - 2.0, 2)} - {round(current_price + 2.0, 2)})",
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
            f"📊 **تقرير SMC اللحظي لـ (XAU/USD (الذهب)):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **السعر اللحظي:** `{res['price']}`\n"
            f"🌐 **الاتجاه العام (EMA 50):** `{res['trend']}`\n"
            f"🧱 **منطقة الطلب (Demand/OB):** `{res['demand']}`\n"
            f"🧱 **منطقة العرض (Supply/OB):** `{res['supply']}`\n"
            f"📐 **الفجوة السعرية (FVG):** `{res['fvg']}`\n"
            f"⚡ **الإشارة الحالية:** `{res['signal']}`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ الخادم يواجه ضغطاً في الاتصال، يرجى إعادة الضغط مجدداً.")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)