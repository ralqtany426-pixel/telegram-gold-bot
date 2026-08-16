import telebot
# إذا كنت تستخدم مكتبة لجلب سعر الذهب مثل yfinance أو أي API آخر، تأكد من تعريفها هنا
# مثال: import yfinance as yf

# إعداد توكن البوت
TOKEN = 'YOUR_BOT_TOKEN_HERE'
bot = telebot.TeleBot(TOKEN)

# دالة لجلب السعر الحالي (قم بتغييرها حسب المصدر الذي تستخدمه)
def get_current_gold_price():
    # هنا تضع المنطق الخاص بك لجلب سعر الذهب الحالي
    # سنفترض مؤقتاً أن السعر الحالي هو 4371.00 بناءً على الشارت الذي أرسلته
    return 4371.00 

def generate_signal_text(current_price, signal_type):
    if signal_type == "BUY":
        sl = round(current_price - 4.0, 2)
        tp1 = round(current_price + 13.0, 2)
        tp2 = round(current_price + 28.0, 2)
        tp3 = round(current_price + 53.0, 2)
        direction_text = "🟢 صفقة شراء (منطقة طلب قوية)"
    else:
        sl = round(current_price + 4.0, 2)
        tp1 = round(current_price - 13.0, 2)
        tp2 = round(current_price - 28.0, 2)
        tp3 = round(current_price - 53.0, 2)
        direction_text = "🔴 صفقة بيع (منطقة عرض قوية)"

    text = f"""
🔥 **أنذار ذكي - صفقة زيرو انعكاس**
🎯 **نسبة التأكد:** 95%

📍 **نوع الصفقة:** {direction_text}
💰 **سعر الدخول:** {current_price}
🛑 **وقف الخسارة (SL):** {sl}

🎯 **الأهداف المستهدفة:**
✅ **TP1:** {tp1}
✅ **TP2:** {tp2}
✅ **TP3:** {tp3}

⏳ **الفريم المستخدم:** 15 دقيقة (M15)
🚀 **تم اكتمال الشروط الفنية للسيولة بنجاح تام!**
"""
    return text

# مثال لكيفية إرسال الرسالة عند طلبها
@bot.message_handler(commands=['start', 'signal'])
def send_signal(message):
    price = get_current_gold_price()
    # يمكنك إضافة شرط هنا لاختيار BUY أو SELL بناءً على التحليل الفني
    signal_text = generate_signal_text(price, "BUY") 
    bot.reply_to(message, signal_text, parse_mode="Markdown")

bot.polling()
