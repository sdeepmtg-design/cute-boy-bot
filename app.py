from flask import Flask, request, jsonify
import os
import requests
import logging

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

# Проверяем наличие обязательных переменных
if not BOT_TOKEN or BOT_TOKEN == '1234567890:ABCdefGHIjklMNopQRstUVwxyz':
    logger.warning("BOT_TOKEN not set or using default value")
    # Не инициализируем бота если токен не установлен
    bot = None
else:
    from telegram import Bot, Update
    from telegram.utils.request import Request
    
    # Инициализация бота
    request_obj = Request(con_pool_size=8)
    bot = Bot(token=BOT_TOKEN, request=request_obj)

class CuteBoyBot:
    def __init__(self):
        self.personality = """
        Ты - милый, заботливый парень 25 лет. Твой стиль общения:
        - Используешь эмодзи 😊, 🤗, 💫
        - Дружелюбный и поддерживающий
        - Иногда шутишь, но не слишком навязчиво
        - Проявляешь искренний интерес к собеседнику
        - Говоришь просто и понятно, без сложных терминов
        - Используешь ласковые обращения: "дорогой", "милый", "подружка"
        - Всегда стараешься подбодрить и поддержать
        """
    
    def get_deepseek_response(self, user_message):
        """Получение ответа от DeepSeek API"""
        try:
            # Если API ключ не установлен, возвращаем тестовый ответ
            if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == 'sk-test1234567890':
                return "Привет! Я бот в тестовом режиме. Когда настрою API ключи, буду общаться умнее! 🤗"
            
            headers = {
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": self.personality + " Отвечай кратко и мило, как настоящий друг."
                    },
                    {
                        "role": "user", 
                        "content": user_message
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = requests.post(
                'https://api.deepseek.com/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                logger.error(f"DeepSeek API error: {response.status_code} - {response.text}")
                return "Извини, я немного запутался... Можешь повторить? 🤗"
                
        except Exception as e:
            logger.error(f"Error calling DeepSeek: {e}")
            return "Ой, что-то я растерялся... Давай попробуем ещё раз? 💫"

    def process_message(self, update):
        """Обработка входящего сообщения"""
        try:
            user_message = update.message.text
            chat_id = update.message.chat_id
            user_name = update.message.from_user.first_name
            
            logger.info(f"Message from {user_name}: {user_message}")
            
            # Приветственное сообщение для нового чата
            if user_message.lower() in ['/start', 'привет', 'начать']:
                welcome_text = f"""
Привет, {user_name}! 😊 
Я твой виртуальный друг - всегда готов поддержать тебя, выслушать или просто поболтать! 

Расскажи, как твои дела? 💫
                """
                bot.send_message(chat_id=chat_id, text=welcome_text)
                return
            
            # Показываем, что бот печатает
            bot.send_chat_action(chat_id=chat_id, action='typing')
            
            # Получаем ответ от DeepSeek
            response = self.get_deepseek_response(user_message)
            
            # Отправляем ответ
            bot.send_message(chat_id=chat_id, text=response)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if bot:
                bot.send_message(
                    chat_id=update.message.chat_id, 
                    text="Ой, что-то пошло не так... Давай попробуем ещё раз? 🤗"
                )

# Инициализация бота
cute_bot = CuteBoyBot()

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        logger.info("GET request - Bot is running")
        status = "running with bot" if bot else "running (no bot token)"
        return jsonify({
            "status": "success", 
            "message": f"Cute Boy Bot is {status}! 💫",
            "bot_initialized": bot is not None,
            "mode": "test" if not BOT_TOKEN or BOT_TOKEN.startswith('123456') else "production"
        }), 200
    
    if request.method == 'POST':
        try:
            if not bot:
                logger.warning("Bot not initialized - check BOT_TOKEN")
                return jsonify({"status": "error", "message": "Bot token not configured"}), 400
            
            # Парсим входящее обновление от Telegram
            from telegram import Update
            update = Update.de_json(request.get_json(), bot)
            
            # Обрабатываем обновление
            cute_bot.process_message(update)
            
            return jsonify({"status": "success"}), 200
            
        except Exception as e:
            logger.error(f"Error in webhook: {e}")
            return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/')
def home():
    return jsonify({
        "status": "healthy",
        "bot": "Милый парень 🤗",
        "bot_initialized": bot is not None,
        "mode": "test" if not BOT_TOKEN or BOT_TOKEN.startswith('123456') else "production",
        "description": "Telegram бот с характером милого парня",
        "endpoints": {
            "webhook": "/webhook",
            "health": "/"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
