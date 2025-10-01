import json
import os
from datetime import datetime

class Storage:
    def __init__(self):
        self.data_file = "subscriptions.json"
        self.data = self.load_data()

    def load_data(self):
        """Загрузка данных из файла"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Конвертируем строки дат обратно в datetime
                    for user_id, sub_data in data.get('subscriptions', {}).items():
                        if 'activated_at' in sub_data:
                            sub_data['activated_at'] = datetime.fromisoformat(sub_data['activated_at'])
                        if 'expires_at' in sub_data:
                            sub_data['expires_at'] = datetime.fromisoformat(sub_data['expires_at'])
                    return data
        except Exception as e:
            print(f"Error loading data: {e}")
        return {'subscriptions': {}, 'user_message_count': {}}

    def save_data(self):
        """Сохранение данных в файл"""
        try:
            # Конвертируем datetime в строки для JSON
            data_to_save = {
                'subscriptions': {},
                'user_message_count': self.data.get('user_message_count', {})
            }
            
            for user_id, sub_data in self.data.get('subscriptions', {}).items():
                data_to_save['subscriptions'][user_id] = sub_data.copy()
                if 'activated_at' in sub_data:
                    data_to_save['subscriptions'][user_id]['activated_at'] = sub_data['activated_at'].isoformat()
                if 'expires_at' in sub_data:
                    data_to_save['subscriptions'][user_id]['expires_at'] = sub_data['expires_at'].isoformat()
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving data: {e}")

    @property
    def subscriptions(self):
        return self.data.get('subscriptions', {})

    @property 
    def user_message_count(self):
        return self.data.get('user_message_count', {})

    def update_subscription(self, user_id, subscription_data):
        """Обновление подписки пользователя"""
        user_id_str = str(user_id)
        if 'subscriptions' not in self.data:
            self.data['subscriptions'] = {}
        self.data['subscriptions'][user_id_str] = subscription_data
        self.save_data()

    def update_message_count(self, user_id, count):
        """Обновление счетчика сообщений"""
        user_id_str = str(user_id)
        if 'user_message_count' not in self.data:
            self.data['user_message_count'] = {}
        self.data['user_message_count'][user_id_str] = count
        self.save_data()

# Глобальный экземпляр хранилища
storage = Storage()
