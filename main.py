import os
import time
import threading
import telebot
import pandas as pd
import yfinance as yf
from flask import Flask, request
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN غير موجود!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

user_chat_ids = set()

def fetch_candles(interval='15m', period='2d'):
    """
    جلب بيانات الذهب باستخدام آلية التبديل بين الرموز لضمان استقرار الفريمات اللحظية
    """
    symbols = ["GC=F", "GLD", "XAUUSD=X"]
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(period=period, interval=interval)
            if not df.empty and len(df) >= 10:
                df = df[['Open', 'High', 'Low', 'Close']].astype(float)
                return df
        except Exception as e:
            print(f"Error fetching {sym} ({interval}): {e}")
    return pd.DataFrame()

def scan_gold_smc():
    df_1h = fetch_candles(interval='1h', period='5d')
    df_15m = fetch_candles(interval='15m', period='2d')

    if df_15m.empty or len(df_15m) < 10:
        return None

    current_price = round(df_15m['Close'].iloc[-1], 2)

    trend_1h = "BULLISH 🟢"
    if not df_1h.empty:
        ema_1h = df_1h['Close'].ewm(span=min(len(df_1h), 50), adjust=False).mean().iloc[-1]
        trend_1h = "BULLISH 🟢" if current_price >= ema_1h else "BEARISH 🔴"

    highs = df_15m['High']
    lows = df_15m['Low']

    resistance = round(highs.max(), 2)
    support = round(lows.min(), 2)

    demand_ob = f"{support} ⟷ {round(support + 2.5, 2)}"
    supply_ob = f"{round(resistance - 2.5, 2)} ⟷ {resistance}"

    for i in range(len(df_15m)-4, 2, -1):
        if df_15m['Close'].iloc[i] < df_15m['Open'].iloc[i]:
            if df_15m['Close'].iloc[i+1] > df_15m['High'].iloc[i]:
                demand_ob = f"{round(df_15m['Low'].iloc[i], 2)} ⟷ {round(df_15m['High'].iloc[i], 2)}"
                break

    for i in range(len(df_15m)-4, 2, -1):
        if df_15m['Close'].iloc[i] > df_15m['Open'].iloc[i]:
            if df_15m['Close'].iloc[i+1] < df_15m['Low'].iloc[i]:
                supply_ob = f"{round(df_15m['Low'].iloc[i], 2)} ⟷ {round(df_15m['High'].iloc[i], 2)}"
                break

    fvg_str = "لا توجد فجوة نشطة ⚪"
    for i in range(len(df_15m)-1, 2, -1):
        if df_15m['High'].iloc[i-2] < df_15m['Low'].iloc[i]:
            fvg_min = round(df_15m['High'].iloc[i-2], 2)
            fvg_max = round(df_15m['Low'].iloc[i], 2)
            if current_price >= fvg_min and current_price <= fvg_max + 5.0:
                fvg_str = f"Bullish FVG 🟢 ({fvg_min} - {fvg_max})"
                break
        elif df_15m['Low'].iloc[i-2] > df_15m['High'].iloc[i]:
            fvg_min = round(df_15m['High'].iloc[i], 2)
            fvg_max = round(df_15m['Low'].iloc[i-2], 2)
            if current_price <= fvg_max and current_price >= fvg_min - 5.0:
                fvg_str = f"Bearish FVG 🔴 ({fvg_min} - {fvg_max})"
                break

    range_width = round(resistance - support, 2)
    signal = "انتظار إعادة الاختبار (No Signal) ⏳"

    try:
        d_val = float(demand_ob.split('⟷')[1].strip())
        s_val = float(supply_ob.split('⟷')[0].strip())
    except:
        d_val = support + 3.0
        s_val = resistance - 3.0

    if current_price <= d_val and "BULLISH" in trend_1h:
        signal = "BUY 🚀 (ارتداد من Demand OB + توافق اتجاه 1H)"
    elif current_price >= s_val and "BEARISH" in trend_1h:
        signal = "SELL 📉 (ارتداد من Supply OB + توافق اتجاه 1H)"
    elif current_price <= d_val:
        signal = "BUY Risk ⚠️ (دخول من الطلب ضد اتجاه 1H)"
    elif current_price >= s_val:
        signal = "SELL Risk ⚠️ (دخول من العرض ضد اتجاه 1H)"

    return {
        "price": current_price,
        "trend_1h": trend_1h,
        "demand_ob": demand_ob,
        "supply_ob": supply_ob,
        "fvg": fvg_str,
        "support": support,
        "resistance": resistance,
        "range_width": range_width,
        "signal": signal
    }

def auto_alert_loop():
    last_signal = ""
    while True:
        try:
            time.sleep(900)
            if not user_chat_ids:
                continue

            res = scan_gold_smc()
            if res and ("BUY" in res['signal'] or "SELL" in res['signal']):
                if res['signal'] != last_signal:
                    last_signal = res['signal']
                    alert_msg = (
                        f"🚨 **تنبيه تلقائي: فرصة دخول جديدة (SMC VIP)!**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📍 **السعر الحقيقي:** `{res['price']}` $\n"
                        f"⚡ **الإشارة:** `{res['signal']}`\n"
                        f"🧱 **الطلب (OB):** `{res['demand_ob']}`\n"
                        f"🧱 **العرض (OB):** `{res['supply_ob']}`\n"
                        f"⏳ **الاتجاه العام (1H):** `{res['trend_1h']}`"
                    )
                    for chat_id in user_chat_ids:
                        try:
                            bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                        except Exception as e:
                            print(f"Failed to send alert to {chat_id}: {e}")
        except Exception as e:
            print(f"Error in auto_alert_loop: {e}")

threading.Thread(target=auto_alert_loop, daemon=True).start()

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
    user_chat_ids.add(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_vip = types.KeyboardButton("🔥 صفقة VIP الذهب")
    btn_gold = types.KeyboardButton("تحليل الذهب 🥇")
    markup.add(btn_vip, btn_gold)
    bot.send_message(
        message.chat.id, 
        "مرحباً بك! تم تفعيل التنبيهات التلقائية لك كل 15 دقيقة 🔔\nاختر الخدمة المطلوبة:", 
        reply_markup=markup
    )

def process_analysis_in_background(chat_id):
    res = scan_gold_smc()
    if res:
        msg = (
            f"📊 **التقرير المتقدم لهيكل السوق (XAU/USD - SMC Pro):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **السعر اللحظي:** `{res['price']}` $\n"
            f"⏳ **اتجاه فريم الساعة (1H Trend):** `{res['trend_1h']}`\n"
            f"🛡️ **الدعم / المقاومة:** `{res['support']}` | `{res['resistance']}`\n"
            f"🧱 **منطقة الطلب (Demand OB):** `{res['demand_ob']}`\n"
            f"🧱 **منطقة العرض (Supply OB):** `{res['supply_ob']}`\n"
            f"📐 **الفجوة السعرية (FVG):** `{res['fvg']}`\n"
            f"📏 **اتساع نطاق الحركة (Range):** `{res['range_width']}` $\n"
            f"⚡ **إشارة SMC التأكيدية:** `{res['signal']}`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "⚠️ يتعذر جلب البيانات السعرية حالياً، يرجى المحاولة بعد قليل.")

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    user_chat_ids.add(message.chat.id)
    bot.send_message(message.chat.id, "🔄 **جاري تحليل هيكل السوق (Multi-Timeframe SMC)...**")
    threading.Thread(target=process_analysis_in_background, args=(message.chat.id,), daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)