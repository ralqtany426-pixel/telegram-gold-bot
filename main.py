def background_monitor():
    time.sleep(10)
    while True:
        try:
            for name, sym in SYMBOLS.items():
                analysis = analyze_smc_setup(sym)
                if analysis and analysis["signal"] != "NONE":
                    current_state = analysis["signal"]
                    if current_state != last_states[name]:
                        last_states[name] = current_state
                        price = analysis["price"]
                        users = get_alert_users()

                        decimals = 4 if "EURUSD" in sym else 2

                        # --- حساب الأهداف بناءً على أسلوب SMC الحقيقي ---
                        if current_state == "BUY":
                            # وقف الخسارة يوضع تحت أدنى سعر لمنطقة الطلب
                            sl = round(analysis["demand_low"] - (150.0 if "BTC" in sym else (0.0010 if "EURUSD" in sym else 1.0)), decimals)
                            risk = price - sl
                            
                            # الأهداف تُحسب بناءً على حجم المخاطرة الحقيقي (R:R Ratio)
                            tp1 = round(price + (risk * 1.5), decimals) # عائد 1:1.5
                            tp2 = round(price + (risk * 3.0), decimals) # عائد 1:3
                            direction = "شراء (BUY) 📈"
                        else:
                            # وقف الخسارة يوضع فوق أعلى سعر لمنطقة العرض
                            sl = round(analysis["supply_high"] + (150.0 if "BTC" in sym else (0.0010 if "EURUSD" in sym else 1.0)), decimals)
                            risk = sl - price
                            
                            tp1 = round(price - (risk * 1.5), decimals)
                            tp2 = round(price - (risk * 3.0), decimals)
                            direction = "بيع (SELL) 📉"

                        msg = (
                            f"🚨 **تنبيه SMC احترافي (BOS + OB) على {name}** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 الصفقة: {direction}\n"
                            f"📍 سعر الدخول: `{price}`\n"
                            f"🧱 المنطقة المفعلة: `{analysis['demand'] if current_state == 'BUY' else analysis['supply']}`\n"
                            f"⛔ وقف الخسارة (SL): `{sl}`\n"
                            f"🎯 الهدف الأول (TP1): `{tp1}`\n"
                            f"🎯 الهدف الثاني (TP2): `{tp2}`\n\n"
                            f"💡 *نفذ الصفقة يدوياً من تطبيق MT5.*"
                        )

                        for chat_id in users:
                            try:
                                bot.send_message(chat_id, msg, parse_mode="Markdown")
                            except:
                                pass
            time.sleep(60)
        except Exception:
            time.sleep(60)