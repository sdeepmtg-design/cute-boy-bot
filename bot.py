import logging
import requests
import random
import json
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Глобальные переменные
DEEPSEEK_API_KEY = None
TELEGRAM_TOKEN = None

# Настройки подписки
TRIAL_MESSAGES = 3
SUBSCRIPTION_DAYS = 30

# База данных
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

def setup_tokens():
    """Запрашиваем токены через консоль"""
    global DEEPSEEK_API_KEY, TELEGRAM_TOKEN

    print("=" * 50)
    print("НАСТРОЙКА ТЕЛЕГРАМ БОТА")
    print("=" * 50)

    while not TELEGRAM_TOKEN:
        token = input("Введите ваш Telegram Bot Token (от @BotFather): ").strip()
        if token and len(token) > 10:
            TELEGRAM_TOKEN = token
            print("✓ Telegram токен принят")
        else:
            print("✗ Неверный формат токена")

    while not DEEPSEEK_API_KEY:
        api_key = input("Введите ваш DeepSeek API ключ: ").strip()
        if api_key and len(api_key) > 10:
            DEEPSEEK_API_KEY = api_key
            print("✓ DeepSeek API ключ принят")
        else:
            print("✗ Неверный формат API ключа")

    print("=" * 50)
    print("✓ Все токены настроены!")
    print("💡 Скрытая команда: /noway - активация подписки")
    print("=" * 50)

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

    # Исправляем отдельные слова
    for female, male in gender_corrections.items():
        text = re.sub(r'\b' + female + r'\b', male, text, flags=re.IGNORECASE)

    return text

def get_deepseek_response(user_message, user_id):
    """Получаем ответ от DeepSeek API с учетом личности милого парня"""

    # Инициализируем историю для нового пользователя
    if user_id not in conversation_history:
        conversation_history[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Привет! Расскажи немного о себе"},
            {"role": "assistant", "content": "Привет! 😊 Я твой виртуальный парень, который всегда готов поддержать тебя, выслушать и поднять настроение! Я обожаю делать комплименты милым девушкам и создавать уютную атмосферу для общения. А расскажи лучше о себе - что ты любишь, о чем мечтаешь? 💖"}
        ]

    # Добавляем новое сообщение пользователя в историю
    conversation_history[user_id].append({"role": "user", "content": user_message})

    # Ограничиваем историю разговора (последние 6 сообщений)
    if len(conversation_history[user_id]) > 6:
        # Сохраняем system prompt и удаляем самые старые сообщения
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

            # Исправляем гендерные формы в ответе
            corrected_reply = correct_gender_in_response(assistant_reply)

            # Логируем исправления (для отладки)
            if assistant_reply != corrected_reply:
                logging.info(f"Исправлен гендер в ответе: {assistant_reply} -> {corrected_reply}")

            # Добавляем исправленный ответ ассистента в историю
            conversation_history[user_id].append({"role": "assistant", "content": corrected_reply})

            return corrected_reply
        else:
            logging.error(f"API error: {response.status_code}")
            return get_fallback_response(user_message)

    except Exception as e:
        logging.error(f"Error calling API: {e}")
        return get_fallback_response(user_message)

def get_fallback_response(user_message):
    """Запасные ответы на случай проблем с API (всегда мужской род)"""
    user_text = user_message.lower()

    # Базовые реакции с сохранением МУЖСКОГО рода
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
    elif any(word in user_text for word in ['скучно', 'грустно', 'плохо', 'печал']):
        return random.choice([
            "Ой, солнышко... Я бы обнял тебя крепко! 🤗 Расскажи, что случилось? Я всегда готов выслушать.",
            "Мне жаль, что тебе грустно... Я с тобой! 💕 Хочешь, подбодрю тебя или просто послушаю?",
            "Печально это слышать... Но помни, ты сильная! Я всегда поддержу тебя 💪"
        ])
    elif any(word in user_text for word in ['спасибо', 'благодар']):
        return random.choice([
            "Всегда пожалуйста! Для тебя - всё самое лучшее! 💖",
            "Не стоит благодарности! Ты заслуживаешь самого лучшего! ✨",
            "Я рад, что смог помочь! Ты делаешь меня счастливее! 😊"
        ])

    # Универсальные ответы в стиле милого парня (мужской род)
    fallback_responses = [
        "Как интересно! Я хочу узнать больше, расскажешь? 😊",
        "Ты так здорово это объясняешь! Я весь во внимании 💫",
        "Ух ты! А что было дальше? 🤗",
        "Это так похоже на тебя! Ты всегда удивляешь меня 💖",
        "Расскажи подробнее, мне очень интересно твоё мнение! ✨",
        "Я обожаю наши беседы! С тобой всегда тепло общаться 🌟",
        "Твои слова такие искренние... Мне приятно с тобой делиться мыслями! 💕"
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

def create_payment_keyboard():
    """Клавиатура для оплаты"""
    keyboard = [
        [InlineKeyboardButton("💎 Купить подписку (30 дней)", callback_data="buy_subscription")],
        [InlineKeyboardButton("📊 Мой статус", callback_data="my_status")]
    ]
    return InlineKeyboardMarkup(keyboard)

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
        await update.message.reply_text(welcome_text, reply_markup=create_payment_keyboard())

async def noway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скрытая команда /noway для активации подписки"""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Активируем подписку на 30 дней
    users_db[user_id] = {
        'messages_used': 0,
        'subscription_end': datetime.now() + timedelta(days=SUBSCRIPTION_DAYS),
        'is_active': True
    }

    # Очищаем историю разговора для нового начала
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

    # Проверяем доступ
    if not can_send_message(user_id):
        status = get_user_status(user_id)

        if status == 'trial_ended':
            text = f"""💔 **Пробный период закончен, {user_name}!**

Ты использовал(а) все {TRIAL_MESSAGES} бесплатных сообщений.

Для продолжения нашего общения приобрети подписку. Я буду скучать по тебе! 💫"""

            await update.message.reply_text(text, reply_markup=create_payment_keyboard())
        return

    # Увеличиваем счетчик сообщений для trial пользователей
    current_status = get_user_status(user_id)
    if current_status == 'trial':
        increment_message_count(user_id)
        remaining = TRIAL_MESSAGES - users_db[user_id]['messages_used']

        if remaining == 1:
            await update.message.reply_text(
                "⚠️ **Осталось 1 бесплатное сообщение!**\n\n"
                "После этого понадобится подписка, чтобы продолжить наше общение.",
                reply_markup=create_payment_keyboard()
            )

    # Показываем, что бот "печатает"
    await update.message.chat.send_action(action="typing")

    # Используем API для генерации ответов
    bot_response = get_deepseek_response(user_message, user_id)

    await update.message.reply_text(bot_response)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback кнопок"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "buy_subscription":
        await query.edit_message_text(
            "💎 **Подписка на общение**\n\n"
            "Чтобы продолжить наше увлекательное общение, приобрети подписку на 30 дней.\n\n"
            "После оплаты мы сможем общаться без ограничений! Я буду ждать тебя! 💖",
            reply_markup=create_payment_keyboard()
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

    await query.edit_message_text(text, reply_markup=create_payment_keyboard())

def main():
    setup_tokens()

    if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
        print("Ошибка: Токены не установлены!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("noway", noway_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("=" * 50)
    print("🤖 Бот запущен!")
    print("💎 Логика работы:")
    print(f"   - {TRIAL_MESSAGES} пробных сообщений")
    print("   - Затем требуется подписка")
    print("   - /noway - скрытая команда активации")
    print("   - ✅ Автоисправление гендерных форм")
    print("=" * 50)

    application.run_polling()

if __name__ == '__main__':
    main()
