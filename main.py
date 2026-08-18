import os
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    I am alive!


def run():
    # Render يزودنا برقم الport تلقائياً عبر المتغير البيئي PORT
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# استدعِ هذه الدالة قبل تشغيل البوت الخاص بك
if __name__ == '__main__':
    keep_alive()
    # هنا تضع كود تشغيل بوت تليجرام الخاص بك (مثل bot.infinity_polling())