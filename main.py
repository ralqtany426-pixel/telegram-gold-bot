import time

def risk_management_filter(market_trend: str, signal_type: str) -> dict:
    market_trend = market_trend.capitalize()
    signal_type = signal_type.upper()
    
    if market_trend == "Bullish" and signal_type == "BUY":
        return {"status": "APPROVED", "message": "🟢 تم قبول الصفقة: السوق صاعد للشراء فقط."}
    elif market_trend == "Bearish" and signal_type == "SELL":
        return {"status": "APPROVED", "message": "🔴 تم قبول الصفقة: السوق هابط للبيع فقط."}
    else:
        return {"status": "REJECTED", "message": "🚫 تم التحفظ على الصفقة عكس الاتجاه."}

if __name__ == "__main__":
    print("🤖 بوت إدارة المخاطر يعمل الآن ومستعد لفحص السوق...")
    
    while True:
        # هنا يتم فحص السوق باستمرار لضمان عدم إغلاق السيرفر على Render
        current_market = "Bullish"
        incoming_signal = "BUY"
        
        result = risk_management_filter(current_market, incoming_signal)
        print(result["message"])
        
        # الانتظار لمدة 60 ثانية قبل الفحص التالي
        time.sleep(60)