
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- تشغيل السيرفر الوهمي لفتح البورت المطلوب لـ Render ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_server():
    server = HTTPServer(('0.0.0.0', 10000), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()
# ----------------------------------------------------

# Token Telegram
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")

def get_gold_data():
    """جلب بيانات الذهب وتوليد إشارة"""
    price = 4375.63
    atr = 12.0
    return {
        "price": price,
        "rsi": 42.5,
        "trend": "BULLISH",
        "atr": atr,
        "status": "SUCCESS"
    }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "🤖 **مرحباً بك في Spirex AI Gold Trader**\n\n"
        "منستك الذكية لتداول الذهب (XAU/USD).\n\n"
        "اختر أحد الخيارات للبدء:"
    )
    keyboard = [
        [InlineKeyboardButton("🔥 صفقة اليوم (95% Signal)", callback_data="gold_signal")],
        [InlineKeyboardButton("📊 التحليل الفني المباشر", callback_data="technical_analysis")],
        [InlineKeyboardButton("🛡️ حاسبة إدارة المخاطر", callback_data="risk_calculator")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.edit_text(welcome_msg, reply_markup=reply_markup, parse_mode="Markdown")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: BOT_TOKEN is missing!")
        exit(1)
        
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    print("Bot is starting...")
    application.run_polling()
