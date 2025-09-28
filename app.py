from flask import Flask, request, jsonify
import os
import requests
import logging
import random
import tempfile

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
YANDEX_API_KEY = os.environ.get('YANDEX_API_KEY')
YANDEX_FOLDER_ID = os.environ.get('YANDEX_FOLDER_ID')

if not BOT_TOKEN:
    bot = None
else:
    from telegram import Bot, Update
    from telegram.utils.request import Request
    request_obj = Request(con_pool_size=8)
    bot = Bot(token=BOT_TOKEN, request=request_obj)

class CuteBoyBot:
    def yandex_tts(self, text):
        """Яндекс TTS с разными голосами"""
        try:
            if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
                return None
            
            clean_text = text.replace("🎤", "").replace("🤗", "").replace("💫", "").replace("😊", "").strip()
            
            # Пробуем разные мужские голоса
            male_voices = ['filipp', 'ermil', 'alexander']
            
            for voice in male_voices:
                logger.info(f"🔊 Trying Yandex voice: {voice}")
                
                url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
                headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
                
                data = {
                    "text": clean_text,
                    "lang": "ru-RU",
                    "voice": voice,
                    "emotion": "good", 
                    "speed": "1.0",
                    "format": "mp3",
                    "folderId": YANDEX_FOLDER_ID
                }
                
                response = requests.post(url, headers=headers, data=data, timeout=10)
                
                if response.status_code == 200:
                    logger.info(f"✅ Yandex TTS success with voice: {voice}")
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                        tmp_file.write(response.content)
                        return tmp_file.name
                else:
                    logger.warning(f"❌ Voice {voice} failed: {response.status_code}")
            
            return None
                
        except Exception as e:
            logger.error(f"❌ Yandex TTS exception: {e}")
            return None

    def send_voice_message(self, chat_id, text):
        """Отправка голосового"""
        try:
            logger.info(f"🎤 Sending voice: {text}")
            bot.send_chat_action(chat_id=chat_id, action='record_voice')
            
            audio_file = self.yandex_tts(text)
            
            if audio_file and os.path.exists(audio_file):
                with open(audio_file, 'rb') as audio:
                    bot.send_voice(chat_id=chat_id, voice=audio, caption="🎤 Алексей")
                logger.info("✅ Yandex voice sent!")
                os.unlink(audio_file)
                return True
            else:
                logger.error("❌ Yandex TTS failed completely")
                return False
                
        except Exception as e:
            logger.error(f"❌ Voice error: {e}")
            return False

    def process_message(self, update):
        try:
            user_message = update.message.text.lower().strip()
            chat_id = update.message.chat_id
            
            logger.info(f"📩 Message: {user_message}")
            
            if user_message in ['голос', 'voice', 'тест']:
                test_text = "Привет! Я Алексей. Это тестовое голосовое сообщение!"
                success = self.send_voice_message(chat_id, test_text)
                
                if not success:
                    bot.send_message(chat_id=chat_id, text="❌ Не удалось отправить голосовое. Проверьте настройки Яндекс.")
                return
            
            if bot:
                bot.send_message(chat_id=chat_id, text="Напиши 'голос' для теста!")

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
