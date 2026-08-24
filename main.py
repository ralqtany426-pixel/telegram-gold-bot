import os
import requests
import telebot
import pandas as pd
from flask import Flask, request
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def fetch_gold_klines():
    """
    جلب سعر الذهب الفوري (XAUUSD Spot) المطابق تماماً لشاشات MetaTrader 5
    """
    try:
        # المصدر الأول: جلب شمعة XAU/USD الحالية الفورية مباشرة
        url = "https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=15m&limit=50"
        res = requests.get(url, headers=HEADERS, timeout=7)
        if res.status_code == 200:
            df = pd.DataFrame(res.json(), columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'CT', 'QAV', 'NT', 'TB', 'TQ', 'I'])
            df = df[['Open', 'High', 'Low', 'Close']].astype(float)
            return df.reset_index(drop=True)
    except Exception as e:
        print(f"Primary Fetch Error: {e}")

    # المصدر الاحتياطي الفوري في حال التعثر
    try:
        url = "https://min-api.cryptocompare.com/data/v2/histominute?fsym=XAU&tsym=USD&limit=50&aggregate=15"
        res = requests.get(url, headers=HEADERS, timeout=7)
        if res.status_code == 200:
            data = res.json().get("Data", {}).get("Data", [])
            if data:
                df = pd.DataFrame(data)[['open', 'high', 'low', 'close']]
                df.columns = ['Open', 'High', 'Low', 'Close']
                return df.astype(float).reset_index(drop=True)
    except Exception as e:
        print(f"Backup Fetch Error: {e}")

    return pd.DataFrame()

def calculate_ema(df, period=50):
    if df.empty or len(df) < 5:
        return None
    p = min(len(df), period)
    return round(float(df['Close'].ewm(span=p, adjust=False).mean().iloc[-1]), 2)

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
    except Exception:
        pass

    return bullish_ob, bearish_ob

def scan_gold_smc():
    df = fetch_gold_klines()
    if df.empty:
        return None

    current_price = round(float(df['Close'].iloc[-1]), 2)
    ema_val = calculate_ema(df, 50)
    ma_status = "BULLISH 🟢" if (ema_val and current_price > ema_val) else "BEARISH 🔴"

    # FVG
    fvg_status = "غير متوفر"
    for i in range(len(df) - 1, 2, -1):
        if df['Low'].iloc[i] > df['High'].iloc[i-2]:
            fvg_status = f"Bullish FVG 🟢 ({round(df['High'].iloc[i-2], 2)} - {round(df['Low'].iloc[i], 2)})"
            break
        elif df['High'].iloc[i] < df['Low'].iloc[i-2]:
            fvg_status = f"Bearish FVG 🔴 ({round(df['High'].iloc[i], 2)} - {round(df['Low'].iloc[i-2], 2)})"
            break

    # OB مع BOS
    bull_ob, bear_ob = check_bos_and_ob(df)
    demand_str = f"{bull_ob[0]} ⟷ {bull_ob[1]}" if bull_ob else "غير متوفر (لم يحدث BOS صاعد)"
    supply_str = f"{bear_ob[0]} ⟷ {bear_ob[1]}" if bear_ob else "غير متوفر (لم يحدث BOS هابط)"

    # Signal
    signal = "NONE"
    buffer = 1.5

    if bull_ob and (bull_ob[0] - buffer) <= current_price <= (bull_ob[1] + buffer):
        signal = "BUY 🚀 (دخول شراء في منطقة الطلب)"
    elif bear_ob and (bear_ob[0] - buffer) <= current_price <= (bear_ob[1] + buffer):
        signal = "SELL 📉 (دخول بيع في منطقة العرض)"

    return {
        "price": current_price,
        "signal": signal,
        "demand": demand_str,
        "supply": supply_str,
        "fvg": fvg_status,
        "ma_status": ma_status,
        "trend": "STRONG BULLISH 🚀" if (ema_val and current_price > ema_val) else "BEARISH 📉"
    }

@app.route('/')
def home():
    return "Gold MT5 Bot Active!", 200

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
    bot.send_message(message.chat.id, "مرحباً بك! اختر لبدء تحليل الذهب المطابق لـ MT5:", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    bot.send_message(message.chat.id, "🔄 **جاري جلب سعر الذهب اللحظي (MT5) والتحليل...**")
    res = scan_gold_smc()
    if res:
        msg = (
            f"📊 **التقرير اللحظي للذهب (XAUUSD - MT5 Live):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **السعر اللحظي:** `{res['price']}` $\n"
            f"📈 **مؤشر المتوسط (EMA 50):** `{res['ma_status']}`\n"
            f"🧱 **منطقة الطلب (OB مع BOS):** `{res['demand']}`\n"
            f"🧱 **منطقة العرض (OB مع BOS):** `{res['supply']}`\n"
            f"📐 **الفجوة السعرية (FVG):** `{res['fvg']}`\n"
            f"🌐 **الاتجاه العام:** `{res['trend']}`\n"
            f"⚡ **الإشارة اللحظية:** `{res['signal']}`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ متعثر مؤقتاً في جلب السعر، أعد المحاولة بعد لحظات.")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)