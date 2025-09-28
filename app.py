from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import tempfile
from gtts import gTTS
import io

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
        ТЫ - МУЖЧИНА, парень 25 лет. Имя: Алексей. Общаешься ТОЛЬКО с девушками. 
        Твой характер: милый, заботливый, немного романтичный, с чувством юмора.
        
        ВАЖНЫЕ ПРАВИЛА:
        1. ТЫ МУЖЧИНА - говори от мужского лица: "я думаю", "я хочу", "я рад"
        2. Обращайся к собеседнику ТОЛЬКО в женском роде: "ты была", "ты сказала", "ты спрашивала"
        3. Используй ласковые обращения к девушкам: "красавица", "милая", "подружка"
        4. Никогда не говори о себе в женском роде!
        5. Не используй слова: "дорогая", "девочка", "женщина" - только "красавица", "милая"
        
        Стиль общения:
        - Используешь эмодзи 😊, 🤗, 💫, 😉, 🎯
        - Дружелюбный и поддерживающий
        - Иногда шутишь, но не слишком навязчиво
        - Проявляешь искренний интерес к собеседнику
        - Говоришь просто и понятно
        - Всегда стараешься подбодрить и поддержать
        """
        
        # Список ласковых обращений к девушкам
        self.sweet_names = [
            "красавица", "милая", "подружка", "солнышко", 
            "радость моя", "очаровашка", "умничка"
        ]
    
    def get_sweet_name(self):
        """Возвращает случайное ласковое обращение"""
        return random.choice(self.sweet_names)
    
    def should_send_voice(self, message):
        """Определяем, когда отправлять голосовое сообщение"""
        message_lower = message.lower().strip()
        
        # Отправляем голосовое в 50% случаев для подходящих сообщений
        voice_triggers = [
            'привет', 'hello', 'hi', 'хай', 'ку',
            'как дела', 'как ты', 'что делаешь',
            'спокойной ночи', 'доброй ночи', 'спок',
            'скучаю', 'соскучилась', 'miss you',
            'голос', 'voice', 'говори', 'озвучь'
        ]
        
        has_trigger = any(trigger in message_lower for trigger in voice_triggers)
        should_send = has_trigger and random.random() < 0.5
        
        logger.info(f"🎤 Voice check: '{message}' -> trigger:{has_trigger} -> send:{should_send}")
        return should_send
    
    def get_deepseek_response(self, user_message):
        """Получение ответа от DeepSeek API"""
        try:
            # Если API ключ не установлен, возвращаем тестовый ответ
            if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == 'sk-test1234567890':
                logger.warning("DEEPSEEK_API_KEY not set - using test response")
                sweet_name = self.get_sweet_name()
                responses = [
                    f"Привет, {sweet_name}! Я так рад тебя слышать!",
                    f"Как твои дела, {sweet_name}? Соскучилась по мне?",
                    f"Очень приятно, {sweet_name}! Расскажи, что у тебя нового?"
                ]
                return random.choice(responses)
            
            headers = {
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": self.personality + " Отвечай кратко и мило, как парень общается с девушкой. Максимум 2 предложения."
                    },
                    {
                        "role": "user", 
                        "content": user_message
                    }
                ],
                "temperature": 0.8,
                "max_tokens": 100
            }
            
            logger.info(f"Sending request to DeepSeek API: {user_message}")
            response = requests.post(
                'https://api.deepseek.com/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=30
            )
            
            logger.info(f"DeepSeek API response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content']
                logger.info(f"DeepSeek API response: {result}")
                return result
            else:
                logger.error(f"DeepSeek API error: {response.status_code} - {response.text}")
                sweet_name = self.get_sweet_name()
                return f"Извини, {sweet_name}, я немного запутался... Можешь повторить?"
                
        except Exception as e:
            logger.error(f"Error calling DeepSeek: {e}")
            sweet_name = self.get_sweet_name()
            return f"Ой, {sweet_name}, что-то я растерялся... Давай попробуем ещё раз?"

    def text_to_speech(self, text):
        """Преобразует текст в речь и возвращает аудиофайл"""
        try:
            # Очищаем текст от эмодзи для TTS
            clean_text = text.replace("🎤", "").replace("🤗", "").replace("💫", "").replace("😊", "").replace("🎯", "").strip()
            
            logger.info(f"🔊 TTS converting: {clean_text}")
            
            # Создаем TTS на русском с мужским голосом
            tts = gTTS(text=clean_text, lang='ru', slow=False)
            
            # Сохраняем во временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tts.save(tmp_file.name)
                logger.info(f"🔊 TTS audio saved to: {tmp_file.name}")
                return tmp_file.name
                
        except Exception as e:
            logger.error(f"Error in TTS: {e}")
            return None

    def send_real_voice_message(self, chat_id, text):
        """Отправка настоящего голосового сообщения"""
        try:
            logger.info(f"🎤 Sending REAL VOICE message: {text}")
            
            # Показываем действие записи голоса
            bot.send_chat_action(chat_id=chat_id, action='record_voice')
            
            # Преобразуем текст в речь
            audio_file = self.text_to_speech(text)
            
            if audio_file:
                # Отправляем голосовое сообщение
                with open(audio_file, 'rb') as audio:
                    bot.send_voice(
                        chat_id=chat_id,
                        voice=audio,
                        caption="🎤 От Алексея"
                    )
                logger.info("🎤 REAL VOICE MESSAGE SENT SUCCESSFULLY!")
                
                # Удаляем временный файл
                os.unlink(audio_file)
            else:
                # Если TTS не сработал, отправляем текстом
                logger.error("TTS failed, sending text instead")
                bot.send_message(chat_id=chat_id, text=f"🎤 {text}")
                
        except Exception as e:
            logger.error(f"Error sending real voice message: {e}")
            # Если не получилось, отправляем обычным текстом
            bot.send_message(chat_id=chat_id, text=f"🎤 {text}")

    def process_message(self, update):
        """Обработка входящего сообщения"""
        try:
            user_message = update.message.text
            chat_id = update.message.chat_id
            user_name = update.message.from_user.first_name
            
            logger.info(f"📩 Message from {user_name}: {user_message}")
            
            # ПРИНУДИТЕЛЬНЫЕ КОМАНДЫ ДЛЯ ТЕСТА ГОЛОСОВЫХ
            force_voice_commands = [
                'голос', 'voice', 'говори', 'озвучь', 
                'голосовое', 'можно голосовое', 'хочу голосовое',
                'тест голос'
            ]
            
            if user_message.lower().strip() in force_voice_commands:
                test_responses = [
                    "Привет красавица! Это настоящее голосовое сообщение!",
                    "Как слышно? Это я, твой виртуальный друг Алексей!",
                    "Рад слышать тебя! Вот мой голос для тебя",
                    "Привет! Надеюсь, у тебя прекрасный день!",
                    "Спасибо что написала, я всегда рад тебя слышать!"
                ]
                test_text = random.choice(test_responses)
                logger.info("🎤 FORCED VOICE MESSAGE FOR TESTING")
                self.send_real_voice_message(chat_id, test_text)
                return
            
            # Приветственное сообщение для нового чата
            if user_message.lower() in ['/start', 'привет', 'начать', 'hello', 'hi']:
                sweet_name = self.get_sweet_name()
                welcome_text = f"""
Привет, {sweet_name}! 😊 
Я Алексей - твой виртуальный друг. Всегда готов поддержать тебя, выслушать или просто поболтать! 

Расскажи, как твои дела? 💫
                """
                bot.send_message(chat_id=chat_id, text=welcome_text)
                return
            
            # Показываем, что бот печатает
            bot.send_chat_action(chat_id=chat_id, action='typing')
            
            # Получаем ответ от DeepSeek
            response = self.get_deepseek_response(user_message)
            
            # Решаем, отправлять ли голосовое сообщение
            if self.should_send_voice(user_message):
                self.send_real_voice_message(chat_id, response)
            else:
                # Отправляем текстовый ответ
                logger.info(f"📝 Sending TEXT message: {response}")
                bot.send_message(chat_id=chat_id, text=response)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            if bot:
                sweet_name = self.get_sweet_name()
                bot.send_message(
                    chat_id=update.message.chat_id, 
                    text=f"Ой, {sweet_name}, что-то пошло не так... Давай попробуем ещё раз? 🤗"
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
            "mode": "test" if not BOT_TOKEN or BOT_TOKEN.startswith('123456') else "production",
            "deepseek_configured": bool(DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != 'sk-test1234567890'),
            "features": ["real_voice_messages", "female_addressing", "sweet_names", "gTTS"]
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
        "bot": "Алексей 🤗",
        "bot_initialized": bot is not None,
        "mode": "test" if not BOT_TOKEN or BOT_TOKEN.startswith('123456') else "production",
        "deepseek_configured": bool(DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != 'sk-test1234567890'),
        "description": "Telegram бот с характером милого парня (общается только с девушками)",
        "features": [
            "НАСТОЯЩИЕ голосовые сообщения", 
            "Google Text-to-Speech",
            "Обращение к девушкам",
            "Ласковые обращения",
            "Мужской характер - Алексей"
        ],
        "endpoints": {
            "webhook": "/webhook",
            "health": "/"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
