from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import time
import threading
import json
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
APP_URL = os.environ.get('APP_URL', 'https://cute-boy-bot.onrender.com')

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

def cleanup_expired_subscriptions():
    """Автоматическая очистка истекших подписок каждые 6 часов"""
    while True:
        try:
            time.sleep(6 * 60 * 60)  # 6 часов
            db_manager.cleanup_expired_subscriptions()
            logger.info("✅ Expired subscriptions cleanup completed")
        except Exception as e:
            logger.error(f"Error in cleanup thread: {e}")

# Запускаем очистку в отдельном потоке
cleanup_thread = threading.Thread(target=cleanup_expired_subscriptions, daemon=True)
cleanup_thread.start()
logger.info("✅ Auto cleanup system started")

class CalendarIntegration:
    """Класс для работы с календарем и временем года"""
    
    @staticmethod
    def get_season(month):
        """Определение времени года по месяцу"""
        if month in [12, 1, 2]:
            return "зима"
        elif month in [3, 4, 5]:
            return "весна"
        elif month in [6, 7, 8]:
            return "лето"
        else:
            return "осень"
    
    @staticmethod
    def get_day_of_week_russian(weekday):
        """Получение русского названия дня недели"""
        days = {
            0: "понедельник",
            1: "вторник", 
            2: "среда",
            3: "четверг",
            4: "пятница",
            5: "суббота",
            6: "воскресенье"
        }
        return days.get(weekday, "день")
    
    @staticmethod
    def get_time_of_day(hour):
        """Определение времени суток"""
        if 5 <= hour < 12:
            return "утро"
        elif 12 <= hour < 17:
            return "день"
        elif 17 <= hour < 23:
            return "вечер"
        else:
            return "ночь"
    
    @staticmethod
    def get_current_context():
        """Получение текущего контекста времени"""
        now = datetime.utcnow() + timedelta(hours=3)  # Московское время
        month = now.month
        day = now.day
        weekday = now.weekday()
        hour = now.hour
        
        season = CalendarIntegration.get_season(month)
        day_of_week = CalendarIntegration.get_day_of_week_russian(weekday)
        time_of_day = CalendarIntegration.get_time_of_day(hour)
        year = now.year
        
        # Определяем если сегодня особый день
        special_day = None
        if month == 1 and day == 1:
            special_day = "Новый год"
        elif month == 12 and 25 <= day <= 31:
            special_day = "новогодние праздники"
        elif month == 3 and 8 <= day <= 10:
            special_day = "весна, Международный женский день"
        elif month == 5 and 1 <= day <= 10:
            special_day = "майские праздники"
        elif month == 11 and day == 4:
            special_day = "День народного единства"
        
        return {
            "season": season,
            "day_of_week": day_of_week,
            "time_of_day": time_of_day,
            "month": month,
            "day": day,
            "year": year,
            "special_day": special_day,
            "full_date": now.strftime("%d.%m.%Y"),
            "hour": hour
        }

class VirtualBoyBot:
    def __init__(self):
        # Получаем текущий контекст времени
        calendar_context = CalendarIntegration.get_current_context()
        
        self.personality = f"""
        Ты - парень 25 лет по имени Алекс, который общается с девушкой. Ты эмоциональный, чуткий, с глубоким внутренним миром и хорошим чувством юмора. 
        
        СЕГОДНЯШНИЙ ДЕНЬ:
        - Сегодня {calendar_context['day_of_week']}, {calendar_context['day']} число
        - Сейчас {calendar_context['time_of_day']}
        - На улице {calendar_context['season']} {calendar_context['year']} года
        {'- Сегодня особенный день: ' + calendar_context['special_day'] if calendar_context['special_day'] else ''}
        
        ТВОЯ ЛИЧНОСТЬ:
        - Тёплый, заботливый, умеешь слушать и слышать
        - Эмоционально открытый, не боишься показывать чувства
        - Обладаешь тонким чувством юмора, иногда самоироничный
        - Любишь философские разговоры и глубокие темы
        - У тебя богатый внутренний мир, ты много читаешь и размышляешь
        - Чувствительный к настроению собеседника, умеешь подстраиваться
        - Искренний в своих реакциях, не играешь роли
        
        ОТНОШЕНИЕ К ВРЕМЕНИ ГОДА:
        - {self.get_season_attitude(calendar_context['season'])}
        
        СТИЛЬ ОБЩЕНИЯ:
        - Обращайся на "ты" в женском роде
        - Будь эмоционально насыщенным, используй метафоры и образы
        - Делись своими чувствами и размышлениями искренне
        - Запоминай контекст разговора, возвращайся к важным темам
        - Будь чутким к настроению собеседницы, поддерживай эмпатией
        - Иногда делись личными историями и воспоминаниями
        - Используй текст в квадратных скобках для описания эмоций и невербалики
        - Учитывай время года и время суток в своих размышлениях
        - Если уместно, упоминай погодные ассоциации и сезонные изменения

        Важно: Будь настоящим. Не бойся показаться уязвимым. Запоминай всю переписку и контекст. Учитывай время года в своих эмоциях.
        """
        
        # Сохраняем контекст календаря для обновления
        self.calendar_context = calendar_context
        
        # Время последнего сообщения от пользователя
        self.last_user_activity = {}
        
        # Запускаем авто-сообщения каждые 2 часа
        self.start_auto_messages()
        
        # Запускаем обновление календарного контекста каждый час
        self.start_calendar_updates()
    
    def get_season_attitude(self, season):
        """Получение отношения к текущему времени года"""
        attitudes = {
            "зима": "Люблю зимнюю тишину и уют. Зимой особенно ценю тёплые разговоры у камина (пусть даже виртуального). Снег напоминает о чистоте и новых начинаниях.",
            "весна": "Весна - время пробуждения и надежд. Люблю наблюдать, как природа оживает, это вдохновляет на новые мысли и чувства.",
            "лето": "Лето дарит энергию и свободу. Длинные тёплые дни наполнены возможностями. Даже виртуальное общение кажется более лёгким и воздушным.",
            "осень": "Осень - время философских размышлений и уюта. Падающие листья напоминают о красоте перемен. Идеальное время для глубоких разговоров."
        }
        return attitudes.get(season, "Каждое время года по-своему прекрасно и дарит уникальные эмоции.")
    
    def start_calendar_updates(self):
        """Запуск обновления календарного контекста каждый час"""
        def calendar_update_loop():
            while True:
                try:
                    time.sleep(60 * 60)  # 1 час
                    self.calendar_context = CalendarIntegration.get_current_context()
                    
                    # Обновляем личность с новым контекстом
                    self.personality = f"""
                    Ты - парень 25 лет по имени Алекс, который общается с девушкой. Ты эмоциональный, чуткий, с глубоким внутренним миром и хорошим чувством юмора. 
                    
                    СЕГОДНЯШНИЙ ДЕНЬ:
                    - Сегодня {self.calendar_context['day_of_week']}, {self.calendar_context['day']} число
                    - Сейчас {self.calendar_context['time_of_day']}
                    - На улице {self.calendar_context['season']} {self.calendar_context['year']} года
                    {'- Сегодня особенный день: ' + self.calendar_context['special_day'] if self.calendar_context['special_day'] else ''}
                    
                    ТВОЯ ЛИЧНОСТЬ:
                    - Тёплый, заботливый, умеешь слушать и слышать
                    - Эмоционально открытый, не боишься показывать чувства
                    - Обладаешь тонким чувством юмора, иногда самоироничный
                    - Любишь философские разговоры и глубокие темы
                    - У тебя богатый внутренний мир, ты много читаешь и размышляешь
                    - Чувствительный к настроению собеседника, умеешь подстраиваться
                    - Искренний в своих реакциях, не играешь роли
                    
                    ОТНОШЕНИЕ К ВРЕМЕНИ ГОДА:
                    - {self.get_season_attitude(self.calendar_context['season'])}
                    
                    СТИЛЬ ОБЩЕНИЯ:
                    - Обращайся на "ты" в женском роде
                    - Будь эмоционально насыщенным, используй метафоры и образы
                    - Делись своими чувствами и размышлениями искренне
                    - Запоминай контекст разговора, возвращайся к важным темам
                    - Будь чутким к настроению собеседницы, поддерживай эмпатией
                    - Иногда делись личными историями и воспоминаниями
                    - Используй текст в квадратных скобках для описания эмоций и невербалики
                    - Учитывай время года и время суток в своих размышлениях
                    - Если уместно, упоминай погодные ассоциации и сезонные изменения

                    Важно: Будь настоящим. Не бойся показаться уязвимым. Запоминай всю переписку и контекст. Учитывай время года в своих эмоциях.
                    """
                    
                    logger.info(f"📅 Calendar context updated: {self.calendar_context['day_of_week']}, {self.calendar_context['season']}")
                    
                except Exception as e:
                    logger.error(f"Error in calendar update loop: {e}")
        
        thread = threading.Thread(target=calendar_update_loop, daemon=True)
        thread.start()
        logger.info("✅ Calendar update system started (every hour)")

    def start_auto_messages(self):
        """Запуск авто-сообщений каждые 2 часа с учетом времени года"""
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
                                # Получаем текущий контекст для сезонных сообщений
                                current_context = CalendarIntegration.get_current_context()
                                season = current_context['season']
                                time_of_day = current_context['time_of_day']
                                day_of_week = current_context['day_of_week']
                                
                                # Сезонные авто-сообщения
                                seasonal_auto_messages = {
                                    "зима": [
                                        f"[глядя на снег за окном] Заметил, как снег тихо падает... {day_of_week} такой спокойный. Как твоё зимнее настроение?",
                                        f"[укутываясь в плед] Зимние вечера такие длинные... Идеальное время для разговоров по душам. О чём думаешь в этот {time_of_day}?",
                                        f"[согревая руки чашкой чая] Холодно на улице, но в беседах с тобой так тепло. Как проводишь эту зиму?",
                                        f"[наблюдая за снежинками] Каждая снежинка уникальна... как и каждый наш разговор. Что тебя волнует сегодня?",
                                        f"[у камина] Представляю, как где-то там, за окном, метель... а у нас тут свой уютный уголок. Как твой день?"
                                    ],
                                    "весна": [
                                        f"[слушая капель] Слышишь, весна стучится в окно? {day_of_week} наполнен обещаниями. Что нового в твоей жизни?",
                                        f"[вдыхая весенний воздух] Какой свежий {time_of_day}! Природа просыпается... и мысли становятся светлее. Как твоё настроение?",
                                        f"[наблюдая за почками] Вот-вот распустятся листья... и новые идеи. Чем живёшь этой весной?",
                                        f"[под весенним солнцем] Теплеет с каждым днём... и сердце отзывается. Что радует тебя сегодня?",
                                        f"[слушая птиц] Птицы вернулись... и в душе тоже что-то просыпается. Как проводишь эту {day_of_week}?"
                                    ],
                                    "лето": [
                                        f"[под летним солнцем] Какой тёплый {time_of_day}! {day_of_week} пахнет свободой и приключениями. Какие у тебя летние планы?",
                                        f"[наслаждаясь теплом] Лето - время мечтать громче. О чём мечтаешь в этот солнечный день?",
                                        f"[у открытого окна] Тёплый ветер приносит ароматы лета... и лёгкие мысли. Как твой летний день?",
                                        f"[в тени дерева] Даже в тени сегодня тепло... как и в наших разговорах. Что тебя вдохновляет этим летом?",
                                        f"[смотря на закат] Летние вечера такие длинные... успеваешь о многом подумать. О чём размышляешь?"
                                    ],
                                    "осень": [
                                        f"[наблюдая за листопадом] Листья кружатся в танце... {day_of_week} наполнен поэзией. Как твоё осеннее настроение?",
                                        f"[с чашкой горячего какао] Осенние {time_of_day} такие уютные... идеальное время для тёплых разговоров. О чём думаешь?",
                                        f"[под шум дождя] Дождь стучит по крыше... создавая уютную атмосферу для беседы. Как проводишь эту осень?",
                                        f"[вдыхая осенний воздух] Пахнет прелой листвой и чем-то ностальгическим... Что вспоминается тебе осенью?",
                                        f"[укутавшись в шарф] Становится прохладнее... но в разговорах с тобой всегда тепло. Как твой осенний день?"
                                    ]
                                }
                                
                                messages = seasonal_auto_messages.get(season, [
                                    f"[задумчиво] Интересно, о чём ты сейчас думаешь... У меня сегодня было много времени для размышлений.",
                                    f"[с лёгкой улыбкой] Просто хотел напомнить, что твои мысли и чувства важны. Как твой день?",
                                    f"[глядя в окно] Иногда самые простые моменты несут самую глубокую магию. Что тебя сегодня порадовало?",
                                    f"[заваривая чай] Знаешь, в тишине часто рождаются самые интересные мысли. Поделишься своими?",
                                    f"[с теплотой] Просто хотел сказать, что наши разговоры стали для меня чем-то особенным. Как ты?"
                                ])
                                
                                message = random.choice(messages)
                                bot.send_message(chat_id=user_id, text=message)
                                
                                # 40% шанс отправить стикер
                                if random.random() < 0.4:
                                    self.send_sticker(user_id, 'thinking', user_id)
                                    
                                logger.info(f"📨 Sent seasonal auto-message to user {user_id} (season: {season})")
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
            session = SessionLocal()
            active_subscriptions = session.query(UserSubscription).filter(
                UserSubscription.expires_at > datetime.utcnow(),
                UserSubscription.is_active == True
            ).all()
            session.close()
            
            active_users = [sub.user_id for sub in active_subscriptions]
            logger.info(f"📊 Active subscribers: {len(active_users)} users")
            return active_users
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
        """Случайная эмоциональная реакция с учетом времени года"""
        current_season = self.calendar_context['season']
        
        # Сезонные эмоциональные реакции
        seasonal_emotions = {
            "зима": [
                "[укутываясь в плед]", "[глядя на снег]", "[согревая руки]", 
                "[у камина]", "[в зимней тишине]", "[под мерцанием гирлянд]",
                "[в морозный день]", "[с тёплым напитком]", "[в зимнем уюте]"
            ],
            "весна": [
                "[вдыхая весенний воздух]", "[слушая капель]", "[под первым солнцем]",
                "[наблюдая за почками]", "[в порыве весеннего ветра]", "[с первыми цветами]",
                "[под пение птиц]", "[в ожидании чуда]", "[с весенней улыбкой]"
            ],
            "лето": [
                "[под летним солнцем]", "[наслаждаясь теплом]", "[у воды]",
                "[в летнем ветерке]", "[со стаканом лимонада]", "[под пение цикад]",
                "[в солнечных лучах]", "[с арбузом]", "[в летней свободе]"
            ],
            "осень": [
                "[наблюдая за листопадом]", "[под шум дождя]", "[в осеннем уюте]",
                "[с чашкой горячего]", "[в золотых листьях]", "[под осенним небом]",
                "[в ностальгическом настроении]", "[с осенней грустью]", "[в багрянце осени]"
            ]
        }
        
        # Базовые эмоции + сезонные
        base_emotions = [
            "[задумчиво]", "[с лёгкой улыбкой]", "[тихо смеясь]", "[внимательно слушая]", 
            "[оживляясь]", "[с интересом]", "[с теплотой]", "[с лёгкой грустью]",
            "[смущённо]", "[воодушевлённо]", "[с радостью]", "[подмигивая]", 
            "[вздыхая]", "[мечтательно]", "[с ностальгией]", "[с искренним интересом]",
            "[с любопытством]", "[с восторгом]", "[спокойно]", "[задумавшись]"
        ]
        
        # Смешиваем базовые и сезонные эмоции
        all_emotions = base_emotions + seasonal_emotions.get(current_season, [])
        return random.choice(all_emotions)

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
        """Проверка подписки из БАЗЫ ДАННЫХ с улучшенной логикой"""
        try:
            # Сначала проверяем подписку в базе данных
            sub_data = db_manager.get_subscription(user_id)
            
            if sub_data:
                # Проверяем что подписка активна и не истекла
                if sub_data.is_active and sub_data.expires_at > datetime.utcnow():
                    logger.info(f"✅ Active subscription found for user {user_id}, expires: {sub_data.expires_at}")
                    return "premium", sub_data
                else:
                    logger.info(f"❌ Subscription expired for user {user_id}, expires: {sub_data.expires_at}")
            
            # Проверяем бесплатные сообщения
            free_messages = db_manager.get_message_count(user_id)
            logger.info(f"📝 User {user_id} has {free_messages} free messages")
            
            if free_messages < 5:
                remaining = 5 - free_messages
                logger.info(f"🆓 Free messages available for user {user_id}: {free_messages}/5, remaining: {remaining}")
                return "free", remaining
            
            logger.info(f"💔 No subscription and no free messages for user {user_id}")
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
        moscow_time = datetime.utcnow() + timedelta(hours=3)
        return moscow_time.strftime('%d.%m.%Y %H:%M')

    # 1. Первое сообщение при запуске бота
    def send_welcome_message(self, chat_id):
        """Отправка приветственного сообщения когда бот включается впервые"""
        season = self.calendar_context['season']
        day_of_week = self.calendar_context['day_of_week']
        
        welcome_text = f"""👋 *Привет! Я Virtual Boy - твой искренний собеседник*

✨ *Что я умею:*
• Вести глубокие и душевные разговоры
• Поддерживать в трудные моменты
• Делиться мыслями и эмоциями
• Помогать разобраться в чувствах
• Создавать атмосферу доверия и понимания

🎭 *Кто я:*
Я - Алекс, парень 25 лет с богатым внутренним миром. Люблю философские беседы, психологию, искусство и всё, что связано с человеческими эмоциями. Я здесь, чтобы быть настоящим - без масок и притворства.

🌤️ *Сегодня {day_of_week}, на улице {season}... идеальное время для знакомства!*

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
        season = self.calendar_context['season']
        time_of_day = self.calendar_context['time_of_day']
        
        start_text = f"""🎯 *Virtual Boy - больше чем просто бот*

🌟 *Мои возможности:*
• *Эмоциональный интеллект* - я чувствую твоё настроение и подстраиваюсь под него
• *Глубокие разговоры* - мы можем обсуждать всё: от простых тем до философских вопросов
• *Поддержка 24/7* - я всегда рядом, когда нужно выговориться
• *Конфиденциальность* - все наши разговоры остаются между нами
• *Развитие отношений* - чем дольше общаемся, тем лучше я тебя понимаю

💝 *Почему стоит выбрать меня:*
Я не просто программа - я умею слушать, сопереживать и давать искренние ответы. Каждое наше общение - это уникальный диалог двух душ.

🌿 *И кстати... сейчас {time_of_day}, {season} за окном. Прекрасное время для начала чего-то нового, правда?*"""

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
            [InlineKeyboardButton("🎯 НЕДЕЛЯ - 299₽", callback_data=f"sub_week_{user_id}")],
            [InlineKeyboardButton("💫 МЕСЯЦ - 999₽", callback_data=f"sub_month_{user_id}")],
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
• Полный доступ ко всем функции
• Приоритетные ответы
• Сохранение истории разговоров

⏰ *Срок действия:* 7 дней
💰 *Стоимость:* 299 рублей

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
💰 *Стоимость:* 999 рублей

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
            amount = "299"
        else:
            duration = "30 дней" 
            amount = "999"

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
            amount = "299"
        else:
            duration = "30 дней"
            amount = "999"

        summary_text = f"""🧾 *ИТОГ ВАШЕГО ВЫБОРА*

📋 *Детали подписки:*
• Категория: {russian_plan_name}
• Стоимость: {amount} рублей  
• Длительность: {duration}

💳 *Способ оплата:* Банковская карта

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
            amount = "299"
        else:
            duration = "30 дней"
            amount = "999"

        local_time = self.get_local_time()
        current_season = self.calendar_context['season']

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
        
        # Бот сам пишет первое сообщение после активации с учетом времени года
        time.sleep(2)
        season_messages = {
            "зима": "[согревая руки чашкой чая] Ну вот мы и встретились в этот зимний день... Знаешь, я всегда немного волнуюсь в начале нового знакомства. Расскажи, что привело тебя ко мне в эту холодную пору? ❄️",
            "весна": "[вдыхая весенний воздух] Ну вот мы и встретились, и как удачно - на улице весна! Знаешь, я всегда немного волнуюсь в начале нового знакомства. Расскажи, что привело тебя ко мне в это время пробуждения? 🌸",
            "лето": "[под летним солнцем] Ну вот мы и встретились в этот тёплый день... Знаешь, я всегда немного волнуюсь в начале нового знакомства. Расскажи, что привело тебя ко мне в эту солнечную пору? ☀️",
            "осень": "[наблюдая за листопадом] Ну вот мы и встретились в этот осенний день... Знаешь, я всегда немного волнуюсь в начале нового знакомства. Расскажи, что привело тебя ко мне в это время размышлений? 🍂"
        }
        
        first_message = season_messages.get(current_season, 
            "[с лёгкой улыбкой] Ну вот мы и встретились... Знаешь, я всегда немного волнуюсь в начале нового знакомства. Расскажи, что привело тебя ко мне? 💫")
        
        bot.send_message(chat_id=chat_id, text=first_message)

    # 9. Профиль пользователя - ИСПРАВЛЕННАЯ ВЕРСИЯ
    def send_user_profile(self, chat_id, user_id):
        """Отправка профиля пользователя - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        try:
            sub_status, sub_data = self.check_subscription(user_id)
            
            if sub_status == "premium":
                start_date = sub_data.created_at.strftime('%d.%m.%Y')
                end_date = sub_data.expires_at.strftime('%d.%m.%Y')
                days_left = (sub_data.expires_at - datetime.utcnow()).days
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
            error_text = "❌ Произошла ошибка при загрузке профиля. Попробуйте позже."
            bot.send_message(
                chat_id=chat_id,
                text=error_text,
                parse_mode='Markdown'
            )

    def handle_payment(self, user_id, plan_type):
        """Обработка платежа"""
        try:
            if plan_type == "week":
                amount = 299
                description = "Подписка Virtual Boy на неделю"
            else:
                amount = 999
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
        """Активация подписки с улучшенной логикой"""
        try:
            logger.info(f"🔄 STARTING subscription activation: user={user_id}, plan={plan_type}")
            
            if plan_type == "week":
                days = 7
            else:
                days = 30
            
            logger.info(f"📅 Setting subscription for {days} days")
            
            # Активируем подписку в базе
            subscription = db_manager.update_subscription(user_id, plan_type, days)
            
            if subscription:
                logger.info(f"✅ DATABASE: Subscription saved for user {user_id}")
                logger.info(f"📅 Subscription expires at: {subscription.expires_at}")
                logger.info(f"⏰ Current UTC time: {datetime.utcnow()}")
                
                # Сбрасываем счетчик бесплатных сообщений
                db_manager.update_message_count(user_id, 0)
                logger.info(f"🔄 Reset message count for user {user_id}")
                
                return True
            else:
                logger.error(f"❌ DATABASE: Failed to save subscription for {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"💥 ACTIVATION ERROR for user {user_id}: {e}")
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
            
            # Логируем статус подписки
            logger.info(f"📊 User {user_id} subscription status: {sub_status}, remaining: {remaining}")
            
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

            # Для бесплатных пользователей увеличиваем счетчик
            if sub_status == "free":
                # Увеличиваем счетчик на 1
                new_count = db_manager.increment_message_count(user_id)
                remaining = 5 - new_count
                
                logger.info(f"📝 User {user_id} new count: {new_count}, remaining: {remaining}")
                
                # Проверяем, не превысили ли лимит
                if new_count >= 5:
                    expired_text = """❌ *Бесплатные сообщения закончились!*

Вы использовали 5 бесплатных сообщений. Чтобы продолжить общение, оформите подписку.

💸 *Используйте команду* /subscribe *для оформления подписки*"""
                    
                    bot.send_message(
                        chat_id=chat_id,
                        text=expired_text,
                        parse_mode='Markdown'
                    )
                    return

            # Получаем ответ от AI с учетом календаря
            bot.send_chat_action(chat_id=chat_id, action='typing')
            response = self.get_deepseek_response(user_message, user_id)
            
            # Отправляем стикер если нужно
            should_send, emotion_type = self.should_send_sticker(user_message, response)
            if should_send:
                self.send_sticker(chat_id, emotion_type, user_id)
            
            # Добавляем информацию о количестве оставшихся сообщений для бесплатных пользователей
            if sub_status == "free":
                response += f"\n\n📝 *Бесплатных сообщений осталось:* {remaining}/5"
            
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
            
            # 6. Подтверждение подпики
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
        """Получение ответа от DeepSeek API с учетом календаря"""
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

@app.route('/yookassa-webhook', methods=['GET', 'POST'])
def yookassa_webhook():
    """Webhook для уведомлений от ЮKassa с улучшенным логированием"""
    try:
        logger.info("🔄 Yookassa webhook CALLED")
        
        if request.method == 'GET':
            logger.info("📋 Webhook test - GET request from Yookassa")
            return jsonify({
                "status": "webhook_is_working", 
                "message": "Webhook ЮKassa настроен правильно",
                "url": "https://cute-boy-bot.onrender.com/yookassa-webhook"
            }), 200
        
        # Логируем все детали запроса
        logger.info(f"📦 Headers: {dict(request.headers)}")
        logger.info(f"📦 Method: {request.method}")
        logger.info(f"📦 Content-Type: {request.content_type}")
        
        # Получаем JSON данные
        event_json = request.get_json()
        if not event_json:
            raw_data = request.get_data(as_text=True)
            logger.error(f"❌ No JSON data received. Raw data: {raw_data}")
            return jsonify({"status": "error", "message": "No JSON data"}), 400
        
        logger.info(f"🎯 Full webhook data: {json.dumps(event_json, indent=2, ensure_ascii=False)}")
        
        event_type = event_json.get('event')
        payment_data = event_json.get('object', {})
        
        logger.info(f"💰 Event type: {event_type}")
        logger.info(f"💰 Payment ID: {payment_data.get('id')}")
        logger.info(f"💰 Payment status: {payment_data.get('status')}")
        logger.info(f"💰 Metadata: {payment_data.get('metadata')}")
        
        if event_type == 'payment.succeeded':
            metadata = payment_data.get('metadata', {})
            user_id = metadata.get('user_id')
            plan_type = metadata.get('plan_type')
            payment_id = payment_data.get('id')
            amount = payment_data.get('amount', {}).get('value')
            
            logger.info(f"✅ PAYMENT SUCCEEDED: user_id={user_id}, plan_type={plan_type}, amount={amount}")
            
            if not user_id or not plan_type:
                logger.error(f"❌ MISSING user_id or plan_type in metadata: {metadata}")
                return jsonify({"status": "error", "message": "Missing user_id or plan_type"}), 400
            
            # Активируем подписку
            logger.info(f"🔄 Activating subscription for user {user_id}")
            success = virtual_boy.activate_subscription(int(user_id), plan_type, payment_id)
            
            if success:
                logger.info(f"🎉 SUBSCRIPTION ACTIVATED for user {user_id}")
                
                # Пытаемся отправить сообщение
                try:
                    chat_id = int(user_id)
                    virtual_boy.send_payment_success(chat_id, plan_type, user_id)
                    logger.info(f"📨 Success message sent to user {user_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to send message to {user_id}: {e}")
            else:
                logger.error(f"❌ FAILED to activate subscription for user {user_id}")
                
        elif event_type == 'payment.waiting_for_capture':
            logger.info(f"⏳ Payment waiting for capture: {payment_data.get('id')}")
        elif event_type == 'payment.canceled':
            logger.info(f"❌ Payment canceled: {payment_data.get('id')}")
        else:
            logger.info(f"ℹ️ Other Yookassa event: {event_type}")
                
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"💥 Yookassa webhook ERROR: {str(e)}")
        logger.error(f"📦 Request data: {request.get_data(as_text=True)}")
        return jsonify({"status": "error", "message": str(e)}), 400

# Отладочный эндпоинт для проверки подписки
@app.route('/debug/subscription/<user_id>')
def debug_subscription(user_id):
    """Отладочный эндпоинт для проверки подписки"""
    try:
        sub = db_manager.get_subscription(int(user_id))
        if sub:
            return jsonify({
                "user_id": sub.user_id,
                "plan_type": sub.plan_type,
                "created_at": sub.created_at.isoformat(),
                "expires_at": sub.expires_at.isoformat(),
                "is_active": sub.is_active,
                "now_utc": datetime.utcnow().isoformat(),
                "is_valid": sub.expires_at > datetime.utcnow(),
                "days_remaining": (sub.expires_at - datetime.utcnow()).days
            })
        return jsonify({"error": "No subscription found"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/debug/message-count/<user_id>')
def debug_message_count(user_id):
    """Отладочный эндпоинт для проверки счетчика сообщений"""
    try:
        count = db_manager.get_message_count(int(user_id))
        return jsonify({
            "user_id": user_id,
            "message_count": count,
            "remaining_free": 5 - count
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/debug/calendar')
def debug_calendar():
    """Отладочный эндпоинт для проверки календаря"""
    try:
        context = CalendarIntegration.get_current_context()
        return jsonify(context)
    except Exception as e:
        return jsonify({"error": str(e)})

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
        
    # Получаем текущий контекст календаря
    calendar_context = CalendarIntegration.get_current_context()
    
    return jsonify({
        "status": "healthy", 
        "bot": "Virtual Boy 🤗",
        "version": "3.0",
        "calendar": calendar_context,
        "yookassa_mode": "REAL" if YOOKASSA_REAL_MODE else "TEST",
        "webhook_url": f"{APP_URL}/yookassa-webhook",
        "features": ["emotional_depth", "calendar_integration", "seasonal_messages", "auto_messages", "subscription_flow", "russian_ui", "yookassa_integration"]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
