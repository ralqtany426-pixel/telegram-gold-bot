def risk_management_filter(market_trend: str, signal_type: str) -> dict:
    """
    فلتر إدارة المخاطر الخارق لتحديد ما إذا كانت الصفقة مقبولة أم مرفوضة بناءً على اتجاه السوق.
    :param market_trend: اتجاه السوق ("Bullish" أو "Bearish")
    :param signal_type: نوع الصفقة الواردة ("BUY" أو "SELL")
    :return: قاموس يحتوي على حالة القبول والتوجيه المناسب
    """
    market_trend = market_trend.capitalize()
    signal_type = signal_type.upper()
    
    if market_trend == "Bullish":
        if signal_type == "BUY":
            return {
                "status": "APPROVED",
                "message": "🟢 تم قبول الصفقة: السوق صاعد، والتوجه مخصص للشراء فقط مع التيار."
            }
        else:
            return {
                "status": "REJECTED",
                "message": "🚫 تم التحفظ على صفقة البيع: السوق تحت سيطرة الاتجاه الصاعد وصانع السوق يدفع للأعلى."
            }
            
    elif market_trend == "Bearish":
        if signal_type == "SELL":
            return {
                "status": "APPROVED",
                "message": "🔴 تم قبول الصفقة: السوق هابط، والتوجه مخصص للبيع فقط لحين اكتمال الارتداد."
            }
        else:
            return {
                "status": "REJECTED",
                "message": "🚫 تم التحفظ على صفقة الشراء: السوق تحت سيطرة الاتجاه الهابط والسيولة المؤسسية تعاكس الشراء."
            }
            
    else:
        return {
            "status": "UNKNOWN",
            "message": "⚠️ اتجاه السوق غير مألوف، يرجى التحقق من حالة السوق."
        }

# --- مثال تجريبي للاختبار ---
# حالياً السوق صاعد (Bullish) ووصلتنا إشارة شراء (BUY)
current_market = "Bullish"
incoming_signal = "BUY"

result = risk_management_filter(current_market, incoming_signal)
print(result["message"])