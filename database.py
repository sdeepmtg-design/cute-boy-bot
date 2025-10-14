import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Получаем URL базы данных из переменных окружения
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///bot_database.db')

# Заменяем начало URL для PostgreSQL на Render
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)
    plan_type = Column(String)
    activated_at = Column(DateTime)
    expires_at = Column(DateTime)
    payment_status = Column(String)

class UserMessageCount(Base):
    __tablename__ = "user_message_counts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)
    message_count = Column(Integer, default=0)

# НОВЫЕ ТАБЛИЦЫ ДЛЯ СОХРАНЕНИЯ СОСТОЯНИЯ
class ConversationHistory(Base):
    __tablename__ = "conversation_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.now)

class UsedStickers(Base):
    __tablename__ = "used_stickers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    sticker_id = Column(String)
    used_at = Column(DateTime, default=datetime.now)

# Создаем таблицы
Base.metadata.create_all(bind=engine)

class DatabaseManager:
    def __init__(self):
        self.db = SessionLocal()
    
    def get_subscription(self, user_id):
        user_id_str = str(user_id)
        try:
            subscription = self.db.query(UserSubscription).filter(
                UserSubscription.user_id == user_id_str
            ).first()
            return subscription
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
            return None
    
    def update_subscription(self, user_id, plan_type, days):
        user_id_str = str(user_id)
        
        try:
            # Удаляем старую подписку если есть
            old_sub = self.get_subscription(user_id)
            if old_sub:
                self.db.delete(old_sub)
                self.db.commit()
            
            # Создаем новую подписку
            new_sub = UserSubscription(
                user_id=user_id_str,
                plan_type=plan_type,
                activated_at=datetime.now(),
                expires_at=datetime.now() + timedelta(days=days),
                payment_status='paid'
            )
            self.db.add(new_sub)
            self.db.commit()
            return new_sub
        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
            self.db.rollback()
            return None
    
    def get_message_count(self, user_id):
        user_id_str = str(user_id)
        try:
            count_obj = self.db.query(UserMessageCount).filter(
                UserMessageCount.user_id == user_id_str
            ).first()
            return count_obj.message_count if count_obj else 0
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
            return 0
    
    def update_message_count(self, user_id, count):
        user_id_str = str(user_id)
        try:
            count_obj = self.db.query(UserMessageCount).filter(
                UserMessageCount.user_id == user_id_str
            ).first()
            
            if count_obj:
                count_obj.message_count = count
            else:
                count_obj = UserMessageCount(
                    user_id=user_id_str,
                    message_count=count
                )
                self.db.add(count_obj)
            
            self.db.commit()
            return count_obj
        except Exception as e:
            logger.error(f"Error updating message count: {e}")
            self.db.rollback()
            return None

    # НОВЫЕ МЕТОДЫ ДЛЯ СОХРАНЕНИЯ СОСТОЯНИЯ
    
    def save_conversation(self, user_id, role, content):
        """Сохраняет сообщение в историю разговоров"""
        user_id_str = str(user_id)
        try:
            # Ограничиваем историю до 20 сообщений на пользователя
            history_count = self.db.query(ConversationHistory).filter(
                ConversationHistory.user_id == user_id_str
            ).count()
            
            if history_count >= 20:
                # Удаляем самые старые сообщения
                oldest_messages = self.db.query(ConversationHistory).filter(
                    ConversationHistory.user_id == user_id_str
                ).order_by(ConversationHistory.timestamp.asc()).limit(history_count - 19).all()
                
                for msg in oldest_messages:
                    self.db.delete(msg)
            
            conversation = ConversationHistory(
                user_id=user_id_str,
                role=role,
                content=content
            )
            self.db.add(conversation)
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            self.db.rollback()
            return False
    
    def get_conversation_history(self, user_id, limit=20):
        """Получает историю разговоров пользователя"""
        user_id_str = str(user_id)
        try:
            messages = self.db.query(ConversationHistory).filter(
                ConversationHistory.user_id == user_id_str
            ).order_by(ConversationHistory.timestamp.asc()).limit(limit).all()
            
            return [
                {
                    "role": msg.role, 
                    "content": msg.content, 
                    "timestamp": msg.timestamp
                }
                for msg in messages
            ]
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def clear_conversation_history(self, user_id):
        """Очищает историю разговоров пользователя"""
        user_id_str = str(user_id)
        try:
            self.db.query(ConversationHistory).filter(
                ConversationHistory.user_id == user_id_str
            ).delete()
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error clearing conversation history: {e}")
            self.db.rollback()
            return False
    
    def add_used_sticker(self, user_id, sticker_id):
        """Добавляет стикер в список использованных"""
        user_id_str = str(user_id)
        try:
            # Очищаем старые записи (больше 100 на пользователя)
            sticker_count = self.db.query(UsedStickers).filter(
                UsedStickers.user_id == user_id_str
            ).count()
            
            if sticker_count >= 100:
                oldest_stickers = self.db.query(UsedStickers).filter(
                    UsedStickers.user_id == user_id_str
                ).order_by(UsedStickers.used_at.asc()).limit(sticker_count - 99).all()
                
                for sticker in oldest_stickers:
                    self.db.delete(sticker)
            
            used_sticker = UsedStickers(
                user_id=user_id_str,
                sticker_id=sticker_id
            )
            self.db.add(used_sticker)
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding used sticker: {e}")
            self.db.rollback()
            return False
    
    def get_used_stickers(self, user_id):
        """Получает множество использованных стикеров пользователя"""
        user_id_str = str(user_id)
        try:
            stickers = self.db.query(UsedStickers).filter(
                UsedStickers.user_id == user_id_str
            ).all()
            return {sticker.sticker_id for sticker in stickers}
        except Exception as e:
            logger.error(f"Error getting used stickers: {e}")
            return set()
    
    def clear_used_stickers(self, user_id):
        """Очищает список использованных стикеров пользователя"""
        user_id_str = str(user_id)
        try:
            self.db.query(UsedStickers).filter(
                UsedStickers.user_id == user_id_str
            ).delete()
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error clearing used stickers: {e}")
            self.db.rollback()
            return False

# Глобальный экземпляр
db_manager = DatabaseManager()
