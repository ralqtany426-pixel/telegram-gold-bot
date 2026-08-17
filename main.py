import os
import telebot
from flask import Flask, request
import yfinance as yf

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

def get_data():
    g = yf.Ticker("XAUUSD=X")
    df = g.history(period="1d", interval="1m")
    p = df['Close'].iloc[-1] if not df.empty else 4410.0
    return p

@bot.message_handler(commands=['start'])
def start(m):
    p = get_data()
    bot.send_message(m.chat.id, f"🤖 Spirex Gold Bot\nالسعر الحالي: {p:.2f}")

@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "!", 200

if __name__ == "__main__":
    # هذا الأمر ضروري لربط البوت بـ Render
    bot.remove_webhook()
    bot.set_webhook(url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))