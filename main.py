import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
import yfinance as yf
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- خادم وهمي لـ Render ---
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

TOKEN = '8982114650:AAFE5ftQJD9apfBjMmbTqEuX5hcvFkYVNRg'
bot = telebot.TeleBot(TOKEN)

def get_data():
    # تعديل المصدر إلى XAUUSD=X للحصول على سعر الفوركس المباشر
    g = yf.Ticker("XAUUSD=X")
    df = g.history(period="1d", interval="1m")
    
    if df.empty:
        return 4410.0, 0, "مستقر", "4410", 4415, 4420, 4425, 4405, "لا توجد أخبار"
    
    p = df['Close'].iloc[-1]
    prev = df['Open'].iloc[-1]
    chg = ((p - prev) / prev) * 100
    tr = "صاعد 🟢" if chg >= 0 else "هابط 🔴"
    
    # حسابات دقيقة لسعر الذهب (XAUUSD)
    entry_zone = f"{p-0.5:.2f} - {p:.2f}"
    tp1 = p + 1.5
    tp2 = p + 3.0
    tp3 = p + 5.0
    sl = p - 2.0
    
    news_report = "📰 **تقرير الأخبار:** هدوء نسبي في الأسواق. يرجى متابعة الأجندة الاقتصادية لاحتمالية تقلبات عند افتتاح الجلسات."
    
    return p, chg, tr, entry_zone, tp1, tp2, tp3, sl, news_report

@bot.message_handler(commands=['start'])
def start(m):
    p, chg, tr, _, _, _, _, _, _ = get_data()
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📈 تحليل السوق", callback_data="all"))
    markup.row(InlineKeyboardButton("🎯 صفقة زيرو انعكاس", callback_data="sig"))
    markup.row(InlineKeyboardButton("📰 تقرير الأخبار", callback_data="news"))
    bot.send_message(m.chat.id, f"🤖 Spirex Gold Bot\n سعر الذهب الحالي: {p:.2f}\n التغير: {chg:.2f}%\n الاتجاه: {tr}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    p, _, _, ez, tp1, tp2, tp3, sl, news_report = get_data()
    if call.data == "all":
        bot.send_message(call.message.chat.id, f"📊 السعر الفوري (XAUUSD): {p:.2f}")
    elif call.data == "sig":
        bot.send_message(call.message.chat.id, f"🎯 **صفقة زيرو انعكاس:**\n- الدخول: {ez}\n- الهدف 1: {tp1:.2f}\n- الهدف 2: {tp2:.2f}\n- الوقف: {sl:.2f}")
    elif call.data == "news":
        bot.send_message(call.message.chat.id, news_report)

bot.infinity_polling()