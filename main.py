import telebot
import threading
import time
import pandas as pd
import MetaTrader5 as mt5
from flask import Flask, request
from telebot import types

# --- 1. إعدادات المفتاح والبوت ---
TOKEN = '8982114650:AAH9EVAcP9bJnm_3VC72J_o7vMpfTlim2W4'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

SYMBOL = "XAUUSD"  # الرمز المعرف لمنصتك
last_vip_state = "NONE"

# --- 2. الاتصال بـ MetaTrader 5 ---
def init_mt5():
    if not mt5.initialize():
        print("❌ فشل الاتصال بـ MetaTrader 5. تأكد من فتح البرنامج.")
        return False
    return True

def get_mt5_price():
    if not init_mt5():
        return None
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick:
        return round(tick.bid, 2)
    return None

def fetch_mt5_rates(timeframe, count=100):
    if not init_mt5():
        return pd.DataFrame()
    
    tf_map = {
        "15m": mt5.TIMEFRAME_M15,
        "1h": mt5.TIMEFRAME_H1
    }
    
    rates = mt5.copy_rates_from_pos(SYMBOL, tf_map.get(timeframe, mt5.TIMEFRAME_M15), 0, count)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# --- 3. محرك التحليل الشامل ---
def analyze_vip_multi_timeframe():
    df_15m = fetch_mt5_rates("15m", 50)
    df_1h = fetch_mt5_rates("1h", 100)

    if df_15m.empty or df_1h.empty:
        return None

    current_price = get_mt5_price()
    if not current_price:
        current_price = round(df_15m['close'].iloc[-1], 2)

    demand_low = round(df_1h['low'].iloc[-50:-1].min(), 2)
    demand_high = round(demand_low + 4.5, 2)

    supply_high = round(df_1h['high'].iloc[-50:-1].max(), 2)
    supply_low = round(supply_high - 4.5, 2)

    is_bullish_setup = (demand_low <= current_price <= demand_high)
    is_bearish_setup = (supply_low <= current_price <= supply_high)

    signal_type = "NONE"
    if is_bullish_setup:
        signal_type = "BUY"
    elif is_bearish_setup:
        signal_type = "SELL"

    return {
        "price": current_price,
        "signal": signal_type,
        "demand": f"{demand_low} ⟷ {demand_high}",
        "supply": f"{supply_low} ⟷ {supply_high}",
        "demand_low": demand_low,
        "supply_high": supply_high
    }

# --- 4. أوامر البوت والتفاعل ---
@bot.message_handler(commands=['start'])
def start_command(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("💰 السعر اللحظي (MT5)"),
        types.KeyboardButton("🎯 فحص الفرصة الحالية (VIP)"),
        types.KeyboardButton("🧮 حاسبة المخاطر")
    )
    welcome_text = (
        f"👑 **النظام المربوط بـ MetaTrader 5 المباشر**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"مرحباً بك يا عبد الله.\n"
        f"تم ضبط البوت وقراءة السعر المباشر لرمز **{SYMBOL}** من منصتك."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    text = message.text
    chat_id = message.chat.id

    if text == "💰 السعر اللحظي (MT5)":
        price = get_mt5_price()
        if price:
            bot.send_message(chat_id, f"💰 **سعر الذهب المباشر (MT5 - XAUUSD):**\n`{price} $`", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "⚠️ تعذر الاتصال بـ MT5. تأكد من تشغيل البرنامج على جهاز الكمبيوتر.")

    elif text == "🎯 فحص الفرصة الحالية (VIP)":
        analysis = analyze_vip_multi_timeframe()
        if not analysis:
            bot.send_message(chat_id, "⚠️ تعذر جلب البيانات المباشرة من MT5.")
            return

        msg = (
            f"📊 **تقرير التحليل المباشر (XAUUSD):**\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 السعر الحالي: `{analysis['price']} $`\n"
            f"🧱 منطقة الطلب: `{analysis['demand']}`\n"
            f"🧱 منطقة العرض: `{analysis['supply']}`\n"
            f"⚡ حالة الإشارة الحالية: `{analysis['signal']}`"
        )
        bot.send_message(chat_id, msg, parse_mode="Markdown")

    elif text == "🧮 حاسبة المخاطر":
        bot.send_message(chat_id, "🧮 **إدارة المخاطر:** يُنصح بالمخاطرة بـ 1% فقط من رأس المال لكل صفقة.", parse_mode="Markdown")

if __name__ == '__main__':
    if init_mt5():
        print("✅ تم الاتصال بـ MetaTrader 5 بنجاح لرمز XAUUSD.")
        bot.infinity_polling()
    else:
        print("❌ لم يتم الاتصال! تأكد من فتح تطبيق MetaTrader 5 أولاً.")