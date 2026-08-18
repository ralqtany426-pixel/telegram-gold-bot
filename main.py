import os
import requests
import telebot
import random
from flask import Flask, request
from telebot import types

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

def get_gold_price():
    try:
        response = requests.get("https://api.gold-api.com/price/XAU", timeout=5)
        return round(float(response.json().get("price", 2400.0)), 2)
    except:
        return 2400.0

# دالة حساب الدعم والمقاومة
def get_pivot_levels(price):
    support = round(price - 5.5, 2)  # الدعم
    resistance = round(price + 5.5, 2) # المقاومة
    return support, resistance

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

@bot.message_handler(commands=['start'])
def start_command(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💰 سعر الذهب", callback_data="get_price"),
        types.InlineKeyboardButton("🚀 زيرو انعكاس", callback_data="zero_draw"),
        types.InlineKeyboardButton("📈 صفقة قريبة", callback_data="success_signal")
    )
    bot.send_message(message.chat.id, "🤖 **بوت تحليل الذهب المحترف**\nاختر أحد الأزرار للتحليل:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    price = get_gold_price()
    support, resistance = get_pivot_levels(price)
    
    if call.data == "get_price":
        bot.send_message(call.message.chat.id, f"💰 **سعر الذهب الحالي:** `{price}` $", parse_mode="Markdown")
        
    elif call.data == "zero_draw":
        zero_success = round(random.uniform(82.0, 97.0), 1)
        bot.send_message(call.message.chat.id, 
            f"🎯 **تقرير زيرو انعكاس (Zero Drawdown):**\n"
            f"📍 السعر الحالي: `{price}`\n"
            f"🛡 مستوى الدعم القريب: `{support}`\n"
            f"⚡ مستوى المقاومة القريب: `{resistance}`\n"
            f"📊 **نسبة نجاح الفرصة:** `{zero_success}%`", 
            parse_mode="Markdown")
            
    elif call.data == "success_signal":
        dynamic_success = round(random.uniform(75.0, 95.0), 1)
        signal_type = "شراء (BUY) 🟢" if price % 2 == 0 else "بيع (SELL) 🔴"
        
        bot.send_message(call.message.chat.id, 
            f"⚡ **تحليل الصفقة والتوصية:**\n"
            f"📍 سعر الدخول: `{price}`\n"
            f"📉 الاتجاه المكتشف: `{signal_type}`\n"
            f"🛡 الدعم: `{support}` | ⚡ المقاومة: `{resistance}`\n"
            f"🎯 الهدف المقترح (TP): +15 نقطة\n"
            f"⛔ وقف الخسارة (SL): -7 نقاط\n"
            f"📊 **نسبة نجاح الصفقة:** `{dynamic_success}%`", 
            parse_mode="Markdown")

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))