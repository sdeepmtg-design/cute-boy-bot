import requests
import base64
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class YookassaPayment:
    def __init__(self, shop_id, secret_key):
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.base_url = "https://api.yookassa.ru/v3"
        
        # Базовая авторизация
        credentials = f"{shop_id}:{secret_key}"
        self.auth_header = f"Basic {base64.b64encode(credentials.encode()).decode()}"
        
        self.headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/json',
            'Idempotence-Key': ''
        }

    def generate_idempotence_key(self):
        """Генерация уникального ключа идемпотентности"""
        return f"key_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    def create_payment_link(self, amount, description, user_id, plan_type):
        """Создание платежа в ЮKassa и получение ссылки на оплату"""
        try:
            # Получаем URL приложения из переменных окружения
            app_url = os.environ.get('APP_URL', 'https://your-app.onrender.com')
            
            # Подготавливаем данные для платежа
            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "payment_method_data": {
                    "type": "bank_card"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"{app_url}/payment-success"  # Правильный URL для возврата
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": str(user_id),
                    "plan_type": plan_type,
                    "bot_name": "Virtual Boy"
                }
            }
            
            # Генерируем уникальный ключ для этого запроса
            idempotence_key = self.generate_idempotence_key()
            self.headers['Idempotence-Key'] = idempotence_key
            
            logger.info(f"Creating payment for user {user_id}, amount: {amount} RUB")
            logger.info(f"Return URL: {payment_data['confirmation']['return_url']}")
            
            # Отправляем запрос к API ЮKassa
            response = requests.post(
                f"{self.base_url}/payments",
                headers=self.headers,
                json=payment_data,
                timeout=30
            )
            
            if response.status_code == 200:
                payment_info = response.json()
                
                if payment_info.get('status') == 'pending':
                    confirmation_url = payment_info['confirmation']['confirmation_url']
                    payment_id = payment_info['id']
                    
                    logger.info(f"Payment created successfully: {payment_id}")
                    
                    payment_message = f"""💳 *ОПЛАТА ПОДПИСКИ*

📋 *Детали:*
• Сумма: {amount} рублей
• Описание: {description}

Для завершения оплаты перейдите по ссылке ниже:

[🔗 Перейти к оплате]({confirmation_url})

*После успешной оплаты подписка активируется автоматически.*"""
                    
                    return {
                        "success": True,
                        "message": payment_message,
                        "payment_id": payment_id,
                        "confirmation_url": confirmation_url
                    }
                else:
                    logger.error(f"Unexpected payment status: {payment_info.get('status')}")
                    return {
                        "success": False,
                        "error": f"Неожиданный статус платежа: {payment_info.get('status')}"
                    }
            else:
                error_text = response.text
                logger.error(f"Yookassa API error: {response.status_code} - {error_text}")
                return {
                    "success": False,
                    "error": f"Ошибка API ЮKassa: {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error while creating payment: {e}")
            return {
                "success": False,
                "error": "Ошибка сети при создании платежа"
            }
        except Exception as e:
            logger.error(f"Unexpected error in create_payment: {e}")
            return {
                "success": False,
                "error": "Неожиданная ошибка при создании платежа"
            }

    def get_payment_status(self, payment_id):
        """Получение статуса платежа"""
        try:
            idempotence_key = self.generate_idempotence_key()
            self.headers['Idempotence-Key'] = idempotence_key
            
            response = requests.get(
                f"{self.base_url}/payments/{payment_id}",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                payment_info = response.json()
                return {
                    "success": True,
                    "status": payment_info.get('status'),
                    "paid": payment_info.get('paid', False),
                    "amount": payment_info.get('amount', {}),
                    "metadata": payment_info.get('metadata', {})
                }
            else:
                logger.error(f"Error getting payment status: {response.status_code}")
                return {
                    "success": False,
                    "error": f"Ошибка получения статуса: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"Error in get_payment_status: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def create_payment_test(self, amount, description, user_id, plan_type):
        """Тестовый метод для создания платежа (используется если нет реальных ключей)"""
        logger.info(f"TEST MODE: Creating payment for user {user_id}, amount: {amount}")
        
        test_message = f"""💳 *ТЕСТОВЫЙ РЕЖИМ ОПЛАТЫ*

📋 *Детали:*
• Сумма: {amount} рублей
• Описание: {description}
• Пользователь: {user_id}
• Тариф: {plan_type}

*ВНИМАНИЕ:* Это тестовый режим. Для реальных платежей необходимо настроить ключи ЮKassa."""

        return {
            "success": True,
            "message": test_message,
            "payment_id": f"test_payment_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "confirmation_url": "https://yookassa.ru/test"
        }

# Функция для проверки конфигурации
def check_yookassa_config(shop_id, secret_key):
    """Проверка корректности конфигурации ЮKassa"""
    if not shop_id or shop_id == 'test_shop_id':
        logger.warning("Yookassa shop_id not configured, using test mode")
        return False
        
    if not secret_key or secret_key == 'test_secret_key':
        logger.warning("Yookassa secret_key not configured, using test mode")
        return False
        
    # Проверяем формат ключа (должен начинаться с test_ или live_)
    if secret_key.startswith('test_') or secret_key.startswith('live_'):
        logger.info("Yookassa credentials appear valid")
        return True
    else:
        logger.warning("Yookassa secret_key format is invalid, using test mode")
        return False
