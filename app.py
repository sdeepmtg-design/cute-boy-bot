from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import tempfile
import uuid
import hashlib
import time

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
YANDEX_API_KEY = os.environ.get('YANDEX_API_KEY')  # Ключ от Яндекс Cloud
YANDEX_FOLDER_ID = os.environ.get('YANDEX_FOLDER_ID')  # Folder ID из Яндекс Cloud

if not BOT_TOKEN:
    bot = None
else:
    from telegram import Bot, Update
    from telegram.utils.request import Request
    request_obj = Request(con_pool_size=8)
    bot = Bot(token=BOT_TOKEN, request=request_obj)

class CuteBoyBot:
    def __init__(self):
        self.sweet_names = ["красавица", "милая", "подружка", "солнышко"]
    
    def get_sweet_name(self):
        return random.choice(self.sweet_names)
    
    def should_send_voice(self, message):
        message_lower = message.lower().strip()
        voice_triggers = ['голос', 'voice', 'говори', 'озвучь', 'тест голос']
        return any(trigger in message_lower for trigger in voice_triggers)

    def yandex_text_to_speech(self, text):
        """Используем Яндекс SpeechKit для качественного мужского голоса"""
        try:
            if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
                logger.error("❌ Yandex credentials not set")
                return None
            
            # Очищаем текст
            clean_text = text.replace("🎤", "").replace("🤗", "").replace("💫", "").replace("😊", "").replace("🎯", "").strip()
            
            logger.info(f"🔊 Yandex TTS converting: {clean_text}")
            
            # URL для Яндекс SpeechKit
            url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
            
            headers = {
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
            }
            
            # Параметры для мужского голоса
            data = {
                "text": clean_text,
                "lang": "ru-RU",
                "voice": "filipp",  # Мужские голоса: filipp, ermil, alexander
                "emotion": "good",  # good, neutral, evil
                "speed": "1.0",
                "format": "mp3",
                "folderId": YANDEX_FOLDER_ID
            }
            
            response = requests.post(url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                # Сохраняем аудио во временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                    tmp_file.write(response.content)
                    logger.info(f"🔊 Yandex TTS success: {len(response.content)} bytes")
                    return tmp_file.name
            else:
                logger.error(f"❌ Yandex TTS error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Yandex TTS exception: {e}")
            return None

    def send_voice_with_yandex(self, chat_id, text):
        """Отправка голосового с Яндекс TTS"""
        try:
            logger.info(f"🎤 Sending Yandex voice: {text}")
            bot.send_chat_action(chat_id=chat_id, action='record_voice')
            
            # Используем Яндекс TTS
            audio_file = self.yandex_text_to_speech(text)
            
            if audio_file and os.path.exists(audio_file):
                file_size = os.path.getsize(audio_file)
                logger.info(f"🔊 Yandex audio file ready: {file_size} bytes")
                
                # Отправляем голосовое
                with open(audio_file, 'rb') as audio:
                    bot.send_voice(
                        chat_id=chat_id,
                        voice=audio,
                        caption="🎤 Алексей"
                    )
                logger.info("✅ Yandex voice sent successfully!")
                os.unlink(audio_file)
            else:
                # Fallback на Google TTS
                logger.warning("🔄 Yandex TTS failed, falling back to gTTS")
                self.send_voice_with_gtts(chat_id, text)
                
        except Exception as e:
            logger.error(f"❌ Voice sending error: {e}")
            bot.send_message(chat_id=chat_id, text=f"🎤 {text}")

    def send_voice_with_gtts(self, chat_id, text):
        """Fallback на Google TTS"""
        try:
            from gtts import gTTS
            
            clean_text = text.replace("🎤", "").replace("🤗", "").replace("💫", "").replace("😊", "").replace("🎯", "").strip()
            tts = gTTS(text=clean_text, lang='ru', slow=False)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tts.save(tmp_file.name)
                
                with open(tmp_file.name, 'rb') as audio:
                    bot.send_voice(
                        chat_id=chat_id,
                        voice=audio,
                        caption="🎤 Алексей (резервный голос)"
                    )
                os.unlink(tmp_file.name)
                
        except Exception as e:
            logger.error(f"❌ gTTS fallback failed: {e}")
            bot.send_message(chat_id=chat_id, text=f"🎤 {text}")

    def process_message(self, update):
        try:
            user_message = update.message.text
            chat_id = update.message.chat_id
            
            logger.info(f"📩 Message: {user_message}")
            
            # Тест голосовых
            if self.should_send_voice(user_message):
                test_messages = [
                    "Привет! Я Алексей, очень рад тебя слышать",
                    "Здравствуй! Как твои дела сегодня?",
                    "Приветствую! Очень приятно с тобой познакомиться",
                    "Добрый день! Надеюсь, у тебя прекрасное настроение"
                ]
                test_text = random.choice(test_messages)
                
                if YANDEX_API_KEY and YANDEX_FOLDER_ID:
                    logger.info("🚀 Using Yandex TTS")
                    self.send_voice_with_yandex(chat_id, test_text)
                else:
                    logger.info("🔄 Yandex not configured, using gTTS")
                    self.send_voice_with_gtts(chat_id, test_text)
                return
            
            # Обычные сообщения
            if bot:
                sweet_name = self.get_sweet_name()
                responses = [
                    f"Привет, {sweet_name}! 🤗",
                    f"Здравствуй, {sweet_name}! 💫",
                    f"Привет, {sweet_name}! 😊"
                ]
                bot.send_message(chat_id=chat_id, text=random.choice(responses))

        except Exception as e:
            logger.error(f"Error: {e}")

cute_bot = CuteBoyBot()

@app.route('/webhook', methods=['POST'])
def webhook():
    if not bot:
        return jsonify({"error": "Bot not configured"}), 400
    
    try:
        from telegram import Update
        update = Update.de_json(request.get_json(), bot)
        cute_bot.process_message(update)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 400

@app.route('/')
def home():
    return jsonify({
        "status": "healthy",
        "tts_engine": "Yandex SpeechKit" if YANDEX_API_KEY else "Google TTS",
        "features": ["real_voice_messages", "yandex_tts"]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
