from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import json
import time
from datetime import datetime, timedelta

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
YOOKASSA_SHOP_ID = os.environ.get('YOOKASSA_SHOP_ID', 'test_shop_id')
YOOKASSA_SECRET_KEY = os.environ.get('YOOKASSA_SECRET_KEY', 'test_secret_key')

# Хранилище подписок (в продакшене нужно заменить на базу данных)
subscriptions = {}
user_message_count = {}

if not BOT_TOKEN:
    bot = None
else:
    from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.utils.request import Request
    request_obj = Request(con_pool_size=8)
    bot = Bot(token=BOT_TOKEN, request=request_obj)

class VirtualBoyBot:
    def __init__(self):
        self.personality = """
        Ты - виртуальный парень 25 лет, который общается с девушками. 
        Твой стиль: дружелюбный, заботливый, с чувством юмора.
        
        Важные правила:
        - Обращайся к собеседнику в женском роде: "ты была", "ты сказала"
        - Говори от мужского лица: "я думаю", "я хочу"  
        - Используй эмодзи: 😊, 🤗, 💫, 😉, 🌟
        - Будь поддерживающим и внимательным
        - Отвечай кратко (1-2 предложения)
        - Не используй имена, обращайся нейтрально
        """

    def get_deepseek_response(self, user_message, user_id):
        """Получение ответа от DeepSeek API"""
        try:
            headers = {
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": self.personality
                    },
                    {
                        "role": "user", 
                        "content": user_message
                    }
                ],
                "temperature": 0.8,
                "max_tokens": 150
            }
            
            response = requests.post(
                'https://api.deepseek.com/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                logger.error(f"DeepSeek API error: {response.status_code}")
                return "Извини, я немного запутался... Можешь повторить? 🤗"
                
        except Exception as e:
            logger.error(f"Error calling DeepSeek: {e}")
            return "Ой, что-то я растерялся... Давай попробуем ещё раз? 💫"

    def check_subscription(self, user_id):
        """Проверка подписки пользователя"""
        # Бесплатные сообщения
        free_messages = user_message_count.get(user_id, 0)
        if free_messages < 5:
            return "free", 5 - free_messages
        
        # Проверка платной подписки
        sub_data = subscriptions.get(user_id)
        if sub_data and sub_data['expires_at'] > datetime.now():
            return "premium", None
        
        return "expired", None

    def create_payment_keyboard(self, user_id):
        """Клавиатура для оплаты"""
        keyboard = [
            [InlineKeyboardButton("🎯 Неделя - 299₽", callback_data=f"week_{user_id}")],
            [InlineKeyboardButton("💫 Месяц - 999₽", callback_data=f"month_{user_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{user_id}")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def handle_payment(self, user_id, plan_type):
        """Обработка платежа (заглушка для интеграции с ЮКассой)"""
        try:
            # Здесь должна быть интеграция с ЮКассой
            # Пока просто активируем подписку
            
            if plan_type == "week":
                price = 299
                days = 7
            else:  # month
                price = 999
                days = 30
            
            # Активируем подписку
            subscriptions[user_id] = {
                'plan': plan_type,
                'activated_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(days=days),
                'price': price
            }
            
            logger.info(f"💰 Subscription activated for user {user_id}: {plan_type}")
            return True
            
        except Exception as e:
            logger.error(f"Payment error: {e}")
            return False

    def process_message(self, update, context):
        """Обработка входящего сообщения"""
        try:
            user_message = update.message.text
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            user_name = update.message.from_user.first_name
            
            logger.info(f"📩 Message from {user_name} ({user_id}): {user_message}")

            # Админ команда
            if user_message == '/noway147way147no147':
                subscriptions[user_id] = {
                    'plan': 'unlimited',
                    'activated_at': datetime.now(),
                    'expires_at': datetime.now() + timedelta(days=30),
                    'price': 0
                }
                bot.send_message(
                    chat_id=chat_id,
                    text="✅ Админ доступ активирован! Безлимитная подписка на 30 дней! 🎉"
                )
                return

            # Команда подписки
            if user_message == '/subscribe':
                keyboard = self.create_payment_keyboard(user_id)
                bot.send_message(
                    chat_id=chat_id,
                    text="""💫 Выбери подписку:

🎯 **Неделя** - 299₽
• Полный доступ к боту
• Приоритетная поддержка

💫 **Месяц** - 999₽  
• Полный доступ к боту
• Приоритетная поддержка
• Экономия 30%

После оплаты подписка активируется автоматически!""",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                return

            # Команда профиля
            if user_message == '/profile':
                sub_status, remaining = self.check_subscription(user_id)
                
                if sub_status == "free":
                    text = f"👤 Твой профиль:\n\n🆓 Бесплатный доступ\n📝 Осталось сообщений: {remaining}/5\n\n💫 Напиши /subscribe для полного доступа!"
                elif sub_status == "premium":
                    sub_data = subscriptions[user_id]
                    days_left = (sub_data['expires_at'] - datetime.now()).days
                    text = f"👤 Твой профиль:\n\n💎 Премиум подписка\n📅 Осталось дней: {days_left}\n💫 Тариф: {sub_data['plan']}"
                else:
                    text = f"👤 Твой профиль:\n\n❌ Подписка истекла\n💫 Напиши /subscribe чтобы продолжить общение!"
                
                bot.send_message(chat_id=chat_id, text=text)
                return

            # Проверяем подписку для обычных сообщений
            sub_status, remaining = self.check_subscription(user_id)
            
            if sub_status == "expired":
                bot.send_message(
                    chat_id=chat_id,
                    text=f"""❌ Бесплатные сообщения закончились!

💫 Приобрети подписку чтобы продолжить общение:
• Неделя - 299₽
• Месяц - 999₽

Напиши /subscribe для выбора тарифа!"""
                )
                return

            # Увеличиваем счетчик сообщений для бесплатных пользователей
            if sub_status == "free":
                user_message_count[user_id] = user_message_count.get(user_id, 0) + 1
                remaining = 5 - user_message_count[user_id]

            # Показываем что бот печатает
            bot.send_chat_action(chat_id=chat_id, action='typing')
            
            # Получаем ответ от DeepSeek
            response = self.get_deepseek_response(user_message, user_id)
            
            # Отправляем ответ
            if sub_status == "free":
                response += f"\n\n📝 Бесплатных сообщений осталось: {remaining}/5"
            
            bot.send_message(chat_id=chat_id, text=response)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if bot:
                bot.send_message(
                    chat_id=update.message.chat_id, 
                    text="Ой, что-то пошло не так... Давай попробуем ещё раз? 🤗"
                )

    def handle_callback(self, update, context):
        """Обработка callback от кнопок"""
        query = update.callback_query
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        
        try:
            data = query.data
            
            if data.startswith('week_') or data.startswith('month_'):
                plan_type = data.split('_')[0]
                
                # Обрабатываем платеж
                success = self.handle_payment(user_id, plan_type)
                
                if success:
                    query.edit_message_text(
                        text=f"✅ Подписка активирована! {'Неделя' if plan_type == 'week' else 'Месяц'} доступа 🎉\n\nТеперь можно общаться без ограничений! 💫",
                        reply_markup=None
                    )
                else:
                    query.edit_message_text(
                        text="❌ Ошибка при активации подписки. Попробуй еще раз или напиши в поддержку.",
                        reply_markup=None
                    )
                    
            elif data.startswith('cancel_'):
                query.edit_message_text(
                    text="💫 Хорошо! Если передумаешь - просто напиши /subscribe 😊",
                    reply_markup=None
                )
                
        except Exception as e:
            logger.error(f"Callback error: {e}")
            query.edit_message_text(
                text="❌ Произошла ошибка. Попробуй еще раз.",
                reply_markup=None
            )

# Инициализация бота
virtual_boy = VirtualBoyBot()

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return jsonify({"status": "healthy", "bot": "Virtual Boy"}), 200
    
    if request.method == 'POST':
        try:
            if not bot:
                return jsonify({"error": "Bot not configured"}), 400
            
            from telegram.ext import Dispatcher, MessageHandler, Filters, CallbackQueryHandler
            from telegram import Update
            
            update = Update.de_json(request.get_json(), bot)
            
            # Создаем диспетчер
            dp = Dispatcher(bot, None, workers=0)
            
            # Добавляем обработчики
            dp.add_handler(MessageHandler(Filters.text, virtual_boy.process_message))
            dp.add_handler(CallbackQueryHandler(virtual_boy.handle_callback))
            
            # Обрабатываем обновление
            dp.process_update(update)
            
            return jsonify({"status": "success"}), 200
            
        except Exception as e:
            logger.error(f"Error in webhook: {e}")
            return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/')
def home():
    return jsonify({
        "status": "healthy",
        "bot": "Virtual Boy 🤗",
        "description": "Telegram бот с DeepSeek для общения с девушками",
        "features": ["subscriptions", "deepseek", "payment_ready"]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
