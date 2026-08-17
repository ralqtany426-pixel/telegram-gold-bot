import os
import telebot
import yfinance as yf
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# تشغيل خادم الويب في خلفية منفصلة لإبقاء Render راضياً
threading.Thread(target=run_flask, daemon=True).start()

def get_data():
    g = yf.Ticker("XAUUSD=X")
    df = g.history(period="1d", interval="1m")
    p = df['Close'].iloc[-1] if not df.empty else 4410.0
    return p

@bot.message_handler(commands=['start'])
def start(m):
    p = get_data()
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📈 تحليل السوق", callback_data="all"))
    bot.send_message(m.chat.id, f"🤖 Spirex Gold Bot\nسعر الذهب الحالي (XAUUSD): {p:.2f}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    p = get_data()
    bot.send_message(call.message.chat.id, f"📊 السعر الفوري المباشر: {p:.2f}")

# حذف أي Webhook قديم عالق قبل تشغيل البوت
bot.remove_webhook()

# التشغيل المباشر الآمن
bot.infinity_polling(skip_pending=True)