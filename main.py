import os
import time
import sqlite3
import threading
import telebot
import pandas as pd
import MetaTrader5 as mt5
from flask import Flask, request
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN غير موجود!")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# --- تهيئة الاتصال بـ MetaTrader 5 ---
if not mt5.initialize():
    print("فشل الاتصال بـ MetaTrader 5، يرجى التأكد من فتح المنصة وتفعيل التداول الآلي.")

SYMBOL = "XAUUSD"  # تأكد من تطابق اسم الرمز لدى بروكِرك (مثل GOLD)

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

# --- جلب البيانات السعرية ---
def fetch_candles_mt5(timeframe_str='30m', count=100):
    tf_map = {
        '30m': mt5.TIMEFRAME_M30,
        '1h':  mt5.TIMEFRAME_H1,
        '4h':  mt5.TIMEFRAME_H4,
        '1d':  mt5.TIMEFRAME_D1
    }
    tf = tf_map.get(timeframe_str, mt5.TIMEFRAME_M30)
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
        
    df = pd.DataFrame(rates)
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
    return df[['Open', 'High', 'Low', 'Close']].astype(float)

def get_live_tick():
    return mt5.symbol_info_tick(SYMBOL)

def analyze_timeframe(df):
    if df.empty or len(df) < 5:
        return {
            "trend": "غير معروف ⚪", "demand": "غير محدد", "supply": "غير محدد", 
            "demand_low": 0, "demand_high": 0, "supply_low": 0, "supply_high": 0,
            "fvg": "لا توجد ⚪", "high": 0, "low": 0
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

    fvg = "لا توجد ⚪"
    for i in range(len(df)-1, 2, -1):
        if df['High'].iloc[i-2] < df['Low'].iloc[i]:
            fvg = f"Bullish FVG 🟢 ({round(df['High'].iloc[i-2], 1)} - {round(df['Low'].iloc[i], 1)})"
            break
        elif df['Low'].iloc[i-2] > df['High'].iloc[i]:
            fvg = f"Bearish FVG 🔴 ({round(df['High'].iloc[i], 1)} - {round(df['Low'].iloc[i-2], 1)})"
            break

    return {
        "trend": trend, "demand": f"🟢 Demand ({d_low} - {d_high})", "supply": f"🔴 Supply ({s_low} - {s_high})", 
        "demand_low": d_low, "demand_high": d_high, "supply_low": s_low, "supply_high": s_high,
        "fvg": fvg, "high": high_val, "low": low_val
    }

def scan_multi_timeframe_smc():
    df_30m = fetch_candles_mt5('30m', 100)
    df_1h  = fetch_candles_mt5('1h', 100)
    df_4h  = fetch_candles_mt5('4h', 100)
    df_1d  = fetch_candles_mt5('1d', 100)
    tick = get_live_tick()

    if df_30m.empty or tick is None:
        return None

    tf_30m = analyze_timeframe(df_30m)
    tf_1h  = analyze_timeframe(df_1h)
    tf_4h  = analyze_timeframe(df_4h)
    tf_1d  = analyze_timeframe(df_1d)

    bull_count = sum(1 for tf in [tf_30m, tf_1h, tf_4h, tf_1d] if "BULLISH" in tf['trend'])

    if bull_count >= 3:
        signal = "BUY Strong 🚀 (توافق صاعد قوي)"
    elif bull_count <= 1:
        signal = "SELL Strong 📉 (توافق هابط قوي)"
    else:
        signal = "WAIT ⏳ (تضارب الاتجاهات)"

    return {
        "price": round(tick.bid, 2), "30m": tf_30m, "1h": tf_1h, "4h": tf_4h, "1d": tf_1d, "signal": signal
    }

# --- منبه الصفقات الناجحة والتلقائي ---
def auto_alert_loop():
    last_alert_key = ""
    while True:
        try:
            time.sleep(30) # فحص كل 30 ثانية
            users = get_all_users()
            if not users:
                continue

            res = scan_multi_timeframe_smc()
            if res:
                p = res['price']
                tf30 = res['30m']
                
                # شرط الصفقة المضمونة القوية (توافق + ملامسة منطقة)
                is_high_winrate = False
                alert_type = ""
                
                if "BUY Strong" in res['signal'] and tf30['demand_low'] <= p <= (tf30['demand_high'] + 1.0):
                    is_high_winrate = True
                    alert_type = "🔥 **صفقة شراء VIP عالي النجاح! (ملامسة منطقة طلب + توافق صاعد)**"
                elif "SELL Strong" in res['signal'] and (tf30['supply_low'] - 1.0) <= p <= tf30['supply_high']:
                    is_high_winrate = True
                    alert_type = "🔥 **صفقة بيع VIP عالي النجاح! (ملامسة منطقة عرض + توافق هابط)**"

                current_key = f"{res['signal']}_{is_high_winrate}_{round(p, 1)}"

                if is_high_winrate and current_key != last_alert_key:
                    last_alert_key = current_key
                    
                    sl = round(tf30['demand_low'] - 3.0, 2) if "شراء" in alert_type else round(tf30['supply_high'] + 3.0, 2)
                    tp = round(tf30['supply_low'], 2) if "شراء" in alert_type else round(tf30['demand_high'], 2)

                    alert_msg = (
                        f"🚨 **تنبيه صفقة ناجحة عالية الدقة!**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{alert_type}\n\n"
                        f"📍 **السعر اللحظي:** `{p}` $\n"
                        f"🎯 **الدخول:** `{p}`\n"
                        f"🛑 **وقف الخسارة (SL):** `{sl}`\n"
                        f"🎯 **الهدف (TP):** `{tp}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━━"
                    )
                    for chat_id in users:
                        try:
                            bot.send_message(chat_id, alert_msg, parse_mode="Markdown")
                        except Exception as e:
                            print(f"Failed alert: {e}")
        except Exception as e:
            print(f"Error in alert loop: {e}")

threading.Thread(target=auto_alert_loop, daemon=True).start()

# --- لوحة التحكم والقطع الفنية ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    add_user(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_live = types.KeyboardButton("⚡ السعر اللحظي")
    btn_vip = types.KeyboardButton("🔥 صفقات VIP (الطلب والعرض)")
    btn_sr = types.KeyboardButton("📊 الدعم والمقاومة")
    btn_gold = types.KeyboardButton("تحليل الذهب 🥇")
    markup.add(btn_live, btn_vip, btn_sr, btn_gold)
    
    bot.send_message(
        message.chat.id, 
        "مرحباً بك! تم تفعيل الميزات المتقدمة والمنبه الآلي للصفقات الناجحة 🔔", 
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "⚡ السعر اللحظي")
def send_live_price(message):
    tick = get_live_tick()
    if tick:
        spread = round((tick.ask - tick.bid) * 10, 1)
        msg = (
            f"⚡ **السعر المباشر للذهب (MT5):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔻 **Bid (البيع):** `{tick.bid}` $\n"
            f"🔺 **Ask (الشراء):** `{tick.ask}` $\n"
            f"📏 **السبيد (Spread):** `{spread}` pips\n"
            f"⏰ **الوقت:** `لحظي`"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ فشل جلب السعر المباشر من منصة MT5.")

@bot.message_handler(func=lambda m: m.text == "🔥 صفقات VIP (الطلب والعرض)")
def send_vip_trade(message):
    res = scan_multi_timeframe_smc()
    if not res:
        bot.send_message(message.chat.id, "⚠️ يتعذر حساب صفقات VIP الآن.")
        return

    p = res['price']
    tf30 = res['30m']
    
    if "BUY" in res['signal']:
        entry = p
        sl = round(tf30['demand_low'] - 2.5, 2)
        tp = round(tf30['supply_low'], 2)
        trade_type = "BUY 🟢"
    else:
        entry = p
        sl = round(tf30['supply_high'] + 2.5, 2)
        tp = round(tf30['demand_high'], 2)
        trade_type = "SELL 🔴"

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0

    msg = (
        f"🔥 **توصية VIP بناءً على هيكل SMC:**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **نوع الصفقة:** `{trade_type}`\n"
        f"📍 **نقطة الدخول:** `{entry}` $\n"
        f"🛑 **وقف الخسارة (SL):** `{sl}` $\n"
        f"🎯 **هدف أخذ الربح (TP):** `{tp}` $\n"
        f"⚖️ **نسبة العائد للمخاطرة:** `1:{rr}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧱 **منطقة الطلب القريبة:** `{tf30['demand']}`\n"
        f"🧱 **منطقة العرض القريبة:** `{tf30['supply']}`"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 الدعم والمقاومة")
def send_support_resistance(message):
    df_1h = fetch_candles_mt5('1h', 100)
    df_4h = fetch_candles_mt5('4h', 100)
    tick = get_live_tick()

    if df_1h.empty or tick is None:
        bot.send_message(message.chat.id, "⚠️ تعذر حساب مستويات الدعم والمقاومة.")
        return

    price = tick.bid
    r1 = round(df_1h['High'].tail(24).max(), 2)
    s1 = round(df_1h['Low'].tail(24).min(), 2)
    r2 = round(df_4h['High'].tail(50).max(), 2)
    s2 = round(df_4h['Low'].tail(50).min(), 2)

    msg = (
        f"📊 **مستويات الدعم والمقاومة الرئيسية (XAU/USD):**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 **السعر الحالي:** `{price}` $\n\n"
        f"🔴 **المقاومة القوية (4H R2):** `{r2}` $\n"
        f"🔴 **المقاومة اللحظية (1H R1):** `{r1}` $\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 **الدعم اللحظي (1H S1):** `{s1}` $\n"
        f"🟢 **الدعم القوي (4H S2):** `{s2}` $\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "تحليل الذهب 🥇")
def handle_gold_analysis(message):
    add_user(message.chat.id)
    bot.send_message(message.chat.id, "🔄 **جاري تحليل مناطق الطلب والعرض والتوافق...**")
    
    def process():
        res = scan_multi_timeframe_smc()
        if res:
            msg = (
                f"📊 **التقرير المتقدم لهيكل السوق (XAU/USD - 30M SMC Pro):**\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📍 **السعر اللحظي (MT5):** `{res['price']}` $\n\n"
                f"⚡ **إشارة الحسم العامة:** `{res['signal']}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔹 **فريم 30 دقيقة (30M):**\n"
                f"• الاتجاه: `{res['30m']['trend']}`\n"
                f"• منطقة الطلب: `{res['30m']['demand']}`\n"
                f"• منطقة العرض: `{res['30m']['supply']}`\n\n"
                f"🔹 **فريم الساعة (1H):**\n"
                f"• الاتجاه: `{res['1h']['trend']}`\n\n"
                f"🔹 **فريم 4 ساعات (4H):**\n"
                f"• الاتجاه: `{res['4h']['trend']}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━"
            )
            bot.send_message(message.chat.id, msg, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "⚠️ متعذر جلب البيانات السعرية اللحظية.")
            
    threading.Thread(target=process, daemon=True).start()

# --- خادم Flask للتشغيل ---
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