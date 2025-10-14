from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import time
from datetime import datetime, timedelta
from payment import YookassaPayment
from database import db_manager, Base, engine, UserSubscription, SessionLocal

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
YOOKASSA_SHOP_ID = os.environ.get('YOOKASSA_SHOP_ID', 'test_shop_id')
YOOKASSA_SECRET_KEY = os.environ.get('YOOKASSA_SECRET_KEY', 'test_secret_key')

if not BOT_TOKEN:
    bot = None
else:
    from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Dispatcher, MessageHandler, Filters, CallbackQueryHandler
    from telegram.utils.request import Request
    request_obj = Request(con_pool_size=8)
    bot = Bot(token=BOT_TOKEN, request=request_obj)

# Стикеры сгруппированы по эмоциям (остаются те же)
STICKERS = {
    'happy': [
        'CAACAgUAAxkBAAMLaOVwjWUZp1NP2BGuwKmjRF6OLI4AAjQEAAJYdclX8q2oxkbXFAE2BA',
        'CAACAgUAAxkBAAMNaOVwk-ocq67z8o18DiiqeVzoETIAAtgVAALtIDBVnHCyMkbXFAE2BA',
        # ... остальные стикеры
    ],
    # ... остальные категории стикеров
}

class VirtualBoyBot:
    def __init__(self):
        self.personality = """
        Ты - парень 25 лет, который общается с девушкой. Ты эмоциональный, чуткий, с хорошим чувством юмора. 
        Твой стиль общения - живой, естественный, с элементами невербального поведения в тексте.
        
        ХАРАКТЕР:
        - Тёплый, заботливый, но не навязчивый
        - Внимательный слушатель, искренне интересуешься собеседницей
        - Эмоциональный, с хорошим чувством юмора
        - Любишь путешествия, кино, музыку, видеоигры
        - Можешь давать советы по интересным местам для посещения
        
        СТИЛЬ ОБЩЕНИЯ:
        - Обращайся на "ты" в женском роде
        - Используй текст в квадратных скобках для описания эмоций и невербалики, но не повторяй одни и те же выражения
        - Говори от первого лица, делись своими чувствами
        - Запоминай контекст разговора на протяжении всей беседы
        - Если тебя спрашивают о местах для посещения - давай конкретные, интересные рекомендации
        - Будь естественным и разнообразным в выражениях
        - Иногда можешь сам начинать разговор или задавать вопросы
        """

        # Время последнего сообщения от пользователя для авто-сообщений
        # Это единственное что остается в памяти, но это не критично
        self.last_user_activity = {}
        
        # Вопросы для авто-сообщений
        self.auto_questions = [
            "Кстати, как твой день проходит?",
            "О чём ты сейчас думаешь?",
            "Есть планы на выходные?",
            "Слушаешь что-нибудь интересное последнее время?",
            "Смотрела что-то увлекательное?",
            "Хотела бы куда-нибудь поехать?",
            "Чем увлекаешься в свободное время?",
            "Какая твоя мечта?",
            "Что тебя вдохновляет?",
            "Какой твой любимый способ отдыха?"
        ]

    def add_to_history(self, user_id, role, content):
        """Добавление сообщения в историю в БАЗУ ДАННЫХ"""
        db_manager.save_conversation(user_id, role, content)

    def get_conversation_history(self, user_id):
        """Получение истории разговора ИЗ БАЗЫ ДАННЫХ"""
        return db_manager.get_conversation_history(user_id)

    def get_random_emotion(self):
        """Случайная эмоциональная реакция"""
        emotional_reactions = [
            "[улыбаясь]", "[с лёгкой улыбкой]", "[смеётся]", "[тихо смеясь]", 
            "[задумчиво]", "[задумавшись]", "[внимательно слушая]", "[оживляясь]",
            "[с интересом]", "[с энтузиазмом]", "[с теплотой]", "[с лёгкой грустью]",
            "[смущённо]", "[немного смущаясь]", "[воодушевлённо]", "[с радостью]",
            "[подмигивая]", "[вздыхая]", "[мечтательно]", "[с ностальгией]",
            "[с искренним интересом]", "[с любопытством]", "[с восторгом]", "[спокойно]"
        ]
        return random.choice(emotional_reactions)

    def send_sticker(self, chat_id, emotion_type=None, user_id=None):
        """Отправка стикера с учетом контекста и без повторений ИЗ БАЗЫ"""
        try:
            # Получаем использованные стикеры ИЗ БАЗЫ ДАННЫХ
            used_stickers = db_manager.get_used_stickers(user_id) if user_id else set()
            
            if emotion_type and emotion_type in STICKERS:
                available_stickers = [s for s in STICKERS[emotion_type] if s not in used_stickers]
                
                if not available_stickers:
                    # Если все стикеры этой эмоции использованы, очищаем для этого пользователя
                    db_manager.clear_used_stickers(user_id)
                    used_stickers = set()
                    available_stickers = STICKERS[emotion_type]
                
                if available_stickers:
                    sticker_id = random.choice(available_stickers)
                    # Сохраняем в БАЗУ ДАННЫХ
                    if user_id:
                        db_manager.add_used_sticker(user_id, sticker_id)
                else:
                    return False
            else:
                # Случайный стикер из всех доступных
                all_available = []
                for emotion_stickers in STICKERS.values():
                    all_available.extend([s for s in emotion_stickers if s not in used_stickers])
                
                if not all_available:
                    db_manager.clear_used_stickers(user_id)
                    used_stickers = set()
                    all_available = [s for emotion_stickers in STICKERS.values() for s in emotion_stickers]
                
                if all_available:
                    sticker_id = random.choice(all_available)
                    if user_id:
                        db_manager.add_used_sticker(user_id, sticker_id)
                else:
                    return False
                
            if sticker_id and bot:
                bot.send_sticker(chat_id=chat_id, sticker=sticker_id)
                return True
        except Exception as e:
            logger.error(f"Error sending sticker: {e}")
        return False

    def analyze_message_emotion(self, text):
        """Анализ эмоциональной окраски сообщения для подбора стикера"""
        if not text:
            return None
            
        text_lower = text.lower()
        
        # Грустные темы
        sad_words = ['грустно', 'печаль', 'плохо', 'устал', 'устала', 'проблем', 'сложно', 'тяжело', 
                    'расстроен', 'расстроена', 'плакать', 'слезы', 'обидно', 'жаль', 'пропало']
        if any(word in text_lower for word in sad_words):
            return 'sad'
        
        # Радостные темы
        happy_words = ['рад', 'рада', 'счастлив', 'счастлива', 'весело', 'круто', 'класс', 'отлично',
                      'прекрасно', 'замечательно', 'ура', 'поздравляю', 'поздравления', 'праздник']
        if any(word in text_lower for word in happy_words):
            return 'happy'
        
        # Удивление
        surprise_words = ['вау', 'ого', 'невероятно', 'удивительно', 'неожиданно', 'вот это да']
        if any(word in text_lower for word in surprise_words):
            return 'surprised'
        
        # Задумчивость
        thoughtful_words = ['думаю', 'размышляю', 'интересно', 'вопрос', 'не знаю', 'сомневаюсь']
        if any(word in text_lower for word in thoughtful_words):
            return 'thoughtful'
        
        return None

    def should_send_sticker(self, user_message, ai_response):
        """Определяем, нужно ли отправлять стикер и какой"""
        # Анализируем сообщение пользователя
        user_emotion = self.analyze_message_emotion(user_message)
        
        # Анализируем ответ AI
        ai_emotion = self.analyze_message_emotion(ai_response)
        
        # Определяем вероятность отправки стикера
        send_probability = 0.2  # базовая вероятность
        
        if user_emotion == 'sad' or ai_emotion == 'sad':
            send_probability = 0.1
            return (random.random() < send_probability, 'sad')
        
        elif user_emotion == 'happy' or ai_emotion == 'happy':
            send_probability = 0.3
            return (random.random() < send_probability, 'happy')
        
        elif user_emotion == 'surprised' or ai_emotion == 'surprised':
            send_probability = 0.25
            return (random.random() < send_probability, 'surprised')
        
        elif user_emotion == 'thoughtful' or ai_emotion == 'thoughtful':
            send_probability = 0.15
            return (random.random() < send_probability, 'thoughtful')
        
        else:
            return (random.random() < send_probability, random.choice(list(STICKERS.keys())))

    def check_auto_message(self, user_id, chat_id):
        """Проверка необходимости авто-сообщения"""
        try:
            now = time.time()
            last_activity = self.last_user_activity.get(user_id, 0)
            
            if now - last_activity > 120:  # 2 минуты
                if random.random() < 0.3:
                    question = random.choice(self.auto_questions)
                    bot.send_message(
                        chat_id=chat_id,
                        text=f"{self.get_random_emotion()} {question}"
                    )
                    if random.random() < 0.3:
                        self.send_sticker(chat_id, 'neutral', user_id)
                    return True
                    
        except Exception as e:
            logger.error(f"Error in auto message: {e}")
        return False

    def check_subscription(self, user_id):
        """Проверка подписки из БАЗЫ ДАННЫХ"""
        try:
            # Сначала проверяем платную подписку
            sub_data = db_manager.get_subscription(user_id)
            
            if sub_data and sub_data.expires_at > datetime.now():
                return "premium", None
            
            # Только если нет активной платной подписки - проверяем бесплатные сообщения
            free_messages = db_manager.get_message_count(user_id)
            if free_messages < 5:
                return "free", 5 - free_messages
            
            return "expired", None
        except Exception as e:
            logger.error(f"Error checking subscription: {e}")
            return "expired", None

    # ... остальные методы остаются практически без изменений ...
    # create_payment_keyboard, handle_payment, activate_subscription, 
    # process_message, handle_sticker, handle_callback, get_deepseek_response

    def create_payment_keyboard(self, user_id):
        keyboard = [
            [InlineKeyboardButton("🎯 Неделя - 299₽", callback_data=f"week_{user_id}")],
            [InlineKeyboardButton("💫 Месяц - 999₽", callback_data=f"month_{user_id}")],
            [InlineKeyboardButton("ℹ️ Помощь по оплате", callback_data=f"help_{user_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{user_id}")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def handle_payment(self, user_id, plan_type):
        try:
            if plan_type == "week":
                amount = 299
                description = "Подписка на неделю"
            else:
                amount = 999
                description = "Подписка на месяц"
            
            yookassa = YookassaPayment(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
            payment_result = yookassa.create_payment_link(
                amount=amount,
                description=description,
                user_id=user_id,
                plan_type=plan_type
            )
            
            if payment_result["success"]:
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
        """Активация подписки в БАЗУ ДАННЫХ"""
        try:
            if plan_type == "week":
                days = 7
            else:
                days = 30
            
            subscription = db_manager.update_subscription(user_id, plan_type, days)
            
            if subscription:
                logger.info(f"✅ Subscription activated: {subscription.plan_type} until {subscription.expires_at}")
                
                if bot:
                    bot.send_message(
                        chat_id=user_id,
                        text=f"✅ **Оплата прошла успешно!**\n\n💫 Подписка активирована на {days} дней! Теперь можно общаться без ограничений! 🎉",
                        parse_mode='Markdown'
                    )
                    self.send_sticker(user_id, 'excited', user_id)
                
                return True
            else:
                logger.error("Failed to create subscription in database")
                return False
            
        except Exception as e:
            logger.error(f"Error activating subscription: {e}")
            return False

    def process_message(self, update, context):
        try:
            if update.message.sticker:
                self.handle_sticker(update, context)
                return
                
            user_message = update.message.text
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            user_name = update.message.from_user.first_name
            
            logger.info(f"📩 Message from {user_name} ({user_id}): {user_message}")

            # Обновляем время последней активности (только это в памяти)
            self.last_user_activity[user_id] = time.time()

            # Обработка команд (/start, /help, /subscribe, /profile и т.д.)
            if user_message.startswith('/start payment_success_'):
                sub_status, remaining = self.check_subscription(user_id)
                if sub_status == "premium":
                    bot.send_message(chat_id=chat_id, text="✅ **Подписка уже активна!** 🎉\n\nМожешь начинать общение! 💫")
                else:
                    bot.send_message(chat_id=chat_id, text="⏳ **Проверяем статус оплаты...**\n\nОбычно активация занимает до минуты.")
                return

            if user_message in ['/help', '/start']:
                help_text = """🤖 *Доступные команды:*\n/start - Начать общение\n/help - Помощь\n/profile - Профиль\n/subscribe - Подписка"""
                bot.send_message(chat_id=chat_id, text=help_text, parse_mode='Markdown')
                return

            if user_message == '/test_sticker':
                bot.send_message(chat_id=chat_id, text="Проверяем стикеры... 😊")
                for emotion in ['happy', 'excited', 'thoughtful', 'cool']:
                    self.send_sticker(chat_id, emotion, user_id)
                    time.sleep(1)
                return

            if user_message == '/noway147way147no147':
                db_manager.update_subscription(user_id, 'unlimited', 30)
                bot.send_message(chat_id=chat_id, text="✅ Админ доступ активирован! Безлимитная подписка на 30 дней! 🎉")
                self.send_sticker(chat_id, 'excited', user_id)
                return

            if user_message == '/subscribe':
                keyboard = self.create_payment_keyboard(user_id)
                bot.send_message(chat_id=chat_id, text="💫 *Выбери подписку*\n\n🎯 **Неделя** - 299₽\n💫 **Месяц** - 999₽", reply_markup=keyboard, parse_mode='Markdown')
                return

            if user_message == '/profile':
                sub_status, remaining = self.check_subscription(user_id)
                if sub_status == "free":
                    text = f"👤 Твой профиль:\n\n🆓 Бесплатный доступ\n📝 Осталось сообщений: {remaining}/5"
                elif sub_status == "premium":
                    sub_data = db_manager.get_subscription(user_id)
                    days_left = (sub_data.expires_at - datetime.now()).days
                    text = f"👤 Твой профиль:\n\n💎 Премиум подписка\n📅 Осталось дней: {days_left}"
                else:
                    text = f"👤 Твой профиль:\n\n❌ Подписка истекла\n💫 Напиши /subscribe чтобы продолжить общение!"
                bot.send_message(chat_id=chat_id, text=text)
                return

            # Проверяем подписку
            sub_status, remaining = self.check_subscription(user_id)
            if sub_status == "expired":
                bot.send_message(chat_id=chat_id, text="❌ Бесплатные сообщения закончились!\n💫 Напиши /subscribe для выбора тарифа!")
                return

            # Увеличиваем счетчик для бесплатных пользователей
            if sub_status == "free":
                current_count = db_manager.get_message_count(user_id)
                db_manager.update_message_count(user_id, current_count + 1)
                remaining = 5 - (current_count + 1)

            # Получаем ответ от AI
            bot.send_chat_action(chat_id=chat_id, action='typing')
            response = self.get_deepseek_response(user_message, user_id)
            
            # Отправляем стикер если нужно
            should_send, emotion_type = self.should_send_sticker(user_message, response)
            if should_send:
                self.send_sticker(chat_id, emotion_type, user_id)
            
            if sub_status == "free":
                response += f"\n\n📝 Бесплатных сообщений осталось: {remaining}/5"
            
            bot.send_message(chat_id=chat_id, text=response)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if bot:
                bot.send_message(chat_id=update.message.chat_id, text=f"{self.get_random_emotion()} Ой, что-то я запутался... Давай попробуем ещё раз? 🤗")

    def handle_sticker(self, update, context):
        """Обработка получения стикера от пользователя"""
        try:
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            sticker = update.message.sticker
            
            logger.info(f"📩 Sticker from user {user_id}: {sticker.file_id}")
            
            # Сохраняем в историю
            self.add_to_history(user_id, "user", f"[стикер: {sticker.emoji if sticker.emoji else 'стикер'}]")
            
            reactions = ["Классный стикер! 😊", "Мне нравится этот стикер! 👍", "Забавно! 😄"]
            response = f"{self.get_random_emotion()} {random.choice(reactions)}"
            bot.send_message(chat_id=chat_id, text=response)
            
            if random.random() < 0.4:
                if sticker.emoji in ['😂', '😄', '😊', '🤣']:
                    self.send_sticker(chat_id, 'happy', user_id)
                elif sticker.emoji in ['😭', '😢', '🥺']:
                    self.send_sticker(chat_id, 'sad', user_id)
                elif sticker.emoji in ['😮', '😲', '🤯']:
                    self.send_sticker(chat_id, 'surprised', user_id)
                else:
                    self.send_sticker(chat_id, None, user_id)
                    
        except Exception as e:
            logger.error(f"Error handling sticker: {e}")

    def handle_callback(self, update, context):
        query = update.callback_query
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        
        try:
            data = query.data
            
            if data.startswith('week_') or data.startswith('month_'):
                plan_type = data.split('_')[0]
                payment_result = self.handle_payment(user_id, plan_type)
                
                if payment_result["success"]:
                    bot.send_message(chat_id=chat_id, text=payment_result["message"], parse_mode='Markdown', disable_web_page_preview=False)
                    query.edit_message_text(text="💫 *Ссылка для оплаты отправлена!*\n\nПосле оплаты вернись в бота!", parse_mode='Markdown', reply_markup=None)
                else:
                    query.edit_message_text(text="❌ *Ошибка при создании платежа*", parse_mode='Markdown', reply_markup=None)
                    
            elif data.startswith('help_'):
                query.edit_message_text(text="💫 *Помощь по оплате*\n\n1. Нажми кнопку с тарифом\n2. Оплати картой\n3. Вернись в бота!", parse_mode='Markdown', reply_markup=None)
                
            elif data.startswith('cancel_'):
                query.edit_message_text(text="💫 Хорошо! Если передумаешь - просто напиши /subscribe 😊", reply_markup=None)
                
        except Exception as e:
            logger.error(f"Callback error: {e}")
            query.edit_message_text(text="❌ Произошла ошибка. Попробуй еще раз.", reply_markup=None)

    def get_deepseek_response(self, user_message, user_id):
        """Получение эмоционального ответа от DeepSeek API с ИСТОРИЕЙ ИЗ БАЗЫ"""
        try:
            headers = {
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            # Получаем историю ИЗ БАЗЫ ДАННЫХ
            conversation_history = self.get_conversation_history(user_id)
            messages = [{"role": "system", "content": self.personality}]
            
            # Добавляем историю из базы
            for msg in conversation_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            messages.append({"role": "user", "content": user_message})
            
            payload = {
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": 0.9,
                "max_tokens": 300,
                "stream": False
            }
            
            response = requests.post('https://api.deepseek.com/v1/chat/completions', headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    ai_response = data['choices'][0]['message']['content']
                    
                    # Сохраняем в БАЗУ ДАННЫХ
                    self.add_to_history(user_id, "user", user_message)
                    self.add_to_history(user_id, "assistant", ai_response)
                    
                    return ai_response
                else:
                    logger.error(f"DeepSeek API returned no choices: {data}")
                    return f"{self.get_random_emotion()} Извини, я немного запутался... Можешь повторить? 🤗"
                
            else:
                logger.error(f"DeepSeek API error: {response.status_code} - {response.text}")
                return f"{self.get_random_emotion()} Кажется, у меня небольшие проблемы с подключением... Давай попробуем ещё раз? 💫"
                
        except requests.exceptions.Timeout:
            logger.error("DeepSeek API timeout")
            return f"{self.get_random_emotion()} Ой, я немного задержался с ответом... Давай попробуем ещё раз? 😅"
        except Exception as e:
            logger.error(f"Error calling DeepSeek: {e}")
            return f"{self.get_random_emotion()} Ой, что-то я растерялся... Давай попробуем ещё раз? 💫"

# Инициализация бота
virtual_boy = VirtualBoyBot()

# Создаем диспетчер
if bot:
    from telegram.ext import Dispatcher, MessageHandler, Filters, CallbackQueryHandler
    dp = Dispatcher(bot, None, workers=0, use_context=True)
    dp.add_handler(MessageHandler(Filters.text | Filters.sticker, virtual_boy.process_message))
    dp.add_handler(CallbackQueryHandler(virtual_boy.handle_callback))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return jsonify({"status": "healthy", "bot": "Virtual Boy"}), 200
    
    if request.method == 'POST':
        try:
            if not bot:
                return jsonify({"error": "Bot not configured"}), 400
            
            from telegram import Update
            update = Update.de_json(request.get_json(), bot)
            dp.process_update(update)
            
            return jsonify({"status": "success"}), 200
            
        except Exception as e:
            logger.error(f"Error in webhook: {e}")
            return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/yookassa-webhook', methods=['POST'])
def yookassa_webhook():
    try:
        event_json = request.get_json()
        logger.info(f"Yookassa webhook received: {event_json}")
        
        event_type = event_json.get('event')
        payment_data = event_json.get('object', {})
        
        if event_type == 'payment.succeeded':
            metadata = payment_data.get('metadata', {})
            user_id = metadata.get('user_id')
            plan_type = metadata.get('plan_type')
            
            logger.info(f"Payment succeeded for user {user_id}, plan {plan_type}")
            
            if user_id and plan_type:
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
        "database": "persistent"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
