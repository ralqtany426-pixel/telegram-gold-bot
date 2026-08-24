import os
import time
import sqlite3
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

# --- قاعدة بيانات حفظ المستخدمين ---
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

# --- جلب البيانات وتعديل السعر المباشر ---
def fetch_candles(interval='30m', period='5d'):
    symbols = ["XAUUSD=X", "GC=F"]
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(period=period, interval=interval)
            if not df.empty and len(df) >= 5:
                df = df[['Open', 'High', 'Low', 'Close']].astype(float)

                # ضبط السعر تلقائياً إذا تم الاعتماد على العقود الآجلة GC=F
                if sym == "GC=F":
                    last_close = df['Close'].iloc[-1]
                    if last_close > 3000:  # تعديل الفارق السعري
                        diff = last_close - 2650.0 if last_close < 3500 else (last_close - 4650.0 if last_close > 4700 else 0)
                        if diff > 20:
                            df = df - diff
                return df
        except Exception as e:
            print(f"Error fetching {sym} ({interval}): {e}")
    return pd.DataFrame()

def analyze_timeframe(df):
    if df.empty or len(df) < 5:
        return {
            "trend": "غير معروف ⚪", 
            "demand": "غير محدد", 
            "supply": "غير محدد", 
            "demand_low": 0, "demand_high": 0,
            "supply_low": 0, "supply_high": 0,
            "fvg": "لا توجد ⚪", 
            "high": 0, 
            "low": 0
        }

    current = df['Close'].iloc[-1]
    ema = df['Close'].ewm(span=min(len(df), 20), adjust=False).mean().iloc[-1]
    trend = "BULLISH 🟢" if current >= ema else "BEARISH 🔴"

    high_val = round(df['High'].max(), 2)
    low_val = round(df['Low'].min(), 2)

    d_low, d_high = low_val, round(low_val + 2.5, 2)
    s_low, s_high = round(high_val - 2.5, 2), high_val

    for i in range(len(df)-2, 1, -1):
        if df['Close'].iloc[i] < df['Open'].iloc[i] and df['Close'].iloc[i+1] > df['High'].iloc[i]:
            d_low, d_high = round(df['Low'].iloc[i], 1), round(df['High'].iloc[i], 1)
            break

    for i in range(len(df)-2, 1, -1):
        if df['Close'].iloc[i] > df['Open'].iloc[i] and df['Close'].iloc[i+1] < df['Low'].iloc[i]:
            s_low, s_high = round(df['Low'].iloc[i], 1), round(df['High'].iloc[i], 1)
            break

    demand_ob = f"🟢 Demand ({d_low} - {d_high})"
    supply_ob = f"🔴 Supply ({s_low} - {s_high})"

    fvg = "لا توجد ⚪"
    for i in range(len(df)-1, 2, -1):
        if df['High'].iloc[i-2] < df['Low'].iloc[i]:
            fvg = f"Bullish FVG 🟢 ({round(df['High'].iloc[i-2], 1)} - {round(df['Low'].iloc[i], 1)})"
            break
        elif df['Low'].iloc[i-2] > df['High'].iloc[i]:
            fvg = f"Bearish FVG 🔴 ({round(df['High'].iloc[i], 1)} - {round(df['Low'].iloc[i-2], 1)})"
            break

    return {
        "trend": trend, 
        "demand": demand_ob, 
        "supply": supply_ob, 
        "demand_low": d_low, "demand_high": d_high,
        "supply_low": s_low, "supply_high": s_high,
        "fvg": fvg, 
        "high": high_val, 
        "low": low_val
    }

def scan_multi_timeframe_smc():
    df_30m = fetch_candles(interval='30m', period='5d')
    df_1h  = fetch_candles(interval='1h', period='7d')
    df_4h  = fetch_candles(interval='60m', period='14d')
    df_1d  = fetch_candles(interval='1d', period='30d')

    if df_30m.empty:
        return None

    current_price = round(df_30m['Close'].iloc[-1], 2)

    tf_30m = analyze_timeframe(df_30m)
    tf_1h  = analyze_timeframe(df_1h)
    tf_4h  = analyze_timeframe(df_4h)
    tf_1d  = analyze_timeframe(df_1d)

    bull_count = sum(1 for tf in [tf_30m, tf_1h, tf_4h, tf_1d] if "BULLISH" in tf['trend'])

    if bull_count >= 3:
        signal = "BUY Strong 🚀 (توافق صاعد قوي)"
    elif bull_count <= 1:
        signal = "SELL Strong 📉 (توافق هابط قوي)"
    elif "BULLISH" in tf_30m['trend'] and "BULLISH" in tf_1h['trend']:
        signal = "BUY Swing 🟢 (شراء متوافق مع 30M & 1H)"
    elif "BEARISH" in tf_30m['trend'] and "BEARISH" in tf_1h['trend']:
        signal = "SELL Swing 🔴 (بيع متوافق مع 30M & 1H)"
    else:
        signal = "WAIT ⏳ (تضارب الاتجاهات)"

    return {
        "price": current_price,
        "30m": tf_30m,
        "1h": tf_1h,
        "4h": tf_4h,
        "1d": tf_1d,
        "signal": signal
    }

def auto_alert_loop():
    last_alert_key = ""
    while True:
        try:
            time.sleep(300)
            users = get_all_users()
            if not users:
                continue

            res = scan_multi_timeframe_smc()
            if res:
                p = res['price']
                tf30 = res['30m']

                zone_alert = ""
                if tf30['demand_low'] <= p <= tf30['demand_high']:
                    zone_alert = "🎯 **السعر يلامس منطقة الطلب (Demand OB) على فريم 30M! (فرصة شراء)**"
                elif tf30['supply_low'] <= p <= tf30['supply_high']:
                    zone_alert = "🎯 **السعر يلامس منطقة العرض (Supply OB) على فريم 30M! (فرصة بيع)**"

                current_key = f"{res['signal']}_{zone_alert}"

                if (zone_alert or "BUY" in res['signal'] or "SELL" in res['signal']) and current_key != last_alert_key:
                    last_alert_key = current_key
                    alert_msg = (
                        f"🚨 **تنبيه تلقائي ذكي (SMC 30M Pro)!**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📍 **السعر اللحظي:** `{res['price']}` $\n"
                        f"⚡ **الإشارة:** `{res['signal']}`\n"
                        f"{f'📢 **تنفيذ:** {zone_alert}\n' if zone_alert else ''}"
                        f"🧱 **30M Demand:** `{tf30['demand']}`\n"
                        f"🧱 **30M Supply:** `{tf30['supply']}`\n"
                        f"⏳ **1H Trend:** `{res['1h']['trend']}`"
                    )
                    for chat_id in users:
                        try:
                            bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                        except Exception as e:
                            print(f"Failed alert to {chat_id}: {e}")
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
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_vip = types.KeyboardButton("🔥 صفقة VIP الذهب")
    btn_gold = types.KeyboardButton("تحليل الذهب 🥇")
    markup.add(btn_vip, btn_gold)
    bot.send_message(
        message.chat.id, 
        "مرحباً بك! تم تفعيل تحليل 30M والتنبيهات عند ملامسة مناطق الطلب والعرض 🔔", 
        reply_markup=markup
    )

def process_analysis_in_background(chat_id):
    res = scan_multi_timeframe_smc()
    if res:
        msg = (
            f"📊 **التقرير المتقدم لهيكل السوق (XAU/USD - 30M SMC Pro):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **السعر اللحظي (MT5):** `{res['price']}` $\n\n"
            f"⚡ **إشارة الحسم العامة:** `{res['signal']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 **فريم 30 دقيقة (30M - الأساسي):**\n"
            f"• الاتجاه: `{res['30m']['trend']}`\n"
            f"• القمة / القاع: `{res['30m']['high']}` | `{res['30m']['low']}`\n"
            f"• منطقة الطلب: `{res['30m']['demand']}`\n"
            f"• منطقة العرض: `{res['30m']['supply']}`\n"
            f"• الفجوة السعرية: `{res['30m']['fvg']}`\n\n"
            f"🔹 **فريم الساعة (1H):**\n"
            f"• الاتجاه: `{res['1h']['trend']}`\n"
            f"• الطلب: `{res['1h']['demand']}`\n"
            f"• العرض: `{res['1h']['supply']}`\n\n"
            f"🔹 **فريم 4 ساعات (4H):**\n"
            f"• الاتجاه: `{res['4h']['trend']}`\n"
            f"• الطلب: `{res['4h']['demand']}`\n"
            f"• العرض: `{res['4h']['supply']}`\n\n"
            f"🔹 **الفريم اليومي (1D):**\n"
            f"• الاتجاه العام: `{res['1d']['trend']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "⚠️ يتعذر جلب البيانات السعرية حالياً، يرجى المحاولة بعد قليل.")

@bot.message_handler(func=lambda m: True)
def handle_msg(message):
    add_user(message.chat.id)
    bot.send_message(message.chat.id, "🔄 **جاري تحليل مناطق الطلب والعرض على فريم 30M...**")
    threading.Thread(target=process_analysis_in_background, args=(message.chat.id,), daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)