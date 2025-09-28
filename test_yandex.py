import os
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

YANDEX_API_KEY = os.environ.get('YANDEX_API_KEY')
YANDEX_FOLDER_ID = os.environ.get('YANDEX_FOLDER_ID')

print(f"🔧 API Key: {YANDEX_API_KEY[:10]}..." if YANDEX_API_KEY else "❌ API Key: NOT SET")
print(f"🔧 Folder ID: {YANDEX_FOLDER_ID}" if YANDEX_FOLDER_ID else "❌ Folder ID: NOT SET")

if YANDEX_API_KEY and YANDEX_FOLDER_ID:
    url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
    
    data = {
        "text": "тест",
        "lang": "ru-RU", 
        "voice": "filipp",
        "folderId": YANDEX_FOLDER_ID
    }
    
    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        print(f"🔧 Response status: {response.status_code}")
        print(f"🔧 Response text: {response.text[:100]}")
    except Exception as e:
        print(f"❌ Error: {e}")
