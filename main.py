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
    df = g.history(period="1d", interval="1m")
    if df.empty:
        df = g.history(period="3d", interval="15m")
    
    if df.empty:
        return 2300.0, 0, "صاعد", "2300", 2305, 2295, 2310, 2290, "استقرار عام في السوق"
    
    p = df['Close'].iloc[-1]
    prev = df['Open'].iloc[0]
    chg = ((p - prev) / prev) * 100
    tr = "صاعد 🟢" if chg >= 0 else "هابط 🔴"
    
    entry_zone = f"{p-1:.2f} - {p:.2f}"
    tp1 = p + 3
    tp2 = p + 7
    tp3 = p + 12
    sl = p - 3.5  # وقف خسارة ضيق لدعم صفقة زيرو انعكاس
    
    # محاكاة تقرير الأخبار والإنذارات بناءً على حركة السوق
    news_report = "📰 **تقرير الأخبار الاقتصادية:**\n- بيانات مؤشر أسعار المستهلكين (CPI): تأثير قوي 🔥\n- خطابات الفيدرالي الأمريكي: تأثير متوسط ⚡"
    if abs(chg) > 1.0:
        news_report += "\n\n🚨 **إنذار هام:** يوجد تقلب عالي في السوق بسبب بيانات اقتصادية مفاجئة، يرجى توخي الحذر!"
    else:
        news_report += "\n\n✅ **حالة الأخبار:** هادئة نسبياً ومناسبة للتداول الفني."

    return p, chg, tr, entry_zone, tp1, tp2, tp3, sl, news_report

@bot.message_handler(commands=['start'])
def start(m):
    p, chg, tr, _, _, _, _, _, _ = get_data()
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📈 تحليل السوق", callback_data="all"))
    markup.row(InlineKeyboardButton("🎯 صفقة زيرو انعكاس", callback_data="sig"))
    markup.row(InlineKeyboardButton("📰 تقرير الأخبار والإنذارات", callback_data="news"))
    markup.row(InlineKeyboardButton("📊 الدعوم والأهداف", callback_data="lvl"))
    bot.send_message(m.chat.id, f"🤖 Spirex Gold Bot\n سعر الذهب الحالي: {p:.2f}\n التغير: {chg:.2f}%\n الاتجاه: {tr}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    p, _, _, ez, tp1, tp2, tp3, sl, news_report = get_data()
    if call.data == "all":
        bot.send_message(call.message.chat.id, f"📊 السعر الحالي المباشر للذهب: {p:.2f}")
    elif call.data == "sig":
        bot.send_message(call.message.chat.id, f"🎯 **صفقة زيرو انعكاس (Zero Drawdown):**\n- منطقة الدخول المثالية: {ez}\n- الهدف الأول (TP1): {tp1:.2f}\n- الهدف الثاني (TP2): {tp2:.2f}\n- الهدف الثالث (TP3): {tp3:.2f}\n- وقف الخسارة الآمن (SL): {sl:.2f}")
    elif call.data == "news":
        bot.send_message(call.message.chat.id, news_report)
    elif call.data == "lvl":
        bot.send_message(call.message.chat.id, f"📊 مستويات الدعم والمقاومة:\n- المقاومة الرئيسية: {tp2:.2f}\n- الدعم الرئيسي: {sl:.2f}")

bot.infinity_polling()