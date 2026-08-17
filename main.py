import os
import telebot
from flask import Flask, request

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# الرابط الجديد الصحيح
RENDER_URL = 'https://telegram-gold-bot-2mth.onrender.com'

@app.route('/')
def home():
    return "Bot is running live and ready!"

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🤖 أهلاً بك يا عبد الله! يعمل بوت الذهب بنجاح تام.")

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=f'{RENDER_URL}/{TOKEN}')
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))