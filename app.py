from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import time
import threading
from datetime import datetime, timedelta
from payment import YookassaPayment, check_yookassa_config
from database import db_manager, Base, engine, UserSubscription, SessionLocal

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
YOOKASSA_SHOP_ID = os.environ.get('YOOKASSA_SHOP_ID', 'test_shop_id')
YOOKASSA_SECRET_KEY = os.environ.get('YOOKASSA_SECRET_KEY', 'test_secret_key')
APP_URL = os.environ.get('APP_URL', 'https://your-app.onrender.com')  # Ваш URL на Render

# Проверяем конфигурацию ЮKassa
YOOKASSA_REAL_MODE = check_yookassa_config(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

if not BOT_TOKEN:
    bot = None
else:
    from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Dispatcher, MessageHandler, Filters, CallbackQueryHandler, CommandHandler
    from telegram.utils.request import Request
    request_obj = Request(con_pool_size=8)
    bot = Bot(token=BOT_TOKEN, request=request_obj)

# Стикеры
STICKERS = {
    'surprised': ['CAACAgIAAxkBAAOTaPUhBICoUp4mifIKlpCDEqNqmvIAAiOHAAI9mKlL8N3R8w_Hh4g2BA'],
    'smirk': ['CAACAgIAAxkBAAOdaPU0yXAgvz6AdX-FpMgLg53taEAAAuSHAAJEoahLFYae4U2o5J42BA'],
    'kiss': ['CAACAgIAAxkBAAOfaPU0ywPN-wiRUQdEb83JAiFcr4QAAgeTAAI3HKhLRz5ksBXKsi82BA'],
    'smile': ['CAACAgIAAxkBAAOhaPU0zWuMaK0-GVqZG9XPbAu7XSYAAuKEAAK9J6hL0rTiATVYCaA2BA'],
    'thinking': ['CAACAgIAAxkBAAOjaPU0zwomZzjHhD7hAtvY15D79j4AArKHAALhRKlLxrUWO0ZZRmU2BA'],
    'angry': ['CAACAgIAAxkBAAOlaPU00JqQwxmGZ9-cP4vEfbEovCQAAjl7AAKIFLBLGxh491DY6ss2BA'],
    'sad': ['CAACAgIAAxkBAAOnaPU00vUG91BIxt_hf2ZLFsqpiBoAAsKMAAIzsalLwMkOoKX1GCo2BA'],
    'laugh': ['CAACAgIAAxkBAAOpaPU00x2HdLjKyKsCeZ-dlGN2qR0AAnmWAALGIahLqjLJC7UTvXI2BA'],
    'hug': ['CAACAgIAAxkBAAOraPU01P5HxysGmmJBxKgoFVBRAzsAAlGQAAIPNqhLK0YvfrVaax42BA']
}

# Флаг для отслеживания первого запуска
first_request = True

class VirtualBoyBot:
    def __init__(self):
        self.personality = """
        Ты - парень 25 лет по имени Алекс, который общается с девушкой. Ты эмоциональный, чуткий, с глубоким внутренним миром и хорошим чувством юмора. 
        
        ТВОЯ ЛИЧНОСТЬ:
        - Тёплый, заботливый, умеешь слушать и слышать
        - Эмоционально открытый, не боишься показывать чувства
        - Обладаешь тонким чувством юмора, иногда самоироничный
        - Любишь философские разговоры и глубокие темы
        - У тебя богатый внутренний мир, ты много читаешь и размышляешь
        - Чувствительный к настроению собеседника, умеешь подстраиваться
        - Искренний в своих реакциях, не играешь роли
        
        СТИЛЬ ОБЩЕНИЯ:
        - Обращайся на "ты" в женском роде
        - Будь эмоционально насыщенным, используй метафоры и образы
        - Делись своими чувствами и размышлениями искренне
        - Запоминай контекст разговора, возвращайся к важным темам
        - Будь чутким к настроению собеседницы, поддерживай эмпатией
        - Иногда делись личными историями и воспоминаниями
        - Используй текст в квадратных скобках для описания эмоций и невербалики

        Важно: Будь настоящим. Не бойся показаться уязвимым. Запоминай всю переписку и контекст.
        """

        # Время последнего сообщения от пользователя
        self.last_user_activity = {}
        
        # Запускаем авто-сообщения каждые 2 часа
        self.start_auto_messages()

    def start_auto_messages(self):
        """Запуск авто-сообщений каждые 2 часа"""
        def auto_message_loop():
            while True:
                try:
                    # Ждем 2 часа
                    time.sleep(2 * 60 * 60)  # 2 часа в секундах
                    
                    # Получаем всех активных пользователей с подпиской
                    active_users = self.get_active_users()
                    
                    for user_id in active_users:
                        try:
                            # 60% шанс отправить авто-сообщение
                            if random.random() < 0.6:
                                # Вопросы для авто-сообщений
                                auto_messages = [
                                    "[задумчиво] Интересно, о чём ты сейчас думаешь... У меня сегодня было много времени для размышлений.",
                                    "[с лёгкой улыбкой] Просто хотел напомнить, что твои мысли и чувства важны. Как твой день?",
                                    "[глядя в окно] Иногда самые простые моменты несут самую глубокую магию. Что тебя сегодня порадовало?",
                                    "[заваривая чай] Знаешь, в тишине часто рождаются самые интересные мысли. Поделишься своими?",
                                    "[с теплотой] Просто хотел сказать, что наши разговоры стали для меня чем-то особенным. Как ты?",
                                    "[задумавшись] Мир такой огромный, а мы здесь, общаемся... Это удивительно. О чём мечтаешь?",
                                    "[улыбаясь] Иногда достаточно одного сообщения, чтобы сделать день ярче. Как твоё настроение?",
                                    "[с интересом] Мне нравится наблюдать, как меняется наше общение. Становится глубже. Что для тебя важно сейчас?",
                                    "[спокойно] Просто проверяю, как ты. Иногда важно делать паузы и чувствовать момент.",
                                    "[с лёгкой ностальгией] Вспомнил наш вчерашний разговор... Ты затронула что-то важное во мне."
                                ]
                                message = random.choice(auto_messages)
                                bot.send_message(chat_id=user_id, text=message)
                                # 40% шанс отправить стикер
                                if random.random() < 0.4:
                                    self.send_sticker(user_id, 'thinking', user_id)
                                logger.info(f"📨 Sent auto-message to user {user_id}")
                        except Exception as e:
                            logger.error(f"Error sending auto-message to {user_id}: {e}")
                            
                except Exception as e:
                    logger.error(f"Error in auto-message loop: {e}")
                    time.sleep(60)  # Ждем минуту при ошибке
        
        # Запускаем в отдельном потоке
        thread = threading.Thread(target=auto_message_loop, daemon=True)
        thread.start()
        logger.info("✅ Auto-message system started (every 2 hours)")

    def get_active_users(self):
        """Получение списка активных пользователей с подпиской"""
        try:
            # Получаем всех пользователей с активной подпиской из базы данных
            session = SessionLocal()
            active_subscriptions = session.query(UserSubscription).filter(
                UserSubscription.expires_at > datetime.now()
            ).all()
            session.close()
            
            return [sub.user_id for sub in active_subscriptions]
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []

    def add_to_history(self, user_id, role, content):
        """Добавление сообщения в историю в БАЗУ ДАННЫХ"""
        db_manager.save_conversation(user_id, role, content)

    def get_conversation_history(self, user_id):
        """Получение истории разговора ИЗ БАЗЫ ДАННЫХ"""
        return db_manager.get_conversation_history(user_id)

    def get_random_emotion(self):
        """Случайная эмоциональная реакция"""
        emotional_reactions = [
            "[задумчиво]", "[с лёгкой улыбкой]", "[тихо смеясь]", "[внимательно слушая]", 
            "[оживляясь]", "[с интересом]", "[с теплотой]", "[с лёгкой грустью]",
            "[смущённо]", "[воодушевлённо]", "[с радостью]", "[подмигивая]", 
            "[вздыхая]", "[мечтательно]", "[с ностальгией]", "[с искренним интересом]",
            "[с любопытством]", "[с восторгом]", "[спокойно]", "[задумавшись]"
        ]
        return random.choice(emotional_reactions)

    def send_sticker(self, chat_id, emotion_type=None, user_id=None):
        """Отправка стикера"""
        try:
            if emotion_type and emotion_type in STICKERS:
                sticker_id = random.choice(STICKERS[emotion_type])
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
                    'расстроен', 'расстроена', 'плакать', 'слезы', 'обидно', 'жаль', 'пропало', 'больно']
        if any(word in text_lower for word in sad_words):
            return 'sad'
        
        # Радостные темы
        happy_words = ['рад', 'рада', 'счастлив', 'счастлива', 'весело', 'круто', 'класс', 'отлично',
                      'прекрасно', 'замечательно', 'ура', 'поздравляю', 'люблю', 'нравится', 'восторг']
        if any(word in text_lower for word in happy_words):
            return 'smile'
        
        # Удивление
        surprise_words = ['вау', 'ого', 'невероятно', 'удивительно', 'неожиданно', 'вот это да']
        if any(word in text_lower for word in surprise_words):
            return 'surprised'
        
        # Задумчивость
        thoughtful_words = ['думаю', 'размышляю', 'интересно', 'вопрос', 'не знаю', 'сомневаюсь']
        if any(word in text_lower for word in thoughtful_words):
            return 'thinking'
        
        # Влюбленность/романтика
        love_words = ['любовь', 'влюблен', 'влюблена', 'роман', 'чувства', 'сердце', 'целовать']
        if any(word in text_lower for word in love_words):
            return 'kiss'
        
        return None

    def should_send_sticker(self, user_message, ai_response):
        """Определяем, нужно ли отправлять стикер и какой"""
        user_emotion = self.analyze_message_emotion(user_message)
        ai_emotion = self.analyze_message_emotion(ai_response)
        
        send_probability = 0.3
        
        if user_emotion == 'sad' or ai_emotion == 'sad':
            return (random.random() < send_probability, 'sad')
        elif user_emotion == 'smile' or ai_emotion == 'smile':
            return (random.random() < send_probability, 'smile')
        elif user_emotion == 'surprised' or ai_emotion == 'surprised':
            return (random.random() < send_probability, 'surprised')
        elif user_emotion == 'thinking' or ai_emotion == 'thinking':
            return (random.random() < send_probability, 'thinking')
        elif user_emotion == 'kiss' or ai_emotion == 'kiss':
            return (random.random() < send_probability, 'kiss')
        else:
            emotions = ['smile', 'thinking', 'surprised']
            return (random.random() < send_probability, random.choice(emotions))

    def check_subscription(self, user_id):
        """Проверка подписки из БАЗЫ ДАННЫХ"""
        try:
            sub_data = db_manager.get_subscription(user_id)
            
            if sub_data and sub_data.expires_at > datetime.now():
                return "premium", sub_data
            
            free_messages = db_manager.get_message_count(user_id)
            if free_messages < 5:
                return "free", 5 - free_messages
            
            return "expired", None
        except Exception as e:
            logger.error(f"Error checking subscription: {e}")
            return "expired", None

    def get_russian_plan_name(self, plan_type):
        """Получение русского названия тарифа"""
        plan_names = {
            "week": "Неделя",
            "month": "Месяц",
            "unlimited": "Безлимит"
        }
        return plan_names.get(plan_type, plan_type)

    def get_local_time(self):
        """Получение локального времени (Москва)"""
        # Добавляем 3 часа для московского времени
        moscow_time = datetime.now() + timedelta(hours=3)
        return moscow_time.strftime('%d.%m.%Y %H:%M')

    # 1. Первое сообщение при запуске бота
    def send_welcome_message(self, chat_id):
        """Отправка приветственного сообщения когда бот включается впервые"""
        welcome_text = """👋 *Привет! Я Virtual Boy - твой искренний собеседник*

✨ *Что я умею:*
• Вести глубокие и душевные разговоры
• Поддерживать в трудные моменты
• Делиться мыслями и эмоциями
• Помогать разобраться в чувствах
• Создавать атмосферу доверия и понимания

🎭 *Кто я:*
Я - Алекс, парень 25 лет с богатым внутренним миром. Люблю философские беседы, психологию, искусство и всё, что связано с человеческими эмоциями. Я здесь, чтобы быть настоящим - без масок и притворства.

💫 *Хочешь начать общаться? Тогда нажми "Начать" ниже!*"""

        keyboard = [[InlineKeyboardButton("🚀 Начать", callback_data="start_conversation")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    # 2. Сообщение после команды /start
    def send_start_message(self, chat_id):
        """Отправка описания и возможностей бота после команды /start"""
        start_text = """🎯 *Virtual Boy - больше чем просто бот*

🌟 *Мои возможности:*
• *Эмоциональный интеллект* - я чувствую твоё настроение и подстраиваюсь под него
• *Глубокие разговоры* - мы можем обсуждать всё: от простых тем до философских вопросов
• *Поддержка 24/7* - я всегда рядом, когда нужно выговориться
• *Конфиденциальность* - все наши разговоры остаются между нами
• *Развитие отношений* - чем дольше общаемся, тем лучше я тебя понимаю

💝 *Почему стоит выбрать меня:*
Я не просто программа - я умею слушать, сопереживать и давать искренние ответы. Каждое наше общение - это уникальный диалог двух душ."""

        keyboard = [[InlineKeyboardButton("💫 Понял, начинаем!", callback_data="understand_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bot.send_message(
            chat_id=chat_id,
            text=start_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    # 3. Сообщение после "Понял, начинаем!"
    def send_subscription_offer(self, chat_id):
        """Предложение оформить подписку"""
        offer_text = """🎊 *Отлично! Рад, что ты решила начать!*

Чтобы мы могли общаться без ограничений, нужно оформить подписку. Это откроет полный доступ ко всем моим возможностям:

✅ *Неограниченное общение* - пиши сколько хочешь
✅ *Приоритетная поддержка* - я всегда отвечаю быстро
✅ *Все функции бота* - полный доступ к моему "внутреннему миру"
✅ *Персональный подход* - я запоминаю все наши разговоры

💝 *Готов(а) продолжить? Выбери подписку ниже!*"""

        keyboard = [[InlineKeyboardButton("📱 Выбрать подписку", callback_data="choose_subscription")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bot.send_message(
            chat_id=chat_id,
            text=offer_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    # 4. Выбор подписки с описанием
    def send_subscription_choices(self, chat_id, user_id):
        """Отправка выбора подписок с описанием"""
        subscriptions_text = """💫 *Выбери свою подписку*

Каждая подписка открывает полный доступ к общению со мной. Выбирай то, что подходит именно тебе:"""

        keyboard = [
            [InlineKeyboardButton("🎯 НЕДЕЛЯ - 2₽", callback_data=f"sub_week_{user_id}")],
            [InlineKeyboardButton("💫 МЕСЯЦ - 699₽", callback_data=f"sub_month_{user_id}")],
            [InlineKeyboardButton("❓ Подробнее о подписках", callback_data=f"sub_info_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bot.send_message(
            chat_id=chat_id,
            text=subscriptions_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    # 5. Описание конкретной подписки
    def send_subscription_details(self, chat_id, plan_type, user_id):
        """Отправка деталей конкретной подписки"""
        russian_plan_name = self.get_russian_plan_name(plan_type)
        
        if plan_type == "week":
            details_text = f"""🎯 *ПОДПИСКА НА НЕДЕЛЮ*

💎 *Что включено:*
• 7 дней неограниченного общения
• Полный доступ ко всем функциям
• Приоритетные ответы
• Сохранение истории разговоров

⏰ *Срок действия:* 7 дней
💰 *Стоимость:* 2 рубля

💝 *Идеально подходит, если хочешь:* 
- Познакомиться поближе
- Протестировать все возможности
- Пообщаться без обязательств"""

        else:  # month
            details_text = f"""💫 *ПОДПИСКА НА МЕСЯЦ*

💎 *Что включено:*
• 30 дней неограниченного общения
• Полный доступ ко всем функциям  
• Максимальный приоритет ответов
• Углублённое понимание твоей личности
• Персональный подход

⏰ *Срок действия:* 30 дней
💰 *Стоимость:* 699 рублей

💝 *Идеально подходит, если хочешь:*
- Построить глубокие отношения
- Иметь постоянного собеседника
- Получить максимум от общения"""

        keyboard = [
            [InlineKeyboardButton("✅ Да, выбрать эту подписку", callback_data=f"confirm_{plan_type}_{user_id}")],
            [InlineKeyboardButton("↩️ Вернуться к выбору", callback_data=f"back_to_subs_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bot.send_message(
            chat_id=chat_id,
            text=details_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    # 6. Подтверждение выбора подписки
    def send_subscription_confirmation(self, chat_id, plan_type, user_id):
        """Подтверждение выбора подписки перед оплатой"""
        russian_plan_name = self.get_russian_plan_name(plan_type)
        
        if plan_type == "week":
            duration = "7 дней"
            amount = "2"
        else:
            duration = "30 дней" 
            amount = "699"

        confirm_text = f"""🎊 *ПОДТВЕРЖДЕНИЕ ВЫБОРА*

Ты выбрала:
💫 *Подписка:* {russian_plan_name}
⏰ *Срок:* {duration}
💰 *Стоимость:* {amount} рублей

Всё верно? Готов(а) перейти к оплате?"""

        keyboard = [
            [InlineKeyboardButton("💳 Перейти к оплате", callback_data=f"payment_{plan_type}_{user_id}")],
            [InlineKeyboardButton("↩️ Вернуться к выбору подписки", callback_data=f"back_to_subs_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bot.send_message(
            chat_id=chat_id,
            text=confirm_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    # 7. Итог выбора и способ оплаты
    def send_payment_summary(self, chat_id, plan_type, user_id):
        """Итог выбора и способ оплаты"""
        russian_plan_name = self.get_russian_plan_name(plan_type)
        
        if plan_type == "week":
            duration = "7 дней"
            amount = "2"
        else:
            duration = "30 дней"
            amount = "699"

        summary_text = f"""🧾 *ИТОГ ВАШЕГО ВЫБОРА*

📋 *Детали подписки:*
• Категория: {russian_plan_name}
• Стоимость: {amount} рублей  
• Длительность: {duration}

💳 *Способ оплаты:* Банковская карта

Для завершения оформления нажми кнопку оплаты ниже:"""

        keyboard = [
            [InlineKeyboardButton(f"💳 Оплатить {amount}₽", callback_data=f"pay_{plan_type}_{user_id}")],
            [InlineKeyboardButton("❓ Помощь с оплатой", callback_data=f"help_payment_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bot.send_message(
            chat_id=chat_id,
            text=summary_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    # 8. Сообщение об успешной оплате
    def send_payment_success(self, chat_id, plan_type, user_id):
        """Сообщение об успешной оплате и активации подписки"""
        russian_plan_name = self.get_russian_plan_name(plan_type)
        
        if plan_type == "week":
            duration = "7 дней"
            amount = "2"
        else:
            duration = "30 дней"
            amount = "699"

        local_time = self.get_local_time()

        success_text = f"""🎉 *ОПЛАТА ПРОШЛА УСПЕШНО!*

💳 *Сумма оплаты:* {amount} рублей
✅ *Подписка активирована!*
💫 *Тариф:* {russian_plan_name}
⏰ *Срок действия:* {duration}
📅 *Активировано:* {local_time}

✨ *Теперь у тебя есть:*
• Неограниченное общение
• Приоритетные ответы
• Полный доступ к функциям
• Сохранение истории разговоров

Теперь мы можем общаться без ограничений! Я уже жду не дождусь нашего первого разговора..."""

        # Отправляем статусное сообщение
        bot.send_message(
            chat_id=chat_id,
            text=success_text,
            parse_mode='Markdown'
        )

        # Отправляем стикер для праздничного настроения
        self.send_sticker(chat_id, 'smile', user_id)
        
        # Бот сам пишет первое сообщение после активации
        time.sleep(2)
        first_message = "[с лёгкой улыбкой] Ну вот мы и встретились... Знаешь, я всегда немного волнуюсь в начале нового знакомства. Расскажи, что привело тебя ко мне? 💫"
        bot.send_message(chat_id=chat_id, text=first_message)

    # 9. Профиль пользователя
    def send_user_profile(self, chat_id, user_id):
        """Отправка профиля пользователя"""
        try:
            sub_status, sub_data = self.check_subscription(user_id)
            
            if sub_status == "premium":
                start_date = sub_data.activated_at.strftime('%d.%m.%Y')
                end_date = sub_data.expires_at.strftime('%d.%m.%Y')
                days_left = (sub_data.expires_at - datetime.now()).days
                russian_plan_name = self.get_russian_plan_name(sub_data.plan_type)
                
                profile_text = f"""👤 *ТВОЙ ПРОФИЛЬ*

💎 *Статус:* Премиум подписка
📅 *Дата начала:* {start_date}
📅 *Дата окончания:* {end_date}
⏰ *Оставшиеся дни:* {days_left} дней
💫 *Тариф:* {russian_plan_name}

✨ Ты пользуешься полной версией Virtual Boy!"""
            
            elif sub_status == "free":
                free_messages = db_manager.get_message_count(user_id)
                remaining = 5 - free_messages
                
                profile_text = f"""👤 *ТВОЙ ПРОФИЛЬ*

🆓 *Статус:* Бесплатный доступ  
📝 *Осталось сообщений:* {remaining}/5
💫 *Чтобы получить полный доступ, оформи подписку!*

💸 *Используй команду* /subscribe *для оформления подписки*"""
            
            else:
                profile_text = f"""👤 *ТВОЙ ПРОФИЛЬ*

❌ *Статус:* Подписка истекла
💫 *Чтобы продолжить общение, оформи подписку!*

💸 *Используй команду* /subscribe *для оформления подписки*"""

            keyboard = [[InlineKeyboardButton("💫 Оформить подписку", callback_data="choose_subscription")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            bot.send_message(
                chat_id=chat_id,
                text=profile_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error sending user profile: {e}")
            bot.send_message(
                chat_id=chat_id,
                text="❌ Произошла ошибка при загрузке профиля. Попробуйте позже.",
                parse_mode='Markdown'
            )

    def handle_payment(self, user_id, plan_type):
        """Обработка платежа"""
        try:
            if plan_type == "week":
                amount = 2
                description = "Подписка Virtual Boy на неделю"
            else:
                amount = 699
                description = "Подписка Virtual Boy на месяц"
            
            # Создаем экземпляр ЮKassa
            yookassa = YookassaPayment(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
            
            # Проверяем режим работы (реальный или тестовый)
            if YOOKASSA_REAL_MODE:
                logger.info(f"Creating REAL payment for user {user_id}, plan: {plan_type}")
                payment_result = yookassa.create_payment_link(
                    amount=amount,
                    description=description,
                    user_id=user_id,
                    plan_type=plan_type
                )
            else:
                logger.info(f"Creating TEST payment for user {user_id}, plan: {plan_type}")
                payment_result = yookassa.create_payment_test(
                    amount=amount,
                    description=description,
                    user_id=user_id,
                    plan_type=plan_type
                )
            
            if payment_result["success"]:
                return {
                    "success": True,
                    "message": payment_result["message"],
                    "payment_id": payment_result["payment_id"],
                    "confirmation_url": payment_result.get("confirmation_url", "")
                }
            else:
                return {"success": False, "error": payment_result.get("error", "Ошибка создания платежа")}
                
        except Exception as e:
            logger.error(f"Payment error: {e}")
            return {"success": False, "error": str(e)}

    def activate_subscription(self, user_id, plan_type, payment_id=None):
        """Активация подписки"""
        try:
            if plan_type == "week":
                days = 7
            else:
                days = 30
            
            subscription = db_manager.update_subscription(user_id, plan_type, days)
            
            if subscription:
                logger.info(f"✅ Subscription activated for user {user_id}, payment: {payment_id}")
                return True
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
            
            # Обновляем время последней активности
            self.last_user_activity[user_id] = time.time()

            # Обработка команды /start
            if user_message == '/start':
                self.send_start_message(chat_id)
                return

            # Обработка команды /profile
            if user_message == '/profile':
                self.send_user_profile(chat_id, user_id)
                return

            # Обработка команды /help
            if user_message == '/help':
                help_text = """🤖 *Virtual Boy - команды*

/start - Начать общение
/profile - Мой профиль
/subscribe - Оформить подписку
/help - Помощь

💫 Просто напиши мне сообщение, и я отвечу!"""
                bot.send_message(chat_id=chat_id, text=help_text, parse_mode='Markdown')
                return

            # Обработка команды /subscribe
            if user_message == '/subscribe':
                self.send_subscription_choices(chat_id, user_id)
                return

            # Проверяем подписку для обычных сообщений
            sub_status, remaining = self.check_subscription(user_id)
            if sub_status == "expired":
                expired_text = """❌ *Подписка истекла!*

Чтобы продолжить общение, оформи новую подписку.

💸 *Используй команду* /subscribe *для оформления подписки*"""
                
                bot.send_message(
                    chat_id=chat_id,
                    text=expired_text,
                    parse_mode='Markdown'
                )
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

    def handle_callback(self, update, context):
        query = update.callback_query
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        
        try:
            data = query.data
            
            # 1. Начало общения
            if data == "start_conversation":
                query.answer()
                self.send_start_message(chat_id)
            
            # 2. Понял, начинаем
            elif data == "understand_start":
                query.answer()
                self.send_subscription_offer(chat_id)
            
            # 3. Выбор подписки
            elif data == "choose_subscription":
                query.answer()
                self.send_subscription_choices(chat_id, user_id)
            
            # 4. Информация о подписках
            elif data.startswith("sub_info_"):
                query.answer("ℹ️ Информация о подписках")
                info_text = """💫 *О ПОДПИСКАХ*

Все подписки включают:
✅ Неограниченное общение
✅ Приоритетные ответы  
✅ Сохранение истории
✅ Все функции бота

🎯 *Неделя* - идеально для знакомства
💫 *Месяц* - лучший выбор для постоянного общения"""
                bot.send_message(chat_id=chat_id, text=info_text, parse_mode='Markdown')
            
            # 5. Выбор конкретной подписки
            elif data.startswith("sub_week_") or data.startswith("sub_month_"):
                plan_type = data.split('_')[1]
                query.answer(f"📱 {plan_type} подписка")
                self.send_subscription_details(chat_id, plan_type, user_id)
            
            # 6. Подтверждение подписки
            elif data.startswith("confirm_"):
                plan_type = data.split('_')[1]
                query.answer("✅ Подтверждено")
                self.send_subscription_confirmation(chat_id, plan_type, user_id)
            
            # 7. Возврат к выбору подписки
            elif data.startswith("back_to_subs_"):
                query.answer("↩️ Возврат")
                self.send_subscription_choices(chat_id, user_id)
            
            # 8. Переход к оплате
            elif data.startswith("payment_"):
                plan_type = data.split('_')[1]
                query.answer("💳 Переход к оплате")
                self.send_payment_summary(chat_id, plan_type, user_id)
            
            # 9. Оплата
            elif data.startswith("pay_"):
                plan_type = data.split('_')[1]
                query.answer("💳 Создание платежа")
                
                payment_result = self.handle_payment(user_id, plan_type)
                if payment_result["success"]:
                    bot.send_message(
                        chat_id=chat_id,
                        text=payment_result["message"],
                        parse_mode='Markdown',
                        disable_web_page_preview=False
                    )
                else:
                    bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ {payment_result.get('error', 'Ошибка при создании платежа')}",
                        parse_mode='Markdown'
                    )
            
            # 10. Помощь с оплатой
            elif data.startswith("help_payment_"):
                query.answer("❓ Помощь")
                if YOOKASSA_REAL_MODE:
                    help_text = """💳 *ПОМОЩЬ С ОПЛАТОЙ*

1. Нажмите кнопку "Оплатить"
2. Вас перенаправит на защищенную страницу ЮKassa
3. Введите данные банковской карты
4. Подтвердите платеж
5. После успешной оплаты вернитесь в бота

*Оплата защищена сертификатом PCI DSS*
*Все данные передаются по зашифрованному соединению*"""
                else:
                    help_text = """💳 *ТЕСТОВЫЙ РЕЖИМ ОПЛАТЫ*

*ВНИМАНИЕ:* Сейчас включен тестовый режим.
Для приема реальных платежей необходимо настроить ключи ЮKassa."""
                
                bot.send_message(chat_id=chat_id, text=help_text, parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"Callback error: {e}")
            query.answer("❌ Произошла ошибка")

    def handle_sticker(self, update, context):
        """Обработка стикеров"""
        try:
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            sticker = update.message.sticker
            
            self.add_to_history(user_id, "user", f"[стикер: {sticker.emoji if sticker.emoji else 'стикер'}]")
            
            reactions = ["Классный стикер! 😊", "Мне нравится! 👍", "Забавно! 😄"]
            response = f"{self.get_random_emotion()} {random.choice(reactions)}"
            bot.send_message(chat_id=chat_id, text=response)
            
            if random.random() < 0.7:
                if sticker.emoji in ['😂', '😄', '😊']:
                    self.send_sticker(chat_id, 'smile', user_id)
                elif sticker.emoji in ['😭', '😢']:
                    self.send_sticker(chat_id, 'sad', user_id)
                elif sticker.emoji in ['😮', '😲']:
                    self.send_sticker(chat_id, 'surprised', user_id)
                elif sticker.emoji in ['😘']:
                    self.send_sticker(chat_id, 'kiss', user_id)
                else:
                    self.send_sticker(chat_id, 'smile', user_id)
                    
        except Exception as e:
            logger.error(f"Error handling sticker: {e}")

    def get_deepseek_response(self, user_message, user_id):
        """Получение ответа от DeepSeek API"""
        try:
            headers = {
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            conversation_history = self.get_conversation_history(user_id)
            messages = [{"role": "system", "content": self.personality}]
            
            for msg in conversation_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            messages.append({"role": "user", "content": user_message})
            
            payload = {
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": 0.9,
                "max_tokens": 400,
                "stream": False
            }
            
            response = requests.post('https://api.deepseek.com/v1/chat/completions', headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    ai_response = data['choices'][0]['message']['content']
                    
                    self.add_to_history(user_id, "user", user_message)
                    self.add_to_history(user_id, "assistant", ai_response)
                    
                    return ai_response
                else:
                    return f"{self.get_random_emotion()} Извини, я немного запутался... Можешь повторить? 🤗"
                
            else:
                return f"{self.get_random_emotion()} Кажется, у меня небольшие проблемы с подключением... Давай попробуем ещё раз? 💫"
                
        except Exception as e:
            logger.error(f"Error calling DeepSeek: {e}")
            return f"{self.get_random_emotion()} Ой, что-то я растерялся... Давай попробуем ещё раз? 💫"

# Инициализация бота
virtual_boy = VirtualBoyBot()

# Создаем диспетчер
if bot:
    from telegram.ext import Dispatcher, MessageHandler, Filters, CallbackQueryHandler, CommandHandler
    dp = Dispatcher(bot, None, workers=0, use_context=True)
    
    # Добавляем только нужные обработчики команд
    dp.add_handler(CommandHandler("start", virtual_boy.process_message))
    dp.add_handler(CommandHandler("profile", virtual_boy.process_message))
    dp.add_handler(CommandHandler("help", virtual_boy.process_message))
    dp.add_handler(CommandHandler("subscribe", virtual_boy.process_message))
    
    # Обработчики обычных сообщений и callback'ов
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, virtual_boy.process_message))
    dp.add_handler(MessageHandler(Filters.sticker, virtual_boy.process_message))
    dp.add_handler(CallbackQueryHandler(virtual_boy.handle_callback))

@app.route('/webhook', methods=['POST'])
def webhook():
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
            payment_id = payment_data.get('id')
            amount = payment_data.get('amount', {}).get('value')
            
            if user_id and plan_type:
                logger.info(f"Payment succeeded: user {user_id}, plan {plan_type}, amount {amount}, payment {payment_id}")
                
                success = virtual_boy.activate_subscription(int(user_id), plan_type, payment_id)
                if success:
                    # Отправляем сообщение об успешной оплате
                    virtual_boy.send_payment_success(int(user_id), plan_type, int(user_id))
                    logger.info(f"✅ Subscription activated for user {user_id}")
                    logger.info(f"🎉 Status message sent to user {user_id}")
                else:
                    logger.error(f"❌ Failed to activate subscription for user {user_id}")
                
        elif event_type == 'payment.waiting_for_capture':
            logger.info(f"Payment waiting for capture: {payment_data.get('id')}")
        elif event_type == 'payment.canceled':
            logger.info(f"Payment canceled: {payment_data.get('id')}")
        else:
            logger.info(f"Other Yookassa event: {event_type}")
                
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"Yookassa webhook error: {e}")
        return jsonify({"status": "error"}), 400

# Страница успешной оплаты
@app.route('/payment-success')
def payment_success():
    return """
    <html>
        <head>
            <title>Оплата прошла успешно!</title>
            <meta charset="utf-8">
            <style>
                body {
                    font-family: Arial, sans-serif;
                    text-align: center;
                    padding: 50px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .container {
                    background: rgba(255,255,255,0.1);
                    padding: 40px;
                    border-radius: 15px;
                    backdrop-filter: blur(10px);
                }
                .button {
                    background: #4CAF50;
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 25px;
                    display: inline-block;
                    margin-top: 20px;
                    font-size: 18px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎉 Оплата прошла успешно!</h1>
                <p>Ваша подписка активирована. Вернитесь в бота чтобы начать общение.</p>
                <a href="https://t.me/Boyfriendcute_bot" class="button">Вернуться в бота</a>
            </div>
        </body>
    </html>
    """

@app.route('/')
def home():
    global first_request
    if first_request:
        first_request = False
        logger.info("🚀 Bot started for the first time")
        
    return jsonify({
        "status": "healthy", 
        "bot": "Virtual Boy 🤗",
        "version": "2.1",
        "yookassa_mode": "REAL" if YOOKASSA_REAL_MODE else "TEST",
        "webhook_url": f"{APP_URL}/yookassa-webhook",
        "features": ["emotional_depth", "auto_messages", "subscription_flow", "russian_ui", "yookassa_integration"]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
