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
        """
        
        self.sweet_names = [
            "красавица", "милая", "подружка", "солнышко", 
            "радость моя", "очаровашка", "умничка"
        ]
    
    def get_sweet_name(self):
        return random.choice(self.sweet_names)
    
    def should_send_voice(self, message):
        message_lower = message.lower().strip()
        
        voice_triggers = [
            'голос', 'voice', 'говори', 'озвучь', 'тест голос'
        ]
        
        has_trigger = any(trigger in message_lower for trigger in voice_triggers)
        should_send = has_trigger
        
        logger.info(f"🎤 Voice check: '{message}' -> trigger:{has_trigger} -> send:{should_send}")
        return should_send
    
    def get_deepseek_response(self, user_message):
        try:
            if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == 'sk-test1234567890':
                sweet_name = self.get_sweet_name()
                return f"Привет, {sweet_name}! Это тестовый ответ."
            
            headers = {
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": self.personality
                    },
                    {
                        "role": "user", 
                        "content": user_message
                    }
                ],
                "temperature": 0.8,
                "max_tokens": 100
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
                sweet_name = self.get_sweet_name()
                return f"Извини, {sweet_name}, я немного запутался..."
                
        except Exception as e:
            sweet_name = self.get_sweet_name()
            return f"Ой, {sweet_name}, что-то я растерялся..."

    def text_to_speech(self, text):
        """Преобразует текст в речь"""
        try:
            clean_text = text.replace("🎤", "").replace("🤗", "").replace("💫", "").replace("😊", "").replace("🎯", "").strip()
            
            logger.info(f"🔊 TTS converting: {clean_text}")
            
            # Пробуем gTTS
            tts = gTTS(text=clean_text, lang='ru', slow=False)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tts.save(tmp_file.name)
                logger.info(f"🔊 TTS audio saved to: {tmp_file.name}")
                return tmp_file.name
                
        except Exception as e:
            logger.error(f"❌ TTS ERROR: {e}")
            return None

    def send_real_voice_message(self, chat_id, text):
        """Отправка настоящего голосового сообщения"""
        try:
            logger.info(f"🎤 Attempting to send REAL VOICE: {text}")
            
            # Показываем действие записи голоса
            bot.send_chat_action(chat_id=chat_id, action='record_voice')
            
            # Пробуем TTS
            audio_file = self.text_to_speech(text)
            
            if audio_file and os.path.exists(audio_file):
                file_size = os.path.getsize(audio_file)
                logger.info(f"🔊 Audio file created: {audio_file}, size: {file_size} bytes")
                
                # Отправляем голосовое сообщение
                with open(audio_file, 'rb') as audio:
                    bot.send_voice(
                        chat_id=chat_id,
                        voice=audio,
                        caption="🎤 От Алексея"
                    )
                logger.info("✅ REAL VOICE MESSAGE SENT SUCCESSFULLY!")
                
                # Удаляем временный файл
                os.unlink(audio_file)
            else:
                logger.error("❌ TTS failed or file not created")
                # Fallback - отправляем текстом
                bot.send_message(chat_id=chat_id, text=f"❌ Не удалось отправить голосовое. Текст: {text}")
                
        except Exception as e:
            logger.error(f"❌ Error sending real voice message: {e}")
            bot.send_message(chat_id=chat_id, text=f"❌ Ошибка отправки голосового: {e}")

    def process_message(self, update):
        """Обработка входящего сообщения"""
        try:
            user_message = update.message.text
            chat_id = update.message.chat_id
            user_name = update.message.from_user.first_name
            
            logger.info(f"📩 Message from {user_name}: {user_message}")
            
            # ТОЛЬКО тестовые команды для голосовых
            if user_message.lower().strip() in ['голос', 'voice', 'говори', 'озвучь', 'тест голос']:
                test_text = "Привет! Это тестовое голосовое сообщение. Как слышно?"
                logger.info("🎤 FORCED VOICE MESSAGE FOR TESTING")
                self.send_real_voice_message(chat_id, test_text)
                return
            
            # Обычные сообщения - только текст
            bot.send_chat_action(chat_id=chat_id, action='typing')
            response = self.get_deepseek_response(user_message)
            bot.send_message(chat_id=chat_id, text=response)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")

# Инициализация бота
cute_bot = CuteBoyBot()

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return jsonify({"status": "running"}), 200
    
    if request.method == 'POST':
        try:
            if not bot:
                return jsonify({"error": "Bot not configured"}), 400
            
            from telegram import Update
            update = Update.de_json(request.get_json(), bot)
            cute_bot.process_message(update)
            return jsonify({"status": "success"}), 200
            
        except Exception as e:
            logger.error(f"Error in webhook: {e}")
            return jsonify({"status": "error"}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
