import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Подключение к базе данных
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///bot.db')

if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True)
    plan_type = Column(String)  # 'week', 'month', 'unlimited'
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)  # Исправлено на created_at
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserMessageCount(Base):
    __tablename__ = "user_message_counts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True)
    message_count = Column(Integer, default=0)
    last_reset = Column(DateTime, default=datetime.utcnow)

class ConversationHistory(Base):
    __tablename__ = "conversation_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class UsedStickers(Base):
    __tablename__ = "used_stickers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    sticker_id = Column(String)
    used_at = Column(DateTime, default=datetime.utcnow)

# Создаем таблицы
Base.metadata.create_all(bind=engine)

class DatabaseManager:
    def __init__(self):
        self.db = SessionLocal()
    
    def get_subscription(self, user_id):
        try:
            return self.db.query(UserSubscription).filter(UserSubscription.user_id == user_id).first()
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
            return None
    
    def update_subscription(self, user_id, plan_type, days):
        try:
            subscription = self.get_subscription(user_id)
            expires_at = datetime.utcnow() + timedelta(days=days)
            
            if subscription:
                subscription.plan_type = plan_type
                subscription.expires_at = expires_at
                subscription.updated_at = datetime.utcnow()
            else:
                subscription = UserSubscription(
                    user_id=user_id,
                    plan_type=plan_type,
                    expires_at=expires_at,
                    created_at=datetime.utcnow()
                )
                self.db.add(subscription)
            
            self.db.commit()
            self.db.refresh(subscription)
            return subscription
        except Exception as e:
            logger.error(f"Error updating subscription: {e}")
            self.db.rollback()
            return None
    
    def get_message_count(self, user_id):
        try:
            user_count = self.db.query(UserMessageCount).filter(UserMessageCount.user_id == user_id).first()
            if user_count:
                # Проверяем, не пора ли сбросить счетчик (например, раз в месяц)
                if (datetime.utcnow() - user_count.last_reset).days >= 30:
                    user_count.message_count = 0
                    user_count.last_reset = datetime.utcnow()
                    self.db.commit()
                return user_count.message_count
            else:
                # Создаем новую запись
                user_count = UserMessageCount(user_id=user_id, message_count=0)
                self.db.add(user_count)
                self.db.commit()
                return 0
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
            return 0
    
    def update_message_count(self, user_id, count):
        try:
            user_count = self.db.query(UserMessageCount).filter(UserMessageCount.user_id == user_id).first()
            if user_count:
                user_count.message_count = count
            else:
                user_count = UserMessageCount(user_id=user_id, message_count=count)
                self.db.add(user_count)
            
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating message count: {e}")
            self.db.rollback()
            return False
    
    def save_conversation(self, user_id, role, content):
        try:
            # Ограничиваем историю до 20 сообщений на пользователя
            history_count = self.db.query(ConversationHistory).filter(ConversationHistory.user_id == user_id).count()
            if history_count >= 20:
                # Удаляем самые старые сообщения
                oldest_messages = self.db.query(ConversationHistory).filter(
                    ConversationHistory.user_id == user_id
                ).order_by(ConversationHistory.timestamp.asc()).limit(history_count - 19).all()
                
                for msg in oldest_messages:
                    self.db.delete(msg)
            
            conversation = ConversationHistory(
                user_id=user_id,
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
        try:
            messages = self.db.query(ConversationHistory).filter(
                ConversationHistory.user_id == user_id
            ).order_by(ConversationHistory.timestamp.asc()).limit(limit).all()
            
            return [
                {"role": msg.role, "content": msg.content, "timestamp": msg.timestamp}
                for msg in messages
            ]
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def clear_conversation_history(self, user_id):
        try:
            self.db.query(ConversationHistory).filter(ConversationHistory.user_id == user_id).delete()
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error clearing conversation history: {e}")
            self.db.rollback()
            return False
    
    def add_used_sticker(self, user_id, sticker_id):
        try:
            # Очищаем старые записи (больше 100 на пользователя)
            sticker_count = self.db.query(UsedStickers).filter(UsedStickers.user_id == user_id).count()
            if sticker_count >= 100:
                oldest_stickers = self.db.query(UsedStickers).filter(
                    UsedStickers.user_id == user_id
                ).order_by(UsedStickers.used_at.asc()).limit(sticker_count - 99).all()
                
                for sticker in oldest_stickers:
                    self.db.delete(sticker)
            
            used_sticker = UsedStickers(
                user_id=user_id,
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
        try:
            stickers = self.db.query(UsedStickers).filter(UsedStickers.user_id == user_id).all()
            return {sticker.sticker_id for sticker in stickers}
        except Exception as e:
            logger.error(f"Error getting used stickers: {e}")
            return set()
    
    def clear_used_stickers(self, user_id):
        try:
            self.db.query(UsedStickers).filter(UsedStickers.user_id == user_id).delete()
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error clearing used stickers: {e}")
            self.db.rollback()
            return False

# Глобальный экземпляр менеджера БД
db_manager = DatabaseManager()
