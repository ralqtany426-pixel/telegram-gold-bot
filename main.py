import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# وضع توكن البوت الخاص بك هنا
TOKEN = "ضع_توكن_البوت_هنا"
bot = telebot.TeleBot(TOKEN)

# قائمة الأزرار التفاعلية (Spirex AI)
def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🔥 صفقة الذهب الاحترافية", callback_data="gold_signal"))
    markup.row(InlineKeyboardButton("📉 إنذار صفقة زيرو العكاس (95%)", callback_data="zero_signal"))
    markup.row(InlineKeyboardButton("📰 التقرير الأخبار وتأثيرها", callback_data="eco_news"))
    markup.row(InlineKeyboardButton("📊 مناطق الدعم والمقاومة", callback_data="support_resistance"))
    markup.row(InlineKeyboardButton("🛡️ حاسبة إدارة المخاطر", callback_data="risk_calculator"))
    return markup

# رسالة البداية عند كتابة /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_msg = (
        "🤖 **Spirex AI Gold Professional** - النظام الذكي المتقدم\n\n"
        "أهلاً بك عزيزي المتداول. تم تفعيل تحليلات الأطر الأربعة ومؤشرات RSI و MACD.\n"
        "اختر الخدمة المطلوبة:"
    )
    bot.send_message(message.chat.id, welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

# التعامل مع الضغط على الأزرار
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "gold_signal":
        bot.answer_callback_query(call.id, "جاري تحليلات صفقات الذهب الاحترافية...")
        bot.send_message(call.message.chat.id, "📊 جاري فحص أطر الذهب وتوليد التوصية...")
    elif call.data == "zero_signal":
        bot.answer_callback_query(call.id, "جاري البحث عن صفقة زيرو انعكاس...")
    elif call.data == "eco_news":
        bot.answer_callback_query(call.id, "جاري جلب التقارير والأخبار الاقتصادية...")
    elif call.data == "support_resistance":
        bot.answer_callback_query(call.id, "جاري حساب مستويات الدعم والمقاومة...")
    elif call.data == "risk_calculator":
        bot.answer_callback_query(call.id, "فتح حاسبة إدارة المخاطر...")

# تشغيل البوت باستمرار
print("Bot is running...")
bot.infinity_polling()
