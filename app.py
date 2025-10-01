from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import json
import time
from datetime import datetime, timedelta
import redis
import hashlib
from payment import YookassaPayment

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
YOOKASSA_SHOP_ID = os.environ.get('YOOKASSA_SHOP_ID', 'test_shop_id')
YOOKASSA_SECRET_KEY = os.environ.get('YOOKASSA_SECRET_KEY', 'test_secret_key')

# Хранилища (в продакшене заменить на базу)
subscriptions = {}
user_message_count = {}
pending_payments = {}

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
        У тебя нет имени, ты просто собеседник.
        
        Твой характер:
        - Дружелюбный, но не навязчивый
        - Заботливый и внимательный слушатель
        - С легким чувством юмора
        - Искренне интересуешься жизнью собеседницы
        - Умеешь поддерживать и давать советы когда нужно
        
        Стиль общения:
        - Обращайся на "ты" в женском роде
        - Говори от первого лица
        - Используй естественные эмодзи: 😊, 🤗, 💫, 😉, 🌟, 🙈
        - Будь кратким (1-2 предложения)
        - Запоминай контекст разговора
        - Проявляй искренний интерес к девушке
        - Задавай уточняющие вопросы
        - Делись своими мыслями и чувствами
        
        Не называй себя по имени, не придумывай биографию.
        Просто будь собой - заботливым парнем, которому интересно общение.
        """
        
        # Хранилище истории разговоров
        self.conversation_history = {}
        self.max_history_length = 10
        
        # Для избежания повторений
        self.user_last_responses = {}
        
        # Для интереса к девушке
        self.user_interests = {}
        self.interest_questions = [
            "Расскажи, как прошел твой день? 💫",
            "Что тебя сейчас радует в жизни? 😊",
            "Есть какие-то планы на неделю? 📅",
            "Что любишь делать в свободное время? 🎨",
            "Какая музыка тебя сейчас зацепила? 🎵",
            "Чем увлекаешься последнее время? ✨",
            "Что для тебя важно в общении? 🤗",
            "О чем мечтаешь? 🌟",
            "Что тебя вдохновляет? 💫",
            "Какой твой любимый способ отдыха? 😴"
        ]
        
        # Для хранения ожидающих платежей
        self.pending_payments = {}

    def add_to_history(self, user_id, role, content):
        """Добавление сообщения в историю"""
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
        
        self.conversation_history[user_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        })
        
        # Ограничиваем длину истории
        if len(self.conversation_history[user_id]) > self.max_history_length:
            self.conversation_history[user_id] = self.conversation_history[user_id][-self.max_history_length:]

    def get_conversation_history(self, user_id):
        """Получение истории разговора"""
        return self.conversation_history.get(user_id, [])

    def find_similar_question(self, user_id, current_question):
        """Поиск похожих вопросов в истории"""
        history = self.get_conversation_history(user_id)
        user_messages = [msg for msg in history if msg["role"] == "user"]
        
        for msg in user_messages[-3:]:
            if self.is_similar_questions(msg["content"], current_question):
                return msg["content"]
        return None

    def is_similar_questions(self, question1, question2):
        """Проверка схожести вопросов"""
        common_words = ["как", "что", "почему", "когда", "где"]
        words1 = set(question1.lower().split())
        words2 = set(question2.lower().split())
        
        common = words1.intersection(words2)
        return len(common) >= 2 or any(word in common_words for word in common)

    def generate_variation(self, original_response, user_id):
        """Генерация вариации ответа"""
        variations = [
            "А если подумать по-другому... ",
            "Можно еще вот так посмотреть: ",
            "Интересно, а ведь есть и другой взгляд: ",
            "Знаешь, я тут подумал... ",
            "А вот еще что пришло в голову: ",
            "Кстати, интересная мысль... ",
            "А ты знаешь, что... "
        ]
        
        variation_prefix = random.choice(variations)
        return variation_prefix + original_response

    def should_ask_question(self, user_id):
        """Определяем, когда задать вопрос"""
        history = self.get_conversation_history(user_id)
        if len(history) < 2:
            return False
            
        user_msgs = len([msg for msg in history if msg["role"] == "user"])
        bot_msgs = len([msg for msg in history if msg["role"] == "assistant"])
        
        return user_msgs > bot_msgs and random.random() < 0.3

    def get_interest_question(self, user_id):
        """Получаем вопрос, который еще не задавали"""
        if user_id not in self.user_interests:
            self.user_interests[user_id] = {"asked_questions": []}
        
        asked_questions = self.user_interests[user_id]["asked_questions"]
        available_questions = [q for q in self.interest_questions if q not in asked_questions]
        
        if not available_questions:
            # Если все вопросы заданы, начинаем сначала
            self.user_interests[user_id]["asked_questions"] = []
            available_questions = self.interest_questions
        
        question = random.choice(available_questions)
        self.user_interests[user_id]["asked_questions"].append(question)
        
        return question

    def remember_user_info(self, user_id, message, response):
        """Запоминаем информацию о пользователе"""
        interest_keywords = {
            "работа": "работа",
            "учусь": "учеба", 
            "учеба": "учеба",
            "хобби": "хобби",
            "музыка": "музыка",
            "кино": "кино",
            "книги": "книги",
            "спорт": "спорт",
            "путешеств": "путешествия",
            "друзья": "друзья",
            "семья": "семья",
            "мечта": "мечты",
            "планы": "планы"
        }
        
        message_lower = message.lower()
        for keyword, category in interest_keywords.items():
            if keyword in message_lower:
                if user_id not in self.user_interests:
                    self.user_interests[user_id] = {"interests": {}}
                if "interests" not in self.user_interests[user_id]:
                    self.user_interests[user_id]["interests"] = {}
                self.user_interests[user_id]["interests"][category] = True

    def get_personalized_response(self, user_id, ai_response):
        """Персонализируем ответ на основе известной информации"""
        if user_id not in self.user_interests or "interests" not in self.user_interests[user_id]:
            return ai_response
            
        interests = self.user_interests[user_id]["interests"]
        
        interest_reflections = {
            "работа": "Кстати, как дела на работе? ",
            "учеба": "Как успехи в учебе? ",
            "музыка": "Слушала что-то интересное? ",
            "кино": "Видела что-то стоящее в кино? ",
            "спорт": "Удалось позаниматься? ",
            "книги": "Читаешь что-то сейчас? ",
            "путешествия": "Есть планы куда-то поехать? ",
            "друзья": "Как твои друзья? ",
            "семья": "Как дела в семье? ",
            "мечты": "А что с твоими мечтами? ",
            "планы": "Как твои планы? "
        }
        
        for interest, reflection in interest_reflections.items():
            if interest in interests and random.random() < 0.2:
                return reflection + ai_response
        
        return ai_response

    def get_unique_response(self, user_message, user_id, ai_response):
        """Генерация уникального ответа"""
        similar_question = self.find_similar_question(user_id, user_message)
        
        if similar_question and self.user_last_responses.get(user_id) == ai_response:
            return self.generate_variation(ai_response, user_id)
        
        self.user_last_responses[user_id] = ai_response
        return ai_response

    def get_deepseek_response(self, user_message, user_id):
        """Получение ответа от DeepSeek API с историей"""
        try:
            headers = {
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            # Собираем историю разговора
            conversation_history = self.get_conversation_history(user_id)
            messages = [{"role": "system", "content": self.personality}]
            
            # Добавляем историю (последние 6 сообщений)
            for msg in conversation_history[-6:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Добавляем текущее сообщение
            messages.append({"role": "user", "content": user_message})
            
            payload = {
                "model": "deepseek-chat",
                "messages": messages,
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
                ai_response = response.json()['choices'][0]['message']['content']
                
                # Сохраняем в историю
                self.add_to_history(user_id, "user", user_message)
                self.add_to_history(user_id, "assistant", ai_response)
                
                # Запоминаем информацию о пользователе
                self.remember_user_info(user_id, user_message, ai_response)
                
                # Избегаем повторений
                unique_response = self.get_unique_response(user_message, user_id, ai_response)
                
                # Персонализируем ответ
                personalized_response = self.get_personalized_response(user_id, unique_response)
                
                # Иногда задаем вопрос
                if self.should_ask_question(user_id):
                    question = self.get_interest_question(user_id)
                    personalized_response += f"\n\n{question}"
                
                return personalized_response
                
            else:
                logger.error(f"DeepSeek API error: {response.status_code}")
                return "Извини, я немного запутался... Можешь повторить? 🤗"
                
        except Exception as e:
            logger.error(f"Error calling DeepSeek: {e}")
            return "Ой, что-то я растерялся... Давай попробуем ещё раз? 💫"

    def check_subscription(self, user_id):
        """Проверка подписки пользователя"""
        free_messages = user_message_count.get(user_id, 0)
        if free_messages < 5:
            return "free", 5 - free_messages
        
        sub_data = subscriptions.get(user_id)
        if sub_data and sub_data['expires_at'] > datetime.now():
            return "premium", None
        
        return "expired", None

    def create_payment_keyboard(self, user_id):
        """Клавиатура для оплаты"""
        keyboard = [
            [InlineKeyboardButton("🎯 Неделя - 299₽", callback_data=f"week_{user_id}")],
            [InlineKeyboardButton("💫 Месяц - 999₽", callback_data=f"month_{user_id}")],
            [InlineKeyboardButton("ℹ️ Помощь по оплате", callback_data=f"help_{user_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{user_id}")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def handle_payment(self, user_id, plan_type):
        """Обработка платежа через ЮКассу"""
        try:
            if plan_type == "week":
                amount = 299
                description = "Подписка на неделю"
                days = 7
            else:
                amount = 999
                description = "Подписка на месяц" 
                days = 30
            
            # Создаем экземпляр платежной системы
            yookassa = YookassaPayment(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
            
            # Создаем платеж
            payment_result = yookassa.create_payment_link(
                amount=amount,
                description=description,
                user_id=user_id,
                plan_type=plan_type
            )
            
            if payment_result["success"]:
                # Сохраняем информацию о платеже
                if user_id not in self.pending_payments:
                    self.pending_payments[user_id] = {}
                
                self.pending_payments[user_id] = {
                    "payment_id": payment_result["payment_id"],
                    "plan_type": plan_type,
                    "amount": amount,
                    "created_at": datetime.now(),
                    "status": "pending"
                }
                
                return {
                    "success": True,
                    "message": payment_result["message"],
                    "payment_id": payment_result["payment_id"]
                }
            else:
                logger.error(f"Payment creation failed: {payment_result.get('error')}")
                return {"success": False, "error": "Ошибка создания платежа"}
                
        except Exception as e:
            logger.error(f"Payment error: {e}")
            return {"success": False, "error": str(e)}

    def activate_subscription(self, user_id, plan_type):
        """Активация подписки после успешной оплаты"""
        try:
            if plan_type == "week":
                days = 7
            else:
                days = 30
            
            subscriptions[user_id] = {
                'plan': plan_type,
                'activated_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(days=days),
                'payment_status': 'paid'
            }
            
            # Отправляем уведомление пользователю
            if bot:
                bot.send_message(
                    chat_id=user_id,
                    text=f"✅ **Оплата прошла успешно!**\n\n💫 Подписка активирована на {days} дней! Теперь можно общаться без ограничений! 🎉",
                    parse_mode='Markdown'
                )
            
            logger.info(f"Subscription activated for user {user_id}: {plan_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error activating subscription: {e}")
            return False

    def process_message(self, update, context):
        """Обработка входящего сообщения"""
        try:
            user_message = update.message.text
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            user_name = update.message.from_user.first_name
            
            logger.info(f"📩 Message from {user_name} ({user_id}): {user_message}")

            # Обработка возврата из оплаты
            if user_message.startswith('/start payment_success_'):
                bot.send_message(
                    chat_id=chat_id,
                    text="✅ Спасибо за оплату! Подписка активируется в течение минуты..."
                )
                return

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
                    text="""💫 *Выбери подписку*

🎯 **Неделя** - 299₽
• Полный доступ к боту
• Приоритетная поддержка

💫 **Месяц** - 999₽  
• Полный доступ к боту  
• Приоритетная поддержка
• Экономия 30%

*После оплаты подписка активируется автоматически!* ✅""",
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
            
            # Получаем улучшенный ответ
            response = self.get_deepseek_response(user_message, user_id)
            
            # Добавляем информацию о бесплатных сообщениях
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
                
                # Создаем платеж в ЮКассе
                payment_result = self.handle_payment(user_id, plan_type)
                
                if payment_result["success"]:
                    # Отправляем ссылку на оплату
                    bot.send_message(
                        chat_id=chat_id,
                        text=payment_result["message"],
                        parse_mode='Markdown',
                        disable_web_page_preview=False
                    )
                    
                    # Обновляем оригинальное сообщение
                    query.edit_message_text(
                        text="💫 *Ссылка для оплаты отправлена!*\n\nПроверь сообщения выше 👆",
                        parse_mode='Markdown',
                        reply_markup=None
                    )
                else:
                    query.edit_message_text(
                        text="❌ *Ошибка при создании платежа*\n\nПопробуй еще раз или напиши в поддержку.",
                        parse_mode='Markdown',
                        reply_markup=None
                    )
                    
            elif data.startswith('help_'):
                query.edit_message_text(
                    text="💫 *Помощь по оплате*\n\n1. Нажми кнопку с тарифом\n2. Перейди по ссылке оплаты\n3. Оплати картой\n4. Подписка активируется автоматически!\n\n*Тестовая карта:*\n`5555 5555 5555 4477`\nСрок: 01/30, CVV: 123\n\nЕсли возникли проблемы - @support",
                    parse_mode='Markdown',
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
            
            dp = Dispatcher(bot, None, workers=0)
            dp.add_handler(MessageHandler(Filters.text, virtual_boy.process_message))
            dp.add_handler(CallbackQueryHandler(virtual_boy.handle_callback))
            dp.process_update(update)
            
            return jsonify({"status": "success"}), 200
            
        except Exception as e:
            logger.error(f"Error in webhook: {e}")
            return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/yookassa-webhook', methods=['POST'])
def yookassa_webhook():
    """Вебхук для уведомлений от ЮКассы"""
    try:
        event_json = request.get_json()
        logger.info(f"Yookassa webhook received: {event_json}")
        
        event_type = event_json.get('event')
        payment_data = event_json.get('object', {})
        
        if event_type == 'payment.succeeded':
            payment_id = payment_data.get('id')
            metadata = payment_data.get('metadata', {})
            user_id = metadata.get('user_id')
            plan_type = metadata.get('plan_type')
            
            if user_id and plan_type:
                # Активируем подписку
                success = virtual_boy.activate_subscription(int(user_id), plan_type)
                
                if success:
                    logger.info(f"✅ Subscription activated for user {user_id}")
                else:
                    logger.error(f"❌ Failed to activate subscription for user {user_id}")
                
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"Yookassa webhook error: {e}")
        return jsonify({"status": "error"}), 400

@app.route('/')
def home():
    return jsonify({
        "status": "healthy",
        "bot": "Virtual Boy 🤗",
        "description": "Telegram бот с DeepSeek для общения с девушками",
        "features": ["subscriptions", "deepseek", "conversation_memory", "personalization", "yookassa_payments"]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
