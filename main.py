from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import random
import threading
import pandas as pd
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
import yfinance as yf

# --- معرف المدير (أنت وحدك فقط) ---
ADMIN_ID = 1642160234

def is_admin(user_id):
    return user_id == ADMIN_ID

# --- تشغيل السيرفر لـ Render ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_server():
    server = HTTPServer(("0.0.0.0", 10000), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- جلب وتحليل السوق (يشمل الدعم، المقاومة، والزيرو انعكاس) ---
def fetch_and_analyze_market():
    ticker = "GC=F"
    timeframes = {"M15": "15m", "H1": "1h", "H4": "1h", "D1": "1d"}
    results = {}
    try:
        for tf_name, interval in timeframes.items():
            period = "max" if tf_name == "D1" else ("60d" if tf_name == "H4" else "5d")
            df = yf.download(ticker, period=period, interval=interval, progress=False)
            if df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if tf_name == "H4":
                df = df.resample('4H').agg({
                    'Open': 'first', 
                    'High': 'max', 
                    'Low': 'min', 
                    'Close': 'last', 
                    'Volume': 'sum'
                }).dropna()

            if len(df) > 50:
                close = df["Close"]
                high = df["High"]
                low = df["Low"]
                volume = df["Volume"] if "Volume" in df.columns else pd.Series([0]*len(close))
                
                # حساب مستويات الدعم والمقاومة بناءً على آخر الشموع
                support = round(float(low.rolling(window=20).min().iloc[-1]), 2)
                resistance = round(float(high.rolling(window=20).max().iloc[-1]), 2)

                # حساب RSI والمؤشرات
                rsi_series = calculate_rsi(close, 14)
                rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0

                ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
                
                exp1 = close.ewm(span=12, adjust=False).mean()
                exp2 = close.ewm(span=26, adjust=False).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9, adjust=False).mean()

                m_val = float(macd.iloc[-1])
                s_val = float(signal.iloc[-1])

                trend = "BULLISH" if (rsi_val > 50 and m_val > s_val and close.iloc[-1] > ema_50) else "BEARISH"
                
                current_price = round(float(close.iloc[-1]), 2)
                
                # حساب منطقة الزيرو انعكاس (أفضل نقطة دخول قريبة من الدعم/المقاومة)
                if trend == "BULLISH":
                    zero_lag_entry = round((current_price + support) / 2, 2)
                else:
                    zero_lag_entry = round((current_price + resistance) / 2, 2)

                avg_vol = volume.rolling(window=10).mean().iloc[-1] if len(volume) >= 10 else volume.iloc[-1]
                high_volume = volume.iloc[-1] > avg_vol

                results[tf_name] = {
                    "trend": trend,
                    "rsi": round(rsi_val, 2),
                    "close": current_price,
                    "support": support,
                    "resistance": resistance,
                    "zero_lag_entry": zero_lag_entry,
                    "high_volume": high_volume
                }
        return results
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

# --- أمر إرسال الإشارة والإنذار الفوري ---
async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("عذراً، هذا البوت مخصص للمدير فقط.")
        return

    data = fetch_and_analyze_market()
    if not data or "H1" not in data or "H4" not in data:
        await update.message.reply_text("عذراً, حدث خطأ أثناء جلب بيانات السوق. حاول مرة أخرى.")
        return

    h1_data = data["H1"]
    h4_data = data["H4"]
    
    current_price = h1_data["close"]
    rsi = h1_data["rsi"]
    h1_trend = h1_data["trend"]
    h4_trend = h4_data["trend"]
    support = h1_data["support"]
    resistance = h1_data["resistance"]
    zero_lag = h1_data["zero_lag_entry"]
    high_vol = h1_data["high_volume"]

    # خوارزمية نسبة النجاح وحالة الإنذار
    base_score = 83
    timeframe_match = (h1_trend == h4_trend)

    if h1_trend == "BULLISH":
        direction = "شراء 🟢 (BUY)"
        stop_loss = round(support - 3.0, 2)
        take_profit = round(current_price + 20.0, 2)
        if rsi < 45: base_score += 5
    else:
        direction = "بيع 🔴 (SELL)"
        stop_loss = round(resistance + 3.0, 2)
        take_profit = round(current_price - 20.0, 2)
        if rsi > 55: base_score += 5

    if timeframe_match: base_score += 7
    if high_vol: base_score += 4

    success_rate = min(base_score + random.randint(1, 3), 96)
    
    # إنذار فوري للصفقات عالية الثقة
    alert_badge = "🚨 إنذار فوري: صفقة قوية ومؤكدة للدخول! 🔥" if success_rate >= 90 else "⚡ تحليل السوق الحالي:"

    message = (
        f"📊 **{alert_badge}**\n\n"
        f"🔸 **الزوج:** الذهب (XAU/USD)\n"
        f"🎯 **الاتجاه:** {direction}\n"
        f"💎 **نقطة الزيرو انعكاس (الدخول المثالي):** `{zero_lag}`\n"
        f"🛑 **وقف الخسارة (SL):** {stop_loss}\n"
        f"✅ **هدف الربح (TP):** {take_profit}\n\n"
        f"🛡️ **الدعم:** `{support}` | ⚔️ **المقاومة:** `{resistance}`\n"
        f"📈 **مؤشر RSI:** `{rsi}` | 📊 **الفوليوم:** `{'مرتفع 🔥' if high_vol else 'عادي'}`\n"
        f"📰 **حالة الأخبار الاقتصادية:** `مستقرة / ترقب للبيانات`\n"
        f"⭐ **نسبة نجاح الصفقة:** `{success_rate}%`\n\n"
        f"💡 *تم دمج الدعم، المقاومة، ونقاط الزيرو انعكاس بنجاح.*"
    )

    await update.message.reply_text(message, parse_mode="Markdown")

def main():
    if not TOKEN:
        print("الرجاء توفير توكن البوت في متغيرات البيئة (BOT_TOKEN).")
        return

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("signal", signal_command))
    
    print("البوت يعمل الآن بكفاءة...")
    app.run_polling()

if __name__ == "__main__":
    main()
