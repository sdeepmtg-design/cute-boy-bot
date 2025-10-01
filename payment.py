import requests
import json
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class YookassaPayment:
    def __init__(self, shop_id, secret_key):
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.base_url = "https://api.yookassa.ru/v3"

    def create_payment(self, amount, description, user_id, plan_type):
        """Создание платежа в ЮКассе"""
        try:
            payment_id = str(uuid.uuid4())
            amount_kopecks = str(int(amount * 100))
            
            # ЗАМЕНИ virtual_boy_friend_bot на username твоего бота!
            bot_username = "Boyfriendcute_bot"
            
            payload = {
                "amount": {
                    "value": amount_kopecks,
                    "currency": "RUB"
                },
                "payment_method_data": {
                    "type": "bank_card"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"https://t.me/{bot_username}?start=payment_success_{user_id}"
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": user_id,
                    "plan_type": plan_type,
                    "payment_id": payment_id
                }
            }
            
            headers = {
                "Content-Type": "application/json",
                "Idempotence-Key": payment_id
            }
            
            auth = (self.shop_id, self.secret_key)
            
            response = requests.post(
                f"{self.base_url}/payments",
                json=payload,
                headers=headers,
                auth=auth,
                timeout=30
            )
            
            if response.status_code == 200:
                payment_data = response.json()
                logger.info(f"Payment created: {payment_data['id']}")
                return {
                    "success": True,
                    "payment_id": payment_data['id'],
                    "confirmation_url": payment_data['confirmation']['confirmation_url'],
                    "status": payment_data['status']
                }
            else:
                logger.error(f"Yookassa API error: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
                
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            return {"success": False, "error": str(e)}

    def check_payment_status(self, payment_id):
        """Проверка статуса платежа"""
        try:
            headers = {
                "Content-Type": "application/json"
            }
            
            auth = (self.shop_id, self.secret_key)
            
            response = requests.get(
                f"{self.base_url}/payments/{payment_id}",
                headers=headers,
                auth=auth,
                timeout=30
            )
            
            if response.status_code == 200:
                payment_data = response.json()
                return {
                    "success": True,
                    "status": payment_data['status'],
                    "paid": payment_data['paid'],
                    "metadata": payment_data.get('metadata', {})
                }
            else:
                return {"success": False, "error": response.text}
                
        except Exception as e:
            logger.error(f"Error checking payment: {e}")
            return {"success": False, "error": str(e)}

    def create_payment_link(self, amount, description, user_id, plan_type):
        """Создание ссылки на оплату для Telegram"""
        payment_result = self.create_payment(amount, description, user_id, plan_type)
        
        if payment_result["success"]:
            confirmation_url = payment_result["confirmation_url"]
            
            payment_message = f"""
💫 *Оплата подписки*

📋 **Тариф**: {description}
💎 **Сумма**: {amount}₽

👉 [Оплатить онлайн]({confirmation_url})

После оплаты подписка активируется автоматически! ✅

💳 *Тестовая карта*:
`5555 5555 5555 4477`
Срок: 01/30, CVV: 123
            """
            
            return {
                "success": True,
                "message": payment_message,
                "payment_id": payment_result["payment_id"],
                "confirmation_url": confirmation_url
            }
        else:
            return payment_result
