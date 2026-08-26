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

# --- جلب السعر المباشر للذهب الفوري ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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

# --- جلب الشمعات ---
def fetch_candles_yf(interval='30m', period='5d'):
    symbols = ["GC=F", "XAUUSD=X"]
    for sym in symbols:
        for attempt in range(2):  
            try:
                ticker = yf.Ticker(sym)
                df = ticker.history(period=period, interval=interval)
                if not df.empty and len(df) >= 10:
                    df = df[['Open', 'High', 'Low', 'Close']].astype(float)
                    return df
            except Exception as e:
                print(f"Attempt {attempt+1} failed for {sym} interval {interval}: {e}")
                time.sleep(0.5)

    return pd.DataFrame()

# --- خوارزمية تحليل هيكل السوق ---
def analyze_timeframe(df, current_price=0):
    if df.empty or len(df) < 5 or current_price == 0:
        return {
            "trend": "NEUTRAL ⚪", 
            "demand": "غير محددة ⚪", "supply": "غير محددة ⚪", 
            "demand_low": 0, "demand_high": 0, 
            "supply_low": 0, "supply_high": 0,
            "fvg": "لا توجد ⚪", "fvg_type": None, "fvg_low": 0, "fvg_high": 0,
            "high": current_price, "low": current_price,
            "is_sweep": False
        }

    recent_df = df.tail(100).copy()
    current = current_price if current_price > 0 else recent_df['Close'].iloc[-1]

    ema = recent_df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
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

    # 1. البحث عن أقرب Order Block شرائي
    for i in range(len(recent_df)-3, 1, -1):
        if recent_df['Close'].iloc[i] < recent_df['Open'].iloc[i]:
            if recent_df['Close'].iloc[i+1] > recent_df['Open'].iloc[i] or recent_df['Close'].iloc[i+2] > recent_df['High'].iloc[i]:
                c_low = round(recent_df['Low'].iloc[i], 1)
                c_high = round(recent_df['High'].iloc[i], 1)
                if c_high < current and (current - c_high) <= 60.0:
                    d_low, d_high = c_low, c_high
                    break

    # 2. البحث عن أقرب Order Block بيعي
    for i in range(len(recent_df)-3, 1, -1):
        if recent_df['Close'].iloc[i] > recent_df['Open'].iloc[i]:
            if recent_df['Close'].iloc[i+1] < recent_df['Open'].iloc[i] or recent_df['Close'].iloc[i+2] < recent_df['Low'].iloc[i]:
                c_low = round(recent_df['Low'].iloc[i], 1)
                c_high = round(recent_df['High'].iloc[i], 1)
                if c_low > current and (c_low - current) <= 60.0:
                    s_low, s_high = c_low, c_high
                    break

    # 3. صيد السيولة (Liquidity Sweep)
    lowest_recent = recent_df['Low'].tail(15).min()
    is_sweep = True if (current > lowest_recent and recent_df['Low'].iloc[-1] <= lowest_recent) else False

    # 4. التقاط الفجوة السعرية (FVG)
    fvg_str = "لا توجد ⚪"
    fvg_type = None
    fvg_low, fvg_high = 0, 0

    for i in range(len(recent_df)-1, 2, -1):
        # Bullish FVG
        if recent_df['High'].iloc[i-2] < recent_df['Low'].iloc[i]:
            f_low = round(recent_df['High'].iloc[i-2], 1)
            f_high = round(recent_df['Low'].iloc[i], 1)
            if f_low <= current <= (f_high + 10.0) or abs(current - f_high) <= 20.0:
                fvg_low, fvg_high = f_low, f_high
                fvg_type = "BULLISH"
                fvg_str = f"Bullish FVG 🟢 ({fvg_low} - {fvg_high})"
                break

        # Bearish FVG
        elif recent_df['Low'].iloc[i-2] > recent_df['High'].iloc[i]:
            f_low = round(recent_df['High'].iloc[i], 1)
            f_high = round(recent_df['Low'].iloc[i-2], 1)
            if (f_low - 10.0) <= current <= f_high or abs(f_low - current) <= 20.0:
                fvg_low, fvg_high = f_low, f_high
                fvg_type = "BEARISH"
                fvg_str = f"Bearish FVG 🔴 ({fvg_low} - {fvg_high})"
                break

    demand_str = f"🟢 Demand ({d_low} - {d_high})" if d_low > 0 else "غير محددة ⚪"
    supply_str = f"🔴 Supply ({s_low} - {s_high})" if s_low > 0 else "غير محددة ⚪"

    return {
        "trend": trend, 
        "demand": demand_str, 
        "supply": supply_str, 
        "demand_low": d_low, "demand_high": d_high, 
        "supply_low": s_low, "supply_high": s_high,
        "fvg": fvg_str, "fvg_type": fvg_type, "fvg_low": fvg_low, "fvg_high": fvg_high,
        "high": round(recent_df['High'].max(), 2), 
        "low": round(recent_df['Low'].min(), 2),
        "is_sweep": is_sweep
    }

# --- الفحص متعدد الفريمات مع دمج الزخم السريع لـ 15M ---
def scan_multi_timeframe_smc():
    price = get_live_price()
    if price is None:
        return None

    df_15m = fetch_candles_yf('15m', '2d')
    df_30m = fetch_candles_yf('30m', '3d')
    df_1h  = fetch_candles_yf('1h', '5d')

    df_4h_raw = fetch_candles_yf('1h', '20d')
    if not df_4h_raw.empty:
        df_4h = df_4h_raw.resample('4h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last'
        }).dropna()
    else:
        df_4h = pd.DataFrame()

    df_1d  = fetch_candles_yf('1d', '30d')

    tf_15m = analyze_timeframe(df_15m, price)
    tf_30m = analyze_timeframe(df_30m, price)
    tf_1h  = analyze_timeframe(df_1h, price)
    tf_4h  = analyze_timeframe(df_4h, price)
    tf_1d  = analyze_timeframe(df_1d, price)

    timeframes = [tf_15m, tf_30m, tf_1h, tf_4h, tf_1d]
    bull_count = sum(1 for tf in timeframes if "BULLISH" in tf['trend'])
    bear_count = sum(1 for tf in timeframes if "BEARISH" in tf['trend'])

    if (tf_1d['trend'] == "BULLISH 🟢" and tf_1h['trend'] != "BEARISH 🔴") or bull_count >= 3:
        market_direction = "صاعد (الاتجاه العام يميل للشراء) 🟢🚀"
        signal = "BUY (بحث عن فرص شراء) 🚀"
    elif (tf_1d['trend'] == "BEARISH 🔴" and tf_1h['trend'] != "BULLISH 🟢") or bear_count >= 3:
        market_direction = "هابط (الاتجاه العام يميل للبيع) 🔴📉"
        signal = "SELL (بحث عن فرص بيع) 📉"
    else:
        market_direction = "عرضي / محايد ⚪"
        signal = "WAIT ⏳ (تذبذب / انتظار)"

    quick_15m_signal = None
    if not df_15m.empty and len(df_15m) >= 3:
        last_close = df_15m['Close'].iloc[-1]
        prev_close = df_15m['Close'].iloc[-2]
        prev_open = df_15m['Open'].iloc[-2]
        body_size = last_close - df_15m['Open'].iloc[-1]
        prev_body = prev_close - prev_open

        if prev_body > 0 and body_size < -2.0 and "SELL" in signal:
            quick_15m_signal = "SELL 🔴 (قنص هبوط سريع 15M)"
        elif prev_body < 0 and body_size > 2.0 and "BUY" in signal:
            quick_15m_signal = "BUY 🟢 (قنص صعود سريع 15M)"

    return {
        "price": price, 
        "market_direction": market_direction,
        "quick_15m": quick_15m_signal,
        "15m": tf_15m, "30m": tf_30m, "1h": tf_1h, "4h": tf_4h, "1d": tf_1d, 
        "signal": signal
    }

# --- اختيار الفريم النشط ---
def select_active_timeframe(res, price):
    active_tf = res['30m']

    if active_tf['demand_low'] == 0 and active_tf['supply_low'] == 0:
        if res['15m']['demand_low'] > 0 or res['15m']['supply_low'] > 0:
            active_tf = res['15m']
        elif res['1h']['demand_low'] > 0 or res['1h']['supply_low'] > 0:
            active_tf = res['1h']

    if res['1h']['demand_low'] > 0 and (res['1h']['demand_low'] - 2.0) <= price <= (res['1h']['demand_high'] + 2.0):
        active_tf = res['1h']
    elif res['1h']['supply_low'] > 0 and (res['1h']['supply_low'] - 2.0) <= price <= (res['1h']['supply_high'] + 2.0):
        active_tf = res['1h']

    return active_tf

# --- حساب الأهداف ---
def calculate_trade_targets(price, active_tf, signal_type):
    if "BUY" in signal_type:
        d_low = active_tf['demand_low'] if active_tf['demand_low'] > 0 else price - 5.0
        sl_raw = d_low - 2.5
        sl = round(max(sl_raw, price - 7.0), 2)

        risk = abs(price - sl) if abs(price - sl) >= 2.0 else 4.0
        tp1 = round(price + (risk * 1.5), 2)
        tp2 = round(price + (risk * 2.5), 2)
        tp3 = round(price + (risk * 3.5), 2)
        return "BUY 🟢", sl, tp1, tp2, tp3
    else:
        s_high = active_tf['supply_high'] if active_tf['supply_high'] > 0 else price + 5.0
        sl_raw = s_high + 2.5
        sl = round(min(sl_raw, price + 7.0), 2)

        risk = abs(sl - price) if abs(sl - price) >= 2.0 else 4.0
        tp1 = round(price - (risk * 1.5), 2)
        tp2 = round(price - (risk * 2.5), 2)
        tp3 = round(price - (risk * 3.5), 2)
        return "SELL 🔴", sl, tp1, tp2, tp3

# --- حلقة التنبيهات التلقائية المحدثة (فلترة الإشارات المزدوجة) ---
def auto_alert_loop():
    last_alert_price = 0.0
    last_signal_type = ""

    while True:
        try:
            users = get_all_users()
            if users:
                res = scan_multi_timeframe_smc()
                if res:
                    p = res['price']
                    active_tf = select_active_timeframe(res, p)

                    is_alert = False
                    alert_type = ""
                    signal_type = ""

                    trend_1d_bullish = "BULLISH" in res['1d']['trend']

                    if res.get('quick_15m'):
                        is_alert = True
                        signal_type = "BUY" if "BUY" in res['quick_15m'] else "SELL"
                        alert_type = f"⚡ **{res['quick_15m']} (فرصة سريعة مؤكدة)**"

                    elif (active_tf['demand_high'] > 0 and (active_tf['demand_low'] - 2.0) <= p <= (active_tf['demand_high'] + 3.0)) or active_tf['is_sweep']:
                        is_alert = True
                        alert_type = "🔥 **صفقة شراء VIP (منطقة طلب / صيد سيولة معتمدة)**"
                        signal_type = "BUY"

                    elif active_tf['supply_low'] > 0 and (active_tf['supply_low'] - 3.0) <= p <= (active_tf['supply_high'] + 2.0):
                        is_alert = True
                        alert_type = "🔥 **صفقة بيع VIP (ملامسة منطقة العرض معتمدة)**"
                        signal_type = "SELL"

                    elif "BUY" in res['signal'] and trend_1d_bullish:
                        is_alert = True
                        alert_type = "⚡ **صفقة شراء استمرارية VIP (توافق اتجاه صاعد قوي)**"
                        signal_type = "BUY"

                    elif "SELL" in res['signal'] and not trend_1d_bullish:
                        is_alert = True
                        alert_type = "⚡ **صفقة بيع استمرارية VIP (توافق اتجاه هابط قوي)**"
                        signal_type = "SELL"

                    distance_from_last = abs(p - last_alert_price)
                    if is_alert and (signal_type != last_signal_type or distance_from_last >= 5.0):
                        last_alert_price = p
                        last_signal_type = signal_type

                        trade_type, sl, tp1, tp2, tp3 = calculate_trade_targets(p, active_tf, signal_type)

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

        time.sleep(20)

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

    bot.send_message(message.chat.id, "مرحباً بك! تم تفعيل فلتر منع التضارب بنجاح ⚡", reply_markup=markup)

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
    active_tf = select_active_timeframe(res, p)
    trend_1d_bullish = "BULLISH" in res['1d']['trend']

    if res.get('quick_15m'):
        trade_type = "BUY 🟢" if "BUY" in res['quick_15m'] else "SELL 🔴"
        _, sl, tp1, tp2, tp3 = calculate_trade_targets(p, active_tf, trade_type)
    elif active_tf['demand_low'] > 0 and p <= active_tf['demand_high'] + 3.0:
        trade_type, sl, tp1, tp2, tp3 = calculate_trade_targets(p, active_tf, "BUY")
    elif active_tf['supply_high'] > 0 and p >= active_tf['supply_low'] - 3.0:
        trade_type, sl, tp1, tp2, tp3 = calculate_trade_targets(p, active_tf, "SELL")
    elif "BUY" in res['signal'] and trend_1d_bullish:
        trade_type, sl, tp1, tp2, tp3 = calculate_trade_targets(p, active_tf, "BUY")
    elif "SELL" in res['signal'] and not trend_1d_bullish:
        trade_type, sl, tp1, tp2, tp3 = calculate_trade_targets(p, active_tf, "SELL")
    else:
        trade_type = "WAIT"

    if "WAIT" in trade_type:
        msg = (
            f"🔥 **توصية VIP بناءً على SMC:**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **حالة السوق:** `انتظار ⏳`\n"
            f"📍 **السعر اللحظي:** `{p}` $\n\n"
            f"💡 **الملاحظة:** انتظر ملامسة منطقة طلب أو عرض واضحة ليتم تفعيل الفرصة.\n"
            f"🧭 **الاتجاه العام:** `{res['market_direction']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
    else:
        msg = (
            f"🔥 **توصية VIP بناءً على SMC:**\n"
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
    df_1h = fetch_candles_yf('1h', '5d')
    if p:
        if not df_1h.empty:
            recent_highs = df_1h['High'].tail(24)
            recent_lows = df_1h['Low'].tail(24)

            r1_candidates = recent_highs[recent_highs > p]
            s1_candidates = recent_lows[recent_lows < p]

            r1 = round(r1_candidates.min(), 2) if not r1_candidates.empty else round(p + 10.0, 2)
            s1 = round(s1_candidates.max(), 2) if not s1_candidates.empty else round(p - 10.0, 2)
        else:
            r1 = round(p + 10.0, 2)
            s1 = round(p - 10.0, 2)

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
        "✅ **الحالة:** مُفعل (مع فلتر منع التضارب والمسافة السعرية).\n"
        "⏱️ **معدل الفحص:** كل 20 ثانية.\n"
        "🎯 **الهدف:** إرسال فرصة واحدة مؤكدة متوافقة مع الاتجاه العام."
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