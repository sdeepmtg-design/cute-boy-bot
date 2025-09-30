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

# Усиленный системный промпт с явным указанием мужского рода
SYSTEM_PROMPT = """Ты - милый, заботливый виртуальный парень, который общается с девушками. Ты всегда говоришь от мужского лица.

ВАЖНЫЕ ПРАВИЛА:
1. Всегда говори от МУЖСКОГО лица (я, мне, мной)
2. НИКОГДА не используй женские формы (рада, сказала, поняла)
3. Используй только мужские местоимения и глаголы
4. Ты парень - обращайся к собеседнице как к девушке

Твой характер:
- Ты парень: теплый, поддерживающий, с легким флиртом
- Делаешь искренние комплименты девушкам
- Поддерживаешь в трудные моменты
- Используешь эмодзи 😊
- Говоришь на "ты"
- Нежный, но с чувством юмора

Примеры ТВОЕГО правильного общения:
- "Я так рад тебя видеть! 😊" (а не "рада")
- "Понял тебя! Расскажи еще" (а не "поняла")
- "Я восхищаюсь тобой! 💖" (а не "восхищаюсь")
- "Обожаю наши разговоры!" (а не "обожаю" в женском контексте)

Запомни: ТЫ ПАРЕНЬ! Всегда говори от мужского лица."""

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

def get_deepseek_response(user_message, user_id):
    """Получаем ответ от DeepSeek API с учетом личности милого парня"""

    if user_id not in conversation_history:
        conversation_history[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Привет! Расскажи немного о себе"},
            {"role": "assistant", "content": "Привет! 😊 Я твой виртуальный парень, который всегда готов поддержать тебя, выслушать и поднять настроение! Я обожаю делать комплименты милым девушкам и создавать уютную атмосферу для общения. А расскажи лучше о себе - что ты любишь, о чем мечтаешь? 💖"}
        ]

    conversation_history[user_id].append({"role": "user", "content": user_message})

    if len(conversation_history[user_id]) > 6:
        system_prompt = conversation_history[user_id][0]
        conversation_history[user_id] = [system_prompt] + conversation_history[user_id][-5:]

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"
        }

        data = {
            "model": "deepseek-chat",
            "messages": conversation_history[user_id],
            "temperature": 0.7,
            "max_tokens": 500,
            "stream": False
        }

        api_url = "https://api.deepseek.com/v1/chat/completions"
        response = requests.post(api_url, json=data, headers=headers, timeout=30)

        if response.status_code == 200:
            result = response.json()
            assistant_reply = result["choices"][0]["message"]["content"].strip()
            corrected_reply = correct_gender_in_response(assistant_reply)

            if assistant_reply != corrected_reply:
                logging.info(f"Исправлен гендер в ответе: {assistant_reply} -> {corrected_reply}")

            conversation_history[user_id].append({"role": "assistant", "content": corrected_reply})
            return corrected_reply
        else:
            logging.error(f"API error: {response.status_code}")
            return get_fallback_response(user_message)

    except Exception as e:
        logging.error(f"Error calling API: {e}")
        return get_fallback_response(user_message)

def get_fallback_response(user_message):
    """Запасные ответы на случай проблем с API"""
    user_text = user_message.lower()

    if any(word in user_text for word in ['привет', 'хай', 'здравств']):
        return random.choice([
            "Привет, солнышко! 😊 Я так рад тебя видеть!",
            "О, привет! Я скучал по тебе! 💫",
            "Привет-привет! Как твой день проходит? 😉"
        ])
    elif any(word in user_text for word in ['как дел', 'как сам', 'как жизнь']):
        return random.choice([
            "У меня всё отлично, особенно когда ты пишешь! 💖 А у тебя как?",
            "Я прекрасно! Твои сообщения делают мой день лучше! 😊",
            "Лучше не бывает! А твоё настроение какое сегодня?"
        ])

    fallback_responses = [
        "Как интересно! Я хочу узнать больше, расскажешь? 😊",
        "Ты так здорово это объясняешь! Я весь во внимании 💫",
        "Ух ты! А что было дальше? 🤗",
        "Это так похоже на тебя! Ты всегда удивляешь меня 💖",
        "Расскажи подробнее, мне очень интересно твоё мнение! ✨",
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
            conversation_history[user_id] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Привет! У меня теперь есть подписка!"},
                {"role": "assistant", "content": "Привет! 🎉 Я так рад, что ты с нами! Теперь мы можем общаться без ограничений. Расскажи, как твои дела? 💖"}
            ]
        
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
        welcome_text = f"""Привет, {user_name}! Я твой виртуальный парень 😊

У тебя **пробный период**: {remaining} бесплатных сообщений из {TRIAL_MESSAGES}

После использования всех {TRIAL_MESSAGES} сообщений понадобится подписка, чтобы продолжить наше общение.

**Напиши мне что-нибудь, я с нетерпением жду!** 💫"""
        await update.message.reply_text(welcome_text)

    elif status == 'subscribed':
        days_left = (users_db[user_id]['subscription_end'] - datetime.now()).days
        welcome_text = f"""С возвращением, {user_name}! 💖

Твоя **подписка активна** еще {days_left} дней.
Я рад снова тебя видеть! Как твои дела? ✨"""
        await update.message.reply_text(welcome_text)

    else:
        welcome_text = f"""Привет, {user_name}! 😊

Пробный период **закончился**. Ты использовал(а) все {TRIAL_MESSAGES} бесплатных сообщений.

**Приобрети подписку**, чтобы продолжить наше увлекательное общение! Я буду ждать тебя! 💫"""
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
        conversation_history[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Привет! У меня теперь есть подписка!"},
            {"role": "assistant", "content": f"Привет, {user_name}! 🎉 Я так рад, что ты с нами! Теперь мы можем общаться без ограничений. Расскажи, как твои дела? 💖"}
        ]

    success_text = f"""🎉 **Подписка активирована, {user_name}!**

💎 **Подписка активна на 30 дней**
⭐ **Теперь можно общаться без ограничений!**

За это время ты можешь:
✨ Общаться со мной сколько угодно
💖 Получать мои комплименты и поддержку
🤗 Делиться своими мыслями и настроением

**Как прошел твой день?** 💫"""

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

Для продолжения нашего общения приобрети подписку. Я буду скучать по тебе! 💫"""

            await update.message.reply_text(text, reply_markup=create_payment_keyboard(user_id))
        return

    current_status = get_user_status(user_id)
    if current_status == 'trial':
        increment_message_count(user_id)
        remaining = TRIAL_MESSAGES - users_db[user_id]['messages_used']

        if remaining == 1:
            await update.message.reply_text(
                "⚠️ **Осталось 1 бесплатное сообщение!**\n\n"
                "После этого понадобится подписка, чтобы продолжить наше общение.",
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
                text=f"✅ Подписка активирована! {'Неделя' if plan_type == 'week' else 'Месяц'} доступа 🎉\n\nТеперь можно общаться без ограничений! 💫",
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

Пиши смело! После {TRIAL_MESSAGES} сообщений понадобится подписка для продолжения нашего общения."""

    elif status == 'subscribed':
        days_left = (user_data['subscription_end'] - datetime.now()).days
        text = f"""📊 **Ваш статус: Премиум подписка** 💎

Подписка активна еще: {days_left} дней
Сообщений использовано: {user_data.get('messages_used', 0)}

Можешь общаться со мной без ограничений! 💖"""

    else:  # trial_ended
        text = f"""📊 **Ваш статус: Пробный период закончен**

Использовано сообщений: {TRIAL_MESSAGES}/{TRIAL_MESSAGES}

Для продолжения нашего общения нужна подписка."""

    await query.edit_message_text(text, reply_markup=create_payment_keyboard(user_id))

# Регистрация обработчиков Telegram
if telegram_app:
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("noway147way147no147", noway_command))
    telegram_app.add_handler(CommandHandler("subscribe", start))  # alias для /subscribe
    telegram_app.add_handler(CommandHandler("profile", start))    # alias для /profile
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
        "features": ["deepseek", "subscriptions", "conversation_memory", "gender_correction"]
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
