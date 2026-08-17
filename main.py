import os
import telebot
from flask import Flask, request

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# رابط استضافة سيرفرك على Render (استبدل هذا الرابط برابط موقعك الحقيقي على Render)
RENDER_URL = 'https://gold-signal-trader.onrender.com'

@app.route('/')
def home():
    return "Bot is running live!"

@app.route(f'/{TOKEN}', methods=['POST'])
def receive_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🤖 أهلاً بك يا عبد الله! بوت تداول الذهب يعمل الآن بنظام الـ Webhook بنجاح تام.")

if __name__ == '__main__':
    # إزالة أي ويب هوك قديم وتعيين الرابط الجديد تلقائياً عند التشغيل
    bot.remove_webhook()
    bot.set_webhook(url=f'{RENDER_URL}/{TOKEN}')
    
    # تشغيل سيرفر Flask على بورت Render
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))