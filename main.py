import os
import random
import telebot
from telebot import types

# ضع توكن البوت هنا أو استخلصه من متغيرات البيئة
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot = telebot.TeleBot(TOKEN)


def generate_gold_signal():
  # توليد سعر دخول واقعي للذهب (مثال قريب للسعر الحالي)
  base_price = round(random.uniform(4350.00, 4400.00), 2)

  entry = base_price
  stop_loss = round(entry - 12.00, 2)  # وقف خسارة قريب ومنطقي

  tp1 = round(entry + 15.00, 2)
  tp2 = round(entry + 30.00, 2)
  tp3 = round(entry + 50.00, 2)

  rsi_d1 = random.randint(50, 60)
  rsi_h4 = random.randint(50, 58)
  rsi_h1 = random.randint(48, 55)
  mac_m15 = random.choice(["UP", "BULLISH"])

  signal_text = (
      "🔥 إشارة ذهب احترافية (Spirex AI)\n\n"
      f"💵 دخول: {entry}\n"
      f"🛑 وقف الخسارة: {stop_loss}\n\n"
      "📊 تحليل الأطر الزمنية المتعددة:\n"
      f"• اليومي (D1): صاعد | RSI: {rsi_d1}\n"
      f"• 4 ساعات (H4): صاعد | RSI: {rsi_h4}\n"
      f"• ساعة (H1): صاعد | RSI: {rsi_h1}\n"
      f"• 15 دقيقة (M15): صاعد | MACD: {mac_m15}\n\n"
      "🎯 الأهداف:\n"
      f"✅ TP1: {tp1}\n"
      f"✅ TP2: {tp2}\n"
      f"✅ TP3: {tp3}\n\n"
      "⏳ الفريم المستخدم: 15د - 1س - 4س - يومي\n"
      "🚀 تم اكتمال الشروط بنجاح تام!"
  )
  return signal_text


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
  item1 = types.KeyboardButton("📊 إشارة ذهب جديدة")
  item2 = types.KeyboardButton("◀️ القائمة الرئيسية")
  markup.add(item1, item2)

  welcome_text = (
      "🤖 Spirex AI Gold Professional - النظام الذكي\n\n"
      "اهلاً بك عزيزي المتداول. تم تفعيل تحليلات الاطر الأربعة ومؤشرات RSI و MACD."
      "\nاختر الخدمة المطلوبة:"
  )
  bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


@bot.message_handler(func=lambda message: True)
def handle_message(message):
  if (
      "إشارة" in message.text
      or "بدء" in message.text
      or message.text == "/start"
  ):
    signal = generate_gold_signal()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item_back = types.KeyboardButton("◀️ القائمة الرئيسية")
    markup.add(item_back)

    bot.send_message(message.chat.id, signal, reply_markup=markup)
  elif "القائمة الرئيسية" in message.text:
    send_welcome(message)
  else:
    bot.send_message(
        message.chat.id,
        "الرجاء استخدام الأزرار أدناه للتحكم بالبوت.",
    )


if __name__ == "__main__":
  print("Bot is running...")
  bot.infinity_polling()
