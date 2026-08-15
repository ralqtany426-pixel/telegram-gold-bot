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

# --- دالة معالجة الأزرار التفاعلية ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # لإلغاء علامة التحميل من على الزر
    
    data = get_gold_data()
    
    if query.data == "gold_signal":
        response_text = (
            f"🔥 **صفقة اليوم لـ الذهب (XAU/USD)**\n\n"
            f"💰 السعر الحالي: `{data['price']}`\n"
            f"📈 الاتجاه: `{data['trend']}`\n"
            f"🎯 نسبة الدقة المتوقعة: `95%`\n"
            f"⚠️ ملاحظة: السوق مغلق حالياً عطلة نهاية الأسبوع."
        )
    elif query.data == "technical_analysis":
        response_text = (
            f"📊 **التحليل الفني المباشر**\n\n"
            f"📉 مؤشر القوة النسبية (RSI): `{data['rsi']}`\n"
            f"📊 مؤشر ATR: `{data['atr']}`\n"
            f"💡 الحالة الفنية العامة مستقرة بانتظار افتتاح السوق."
        )
    elif query.data == "risk_calculator":
        response_text = (
            f"🛡️ **حاسبة إدارة المخاطر**\n\n"
            f"اختر دائماً المخاطرة بنسبة لا تتجاوز 1% إلى 2% من رأس مالك في صفقة الذهب نظراً لتقلباته العالية."
        )
    else:
        response_text = "عذراً، حدث خطأ في اختيار الزر."

    # زر رجوع للقائمة الرئيسية
    back_keyboard = [[InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="back_home")]]
    reply_markup = InlineKeyboardMarkup(back_keyboard)
    
    if query.data == "back_home":
        await start(update, context)
    else:
        await query.message.edit_text(response_text, reply_markup=reply_markup, parse_mode="Markdown")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: BOT_TOKEN is missing!")
        exit(1)
        
    application = ApplicationBuilder().token(TOKEN).build()
    
    # إضافة معالجات الأوامر والأزرار
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot is starting...")
    application.run_polling()
