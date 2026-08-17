import os
import telebot
import yfinance as yf
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- دالة جلب البيانات ---
def get_data():
    g = yf.Ticker("XAUUSD=X")
    df = g.history(period="1d", interval="1m")
    p = df['Close'].iloc[-1] if not df.empty else 4410.0
    return p

# --- أوامر البوت ---
@bot.message_handler(commands=['start'])
def start(m):
    p = get_data()
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📈 تحليل", callback_data="all"))
    bot.send_message(m.chat.id, f"🤖 Spirex Gold Bot\nالسعر الحالي: {p:.2f}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    p = get_data()
    bot.send_message(call.message.chat.id, f"📊 السعر الفوري: {p:.2f}")

# --- الربط عبر Webhook لضمان عدم التعارض ---
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url="https://<YOUR_RENDER_APP_URL>/" + TOKEN) # استبدل برابط تطبيقك في Render
    return "Webhook set!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))