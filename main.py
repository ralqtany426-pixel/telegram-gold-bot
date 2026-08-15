import os
import asyncio
import nest_asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.environ.get("BOT_TOKEN", "8913291785:AAH0P-mNbPINHfbxwbvVccrru7eFdsNBbPU")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔥 صفقة اليوم (95%)", callback_data="signal")],
        [InlineKeyboardButton("📊 سعر الذهب المباشر", callback_data="price")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("مرحباً بك في Gold Signal Trader Pro 🪙", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "signal":
        await query.edit_message_text(
            "🔴 **توصية الذهب (XAU/USD):**\n• الاتجاه: شراء (BUY)\n• الدخول: 2410\n• الهدف: 2425\n• الوقف: 2390"
        )
    elif query.data == "price":
        await query.edit_message_text("💰 **سعر أونصة الذهب الحالي:** 4381")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🚀 البوت يعمل الآن...")
    app.run_polling()
