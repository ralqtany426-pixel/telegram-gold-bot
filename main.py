import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
import yfinance as yf
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- خادم وهمي لإرضاء منفذ Port الخاص بسيرفر Render المجاني ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# تشغيل الخادم الوهمي في الخلفية
threading.Thread(target=run_dummy_server, daemon=True).start()
# -------------------------------------------------------------

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)

def get_data():
    g = yf.Ticker("GC=F")
    df = g.history(period="3d", interval="15m")
    if df.empty:
        return 2300.0, 0, 50, "صاعد", "2300", 2305, 2295
    p = df['Close'].iloc[-1]
    prev = df['Close'].iloc[0]
    chg = ((p - prev) / prev) * 100
    tr = "صاعد 🟢" if chg >= 0 else "هابط 🔴"
    return p, chg, 60, tr, f"{p-2:.2f}-{p:.2f}", p+3, p+7, p+12, p-4

@bot.message_handler(commands=['start'])
def start(m):
    p, chg, mood, tr, _, _, _, _, _ = get_data()
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📈 تحليل السوق", callback_data="all"))
    markup.row(InlineKeyboardButton("🔥 صفقة الذهب", callback_data="sig"))
    markup.row(InlineKeyboardButton("📊 الدعوم والأهداف", callback_data="lvl"))
    bot.send_message(m.chat.id, f"🤖 Spirex Bot\nسعر الذهب: {p:.2f}\nالتغير: {chg:.2f}%\nالاتجاه: {tr}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    p, _, _, _, ez, tp1, tp2, tp3, sl = get_data()
    if call.data == "all":
        bot.send_message(call.message.chat.id, f"📊 السعر الحالي المباشر: {p:.2f}")
    elif call.data == "sig":
        bot.send_message(call.message.chat.id, f"🔥 التوصية القريبة:\nالدخول: {ez}\nالهدف 1: {tp1:.2f}\nالهدف 2: {tp2:.2f}\nالوقف: {sl:.2f}")
    elif call.data == "lvl":
        bot.send_message(call.message.chat.id, f"📊 المقاومة: {tp2:.2f}\nالدعم: {sl:.2f}")

bot.infinity_polling()