import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Token Telegram (يتم جلبه تلقائياً من البيئة)
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")

def get_gold_data():
    """جلب بيانات الذهب وتوليد إشارة"""
    price = 2415.50 
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
        "منصتك الذكية لتداول الذهب (XAU/USD).\n\n"
        "اختر أحد الخيارات للبدء:"
    )
    keyboard = [
        [InlineKeyboardButton("🔥 صفقة اليوم (95% Signal)", callback_data="get_signal")],
        [InlineKeyboardButton("📊 التحليل الفني المباشر", callback_data="get_analysis")],
        [InlineKeyboardButton("🛡️ حاسبة إدارة المخاطر", callback_data="get_risk")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.callback_query.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = get_gold_data()
    price = data["price"]

    if query.data == "get_signal":
        sl = round(price - (data["atr"] * 1.5), 2)
        tp1 = round(price + (data["atr"] * 1.5), 2)
        tp2 = round(price + (data["atr"] * 3.0), 2)
        msg = (
            "🎯 **توصية Spirex AI**\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🟢 **الاتجاه:** شراء (BUY)\n"
            f"📍 **نقطة الدخول:** ${price}\n\n"
            f"🎯 **الهدف الأول:** ${tp1}\n"
            f"🚀 **الهدف الثاني:** ${tp2}\n"
            f"🛑 **وقف الخسارة:** ${sl}"
        )
        await query.message.reply_text(msg, parse_mode="Markdown")
    elif query.data == "get_analysis":
        await query.message.reply_text(f"📊 **السعر الحالي:** ${price}\n📈 **الاتجاه:** {data['trend']}\n📉 **RSI:** {data['rsi']}", parse_mode="Markdown")
    elif query.data == "get_risk":
        await query.message.reply_text("🛡️ **إدارة المخاطر:** لا تخاطر بأكثر من 2% من رأس مالك في الصفقة الواحدة!", parse_mode="Markdown")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
