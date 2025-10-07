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
    from telegram.utils.request import Request
    request_obj = Request(con_pool_size=8)
    bot = Bot(token=BOT_TOKEN, request=request_obj)

# Стикеры сгруппированы по эмоциям
STICKERS = {
    'happy': [
        'CAACAgUAAxkBAAMLaOVwjWUZp1NP2BGuwKmjRF6OLI4AAjQEAAJYdclX8q2oxkbXFAE2BA',  # 😆
        'CAACAgUAAxkBAAMNaOVwk-ocq67z8o18DiiqeVzoETIAAtgVAALtIDBVnHCyMkbXFAE2BA',   # 🤣
        'CAACAgUAAxkBAAMPaOVwluKnOJlR7LhcKTLtVGS2rhAAAlwIAAJhLGFU3X2RwyBQui02BA', # 🤣
        'CAACAgUAAxkBAAMRaOVwmpczEO9zyabBtOolNv6ES2IAAj4FAALO4NFXlAFvncKMOnI2BA', # 😆
        'CAACAgUAAxkBAAMTaOVwnCtTxwABI2ZlFIxHUbF0tRX9AAJIBgAC6qPYV9-RdK9DxL27NgQ', # 😃
        'CAACAgUAAxkBAAMXaOVwpFo4mEI3Q15mt_RdYMHpYQsAAhkFAAJTHhlUx7qMwUdQrKA2BA', # 😂
        'CAACAgUAAxkBAAM9aOV1DnbobFVVxWOR6MbwKCPvNr8AAkYFAALFctlX0O9u4pVuENE2BA', # 😁
        'CAACAgUAAxkBAANvaOV1ZAIyQoH2gG0HJBDrimTbW04AAtsRAAJm8clUmEcsxPLhLBM2BA', # 😁
        'CAACAgUAAxkBAANbaOV1RNOUsfpscsWpLzsWctUpSPAAAocPAAIQq6BULmUWUceQ9l02BA', # 😄
        'CAACAgUAAxkBAANhaOV1TIyAGe9mO2gXQ-x0_mZpoC4AAl4PAAKgCqlUkYi61v_Robk2BA', # 😊
    ],
    'excited': [
        'CAACAgUAAxkBAAMZaOVwpjX6zqvuYUlbRXgleJlO-PAAAlkFAAL_D9BXlbrCo5StI6g2BA', # 👏
        'CAACAgUAAxkBAANXaOV1PNaL3dtp_gQeAAH2cFVbRXOtAALCDwACVCZ4VPTM2pdKNmxDNgQ', # 👏
        'CAACAgUAAxkBAAM_aOV1FNjbWkn-9Z1DaEW4MUDUl5AAArQFAALYI_FXpiYOakfl3u82BA', # 🕺
        'CAACAgUAAxkBAAMzaOV07KjoPkqTShVeExuwziKmORUAAvYLAALsoSlVN8FuIWfrVZM2BA', # 🔥
        'CAACAgUAAxkBAANzaOV1b5x9Sv8cWO3c_eyZqS32k1AAAmcVAAI7PQFV-fnWOLEqsNw2BA', # 🔥
        'CAACAgUAAxkBAAN3aOV1dm6wzH4mUlkoT8vvyZRHpbcAAgQQAAKHFQhVDA6AvfnwA7o2BA', # 🎶
    ],
    'thoughtful': [
        'CAACAgUAAxkBAAMVaOVwoc-42szx4QOqA8ue2_kqPXQAAlEGAAKkbdBXN_vBCmyNvTc2BA', # 🤨
        'CAACAgUAAxkBAANLaOV1J87qAgABmuhhxwjbEaW8-l8bAALFBAACa2cYVEPTSfCboscONgQ', # 🧐
        'CAACAgUAAxkBAAODaOV1iyf4Tp2I_FqJ1MEElNZiPT4AAucRAALLy_BVh6CY7cuuTSA2BA', # 🤔
        'CAACAgUAAxkBAANHaOV1IcE-E4O_O26bAAEHvV7dEWhsAAIvBQACdDvxV44Hc91-8uH2NgQ', # 🧠
    ],
    'sad': [
        'CAACAgUAAxkBAAMnaOVwt1X88GnFDsN6yPKBGtYB3vUAAqUGAAItj-hXZkzTnPfY-Lk2BA', # 😭
        'CAACAgUAAxkBAAMpaOVwuoiXB2zXCyHL-65qOb_O6CAAAqkEAAL6cJBUBAgsHkAohMw2BA', # 😭
        'CAACAgUAAxkBAANFaOV1HuGyHJ-fTpZBqQRctu63q8gAAsMFAAJPF2FUed3lJcbaSbo2BA', # 😭
        'CAACAgUAAxkBAANjaOV1Tvz3j7yGdzImS14sOHdM_CIAAnETAAKni6lUAWYX7973Ieg2BA', # 😭
        'CAACAgUAAxkBAAOJaOV1kXDw4IuTPSv9xxGugl8DAe8AAv0PAAK94MhWfjwn-M8jsoM2BA', # 😫
    ],
    'surprised': [
        'CAACAgUAAxkBAAM3aOV0_1W18nu7-6hoh5qcZ2FGxzQAAs0KAAIg59lVCi2RCriwT9A2BA', # 😱
        'CAACAgUAAxkBAAN5aOV1fS230i7n_xWH5I0EPDJwN0QAAkUPAAK1ivlV6a4LlVT2Fqo2BA', # 😱
        'CAACAgUAAxkBAAN1aOV1dfJolvgrfbxUMZdYlZvbseMAAuYPAAK5hglVlOyVVM3_6DQ2BA', # 😲
        'CAACAgUAAxkBAAM7aOV1CFR0GwABwOwzcM0wJGoFdY30AAKXCgACV4cpVWWy2wd1FJI4NgQ', # 😨
        'CAACAgUAAxkBAANPaOV1LYMmqPIUdMfN-VeeU_FqlxYAAh0FAAL53thXYWNfK99_mSY2BA', # 😰
    ],
    'cool': [
        'CAACAgUAAxkBAAMbaOVwqAPY9Z2ZMGhyj1LahL1o_hAAAgkEAALHw3lUjKASq5URxKE2BA', # 🌚
        'CAACAgUAAxkBAANJaOV1Jcik46P1JI5oaVyZRStvgiUAAtwKAAJuLShV9vkd0B8JLR82BA', # 😎
        'CAACAgUAAxkBAAM5aOV1BVr5FCdcCoOqZkQAAWztEB5NAAIXCAAC3-EAAVaCiOfb9qzqzzYE', # 😏
        'CAACAgUAAxkBAANxaOV1a8FUlSQ-yO-BTlTyJLUQPHsAAkcQAAI8JtlU0If0xEJwN9o2BA', # 😏
    ],
    'neutral': [
        'CAACAgUAAxkBAAMjaOVwswzEhwj6Q2AN1WfUd0U-e8QAAssIAAIXaZBVaasDzLMRIr82BA', # 😌
        'CAACAgUAAxkBAANlaOV1Uc47vIWNAXDZXThxlxPW0ooAAokRAALESqlUnGaXb9u1rvY2BA', # 😒
        'CAACAgUAAxkBAANdaOV1RtyM8zIWqnNq5Gfynch-bKQAAlcSAALeK6lUwrQcCyjCuLE2BA', # 🫥
        'CAACAgUAAxkBAANDaOV1HFVrX46orckc5WKkmjiEGosAAmwEAAJ8txFW6a19nBQM5Jo2BA', # 🗿
    ],
    'reactions': [
        'CAACAgUAAxkBAANTaOV1N_DSD_RErE82zJ1yaUkbFfcAApsEAALygeFXA0Wl3FvY7wI2BA', # 👌
        'CAACAgUAAxkBAANpaOV1W53WkN-KZ0QMW1RXTURHnogAAm0RAAKY7alU-DkmZIoo7os2BA', # 👍
        'CAACAgUAAxkBAAOHaOV1j5BvaYemJFFLstXrL2gUrzgAAv0SAAIkGdBWWSWTZ3swBTM2BA', # 👍
        'CAACAgUAAxkBAAOFaOV1jQVIkvf7t398Ndh8K8nL7LsAAv0TAAOu0VaRLcWmdHpxUDYE', # 👈
    ]
}

# Словарь для отслеживания использованных стикеров по пользователям
used_stickers = {}

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
        
        # Время последнего сообщения от пользователя для авто-сообщений
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

    def send_sticker(self, chat_id, emotion_type=None, user_id=None):
        """Отправка стикера с учетом контекста и без повторений"""
        try:
            if user_id not in used_stickers:
                used_stickers[user_id] = set()
            
            if emotion_type and emotion_type in STICKERS:
                available_stickers = [s for s in STICKERS[emotion_type] if s not in used_stickers[user_id]]
                
                if not available_stickers:
                    # Если все стикеры этой эмоции использованы, сбросим для этого пользователя
                    used_stickers[user_id] = set()
                    available_stickers = STICKERS[emotion_type]
                
                if available_stickers:
                    sticker_id = random.choice(available_stickers)
                    used_stickers[user_id].add(sticker_id)
                else:
                    return False
            else:
                # Случайный стикер из всех доступных
                all_available = []
                for emotion_stickers in STICKERS.values():
                    all_available.extend([s for s in emotion_stickers if s not in used_stickers[user_id]])
                
                if not all_available:
                    used_stickers[user_id] = set()
                    all_available = [s for emotion_stickers in STICKERS.values() for s in emotion_stickers]
                
                if all_available:
                    sticker_id = random.choice(all_available)
                    used_stickers[user_id].add(sticker_id)
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
            # На грустные сообщения отправляем реже и только поддерживающие стикеры
            send_probability = 0.1
            return (random.random() < send_probability, 'sad')
        
        elif user_emotion == 'happy' or ai_emotion == 'happy':
            # На радостные сообщения отправляем чаще
            send_probability = 0.3
            return (random.random() < send_probability, 'happy')
        
        elif user_emotion == 'surprised' or ai_emotion == 'surprised':
            send_probability = 0.25
            return (random.random() < send_probability, 'surprised')
        
        elif user_emotion == 'thoughtful' or ai_emotion == 'thoughtful':
            send_probability = 0.15
            return (random.random() < send_probability, 'thoughtful')
        
        else:
            # Случайный стикер для нейтральных сообщений
            return (random.random() < send_probability, random.choice(list(STICKERS.keys())))

    def check_auto_message(self, user_id, chat_id):
        """Проверка необходимости авто-сообщения"""
        try:
            now = time.time()
            last_activity = self.last_user_activity.get(user_id, 0)
            
            # Если прошло больше 2 минут с последнего сообщения пользователя
            if now - last_activity > 120:  # 2 минуты
                # 30% шанс отправить авто-сообщение
                if random.random() < 0.3:
                    question = random.choice(self.auto_questions)
                    bot.send_message(
                        chat_id=chat_id,
                        text=f"{self.get_random_emotion()} {question}"
                    )
                    # Отправляем нейтральный стикер с 30% шансом
                    if random.random() < 0.3:
                        self.send_sticker(chat_id, 'neutral', user_id)
                    return True
                    
        except Exception as e:
            logger.error(f"Error in auto message: {e}")
        return False

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
                # Отправляем праздничный стикер
                self.send_sticker(user_id, 'excited', user_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error activating subscription: {e}")
            return False

    def process_message(self, update, context):
        try:
            # Проверяем, это стикер или текст
            if update.message.sticker:
                self.handle_sticker(update, context)
                return
                
            user_message = update.message.text
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            user_name = update.message.from_user.first_name
            
            logger.info(f"📩 Message from {user_name} ({user_id}): {user_message}")

            # Обновляем время последней активности
            self.last_user_activity[user_id] = time.time()

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

            # Команда помощи - показываем все команды
            if user_message == '/help' or user_message == '/start':
                help_text = """🤖 *Доступные команды:*

/start - Начать общение
/help - Показать это сообщение
/profile - Посмотреть свой профиль и подписку  
/subscribe - Выбрать подписку
/test_sticker - Проверить отправку стикеров
/test_auto - Проверить авто-сообщения

💫 Просто напиши мне что-нибудь, и я отвечу!"""
                
                bot.send_message(
                    chat_id=chat_id,
                    text=help_text,
                    parse_mode='Markdown'
                )
                return

            # Тест стикеров
            if user_message == '/test_sticker':
                bot.send_message(
                    chat_id=chat_id,
                    text="Проверяем стикеры разных эмоций... 😊"
                )
                # Отправляем по одному стикеру из каждой категории
                for emotion in ['happy', 'excited', 'thoughtful', 'cool']:
                    self.send_sticker(chat_id, emotion, user_id)
                    time.sleep(1)
                return

            # Тест авто-сообщений
            if user_message == '/test_auto':
                bot.send_message(
                    chat_id=chat_id,
                    text="Тестируем авто-сообщения... Жди сообщение через 10 секунд! ⏰"
                )
                # Принудительно запускаем авто-сообщение через 10 секунд
                context.job_queue.run_once(
                    lambda context: self.force_auto_message(user_id, chat_id),
                    10
                )
                return

            # Админ команда
            if user_message == '/noway147way147no147':
                db_manager.update_subscription(user_id, 'unlimited', 30)
                bot.send_message(
                    chat_id=chat_id,
                    text="✅ Админ доступ активирован! Безлимитная подписка на 30 дней! 🎉"
                )
                # Отправляем праздничный стикер
                self.send_sticker(chat_id, 'excited', user_id)
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
            
            # Определяем, нужно ли отправлять стикер и какой
            should_send, emotion_type = self.should_send_sticker(user_message, response)
            
            if should_send:
                self.send_sticker(chat_id, emotion_type, user_id)
            
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

    def handle_sticker(self, update, context):
        """Обработка получения стикера от пользователя"""
        try:
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            sticker = update.message.sticker
            
            logger.info(f"📩 Sticker from user {user_id}: {sticker.file_id}")
            
            # Добавляем информацию о стикере в историю
            self.add_to_history(user_id, "user", f"[стикер: {sticker.emoji if sticker.emoji else 'стикер'}]")
            
            # Реагируем на стикер
            reactions = [
                "Классный стикер! 😊",
                "Мне нравится этот стикер! 👍",
                "Забавно! 😄",
                "Отличный выбор стикера! 👌",
                "Ха-ха, хороший! 😂"
            ]
            
            response = f"{self.get_random_emotion()} {random.choice(reactions)}"
            bot.send_message(chat_id=chat_id, text=response)
            
            # Иногда отвечаем стикером (40% шанс)
            if random.random() < 0.4:
                # Выбираем подходящий стикер в ответ
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

    def force_auto_message(self, user_id, chat_id):
        """Принудительная отправка авто-сообщения для тестирования"""
        question = random.choice(self.auto_questions)
        bot.send_message(
            chat_id=chat_id,
            text=f"{self.get_random_emotion()} {question}"
        )
        self.send_sticker(chat_id, 'neutral', user_id)

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
            dp.add_handler(MessageHandler(Filters.text | Filters.sticker, virtual_boy.process_message))
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
        "features": ["subscriptions", "deepseek", "conversation_memory", "yookassa_payments", "postgresql_database"]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
