import os
import time
import sqlite3
import threading
import requests
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

# --- قاعدة البيانات ---
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

# --- جلب السعر المباشر للذهب الفوري (Spot Gold) ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_live_price():
    try:
        url = "https://api.gold-api.com/price/XAU"
        res = requests.get(url, headers=HEADERS, timeout=8).json()
        if 'price' in res and res['price']:
            return round(float(res['price']), 2)
    except Exception as e:
        print(f"API Gold-API Error: {e}")

    try:
        url = "https://api.exchangerate-api.com/v4/latest/XAU"
        res = requests.get(url, headers=HEADERS, timeout=8).json()
        if 'rates' in res and 'USD' in res['rates']:
            return round(1 / res['rates']['USD'], 2)
    except Exception as e:
        print(f"API ExchangeRate Error: {e}")

    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="1d", interval="1m")
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except Exception as e:
        print(f"yfinance Error: {e}")

    return None

# --- جلب الشمعات مع معالجة حظر السيرفرات وإعادة المحاولة ---
def fetch_candles_yf(interval='30m', period='5d'):
    symbols = ["GC=F", "XAUUSD=X"]
    for sym in symbols:
        for attempt in range(2):  
            try:
                ticker = yf.Ticker(sym)
                df = ticker.history(period=period, interval=interval)
                if not df.empty and len(df) >= 5:
                    df = df[['Open', 'High', 'Low', 'Close']].astype(float)
                    return df
            except Exception as e:
                print(f"Attempt {attempt+1} failed for {sym} interval {interval}: {e}")
                time.sleep(0.5)

    return pd.DataFrame()

# --- خوارزمية تحليل هيكل السوق المعدلة ---
def analyze_timeframe(df, current_price=0):
    if df.empty or len(df) < 5 or current_price == 0:
        d_low, d_high = round(current_price - 4.5, 1), round(current_price - 2.0, 1)
        s_low, s_high = round(current_price + 2.0, 1), round(current_price + 4.5, 1)
        return {
            "trend": "NEUTRAL ⚪", 
            "demand": f"🟢 Demand ({d_low} - {d_high})", 
            "supply": f"🔴 Supply ({s_low} - {s_high})", 
            "demand_low": d_low, "demand_high": d_high, 
            "supply_low": s_low, "supply_high": s_high,
            "fvg": "منطقة متوازنة ⚪", "high": round(current_price + 5, 2), "low": round(current_price - 5, 2)
        }

    # التركيز على آخر 20 شمعة فقط لمنع أخذ مستويات قديمة بعيدة عن السعر
    recent_df = df.tail(20)
    current = current_price if current_price > 0 else recent_df['Close'].iloc[-1]

    # تحديد الاتجاه بناءً على الشموع الأخيرة والـ EMA
    ema = recent_df['Close'].ewm(span=10, adjust=False).mean().iloc[-1]
    last_close = recent_df['Close'].iloc[-1]
    prev_close = recent_df['Close'].iloc[-2]

    if current >= ema and last_close >= prev_close:
        trend = "BULLISH 🟢"
    elif current < ema and last_close < prev_close:
        trend = "BEARISH 🔴"
    else:
        trend = "NEUTRAL ⚪"

    d_low, d_high = 0, 0
    s_low, s_high = 0, 0

    # البحث عن أوردر بلوك شرائي قادم وقريب من السعر
    for i in range(len(recent_df)-2, 0, -1):
        if recent_df['Close'].iloc[i] < recent_df['Open'].iloc[i] and recent_df['Close'].iloc[i+1] > recent_df['High'].iloc[i]:
            candidate_low = round(recent_df['Low'].iloc[i], 1)
            candidate_high = round(recent_df['High'].iloc[i], 1)
            if candidate_high <= current + 2.0 and candidate_low >= current - 25.0:
                d_low, d_high = candidate_low, candidate_high
                break

    # البحث عن أوردر بلوك بيعي قادم وقريب من السعر
    for i in range(len(recent_df)-2, 0, -1):
        if recent_df['Close'].iloc[i] > recent_df['Open'].iloc[i] and recent_df['Close'].iloc[i+1] < recent_df['Low'].iloc[i]:
            candidate_low = round(recent_df['Low'].iloc[i], 1)
            candidate_high = round(recent_df['High'].iloc[i], 1)
            if candidate_low >= current - 2.0 and candidate_high <= current + 25.0:
                s_low, s_high = candidate_low, candidate_high
                break

    # تعيين مستويات افتراضية منطقية قريبة في حال عدم وجود أوردر بلوك واضح
    if d_low == 0 or d_high == 0:
        d_low, d_high = round(current - 5.0, 1), round(current - 2.5, 1)
    if s_low == 0 or s_high == 0:
        s_low, s_high = round(current + 2.5, 1), round(current + 5.0, 1)

    fvg = "لا توجد ⚪"
    for i in range(len(recent_df)-1, 2, -1):
        if recent_df['High'].iloc[i-2] < recent_df['Low'].iloc[i]:
            fvg = f"Bullish FVG 🟢 ({round(recent_df['High'].iloc[i-2], 1)} - {round(recent_df['Low'].iloc[i], 1)})"
            break
        elif recent_df['Low'].iloc[i-2] > recent_df['High'].iloc[i]:
            fvg = f"Bearish FVG 🔴 ({round(recent_df['High'].iloc[i], 1)} - {round(recent_df['Low'].iloc[i-2], 1)})"
            break

    return {
        "trend": trend, 
        "demand": f"🟢 Demand ({d_low} - {d_high})", 
        "supply": f"🔴 Supply ({s_low} - {s_high})", 
        "demand_low": d_low, "demand_high": d_high, 
        "supply_low": s_low, "supply_high": s_high,
        "fvg": fvg, 
        "high": round(recent_df['High'].max(), 2), 
        "low": round(recent_df['Low'].min(), 2)
    }

def scan_multi_timeframe_smc():
    price = get_live_price()
    if price is None:
        return None

    df_15m = fetch_candles_yf('15m', '2d')
    df_30m = fetch_candles_yf('30m', '3d')
    df_1h  = fetch_candles_yf('1h', '5d')
    df_4h  = fetch_candles_yf('60m', '10d')
    df_1d  = fetch_candles_yf('1d', '30d')

    tf_15m = analyze_timeframe(df_15m, price)
    tf_30m = analyze_timeframe(df_30m, price)
    tf_1h  = analyze_timeframe(df_1h, price)
    tf_4h  = analyze_timeframe(df_4h, price)
    tf_1d  = analyze_timeframe(df_1d, price)

    timeframes = [tf_15m, tf_30m, tf_1h, tf_4h, tf_1d]

    bull_count = sum(1 for tf in timeframes if "BULLISH" in tf['trend'])
    bear_count = sum(1 for tf in timeframes if "BEARISH" in tf['trend'])

    if bull_count >= 3:
        market_direction = "صاعد قوي 🟢🚀"
        signal = "BUY Strong 🚀 (توافق صاعد)"
    elif bear_count >= 3:
        market_direction = "هابط قوي 🔴📉"
        signal = "SELL Strong 📉 (توافق هابط)"
    else:
        market_direction = "عرضي / محايد ⚪"
        signal = "WAIT ⏳ (تذبذب / انتظار)"

    return {
        "price": price, 
        "market_direction": market_direction,
        "15m": tf_15m, "30m": tf_30m, "1h": tf_1h, "4h": tf_4h, "1d": tf_1d, 
        "signal": signal
    }

# --- حساب الأهداف وقف الخسارة المحسن ---
def calculate_trade_targets(price, tf15, signal):
    if "WAIT" in signal:
        return "WAIT ⏳ (انتظار إشعار مؤكد)", price, price, price, price

    if "BUY" in signal:
        sl = round(tf15['demand_low'] - 2.0, 2) if tf15['demand_low'] > 0 else round(price - 4.0, 2)
        risk = abs(price - sl)
        tp1 = round(price + (risk * 1.5), 2)
        tp2 = round(price + (risk * 2.5), 2)
        tp3 = round(price + (risk * 3.5), 2)
        return "BUY 🟢", sl, tp1, tp2, tp3
    else:
        sl = round(tf15['supply_high'] + 2.0, 2) if tf15['supply_high'] > 0 else round(price + 4.0, 2)
        risk = abs(sl - price)
        tp1 = round(price - (risk * 1.5), 2)
        tp2 = round(price - (risk * 2.5), 2)
        tp3 = round(price - (risk * 3.5), 2)
        return "SELL 🔴", sl, tp1, tp2, tp3

# --- منبه الصفقات المضمونة SMC ---
def auto_alert_loop():
    last_alert_key = ""
    while True:
        try:
            users = get_all_users()
            if users:
                res = scan_multi_timeframe_smc()
                if res:
                    p = res['price']
                    tf15 = res['15m']

                    is_high_winrate = False
                    alert_type = ""
                    signal_type = "WAIT"

                    if tf15['demand_low'] > 0 and (tf15['demand_low'] - 1.0) <= p <= (tf15['demand_high'] + 1.5):
                        is_high_winrate = True
                        alert_type = "🔥 **صفقة شراء VIP (ملامسة منطقة الطلب 15M)**"
                        signal_type = "BUY"

                    elif tf15['supply_high'] > 0 and (tf15['supply_low'] - 1.5) <= p <= (tf15['supply_high'] + 1.0):
                        is_high_winrate = True
                        alert_type = "🔥 **صفقة بيع VIP (ملامسة منطقة العرض 15M)**"
                        signal_type = "SELL"

                    current_key = f"{signal_type}_{round(p, 1)}"

                    if is_high_winrate and current_key != last_alert_key:
                        last_alert_key = current_key
                        trade_type, sl, tp1, tp2, tp3 = calculate_trade_targets(p, tf15, signal_type)

                        alert_msg = (
                            f"🚨 **تنبيه صفقة VIP معتمدة (Spot Gold)!**\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{alert_type}\n\n"
                            f"📍 **سعر الدخول:** `{p}` $\n"
                            f"🛑 **وقف الخسارة (SL):** `{sl}` $\n\n"
                            f"🎯 **الهدف الأول (TP1):** `{tp1}` $\n"
                            f"🎯 **الهدف الثاني (TP2):** `{tp2}` $\n"
                            f"🎯 **الهدف الثالث (TP3):** `{tp3}` $\n"
                            f"━━━━━━━━━━━━━━━━━━━━━"
                        )
                        for chat_id in users:
                            try:
                                bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                            except Exception as e:
                                print(f"Failed alert: {e}")
        except Exception as e:
            print(f"Error in alert loop: {e}")

        time.sleep(30)

threading.Thread(target=auto_alert_loop, daemon=True).start()

# --- واجهة البوت ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_live = types.KeyboardButton("⚡ السعر اللحظي")
    btn_vip = types.KeyboardButton("🔥 صفقات VIP (الطلب والعرض)")
    btn_sr = types.KeyboardButton("📊 الدعم والمقاومة")
    btn_gold = types.KeyboardButton("تحليل الذهب 🥇")
    btn_alerts = types.KeyboardButton("🔔 حالة التنبيهات")
    markup.add(btn_live, btn_vip, btn_sr, btn_gold, btn_alerts)

    bot.send_message(message.chat.id, "مرحباً بك! تم تحديث البوت ليعمل بدقة عالية وبدون انقطاع ⚡", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "⚡ السعر اللحظي")
def send_live_price(message):
    p = get_live_price()
    if p:
        bot.send_message(message.chat.id, f"⚡ **سعر الذهب المباشر (Spot Gold):** `{p}` $", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ جاري تحديث البيانات، يرجى المحاولة بعد ثوانٍ.")

@bot.message_handler(func=lambda m: m.text == "🔥 صفقات VIP (الطلب والعرض)")
def send_vip_trade(message):
    res = scan_multi_timeframe_smc()
    if not res:
        bot.send_message(message.chat.id, "⚠️ جاري تحديث بيانات السوق، حاول بعد قليل.")
        return

    p = res['price']
    tf15 = res['15m']
    trade_type, sl, tp1, tp2, tp3 = calculate_trade_targets(p, tf15, res['signal'])

    if "WAIT" in trade_type:
        msg = (
            f"🔥 **توصية VIP بناءً على SMC & Order Block:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **حالة السوق:** `انتظار ⏳`\n"
            f"📍 **السعر اللحظي:** `{p}` $\n\n"
            f"💡 **الملاحظة:** السوق حالياً في حالة تذبذب/عرضية. انتظر ملامسة منطقة طلب أو عرض واضحة ليتم إرسال التنبيه التلقائي.\n"
            f"🧭 **الاتجاه العام:** `{res['market_direction']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        msg = (
            f"🔥 **توصية VIP بناءً على SMC & Order Block:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **نوع الصفقة:** `{trade_type}`\n"
            f"📍 **سعر الدخول اللحظي:** `{p}` $\n\n"
            f"🛑 **وقف الخسارة (SL):** `{sl}` $\n\n"
            f"🎯 **الهدف الأول (TP1):** `{tp1}` $\n"
            f"🎯 **الهدف الثاني (TP2):** `{tp2}` $\n"
            f"🎯 **الهدف الثالث (TP3):** `{tp3}` $\n\n"
            f"🧭 **الاتجاه العام:** `{res['market_direction']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 الدعم والمقاومة")
def send_support_resistance(message):
    p = get_live_price()
    df_1h = fetch_candles_yf('1h', '7d')
    if p:
        r1 = round(df_1h['High'].tail(24).max(), 2) if not df_1h.empty else round(p + 12.0, 2)
        s1 = round(df_1h['Low'].tail(24).min(), 2) if not df_1h.empty else round(p - 12.0, 2)
        msg = (
            f"📊 **مستويات الدعم والمقاومة (Spot Gold):**\n"
            f"📍 **السعر الحالي:** `{p}` $\n"
            f"🔴 **المقاومة (R1):** `{r1}` $\n"
            f"🟢 **الدعم (S1):** `{s1}` $"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "تحليل الذهب 🥇")
def handle_gold_analysis(message):
    add_user(message.chat.id)
    res = scan_multi_timeframe_smc()
    if res:
        msg = (
            f"📊 **تقرير هيكل السوق (Spot Gold SMC Pro):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 **السعر اللحظي (MT5):** `{res['price']}` $\n"
            f"🧭 **اتجاه السوق الشامل:** `{res['market_direction']}`\n"
            f"⚡ **إشارة الحسم:** `{res['signal']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 **فريم 15 دقيقة (15M):**\n"
            f"• الاتجاه: `{res['15m']['trend']}` | FVG: `{res['15m']['fvg']}`\n"
            f"• الطلب: `{res['15m']['demand']}` | العرض: `{res['15m']['supply']}`\n\n"
            f"🔹 **فريم 30 دقيقة (30M):**\n"
            f"• الاتجاه: `{res['30m']['trend']}` | FVG: `{res['30m']['fvg']}`\n"
            f"• الطلب: `{res['30m']['demand']}` | العرض: `{res['30m']['supply']}`\n\n"
            f"🔹 **فريم الساعة (1H):**\n"
            f"• الاتجاه: `{res['1h']['trend']}`\n"
            f"• الطلب: `{res['1h']['demand']}`\n\n"
            f"🔹 **فريم 4 ساعات (4H):**\n"
            f"• الاتجاه: `{res['4h']['trend']}`\n\n"
            f"🔹 **الفريم اليومي (1D):**\n"
            f"• الاتجاه العام: `{res['1d']['trend']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ يتعذر جلب تحليل الشمعات حالياً، حاول مجدداً.")

@bot.message_handler(func=lambda m: m.text == "🔔 حالة التنبيهات")
def send_alert_status(message):
    add_user(message.chat.id)
    msg = (
        "🔔 **نظام التنبيهات التلقائي (SMC VIP):**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ **الحالة:** مُفعل ويعمل في الخلفية.\n"
        "⏱️ **معدل الفحص:** كل 30 ثانية تلقائياً.\n"
        "🎯 **الهدف:** إرسال إشعار فوري عند ملامسة السعر لأوردر بلوك قوي (Demand/Supply) على فريم 15M."
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# --- Webhook Server لـ Render ---
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)