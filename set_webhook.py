import requests
import os
from dotenv import load_dotenv

load_dotenv()

def set_webhook():
    token = os.environ.get('TELEGRAM_TOKEN')
    render_url = os.environ.get('RENDER_URL')
    
    if not token:
        print("❌ TELEGRAM_TOKEN not found")
        return
    
    if not render_url:
        print("❌ RENDER_URL not found")
        return
    
    webhook_url = f"{render_url}/webhook"
    
    print(f"🔄 Setting webhook to: {webhook_url}")
    
    response = requests.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": webhook_url}
    )
    
    result = response.json()
    print("📡 Webhook set result:", result)
    
    info_response = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
    print("🔍 Webhook info:", info_response.json())

if __name__ == '__main__':
    set_webhook()
