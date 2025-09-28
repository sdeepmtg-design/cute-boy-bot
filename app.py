from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import tempfile

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.environ.get('BOT_TOKEN')
YANDEX_API_KEY = os.environ.get('YANDEX_API_KEY')
YANDEX_FOLDER_ID = os.environ.get('YANDEX_FOLDER_ID')

# Проверяем переменные
logger.info(f"🔧 Config check - Yandex API Key: {'SET' if YANDEX_API_KEY else 'NOT SET'}")
logger.info(f"🔧 Config check - Yandex Folder ID: {'SET' if YANDEX_FOLDER_ID else 'NOT SET'}")

if not BOT_TOKEN:
    bot = None
else:
    from telegram import Bot, Update
    from telegram.utils.request import Request
    request_obj = Request(con_pool_size=8)
    bot = Bot(token=BOT_TOKEN, request=request_obj)

class CuteBoyBot:
    def yandex_tts(self, text):
        """Яндекс TTS"""
        try:
            if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
                logger.error("❌ Yandex credentials missing")
                return None
            
            clean_text = text.replace("🎤", "").replace("🤗", "").replace("💫", "").replace("😊", "").strip()
            logger.info(f"🔊 Yandex TTS: {clean_text}")
            
            url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
            headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
            
            data = {
                "text": clean_text,
                "lang": "ru-RU",
                "voice": "filipp",
                "emotion": "good",
                "speed": "1.0",
                "format": "mp3",
                "folderId": YANDEX_FOLDER_ID
            }
            
            response = requests.post(url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                    tmp_file.write(response.content)
                    logger.info(f"✅ Yandex TTS success")
                    return tmp_file.name
            else:
                logger.error(f"❌ Yandex TTS error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Yandex TTS exception: {e}")
            return None

    def gtts_tts(self, text):
        """Google TTS fallback"""
        try:
            from gtts import gTTS
            clean_text = text.replace("🎤", "").replace("🤗", "").replace("💫", "").replace("😊", "").strip()
            tts = gTTS(text=clean_text, lang='ru', slow=False)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                tts.save(tmp_file.name)
                logger.info("✅ Google TTS success")
                return tmp_file.name
                
        except Exception as e:
            logger.error(f"❌ Google TTS failed: {e}")
            return None

    def send_voice_message(self, chat_id, text):
        """Отправка голосового"""
        try:
            logger.info(f"🎤 Sending voice: {text}")
            bot.send_chat_action(chat_id=chat_id, action='record_voice')
            
            # Сначала пробуем Яндекс
            audio_file = self.yandex_tts(text)
            
            # Если Яндекс не сработал, пробуем Google
            if not audio_file:
                logger.info("🔄 Falling back to Google TTS")
                audio_file = self.gtts_tts(text)
            
            if audio_file and os.path.exists(audio_file):
                with open(audio_file, 'rb') as audio:
                    bot.send_voice(chat_id=chat_id, voice=audio, caption="🎤 Алексей")
                logger.info("✅ Voice sent!")
                os.unlink(audio_file)
            else:
                logger.error("❌ All TTS failed")
                bot.send_message(chat_id=chat_id, text=f"🎤 {text}")
                
        except Exception as e:
            logger.error(f"❌ Voice error: {e}")
            bot.send_message(chat_id=chat_id, text=text)

    def process_message(self, update):
        try:
            user_message = update.message.text.lower().strip()
            chat_id = update.message.chat_id
            
            logger.info(f"📩 Message: {user_message}")
            
            if user_message in ['голос', 'voice', 'тест']:
                test_text = "Привет! Я Алексей. Это тестовое голосовое сообщение через Яндекс SpeechKit!"
                self.send_voice_message(chat_id, test_text)
                return
            
            if bot:
                bot.send_message(chat_id=chat_id, text="Напиши 'голос' для теста голосового сообщения! 🎤")

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
        "yandex_configured": bool(YANDEX_API_KEY and YANDEX_FOLDER_ID)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
