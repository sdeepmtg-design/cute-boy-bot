from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import tempfile
from gtts import gTTS
import io

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

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

    def text_to_speech_improved(self, text):
        """Улучшенный TTS с попыткой мужского голоса"""
        try:
            # Очищаем текст для TTS
            clean_text = text.replace("🎤", "").replace("🤗", "").replace("💫", "").replace("😊", "").replace("🎯", "").strip()
            
            logger.info(f"🔊 TTS converting: {clean_text}")
            
            # Вариант 1: Пробуем разные языки и настройки
            # Для русского мужского голоса можно попробовать:
            tts = gTTS(
                text=clean_text, 
                lang='ru',
                slow=False,  # Немного ускорим
                lang_check=False  # Отключаем проверку языка
            )
            
            # Альтернатива: пробуем английский с русским текстом (иногда лучше)
            # tts = gTTS(text=clean_text, lang='en', slow=False)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tts.save(tmp_file.name)
                logger.info(f"🔊 TTS audio saved")
                return tmp_file.name
                
        except Exception as e:
            logger.error(f"❌ TTS ERROR: {e}")
            return None

    def send_voice_with_fallback(self, chat_id, text):
        """Отправка голосового с улучшенным TTS"""
        try:
            logger.info(f"🎤 Sending voice: {text}")
            bot.send_chat_action(chat_id=chat_id, action='record_voice')
            
            # Пробуем улучшенный TTS
            audio_file = self.text_to_speech_improved(text)
            
            if audio_file and os.path.exists(audio_file):
                # Отправляем голосовое
                with open(audio_file, 'rb') as audio:
                    bot.send_voice(
                        chat_id=chat_id,
                        voice=audio,
                        caption="🎤 Алексей"
                    )
                logger.info("✅ Voice sent!")
                os.unlink(audio_file)
            else:
                # Fallback: отправляем текстом с объяснением
                bot.send_message(
                    chat_id=chat_id, 
                    text=f"🎤 {text}\n\n(К сожалению, голосовой движок временно недоступен 😔)"
                )
                
        except Exception as e:
            logger.error(f"❌ Voice error: {e}")
            bot.send_message(chat_id=chat_id, text=text)

    def process_message(self, update):
        try:
            user_message = update.message.text
            chat_id = update.message.chat_id
            
            logger.info(f"📩 Message: {user_message}")
            
            # Тест голосовых
            if self.should_send_voice(user_message):
                test_messages = [
                    "Привет! Я Алексей, рад тебя слышать",
                    "Здравствуй! Как твои дела?",
                    "Приветствую тебя! Очень приятно познакомиться",
                    "Добрый день! Надеюсь, у тебя все хорошо"
                ]
                test_text = random.choice(test_messages)
                self.send_voice_with_fallback(chat_id, test_text)
                return
            
            # Обычные сообщения
            if bot:
                sweet_name = self.get_sweet_name()
                responses = [
                    f"Привет, {sweet_name}! Как твои дела? 🤗",
                    f"Здравствуй, {sweet_name}! Рад тебя видеть! 💫",
                    f"Привет, {sweet_name}! Что нового? 😊"
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
