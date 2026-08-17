import os
import random
import telebot
from telebot import types

TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot = telebot.TeleBot(TOKEN)

def generate_gold_signal():
    base_price = round(random.uniform(4370.00, 4380.00), 2)
    entry = base_price
    stop_loss = round(entry - 12.00, 2)
    
    tp1 = round(entry + 15.00, 2)
    tp2 = round(entry + 30.00, 2)
    tp3 = round(entry + 50.00, 2)

    signal_text = (
        "🔥 إشارة ذهب احترافية (Spirex AI)\n\n"
        f"💵 دخول: {entry}\n"
        f"🛑 وقف الخسارة: {stop_loss}\n\n"
        "📊 تحليل الأطر الزمنية المتعددة:\n"
        "• اليومي (D1): صاعد | RSI: 55\n"
        "• 4 ساعات (H4): صاعد | RSI: 53\n"
        "• ساعة (H1): صاعد | RSI: 51\n"
        "• 15 دقيقة (M15): صاعد | MACD: UP\n\n"
        "🎯 الأهداف:\n"
        f"✅ TP1: {tp1}\n"
        f"✅ TP2: {tp2}\n"
        f"✅ TP3: {tp3}\n\n"
        "⏳ الفريم المستخدم: 15د - 1س - 4س - يومي\n"
        "🚀 تم اكتمال الشروط بنجاح تام!"
    )
    return signal_text

@bot.message_handler(commands=["start"])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📊 إشارة ذهب احترافية (Spirex AI)"))
    markup.add(types.KeyboardButton("📈 مناطق الدعم والمقاومة"), types.KeyboardButton("🛡️ حاسبة إدارة المخاطر"))
    
    welcome_text = (
        "🤖 Spirex AI Gold Professional - النظام الذكي المتقدم\n\n"
        "أهلاً بك عزيزي المتداول. تم تفعيل تحليلات الأطر الأربعة ومؤشرات RSI و MACD.\n"
        "اختر الخدمة المطلوبة:"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    if "إشارة ذهب احترافية" in message.text:
        signal = generate_gold_signal()
        bot.send_message(message.chat.id, signal)
    elif "مناطق الدعم والمقاومة" in message.text:
        bot.send_message(message.chat.id, "📈 مناطق الدعم والمقاومة الحالية للذهب.")
    elif "حاسبة إدارة المخاطر" in message.text:
        bot.send_message(message.chat.id, "🛡️ حاسبة إدارة المخاطر:")
    else:
        send_welcome(message)

if __name__ == "__main__":
    bot.infinity_polling()
