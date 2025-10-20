import os
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from database import db_manager

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = [int(x) for x in os.environ.get('ADMIN_IDS', '').split(',') if x]

class BotCommands:
    def __init__(self):
        self.commands = {
            'start': '🚀 Запустить бота',
            'help': '📖 Получить справку по командам',
            'profile': '👤 Мой профиль',
            'subscribe': '💳 Купить подписку',
            'history': '📜 История разговоров',
            'stats': '📊 Статистика',
            'support': '🆘 Поддержка'
        }
    
    def get_commands_list(self):
        return "\n".join([f"/{cmd} - {desc}" for cmd, desc in self.commands.items()])

class NotificationManager:
    def __init__(self):
        self.notifications = [
            "💡 Не забывайте, что с подпиской вы получаете неограниченное количество сообщений!",
            "🎯 Хотите больше возможностей? Оформите премиум подписку!",
            "📚 Используйте команду /history чтобы посмотреть историю разговоров",
            "🆘 Нужна помощь? Напишите /support для связи с администратором",
            "⭐ Бот обновляется регулярно! Следите за новыми функциями",
            "💬 Чем больше вы общаетесь, тем лучше бот понимает ваши предпочтения"
        ]
    
    def get_random_notification(self):
        return random.choice(self.notifications)

# Инициализация
bot_commands = BotCommands()
notification_manager = NotificationManager()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    
    welcome_text = f"""
👋 Привет, {username}!

Я - умный ассистент с функциями подписки и сохранения истории.

{bot_commands.get_commands_list()}

💬 Просто напишите мне сообщение, и я отвечу!
    """
    
    await update.message.reply_text(welcome_text)
    
    # Сохраняем стартовое сообщение в историю
    db_manager.save_conversation_message(user_id, 'assistant', welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = f"""
📖 **Доступные команды:**

{bot_commands.get_commands_list()}

**Как пользоваться:**
1. Просто напишите сообщение - и я отвечу
2. Используйте команды для специальных функций
3. История сохраняется 30 дней

💡 **Совет:** Начните с команды /profile чтобы посмотреть свой статус
    """
    
    await update.message.reply_text(help_text)

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /profile"""
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    
    # Получаем информацию о подписке
    subscription = db_manager.get_subscription(user_id)
    message_count = db_manager.get_message_count(user_id)
    
    if subscription and subscription.expires_at > datetime.now():
        subscription_info = f"""
✅ **Активная подписка:**
   • Тип: {subscription.plan_type}
   • Истекает: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}
   • Осталось дней: {(subscription.expires_at - datetime.now()).days}
        """
    else:
        subscription_info = "❌ **Подписка не активна**\nИспользуйте /subscribe для оформления"
    
    profile_text = f"""
👤 **Профиль пользователя:**

**Имя:** {username}
**ID:** {user_id}

**Статистика:**
• Отправлено сообщений: {message_count}

{subscription_info}

💡 Используйте /subscribe для получения полного доступа
    """
    
    await update.message.reply_text(profile_text)

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /subscribe"""
    keyboard = [
        [
            InlineKeyboardButton("💰 Базовый (7 дней) - 299₽", callback_data="subscribe_basic"),
            InlineKeyboardButton("💎 Премиум (30 дней) - 999₽", callback_data="subscribe_premium")
        ],
        [
            InlineKeyboardButton("🚀 PRO (90 дней) - 2499₽", callback_data="subscribe_pro"),
            InlineKeyboardButton("❤️ Пожизненный - 4999₽", callback_data="subscribe_lifetime")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    subscribe_text = """
💳 **Выберите тип подписки:**

• **💰 Базовый** - 7 дней неограниченного общения
• **💎 Премиум** - 30 дней + приоритетная поддержка  
• **🚀 PRO** - 90 дней + все функции + бета-тестирование
• **❤️ Пожизненный** - Вечный доступ ко всем функциям

🎁 **Все подписки включают:**
✓ Неограниченное количество сообщений
✓ Сохранение истории на 30 дней
✓ Доступ ко всем базовым функциям
    """
    
    await update.message.reply_text(subscribe_text, reply_markup=reply_markup)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /history"""
    user_id = update.effective_user.id
    
    # Получаем историю (последние 10 сообщений)
    history = db_manager.get_conversation_history(user_id, limit=10)
    
    if not history:
        await update.message.reply_text("📜 История разговоров пуста")
        return
    
    history_text = "📜 **Последние сообщения:**\n\n"
    
    for i, msg in enumerate(history[-10:], 1):  # Берем последние 10 сообщений
        role_icon = "👤" if msg.role == 'user' else "🤖"
        time = msg.timestamp.strftime('%H:%M')
        # Обрезаем длинные сообщения
        content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
        history_text += f"{role_icon} **{time}**\n{content}\n\n"
    
    await update.message.reply_text(history_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats (только для админов)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Эта команда только для администраторов")
        return
    
    # Простая статистика
    total_messages = len(db_manager.db.query(db_manager.ConversationHistory).all())
    total_users = len(db_manager.db.query(db_manager.UserMessageCount).all())
    active_subscriptions = len(db_manager.db.query(db_manager.UserSubscription).filter(
        db_manager.UserSubscription.expires_at > datetime.now()
    ).all())
    
    stats_text = f"""
📊 **Статистика бота:**

• Всего пользователей: {total_users}
• Всего сообщений: {total_messages}
• Активных подписок: {active_subscriptions}
• Время работы: {datetime.now().strftime('%d.%m.%Y %H:%M')}
    """
    
    await update.message.reply_text(stats_text)

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /support"""
    support_text = """
🆘 **Поддержка**

Если у вас возникли проблемы или вопросы:

📧 **Email:** support@example.com
👨‍💻 **Техническая поддержка:** @admin_username

⏰ **Время работы:** 10:00 - 22:00 (МСК)

⚠️ **Перед обращением:**
1. Проверьте команду /help
2. Убедитесь, что подписка активна (/profile)
3. Перезапустите бота командой /start

Мы ответим вам в ближайшее время!
    """
    
    await update.message.reply_text(support_text)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith('subscribe_'):
        plan_type = data.replace('subscribe_', '')
        plans = {
            'basic': {'days': 7, 'price': '299₽'},
            'premium': {'days': 30, 'price': '999₽'},
            'pro': {'days': 90, 'price': '2499₽'},
            'lifetime': {'days': 36500, 'price': '4999₽'}  # ~100 лет
        }
        
        if plan_type in plans:
            plan = plans[plan_type]
            # Здесь должна быть интеграция с платежной системой
            # Пока просто создаем тестовую подписку
            db_manager.update_subscription(user_id, plan_type.capitalize(), plan['days'])
            
            await query.edit_message_text(
                f"✅ **Подписка оформлена!**\n\n"
                f"Тип: {plan_type.capitalize()}\n"
                f"Срок: {plan['days']} дней\n"
                f"Стоимость: {plan['price']}\n\n"
                f"Теперь у вас неограниченный доступ ко всем функциям! 🎉"
            )

async def send_random_notification(context: ContextTypes.DEFAULT_TYPE):
    """Отправка случайного уведомления"""
    try:
        # Получаем всех активных пользователей (кто писал в последние 3 дня)
        three_days_ago = datetime.now() - timedelta(days=3)
        
        # Здесь можно добавить логику для выбора пользователей
        # Пока отправляем только если в контексте есть chat_id
        if hasattr(context, 'chat_data') and context.chat_data:
            notification = notification_manager.get_random_notification()
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=notification
            )
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Сохраняем сообщение пользователя в историю
    db_manager.save_conversation_message(user_id, 'user', user_message)
    
    # Увеличиваем счетчик сообщений
    current_count = db_manager.get_message_count(user_id)
    db_manager.update_message_count(user_id, current_count + 1)
    
    # Проверяем подписку
    subscription = db_manager.get_subscription(user_id)
    has_active_subscription = subscription and subscription.expires_at > datetime.now()
    
    # Если нет активной подписки, проверяем лимит сообщений
    if not has_active_subscription:
        if current_count >= 10:  # Бесплатный лимит - 10 сообщений
            await update.message.reply_text(
                "❌ **Достигнут лимит сообщений!**\n\n"
                "Вы использовали все бесплатные сообщения. "
                "Для продолжения общения оформите подписку:\n/subscribe"
            )
            return
    
    # Имитация ответа AI (здесь должна быть ваша основная логика бота)
    ai_response = f"🤖 Я получил ваше сообщение: \"{user_message}\"\n\nЭто тестовый ответ. Здесь должна быть ваша основная AI-логика."
    
    # Сохраняем ответ ассистента в историю
    db_manager.save_conversation_message(user_id, 'assistant', ai_response)
    
    await update.message.reply_text(ai_response)
    
    # Случайная отправка уведомления (10% chance)
    if random.random() < 0.1:
        notification = notification_manager.get_random_notification()
        await update.message.reply_text(notification)

async def show_commands_suggestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ подсказок команд при вводе '/'"""
    user_message = update.message.text
    
    if user_message == '/':
        suggestions_text = f"""
💡 **Доступные команды:**

{bot_commands.get_commands_list()}

Просто допишите команду после '/' или нажмите на нужную команду выше.
        """
        await update.message.reply_text(suggestions_text)

def main():
    """Основная функция запуска бота"""
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не установлен")
        return
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("support", support_command))
    
    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Обработчик подсказок команд
    application.add_handler(MessageHandler(filters.Text(['/']), show_commands_suggestions))
    
    # Обработчик обычных сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    print("🤖 Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()
