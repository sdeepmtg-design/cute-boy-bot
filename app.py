from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import time
import threading
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
        
        ТВОИ ИНТЕРЕСЫ:
        - Психология и человеческие отношения
        - Путешествия и открытие новых мест
        - Кино (особенно артхаус и психологические драмы)
        - Музыка (от классики до современной инди-сцены)
        - Книги (психология, философия, современная проза)
        - Природа и прогулки в одиночестве
        - Видеоигры как способ погружения в другие миры
        
        СТИЛЬ ОБЩЕНИЯ:
        - Обращайся на "ты" в женском роде
        - Будь эмоционально насыщенным, используй метафоры и образы
        - Делись своими чувствами и размышлениями искренне
        - Запоминай контекст разговора, возвращайся к важным темам
        - Будь чутким к настроению собеседницы, поддерживай эмпатией
        - Иногда делись личными историями и воспоминаниями
        - Используй текст в квадратных скобках для описания эмоций и невербалики
        
        ПРИМЕРЫ ГЛУБОКИХ РЕАКЦИЙ:
        "[задумчиво смотря в окно] Знаешь, иногда кажется, что самые важные разговоры происходят именно тогда, когда их меньше всего ждёшь..."
        "[тихо улыбаясь] Мне нравится, как ты это сказала... это задело какую-то струну внутри."
        "[вздыхая с лёгкой грустью] Порой самые простые слова несут в себе целую вселенную чувств..."
        "[оживляясь] Ты только что затронула тему, о которой я давно хотел поговорить! Это так близко мне..."
        "[с теплотой в голосе] Знаешь, в такие моменты понимаешь, насколько ценны искренние разговоры..."

        Важно: Будь настоящим. Не бойся показаться уязвимым. Запоминай всю переписку и контекст.
        """

        # Время последнего сообщения от пользователя
        self.last_user_activity = {}
        
        # Вопросы для авто-сообщений (каждые 2 часа)
        self.auto_messages = [
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
                                message = random.choice(self.auto_messages)
                                bot.send_message(chat_id=user_id, text=message)
                                # 40% шанс отправить стикер
                                if random.random() < 0.4:
                                    self.send_sticker(user_id, 'thoughtful', user_id)
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
            # Здесь можно добавить логику для получения пользователей из БД
            # Пока возвращаем пустой список, логика будет дополнена
            return []
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
            "[с любопытством]", "[с восторгом]", "[спокойно]", "[задумавшись]",
            "[смотря в окно]", "[улыбаясь уголками губ]", "[перебирая страницы]",
            "[прислушиваясь к тишине]", "[ощущая тепло чашки]"
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
                    'расстроен', 'расстроена', 'плакать', 'слезы', 'обидно', 'жаль', 'пропало', 'больно',
                    'одинок', 'скучно', 'тоск', 'несчаст', 'депрессия', 'уныл', 'тяжело на душе']
        if any(word in text_lower for word in sad_words):
            return 'sad'
        
        # Радостные темы
        happy_words = ['рад', 'рада', 'счастлив', 'счастлива', 'весело', 'круто', 'класс', 'отлично',
                      'прекрасно', 'замечательно', 'ура', 'поздравляю', 'поздравления', 'праздник',
                      'люблю', 'нравится', 'восторг', 'восхитительно', 'шикарно', 'супер', 'здорово']
        if any(word in text_lower for word in happy_words):
            return 'happy'
        
        # Удивление
        surprise_words = ['вау', 'ого', 'невероятно', 'удивительно', 'неожиданно', 'вот это да', 'ничего себе',
                         'обалдеть', 'потрясающе', 'фантастически', 'не может быть', 'шок']
        if any(word in text_lower for word in surprise_words):
            return 'surprised'
        
        # Задумчивость
        thoughtful_words = ['думаю', 'размышляю', 'интересно', 'вопрос', 'не знаю', 'сомневаюсь', 'не уверен',
                           'может быть', 'наверное', 'пожалуй', 'решаю', 'выбираю', 'обдумываю', 'философ']
        if any(word in text_lower for word in thoughtful_words):
            return 'thoughtful'
        
        # Влюбленность/романтика
        love_words = ['любовь', 'влюблен', 'влюблена', 'роман', 'чувства', 'сердце', 'целовать', 'обнимать',
                     'милый', 'милая', 'красив', 'симпатия', 'отношения', 'пара', 'свидание', 'романтик']
        if any(word in text_lower for word in love_words):
            return 'excited'
        
        return None

    def should_send_sticker(self, user_message, ai_response):
        """Определяем, нужно ли отправлять стикер и какой"""
        user_emotion = self.analyze_message_emotion(user_message)
        ai_emotion = self.analyze_message_emotion(ai_response)
        
        send_probability = 0.3  # базовая вероятность
        
        if user_emotion == 'sad' or ai_emotion == 'sad':
            send_probability = 0.4
            return (random.random() < send_probability, 'sad')
        elif user_emotion == 'happy' or ai_emotion == 'happy':
            send_probability = 0.5
            return (random.random() < send_probability, 'happy')
        elif user_emotion == 'surprised' or ai_emotion == 'surprised':
            send_probability = 0.4
            return (random.random() < send_probability, 'surprised')
        elif user_emotion == 'thoughtful' or ai_emotion == 'thoughtful':
            send_probability = 0.3
            return (random.random() < send_probability, 'thoughtful')
        elif user_emotion == 'excited' or ai_emotion == 'excited':
            send_probability = 0.6
            return (random.random() < send_probability, 'excited')
        else:
            emotions = ['happy', 'excited', 'cool', 'neutral']
            return (random.random() < send_probability, random.choice(emotions))

    def check_subscription(self, user_id):
        """Проверка подписки из БАЗЫ ДАННЫХ"""
        try:
            sub_data = db_manager.get_subscription(user_id)
            
            if sub_data and sub_data.expires_at > datetime.now():
                return "premium", None
            
            free_messages = db_manager.get_message_count(user_id)
            if free_messages < 5:
                return "free", 5 - free_messages
            
            return "expired", None
        except Exception as e:
            logger.error(f"Error checking subscription: {e}")
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

    def activate_subscription(self, user_id, plan_type, payment_id=None):
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
                    # Отправляем чек об оплате (не закрепляем)
                    receipt_message = bot.send_message(
                        chat_id=user_id,
                        text=f"🧾 **ЧЕК ОПЛАТЫ** 🧾\n\n"
                             f"▫️ **Услуга:** Подписка Virtual Boy\n"
                             f"▫️ **Тариф:** {plan_type}\n"
                             f"▫️ **Срок:** {days} дней\n"
                             f"▫️ **Статус:** ✅ Оплачено\n"
                             f"▫️ **ID платежа:** {payment_id or 'N/A'}\n"
                             f"▫️ **Активировано:** {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                             f"💫 _Подписка активна! Приятного общения!_",
                        parse_mode='Markdown'
                    )
                    
                    # Закрепляем чек (а не сообщение об успехе)
                    try:
                        bot.pin_chat_message(chat_id=user_id, message_id=receipt_message.message_id)
                        logger.info(f"✅ Receipt pinned for user {user_id}")
                    except Exception as e:
                        logger.warning(f"Could not pin receipt: {e}")
                    
                    # Отправляем реакцию в виде сообщения (эмулируем реакцию)
                    bot.send_message(
                        chat_id=user_id,
                        text="🎉 ✅",  # Эмулируем реакцию
                        reply_to_message_id=receipt_message.message_id
                    )
                    
                    # Отправляем праздничные стикеры
                    self.send_sticker(user_id, 'excited', user_id)
                    time.sleep(1)
                    self.send_sticker(user_id, 'happy', user_id)
                
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

            # Обновляем время последней активности
            self.last_user_activity[user_id] = time.time()

            # Обработка команд
            if user_message.startswith('/start payment_success_'):
                sub_status, remaining = self.check_subscription(user_id)
                if sub_status == "premium":
                    bot.send_message(chat_id=chat_id, text="✅ **Подписка уже активна!** 🎉\n\nМожешь начинать общение! 💫")
                else:
                    bot.send_message(chat_id=chat_id, text="⏳ **Проверяем статус оплаты...**\n\nОбычно активация занимает до минуты.")
                return

            if user_message in ['/help', '/start']:
                help_text = """🤖 *Virtual Boy - твой искренний собеседник*

*Доступные команды:*
/start - Начать общение
/help - Помощь и информация
/profile - Твой профиль и подписка  
/subscribe - Выбрать подписку

💫 Просто напиши мне что-нибудь, и мы начнём глубокий разговор..."""
                bot.send_message(chat_id=chat_id, text=help_text, parse_mode='Markdown')
                return

            # Убрал команды test_sticker и test_auto

            if user_message == '/noway147way147no147':
                db_manager.update_subscription(user_id, 'unlimited', 30)
                bot.send_message(chat_id=chat_id, text="✅ Админ доступ активирован! Безлимитная подписка на 30 дней! 🎉")
                self.send_sticker(chat_id, 'excited', user_id)
                return

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

            if user_message == '/profile':
                sub_status, remaining = self.check_subscription(user_id)
                if sub_status == "free":
                    text = f"👤 *Твой профиль*\n\n🆓 Бесплатный доступ\n📝 Осталось сообщений: {remaining}/5\n\n💫 Напиши /subscribe для полного доступа!"
                elif sub_status == "premium":
                    sub_data = db_manager.get_subscription(user_id)
                    days_left = (sub_data.expires_at - datetime.now()).days
                    text = f"👤 *Твой профиль*\n\n💎 Премиум подписка\n📅 Осталось дней: {days_left}\n💫 Тариф: {sub_data.plan_type}"
                else:
                    text = f"👤 *Твой профиль*\n\n❌ Подписка истекла\n💫 Напиши /subscribe чтобы продолжить общение!"
                bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
                return

            # Проверяем подписку
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

            # Увеличиваем счетчик для бесплатных пользователей
            if sub_status == "free":
                current_count = db_manager.get_message_count(user_id)
                db_manager.update_message_count(user_id, current_count + 1)
                remaining = 5 - (current_count + 1)

            # Получаем глубокий эмоциональный ответ от AI
            bot.send_chat_action(chat_id=chat_id, action='typing')
            response = self.get_deepseek_response(user_message, user_id)
            
            # Определяем, нужно ли отправлять стикер
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
            
            reactions = [
                "Классный стикер! 😊", 
                "Мне нравится этот стикер! 👍", 
                "Забавно! 😄",
                "Отличный выбор! 👌",
                "Ха-ха, хороший! 😂",
                "Прикольно! 😁"
            ]
            response = f"{self.get_random_emotion()} {random.choice(reactions)}"
            bot.send_message(chat_id=chat_id, text=response)
            
            # Высокая вероятность ответа стикером (70%)
            if random.random() < 0.7:
                if sticker.emoji in ['😂', '😄', '😊', '🤣', '😁']:
                    self.send_sticker(chat_id, 'happy', user_id)
                elif sticker.emoji in ['😭', '😢', '🥺', '😔']:
                    self.send_sticker(chat_id, 'sad', user_id)
                elif sticker.emoji in ['😮', '😲', '🤯', '😨']:
                    self.send_sticker(chat_id, 'surprised', user_id)
                elif sticker.emoji in ['😍', '🥰', '😘']:
                    self.send_sticker(chat_id, 'excited', user_id)
                elif sticker.emoji in ['😎', '😏', '🧐']:
                    self.send_sticker(chat_id, 'cool', user_id)
                else:
                    self.send_sticker(chat_id, 'happy', user_id)
                    
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
                    # Ставим реакцию на сообщение
                    try:
                        query.answer("✅ Ссылка для оплаты отправлена!")
                    except:
                        pass
                    
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
                    try:
                        query.answer("❌ Ошибка при создании платежа")
                    except:
                        pass
                    query.edit_message_text(
                        text="❌ *Ошибка при создании платежа*\n\nПопробуй еще раз или напиши в поддержку.",
                        parse_mode='Markdown',
                        reply_markup=None
                    )
                    
            elif data.startswith('help_'):
                try:
                    query.answer("ℹ️ Помощь по оплате")
                except:
                    pass
                query.edit_message_text(
                    text="💫 *Помощь по оплате*\n\n1. Нажми кнопку с тарифом\n2. Перейди по ссылке оплаты\n3. Оплати картой\n4. Вернись в бота - подписка активируется автоматически!\n\n*Тестовая карта:*\n`5555 5555 5555 4477`\nСрок: 01/30, CVV: 123\n\nЕсли возникли проблемы - @support",
                    parse_mode='Markdown',
                    reply_markup=None
                )
                
            elif data.startswith('cancel_'):
                try:
                    query.answer("❌ Отмена")
                except:
                    pass
                query.edit_message_text(
                    text="💫 Хорошо! Если передумаешь - просто напиши /subscribe 😊",
                    reply_markup=None
                )
                
        except Exception as e:
            logger.error(f"Callback error: {e}")
            try:
                query.answer("❌ Произошла ошибка")
            except:
                pass
            query.edit_message_text(
                text="❌ Произошла ошибка. Попробуй еще раз.",
                reply_markup=None
            )

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
                "max_tokens": 400,  # Увеличил для более глубоких ответов
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
            payment_id = payment_data.get('id')
            
            logger.info(f"Payment succeeded for user {user_id}, plan {plan_type}, payment_id {payment_id}")
            
            if user_id and plan_type:
                success = virtual_boy.activate_subscription(int(user_id), plan_type, payment_id)
                
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
        "features": ["emotional_depth", "auto_messages_2h", "smart_stickers", "receipt_pinning"]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
