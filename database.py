import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

# Используем SQLite (файловая база)
DATABASE_URL = "sqlite:///bot_database.db"

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

# Создаем таблицы
Base.metadata.create_all(bind=engine)

class DatabaseManager:
    def __init__(self):
        self.db = SessionLocal()
    
    def get_subscription(self, user_id):
        user_id_str = str(user_id)
        return self.db.query(UserSubscription).filter(
            UserSubscription.user_id == user_id_str
        ).first()
    
    def update_subscription(self, user_id, plan_type, days):
        user_id_str = str(user_id)
        
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
    
    def get_message_count(self, user_id):
        user_id_str = str(user_id)
        count_obj = self.db.query(UserMessageCount).filter(
            UserMessageCount.user_id == user_id_str
        ).first()
        return count_obj.message_count if count_obj else 0
    
    def update_message_count(self, user_id, count):
        user_id_str = str(user_id)
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

# Глобальный экземпляр
db_manager = DatabaseManager()
