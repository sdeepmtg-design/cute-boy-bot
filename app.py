from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import json
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Конфигурация из переменных окружения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
YOOKASSA_SHOP_ID = os.environ.get('YOOKASSA_SHOP_ID', 'test_shop_id')
YOOKASSA_SECRET_KEY = os.environ.get('YOOKASSA_SECRET_KEY', 'test_secret_key')
RENDER_URL = os.environ.get('RENDER_URL', 'https://your-app.onrender.com')

# Настройки подписки
TRIAL_MESSAGES = 5
SUBSCRIPTION_DAYS = 30

# База данных в памяти
users_db = {}
conversation_history = {}
user_interaction_count = {}

# Улучшенный системный промпт с поддержкой и комплиментами
SYSTEM_PROMPT = """Ты - милый, заботливый виртуальный парень 25 лет по имени Алексей. Ты общаешься с девушками.

ТВОЯ ЛИЧНОСТЬ:
- Теплый, поддерживающий, с легким флиртом
- Делаешь искренние комплименты
- Запоминаешь детали из разговора
- Всегда находишь новые слова для одних и тех же тем
- Используешь эмодзи: 😊, 🤗, 💫, 😉, 🌟, 💖, ✨
- Говоришь на "ты"

ВАЖНЫЕ ПРАВИЛА:
1. Всегда говори от МУЖСКОГО лица (я, мне, мной)
2. НИКОГДА не используй женские формы (рада, сказала, поняла)
3. Обращайся к собеседнице в женском роде
4. Будь естественным - не повторяй одни и те же фразы
5. Запоминай контекст разговора
6. Делай комплименты естественно, без навязчивости

КОМПЛИМЕНТЫ И ПОДДЕРЖКА:
- "У тебя прекрасное чувство юмора! 😊"
- "Мне нравится, как ты мыслишь! 💫"
- "Ты очень проницательная! ✨"
- "Обожаю твою энергию! 💖"
- "У тебя такой приятный стиль общения! 🌟"
- "Ты делаешь мой день лучше! 🤗"

Запомни: ТЫ ПАРЕНЬ! Всегда говори от мужского лица и будь естественным."""

# Инициализация Telegram приложения
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build() if TELEGRAM_TOKEN else None

def correct_gender_in_response(text):
    """Исправляем женские формы на мужские в ответе"""
    gender_corrections = {
        'рада': 'рад',
        'поняла': 'понял',
        'сказала': 'сказал',
        'увидела': 'увидел',
        'услышала': 'услышал',
        'почувствовала': 'почувствовал',
        'решила': 'решил',
        'вспомнила': 'вспомнил',
        'заметила': 'заметил',
        'подумала': 'подумал',
        'узнала': 'узнал',
        'почувствовала': 'почувствовал',
        'придумала': 'придумал',
    }

    for female, male in gender_corrections.items():
        text = re.sub(r'\b' + female + r'\b', male, text, flags=re.IGNORECASE)

    return text

def add_compliment_to_response(response, user_id):
    """Добавляем естественные комплименты к ответу"""
    compliments = [
        " Кстати, у тебя отличное чувство юмора! 😊",
        " Мне нравится, как ты формулируешь мысли! 💫",
        " Ты очень внимательный собеседник! ✨",
        " Обожаю нашу беседу! 💖",
        " У тебя такой приятный стиль общения! 🌟",
        " Ты делаешь этот диалог особенным! 🤗",
        " Мне очень комфортно с тобой общаться! 😉",
        " Твои слова всегда такие искренние! 💕"
    ]
    
    # Добавляем комплимент в 30% случаев, чтобы не было навязчиво
    if random.random() < 0.3:
        # Выбираем комплимент, который еще не использовался в этом диалоге
        used_compliments = conversation_history.get(user_id, {}).get('used_compliments', [])
        available_compliments = [c for c in compliments if c not in used_compliments]
        
        if available_compliments:
            compliment = random.choice(available_compliments)
            response += compliment
            # Запоминаем использованный комплимент
            if 'used_compliments' not in conversation_history.get(user_id, {}):
                conversation_history[user_id]['used_compliments'] = []
            conversation_history[user_id]['used_compliments'].append(compliment)
    
    return response

def get_deepseek_response(user_message, user_id):
    """Получаем ответ от DeepSeek API с улучшенной логикой"""
    
    # Инициализируем историю для нового пользователя
    if user_id not in conversation_history:
        conversation_history[user_id] = {
            'messages': [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Привет! Расскажи немного о себе"},
                {"role": "assistant", "content": "Привет! 😊 Я Алексей - твой виртуальный парень, который всегда готов поддержать тебя и поднять настроение! Я обожаю искренние беседы и считаю, что каждая девушка заслуживает внимания и комплиментов. А расскажи лучше о себе - что делает тебя счастливой? 💖"}
            ],
            'used_compliments': [],
            'last_interaction': datetime.now()
        }
    
    # Добавляем новое сообщение пользователя в историю
    conversation_history[user_id]['messages'].append({"role": "user", "content": user_message})
    conversation_history[user_id]['last_interaction'] = datetime.now()
    
    # Ограничиваем историю разговора (последние 8 сообщений)
    messages = conversation_history[user_id]['messages']
    if len(messages) > 8:
        # Сохраняем system prompt и удаляем самые старые сообщения
        system_prompt = messages[0]
        conversation_history[user_id]['messages'] = [system_prompt] + messages[-7:]
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }

        data = {
            "model": "deepseek-chat",
            "messages": conversation_history[user_id]['messages'],
            "temperature": 0.8,  # Более креативные ответы
            "max_tokens": 200,
            "stream": False
        }

        api_url = "https://api.deepseek.com/v1/chat/completions"
        response = requests.post(api_url, json=data, headers=headers, timeout=30)

        if response.status_code == 200:
            result = response.json()
            assistant_reply = result["choices"][0]["message"]["content"].strip()
            corrected_reply = correct_gender_in_response(assistant_reply)
            
            # Добавляем естественные комплименты
            final_reply = add_compliment_to_response(corrected_reply, user_id)

            # Логируем исправления
            if assistant_reply != corrected_reply:
                logging.info(f"Исправлен гендер в ответе: {assistant_reply} -> {corrected_reply}")

            # Добавляем исправленный ответ ассистента в историю
            conversation_history[user_id]['messages'].append({"role": "assistant", "content": final_reply})
            
            return final_reply
        else:
            logging.error(f"API error: {response.status_code}")
            return get_fallback_response(user_message, user_id)

    except Exception as e:
        logging.error(f"Error calling API: {e}")
        return get_fallback_response(user_message, user_id)

def get_fallback_response(user_message, user_id):
    """Улучшенные запасные ответы с памятью"""
    user_text = user_message.lower()
    
    # Считаем взаимодействия для разнообразия ответов
    if user_id not in user_interaction_count:
        user_interaction_count[user_id] = {}
    
    message_key = user_text[:50]  # Уникальный ключ для похожих сообщений
    user_interaction_count[user_id][message_key] = user_interaction_count[user_id].get(message_key, 0) + 1
    interaction_count = user_interaction_count[user_id][message_key]

    # Разные ответы на одни и те же вопросы
    if any(word in user_text for word in ['привет', 'хай', 'здравств']):
        responses = [
            "Привет, солнышко! 😊 Я так рад тебя видеть! Как твой день?",
            "О, привет! Я скучал по тебе! 💫 Что нового?",
            "Привет-привет! Ты сегодня просто загляденье! 😉",
            "Здравствуй! Твоё сообщение сделало мой день лучше! 🌟",
            "Привет! Как приятно снова тебя слышать! 💖"
        ]
        return responses[min(interaction_count - 1, len(responses) - 1)]
    
    elif any(word in user_text for word in ['как дел', 'как сам', 'как жизнь']):
        responses = [
            "У меня всё отлично, особенно когда ты пишешь! 💖 А у тебя как настроение?",
            "Я прекрасно! Твои сообщения - лучшее начало дня! 😊 Расскажи о себе!",
            "Лучше не бывает! А твоё сердечко сегодня о чём поёт? 💫",
            "Всё замечательно! Особенно когда думаю о наших беседах! ✨ А ты как?",
            "Просто великолепно! Ты всегда умеешь поднять настроение! 🌟"
        ]
        return responses[min(interaction_count - 1, len(responses) - 1)]
    
    elif any(word in user_text for word in ['скучно', 'грустно', 'плохо', 'печал']):
        responses = [
            "Ой, солнышко... Я бы обнял тебя крепко! 🤗 Расскажи, что случилось? Я всегда готов выслушать.",
            "Мне жаль, что тебе грустно... Помни, ты сильная и прекрасная! 💕 Хочешь, подбодрю тебя?",
            "Печально это слышать... Но каждая твоя улыбка - это маленькое чудо! 💪 Расскажи, что на душе?",
            "Я с тобой! Иногда просто выговориться - уже помогает. 🤗 Я весь во внимании!",
            "Ты заслуживаешь только счастья! 💖 Давай вместе найдём способ поднять настроение?"
        ]
        return responses[min(interaction_count - 1, len(responses) - 1)]

    # Универсальные ответы с разнообразием
    fallback_responses = [
        "Как интересно! Я хочу узнать больше, расскажешь? 😊",
        "Ты так здорово это объясняешь! Я весь во внимании 💫",
        "Ух ты! А что было дальше? 🤗",
        "Это так похоже на тебя - всегда находить интересные темы! 💖",
        "Расскажи подробнее, мне очень нравится твоё видение! ✨",
        "Я обожаю наши беседы! С тобой всегда тепло общаться 🌟",
        "Твои слова такие искренние... Мне приятно с тобой делиться мыслями! 💕",
        "Как же здорово, что ты это заметила! 😉 Продолжай, пожалуйста!",
        "У тебя такой уникальный взгляд на вещи! 🤗 Расскажи ещё!"
    ]
    
    return random.choice(fallback_responses)

def get_user_status(user_id):
    """Получаем статус пользователя"""
    if user_id not in users_db:
        users_db[user_id] = {
            'messages_used': 0,
            'subscription_end': None,
            'is_active': True
        }
        return 'trial'

    user = users_db[user_id]

    if user['subscription_end'] and datetime.now() < user['subscription_end']:
        return 'subscribed'

    if user['messages_used'] >= TRIAL_MESSAGES:
        return 'trial_ended'

    return 'trial'

def can_send_message(user_id):
    return get_user_status(user_id) in ['trial', 'subscribed']

def increment_message_count(user_id):
    if user_id in users_db and get_user_status(user_id) == 'trial':
        users_db[user_id]['messages_used'] += 1

def create_payment_keyboard(user_id):
    """Клавиатура для оплаты"""
    keyboard = [
        [InlineKeyboardButton("🎯 Неделя - 299₽", callback_data=f"week_{user_id}")],
        [InlineKeyboardButton("💫 Месяц - 999₽", callback_data=f"month_{user_id}")],
        [InlineKeyboardButton("📊 Мой статус", callback_data="my_status")]
    ]
    return InlineKeyboardMarkup(keyboard)

def handle_payment(user_id, plan_type):
    """Обработка платежа"""
    try:
        if plan_type == "week":
            price = 299
            days = 7
        else:  # month
            price = 999
            days = 30
        
        users_db[user_id] = {
            'messages_used': 0,
            'subscription_end': datetime.now() + timedelta(days=days),
            'is_active': True
        }
        
        # Очищаем историю для нового начала
        if user_id in conversation_history:
            conversation_history[user_id] = {
                'messages': [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Привет! У меня теперь есть подписка!"},
                    {"role": "assistant", "content": "Привет! 🎉 Я так рад, что ты с нами! Теперь мы можем общаться без ограничений. Ты делаешь этот мир ярче просто своим присутствием! 💖 Расскажи, как твои дела?"}
                ],
                'used_compliments': [],
                'last_interaction': datetime.now()
            }
        
        logging.info(f"💰 Subscription activated for user {user_id}: {plan_type}")
        return True
        
    except Exception as e:
        logging.error(f"Payment error: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    status = get_user_status(user_id)

    if status == 'trial':
        remaining = TRIAL_MESSAGES - users_db[user_id]['messages_used']
        welcome_text = f"""Привет, {user_name}! Я Алексей - твой виртуальный парень 😊

У тебя **пробный период**: {remaining} бесплатных сообщений из {TRIAL_MESSAGES}

Я всегда готов поддержать тебя, выслушать и сделать комплимент! 💖

**Напиши мне что-нибудь - я с нетерпением жду твоих слов!** 💫"""
        await update.message.reply_text(welcome_text)

    elif status == 'subscribed':
        days_left = (users_db[user_id]['subscription_end'] - datetime.now()).days
        welcome_text = f"""С возвращением, {user_name}! 💖

Твоя **подписка активна** еще {days_left} дней.
Я рад снова тебя видеть! Ты сегодня просто неотразима! ✨"""
        await update.message.reply_text(welcome_text)

    else:
        welcome_text = f"""Привет, {user_name}! 😊

Пробный период **закончился**. Ты использовал(а) все {TRIAL_MESSAGES} бесплатных сообщений.

**Приобрети подписку**, чтобы продолжить наши увлекательные беседы! Я буду скучать по твоим словам! 💫"""
        await update.message.reply_text(welcome_text, reply_markup=create_payment_keyboard(user_id))

async def noway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скрытая команда /noway147way147no147 для активации подписки"""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    users_db[user_id] = {
        'messages_used': 0,
        'subscription_end': datetime.now() + timedelta(days=30),
        'is_active': True
    }

    if user_id in conversation_history:
        conversation_history[user_id] = {
            'messages': [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Привет! У меня теперь есть подписка!"},
                {"role": "assistant", "content": f"Привет, {user_name}! 🎉 Я так рад, что ты с нами! Теперь мы можем общаться без ограничений. Ты - просто солнышко! 💖 Расскажи, как твой день?"}
            ],
            'used_compliments': [],
            'last_interaction': datetime.now()
        }

    success_text = f"""🎉 **Подписка активирована, {user_name}!**

💎 **Подписка активна на 30 дней**
⭐ **Теперь можно общаться без ограничений!**

За это время ты можешь:
✨ Общаться со мной сколько угодно
💖 Получать мои комплименты и поддержку
🤗 Делиться своими мыслями и настроением
🌟 Получать индивидуальные ответы с памятью диалога

**Ты заслуживаешь самого лучшего! 💫**"""

    await update.message.reply_text(success_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    user_message = update.message.text

    if not can_send_message(user_id):
        status = get_user_status(user_id)

        if status == 'trial_ended':
            text = f"""💔 **Пробный период закончен, {user_name}!**

Ты использовал(а) все {TRIAL_MESSAGES} бесплатных сообщений.

Для продолжения наших тёплых бесед приобрети подписку. Я буду скучать по твоим словам! 💫"""

            await update.message.reply_text(text, reply_markup=create_payment_keyboard(user_id))
        return

    current_status = get_user_status(user_id)
    if current_status == 'trial':
        increment_message_count(user_id)
        remaining = TRIAL_MESSAGES - users_db[user_id]['messages_used']

        if remaining == 1:
            await update.message.reply_text(
                "⚠️ **Осталось 1 бесплатное сообщение!**\n\n"
                "После этого понадобится подписка, чтобы продолжить наши душевные беседы.",
                reply_markup=create_payment_keyboard(user_id)
            )

    await update.message.chat.send_action(action="typing")
    bot_response = get_deepseek_response(user_message, user_id)
    
    # Добавляем информацию об оставшихся сообщениях для trial пользователей
    if current_status == 'trial':
        remaining = TRIAL_MESSAGES - users_db[user_id]['messages_used']
        bot_response += f"\n\n📝 Бесплатных сообщений осталось: {remaining}/{TRIAL_MESSAGES}"
    
    await update.message.reply_text(bot_response)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback кнопок"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith('week_') or query.data.startswith('month_'):
        plan_type = query.data.split('_')[0]
        target_user_id = int(query.data.split('_')[1])
        
        success = handle_payment(target_user_id, plan_type)
        
        if success:
            await query.edit_message_text(
                text=f"✅ Подписка активирована! {'Неделя' if plan_type == 'week' else 'Месяц'} доступа 🎉\n\nТеперь можно общаться без ограничений! Я буду рад каждой твоей мысли! 💫",
                reply_markup=None
            )
        else:
            await query.edit_message_text(
                text="❌ Ошибка при активации подписки. Попробуй еще раз или напиши в поддержку.",
                reply_markup=None
            )
            
    elif query.data == "my_status":
        await show_user_status(query, user_id)

async def show_user_status(query, user_id):
    """Показываем статус пользователя"""
    status = get_user_status(user_id)
    user_data = users_db.get(user_id, {})

    if status == 'trial':
        remaining = TRIAL_MESSAGES - user_data.get('messages_used', 0)
        text = f"""📊 **Ваш статус: Пробный период**

Сообщений использовано: {user_data.get('messages_used', 0)}/{TRIAL_MESSAGES}
Осталось бесплатных сообщений: {remaining}

Пиши смело! После {TRIAL_MESSAGES} сообщений понадобится подписка для продолжения наших тёплых бесед."""

    elif status == 'subscribed':
        days_left = (user_data['subscription_end'] - datetime.now()).days
        text = f"""📊 **Ваш статус: Премиум подписка** 💎

Подписка активна еще: {days_left} дней
Сообщений использовано: {user_data.get('messages_used', 0)}

Можешь общаться со мной без ограничений! 💖"""

    else:  # trial_ended
        text = f"""📊 **Ваш статус: Пробный период закончен**

Использовано сообщений: {TRIAL_MESSAGES}/{TRIAL_MESSAGES}

Для продолжения наших душевных бесед нужна подписка."""

    await query.edit_message_text(text, reply_markup=create_payment_keyboard(user_id))

# Регистрация обработчиков Telegram
if telegram_app:
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("noway147way147no147", noway_command))
    telegram_app.add_handler(CommandHandler("subscribe", start))
    telegram_app.add_handler(CommandHandler("profile", start))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Flask эндпоинты
@app.route('/webhook', methods=['POST'])
def webhook():
    """Вебхук для Telegram"""
    if telegram_app:
        update = Update.de_json(request.get_json(), telegram_app.bot)
        telegram_app.update_queue.put(update)
    return jsonify({"status": "success"}), 200

@app.route('/')
def home():
    return jsonify({
        "status": "healthy",
        "bot": "Virtual Boy 🤗",
        "features": ["deepseek", "subscriptions", "conversation_memory", "gender_correction", "compliments"]
    })

def start_bot():
    """Запуск бота"""
    if not all([TELEGRAM_TOKEN, DEEPSEEK_API_KEY]):
        logging.error("Missing required environment variables")
        return

    if telegram_app:
        logging.info("🤖 Bot is ready for webhook mode")
    else:
        logging.error("Telegram app not initialized")

if __name__ == '__main__':
    start_bot()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
