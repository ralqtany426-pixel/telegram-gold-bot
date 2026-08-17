import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
import yfinance as yf
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- خادم وهمي لمنع توقف سيرفر Render ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# --- إعدادات البوت ---
TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)

def get_data():
    g = yf.Ticker("XAUUSD=X")
    df = g.history(period="1d", interval="1m")
    if df.empty:
        return 4410.0, 0, "مستقر", "4410"
    p = df['Close'].iloc[-1]
    prev = df['Open'].iloc[-1]
    chg = ((p - prev) / prev) * 100
    tr = "صاعد 🟢" if chg >= 0 else "هابط 🔴"
    entry_zone = f"{p-0.5:.2f} - {p:.2f}"
    return p, chg, tr, entry_zone

@bot.message_handler(commands=['start'])
def start(m):
    p, chg, tr, _ = get_data()
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📈 تحليل السوق", callback_data="all"))
    markup.row(InlineKeyboardButton("🎯 صفقة زيرو انعكاس", callback_data="sig"))
    bot.send_message(m.chat.id, f"🤖 Spirex Gold Bot\nسعر الذهب الحالي (XAUUSD): {p:.2f}\nالتغير: {chg:.2f}%\nالاتجاه: {tr}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    p, _, _, ez = get_data()
    if call.data == "all":
        bot.send_message(call.message.chat.id, f"📊 السعر الفوري المباشر: {p:.2f}")
    elif call.data == "sig":
        bot.send_message(call.message.chat.id, f"🎯 **صفقة زيرو انعكاس:**\n- منطقة الدخول: {ez}")

# --- تشغيل البوت بدون تعارض ---
bot.infinity_polling(timeout=10, long_polling_timeout=5)