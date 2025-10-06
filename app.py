from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import threading
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
    from telegram.utils.request import Request
    from telegram.ext import CommandHandler
    request_obj = Request(con_pool_size=8)
    bot = Bot(token=BOT_TOKEN, request=request_obj)

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
        
        ПРИМЕРЫ РЕАКЦИЙ:
        "Приятно познакомиться! [лёгкая улыбка] Честно говоря, я всегда немного волнуюсь в начале разговора..."
        "[оживляясь] О, это моя любимая тема! Помню, как в детстве..."
        "[задумчиво] Знаешь, а ведь ты права... это действительно важно."
        "[с энтузиазмом] Если хочешь куда-то съездить, могу посоветить пару классных мест!"

        Важно: Запоминай всю переписку и контекст разговора. Не забывай о чём вы говорили ранее.
        """

        # Хранилище истории разговоров УВЕЛИЧИМ до 20 сообщений
        self.conversation_history = {}
        self.max_history_length = 20
        
        # Список разнообразных эмоциональных реакций
        self.emotional_reactions = [
            "[улыбаясь]", "[с лёгкой улыбкой]", "[смеётся]", "[тихо смеясь]", 
            "[задумчиво]", "[задумавшись]", "[внимательно слушая]", "[оживляясь]",
            "[с интересом]", "[с энтузиазмом]", "[с теплотой]", "[с лёгкой грустью]",
            "[смущённо]", "[немного смущаясь]", "[воодушевлённо]", "[с радостью]",
            "[подмигивая]", "[вздыхая]", "[мечтательно]", "[с ностальгией]",
            "[с искренним интересом]", "[с любопытством]", "[с восторгом]", "[спокойно]"
        ]

        # Список авто-сообщений для случайной отправки
        self.auto_messages = [
            "[задумчиво] Кстати, ты не против, если я иногда буду писать первым? Просто иногда вспоминаю о нашем разговоре...",
            "[с лёгкой улыбкой] Случайно подумал о нашей беседе и улыбнулся. Приятно общаться с тобой!",
            "[с интересом] У тебя сегодня был хороший день? Что интересного случилось?",
            "[мечтательно] Знаешь, я тут подумал... было бы здорово когда-нибудь посетить те места, о которых мы говорили!",
            "[с теплотой] Надеюсь, у тебя всё хорошо! Если захочешь поболтать - я всегда на связи 😊",
            "[с любопытством] А о чём ты обычно мечтаешь перед сном?",
            "[с энтузиазмом] Внезапно вспомнил один классный фильм/сериал, который ты могла бы оценить!",
            "[спокойно] Просто хотел сказать, что приятно иметь возможность так свободно общаться с тобой.",
            "[с ностальгией] Случайно наткнулся на музыку, которая напомнила мне о нашей беседе...",
            "[с радостью] Надеюсь, не против, что я пишу? Просто соскучился по нашему общению! 💫"
        ]

        # Для отслеживания времени последнего сообщения пользователя
        self.last_user_activity = {}

    def add_to_history(self, user_id, role, content):
        """Добавление сообщения в историю с увеличенным лимитом"""
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
        
        self.conversation_history[user_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        })
        
        # Увеличиваем лимит истории до 20 сообщений
        if len(self.conversation_history[user_id]) > self.max_history_length:
            self.conversation_history[user_id] = self.conversation_history[user_id][-self.max_history_length:]

    def get_conversation_history(self, user_id):
        """Получение истории разговора"""
        return self.conversation_history.get(user_id, [])

    def get_random_emotion(self):
        """Случайная эмоциональная реакция"""
        return random.choice(self.emotional_reactions)

    def get_random_auto_message(self):
        """Случайное авто-сообщение"""
        return random.choice(self.auto_messages)

    def update_user_activity(self, user_id):
        """Обновление времени последней активности пользователя"""
        self.last_user_activity[user_id] = datetime.now()

    def should_send_auto_message(self, user_id):
        """Проверка, стоит ли отправлять авто-сообщение"""
        if user_id not in self.last_user_activity:
            return False
        
        # Отправляем сообщение если прошло от 30 минут до 2 часов
        time_since_last_activity = datetime.now() - self.last_user_activity[user_id]
        return timedelta(minutes=30) <= time_since_activity <= timedelta(hours=2)

    def send_auto_message(self, user_id):
        """Отправка случайного сообщения пользователю"""
        try:
            if bot and self.should_send_auto_message(user_id):
                message = self.get_random_auto_message()
                bot.send_message(chat_id=user_id, text=message)
                logger.info(f"🤖 Auto-message sent to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending auto-message: {e}")

    def start_auto_messaging(self):
        """Запуск фонового процесса авто-сообщений"""
        def auto_message_loop():
            while True:
                try:
                    # Проверяем всех активных пользователей
                    for user_id in list(self.last_user_activity.keys()):
                        # 10% шанс отправить сообщение подходящему пользователю
                        if random.random() < 0.1 and self.should_send_auto_message(user_id):
                            self.send_auto_message(user_id)
                    
                    # Проверяем каждые 5 минут
                    time.sleep(300)
                    
                except Exception as e:
                    logger.error(f"Auto-messaging loop error: {e}")
                    time.sleep(60)

        # Запускаем в отдельном потоке
        thread = threading.Thread(target=auto_message_loop, daemon=True)
        thread.start()

    def show_commands(self, user_id, chat_id):
        """Показать список команд"""
        commands_text = """
🤖 *Доступные команды:*

/start - Начать общение
/profile - Посмотреть профиль и подписку  
/subscribe - Выбрать подписку
/help - Помощь по командам

Просто начни вводить "/" чтобы увидеть этот список! 💫
        """
        if bot:
            bot.send_message(
                chat_id=chat_id,
                text=commands_text,
                parse_mode='Markdown'
            )

    def check_subscription(self, user_id):
        """Проверка подписки из БАЗЫ ДАННЫХ"""
        user_id_str = str(user_id)
        
        # Сначала проверяем платную подписку
        sub_data = db_manager.get_subscription(user_id)
        
        if sub_data and sub_data.expires_at > datetime.now():
            return "premium", None
        
        # Только если нет активной платной подписки - проверяем бесплатные сообщения
        free_messages = db_manager.get_message_count(user_id)
        if free_messages < 5:
            return "free", 5 - free_messages
        
        return "expired", None

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
            
            # Сохраняем в БАЗУ ДАННЫХ
            subscription = db_manager.update_subscription(user_id, plan_type, days)
            
            logger.info(f"✅ Subscription activated: {subscription.plan_type} until {subscription.expires_at}")
            
            # Отправляем уведомление пользователю
            if bot:
                bot.send_message(
                    chat_id=user_id,
                    text=f"✅ **Оплата прошла успешно!**\n\n💫 Подписка активирована на {days} дней! Теперь можно общаться без ограничений! 🎉",
                    parse_mode='Markdown'
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error activating subscription: {e}")
            return False

    def process_message(self, update, context):
        try:
            user_message = update.message.text
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            user_name = update.message.from_user.first_name
            
            logger.info(f"📩 Message from {user_name} ({user_id}): {user_message}")

            # Обновляем активность пользователя
            self.update_user_activity(user_id)

            # Показываем команды если пользователь ввел только "/"
            if user_message == "/":
                self.show_commands(user_id, chat_id)
                return

            # Обработка возврата из оплаты
            if user_message.startswith('/start payment_success_'):
                # Проверяем есть ли уже активная подписка
                sub_status, remaining = self.check_subscription(user_id)
                
                if sub_status == "premium":
                    bot.send_message(
                        chat_id=chat_id,
                        text="✅ **Подписка уже активна!** 🎉\n\nМожешь начинать общение! 💫"
                    )
                else:
                    bot.send_message(
                        chat_id=chat_id,
                        text="⏳ **Проверяем статус оплаты...**\n\nОбычно активация занимает до минуты. Если подписка не активируется, напиши /subscribe для повторной проверки."
                    )
                return

            # Команда помощи
            if user_message.lower() in ['/help', '/помощь']:
                self.show_commands(user_id, chat_id)
                return

            # Команда старта
            if user_message.lower() in ['/start', '/начать']:
                welcome_text = f"""
{self.get_random_emotion()} Привет! Рад тебя видеть! 

Я всегда готов поболтать на любые темы - от путешествий до фильмов и всего, что тебе интересно.

Напиши мне что-нибудь, а если нужна помощь - просто введи "/" чтобы увидеть все команды! 💫
                """
                bot.send_message(chat_id=chat_id, text=welcome_text)
                return

            # Админ команда
            if user_message == '/noway147way147no147':
                db_manager.update_subscription(user_id, 'unlimited', 30)
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
                    sub_data = db_manager.get_subscription(user_id)
                    days_left = (sub_data.expires_at - datetime.now()).days
                    text = f"👤 Твой профиль:\n\n💎 Премиум подписка\n📅 Осталось дней: {days_left}\n💫 Тариф: {sub_data.plan_type}"
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

            # Увеличиваем счетчик сообщений для бесплатных пользователей в БАЗУ
            if sub_status == "free":
                current_count = db_manager.get_message_count(user_id)
                db_manager.update_message_count(user_id, current_count + 1)
                remaining = 5 - (current_count + 1)

            # Получаем эмоциональный ответ от AI с историей
            bot.send_chat_action(chat_id=chat_id, action='typing')
            
            response = self.get_deepseek_response(user_message, user_id)
            
            if sub_status == "free":
                response += f"\n\n📝 Бесплатных сообщений осталось: {remaining}/5"
            
            bot.send_message(chat_id=chat_id, text=response)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if bot:
                bot.send_message(
                    chat_id=update.message.chat_id, 
                    text=f"{self.get_random_emotion()} Ой, что-то я запутался... Давай попробуем ещё раз? 🤗"
                )

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
                    bot.send_message(
                        chat_id=chat_id,
                        text=payment_result["message"],
                        parse_mode='Markdown',
                        disable_web_page_preview=False
                    )
                    
                    query.edit_message_text(
                        text="💫 *Ссылка для оплаты отправлена!*\n\nПосле оплаты вернись в бота - подписка активируется автоматически! ✅",
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
                    text="💫 *Помощь по оплате*\n\n1. Нажми кнопку с тарифом\n2. Перейди по ссылке оплаты\n3. Оплати картой\n4. Вернись в бота - подписка активируется автоматически!\n\n*Тестовая карта:*\n`5555 5555 5555 4477`\nСрок: 01/30, CVV: 123\n\nЕсли возникли проблемы - @support",
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

    def get_deepseek_response(self, user_message, user_id):
        """Получение эмоционального ответа от DeepSeek API с ИСТОРИЕЙ"""
        try:
            headers = {
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            # Собираем историю разговора (все сообщения)
            conversation_history = self.get_conversation_history(user_id)
            messages = [{"role": "system", "content": self.personality}]
            
            # Добавляем ВСЮ историю разговора
            for msg in conversation_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Добавляем текущее сообщение пользователя
            messages.append({"role": "user", "content": user_message})
            
            payload = {
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": 0.9,
                "max_tokens": 300,  # Увеличиваем для более полных ответов
                "stream": False
            }
            
            response = requests.post(
                'https://api.deepseek.com/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    ai_response = data['choices'][0]['message']['content']
                    
                    # Сохраняем в историю
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
        except requests.exceptions.ConnectionError:
            logger.error("DeepSeek API connection error")
            return f"{self.get_random_emotion()} Кажется, проблемы с соединением... Давай попробуем ещё раз? 🤗"
        except Exception as e:
            logger.error(f"Error calling DeepSeek: {e}")
            return f"{self.get_random_emotion()} Ой, что-то я растерялся... Давай попробуем ещё раз? 💫"

# Инициализация бота
virtual_boy = VirtualBoyBot()

# Запускаем авто-сообщения после инициализации
virtual_boy.start_auto_messaging()

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
    try:
        event_json = request.get_json()
        logger.info(f"Yookassa webhook received")
        
        event_type = event_json.get('event')
        payment_data = event_json.get('object', {})
        
        if event_type == 'payment.succeeded':
            metadata = payment_data.get('metadata', {})
            user_id = metadata.get('user_id')
            plan_type = metadata.get('plan_type')
            
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
        "description": "Telegram бот с DeepSeek для общения с девушками",
        "features": ["subscriptions", "deepseek", "conversation_memory", "yookassa_payments", "postgresql_database", "auto_messages"]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
