import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Подключение к базе данных
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    logger.error("❌ DATABASE_URL environment variable is not set!")
    logger.warning("⚠️ Using SQLite - data will be lost on restart!")
    DATABASE_URL = 'sqlite:///temp_bot.db'

# Исправляем URL для SQLAlchemy
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

logger.info(f"🔗 Database URL: {DATABASE_URL}")

try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    
    # Тестируем подключение
    connection = engine.connect()
    connection.close()
    logger.info("✅ Database connection successful")
    
except Exception as e:
    logger.error(f"❌ Database connection failed: {e}")
    # Fallback на SQLite
    engine = create_engine('sqlite:///fallback.db')
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True)
    plan_type = Column(String)  # 'week' or 'month'
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<UserSubscription(user_id={self.user_id}, plan={self.plan_type}, expires={self.expires_at})>"

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class UserMessageCount(Base):
    __tablename__ = "user_message_counts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True)
    message_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

# Создаем таблицы
try:
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables created successfully")
except Exception as e:
    logger.error(f"❌ Error creating tables: {e}")

class DatabaseManager:
    def __init__(self):
        self.session = SessionLocal()
    
    def update_subscription(self, user_id, plan_type, days):
        """Обновление или создание подписки с правильным расчетом времени"""
        try:
            # Удаляем старую подписку если есть
            old_sub = self.session.query(UserSubscription).filter(UserSubscription.user_id == user_id).first()
            if old_sub:
                self.session.delete(old_sub)
                self.session.commit()
            
            # Создаем новую подписку
            created_at = datetime.utcnow()
            expires_at = created_at + timedelta(days=days)
            
            subscription = UserSubscription(
                user_id=user_id,
                plan_type=plan_type,
                created_at=created_at,
                expires_at=expires_at,
                is_active=True
            )
            
            self.session.add(subscription)
            self.session.commit()
            
            logger.info(f"✅ Subscription CREATED: user={user_id}, plan={plan_type}, expires={expires_at}")
            return subscription
            
        except Exception as e:
            logger.error(f"❌ Error updating subscription: {e}")
            self.session.rollback()
            return None
    
    def get_subscription(self, user_id):
        """Получение активной подписки пользователя"""
        try:
            subscription = self.session.query(UserSubscription).filter(
                UserSubscription.user_id == user_id
            ).first()
            
            if subscription:
                is_active = subscription.is_active
                is_valid = subscription.expires_at > datetime.utcnow()
                
                logger.info(f"📊 Subscription check: user={user_id}, active={is_active}, valid={is_valid}, expires={subscription.expires_at}")
                
                if is_active and is_valid:
                    return subscription
                else:
                    logger.warning(f"⚠️ Subscription expired or inactive: user={user_id}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
            return None
    
    def save_conversation(self, user_id, role, content):
        """Сохранение сообщения в историю"""
        try:
            conversation = Conversation(
                user_id=user_id,
                role=role,
                content=content
            )
            self.session.add(conversation)
            self.session.commit()
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            self.session.rollback()
    
    def get_conversation_history(self, user_id, limit=10):
        """Получение истории разговора"""
        try:
            conversations = self.session.query(Conversation).filter(
                Conversation.user_id == user_id
            ).order_by(Conversation.timestamp.desc()).limit(limit).all()
            
            return [
                {"role": conv.role, "content": conv.content}
                for conv in reversed(conversations)
            ]
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def get_message_count(self, user_id):
        """Получение количества отправленных сообщений"""
        try:
            user_count = self.session.query(UserMessageCount).filter(
                UserMessageCount.user_id == user_id
            ).first()
            
            return user_count.message_count if user_count else 0
            
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
            return 0
    
    def update_message_count(self, user_id, count):
        """Обновление счетчика сообщений"""
        try:
            user_count = self.session.query(UserMessageCount).filter(
                UserMessageCount.user_id == user_id
            ).first()
            
            if user_count:
                user_count.message_count = count
                user_count.last_updated = datetime.utcnow()
            else:
                user_count = UserMessageCount(
                    user_id=user_id,
                    message_count=count
                )
                self.session.add(user_count)
            
            self.session.commit()
            
        except Exception as e:
            logger.error(f"Error updating message count: {e}")
            self.session.rollback()
    
    def cleanup_expired_subscriptions(self):
        """Очистка истекших подписок"""
        try:
            expired_count = self.session.query(UserSubscription).filter(
                UserSubscription.expires_at <= datetime.utcnow(),
                UserSubscription.is_active == True
            ).update({"is_active": False})
            
            self.session.commit()
            logger.info(f"🧹 Cleaned up {expired_count} expired subscriptions")
            
        except Exception as e:
            logger.error(f"Error cleaning expired subscriptions: {e}")
            self.session.rollback()
    
    def debug_all_subscriptions(self):
        """Отладочная функция: показать все подписки"""
        try:
            subscriptions = self.session.query(UserSubscription).all()
            result = []
            for sub in subscriptions:
                result.append({
                    "user_id": sub.user_id,
                    "plan_type": sub.plan_type,
                    "created_at": sub.created_at.isoformat(),
                    "expires_at": sub.expires_at.isoformat(),
                    "is_active": sub.is_active,
                    "is_valid": sub.expires_at > datetime.utcnow()
                })
            return result
        except Exception as e:
            logger.error(f"Error getting all subscriptions: {e}")
            return []

# Глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Подключение к базе данных
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    logger.error("❌ DATABASE_URL environment variable is not set!")
    logger.warning("⚠️ Using SQLite - data will be lost on restart!")
    DATABASE_URL = 'sqlite:///temp_bot.db'

# Исправляем URL для SQLAlchemy
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

logger.info(f"🔗 Database URL: {DATABASE_URL}")

try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    
    # Тестируем подключение
    connection = engine.connect()
    connection.close()
    logger.info("✅ Database connection successful")
    
except Exception as e:
    logger.error(f"❌ Database connection failed: {e}")
    # Fallback на SQLite
    DATABASE_URL = 'sqlite:///fallback.db'
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)  # Changed to BigInteger for Telegram IDs
    plan_type = Column(String)  # 'week' or 'month'
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<UserSubscription(user_id={self.user_id}, plan={self.plan_type}, expires={self.expires_at})>"

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)  # Changed to BigInteger
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class UserMessageCount(Base):
    __tablename__ = "user_message_counts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)  # Changed to BigInteger
    message_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

# Создаем таблицы
try:
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables created successfully")
except Exception as e:
    logger.error(f"❌ Error creating tables: {e}")

class DatabaseManager:
    def __init__(self):
        self.SessionLocal = SessionLocal
    
    @contextmanager
    def get_session(self):
        """Контекстный менеджер для сессий"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def update_subscription(self, user_id, plan_type, days):
        """Обновление или создание подписки с правильным расчетом времени"""
        try:
            with self.get_session() as session:
                # Удаляем старую подписку если есть
                old_sub = session.query(UserSubscription).filter(UserSubscription.user_id == user_id).first()
                if old_sub:
                    session.delete(old_sub)
                    session.commit()
                
                # Создаем новую подписку
                created_at = datetime.utcnow()
                expires_at = created_at + timedelta(days=days)
                
                subscription = UserSubscription(
                    user_id=user_id,
                    plan_type=plan_type,
                    created_at=created_at,
                    expires_at=expires_at,
                    is_active=True
                )
                
                session.add(subscription)
                session.commit()
                
                logger.info(f"✅ Subscription CREATED: user={user_id}, plan={plan_type}, expires={expires_at}")
                return subscription
                
        except Exception as e:
            logger.error(f"❌ Error updating subscription: {e}")
            return None
    
    def get_subscription(self, user_id):
        """Получение активной подписки пользователя"""
        try:
            with self.get_session() as session:
                subscription = session.query(UserSubscription).filter(
                    UserSubscription.user_id == user_id
                ).first()
                
                if subscription:
                    is_active = subscription.is_active
                    is_valid = subscription.expires_at > datetime.utcnow()
                    
                    logger.info(f"📊 Subscription check: user={user_id}, active={is_active}, valid={is_valid}, expires={subscription.expires_at}")
                    
                    if is_active and is_valid:
                        return subscription
                    else:
                        logger.warning(f"⚠️ Subscription expired or inactive: user={user_id}")
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
            return None
    
    def save_conversation(self, user_id, role, content):
        """Сохранение сообщения в историю"""
        try:
            with self.get_session() as session:
                conversation = Conversation(
                    user_id=user_id,
                    role=role,
                    content=content
                )
                session.add(conversation)
                session.commit()
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
    
    def get_conversation_history(self, user_id, limit=10):
        """Получение истории разговора"""
        try:
            with self.get_session() as session:
                conversations = session.query(Conversation).filter(
                    Conversation.user_id == user_id
                ).order_by(Conversation.timestamp.desc()).limit(limit).all()
                
                return [
                    {"role": conv.role, "content": conv.content}
                    for conv in reversed(conversations)
                ]
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def get_message_count(self, user_id):
        """Получение количества отправленных сообщений"""
        try:
            with self.get_session() as session:
                user_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                return user_count.message_count if user_count else 0
                
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
            return 0
    
    def update_message_count(self, user_id, count):
        """Обновление счетчика сообщений"""
        try:
            with self.get_session() as session:
                user_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                if user_count:
                    user_count.message_count = count
                    user_count.last_updated = datetime.utcnow()
                else:
                    user_count = UserMessageCount(
                        user_id=user_id,
                        message_count=count
                    )
                    session.add(user_count)
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Error updating message count: {e}")
    
    def increment_message_count(self, user_id):
        """Увеличение счетчика сообщений на 1"""
        try:
            with self.get_session() as session:
                user_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                if user_count:
                    user_count.message_count += 1
                    user_count.last_updated = datetime.utcnow()
                else:
                    user_count = UserMessageCount(
                        user_id=user_id,
                        message_count=1
                    )
                    session.add(user_count)
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Error incrementing message count: {e}")
    
    def cleanup_expired_subscriptions(self):
        """Очистка истекших подписок"""
        try:
            with self.get_session() as session:
                expired_count = session.query(UserSubscription).filter(
                    UserSubscription.expires_at <= datetime.utcnow(),
                    UserSubscription.is_active == True
                ).update({"is_active": False})
                
                session.commit()
                logger.info(f"🧹 Cleaned up {expired_count} expired subscriptions")
                
        except Exception as e:
            logger.error(f"Error cleaning expired subscriptions: {e}")
    
    def debug_all_subscriptions(self):
        """Отладочная функция: показать все подписки"""
        try:
            with self.get_session() as session:
                subscriptions = session.query(UserSubscription).all()
                result = []
                for sub in subscriptions:
                    result.append({
                        "user_id": sub.user_id,
                        "plan_type": sub.plan_type,
                        "created_at": sub.created_at.isoformat(),
                        "expires_at": sub.expires_at.isoformat(),
                        "is_active": sub.is_active,
                        "is_valid": sub.expires_at > datetime.utcnow()
                    })
                return result
        except Exception as e:
            logger.error(f"Error getting all subscriptions: {e}")
            return []
    
    def get_user_stats(self, user_id):
        """Получение статистики пользователя"""
        try:
            with self.get_session() as session:
                subscription = session.query(UserSubscription).filter(
                    UserSubscription.user_id == user_id
                ).first()
                
                message_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                return {
                    "has_subscription": subscription is not None,
                    "subscription_active": subscription.is_active if subscription else False,
                    "subscription_valid": subscription.expires_at > datetime.utcnow() if subscription else False,
                    "plan_type": subscription.plan_type if subscription else None,
                    "expires_at": subscription.expires_at if subscription else None,
                    "message_count": message_count.message_count if message_count else 0
                }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return None

# Глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Подключение к базе данных
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    logger.error("❌ DATABASE_URL environment variable is not set!")
    logger.warning("⚠️ Using SQLite - data will be lost on restart!")
    DATABASE_URL = 'sqlite:///temp_bot.db'

# Исправляем URL для SQLAlchemy
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

logger.info(f"🔗 Database URL: {DATABASE_URL}")

try:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    
    # Тестируем подключение
    connection = engine.connect()
    connection.close()
    logger.info("✅ Database connection successful")
    
except Exception as e:
    logger.error(f"❌ Database connection failed: {e}")
    # Fallback на SQLite
    DATABASE_URL = 'sqlite:///fallback.db'
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)
    plan_type = Column(String)  # 'week' or 'month'
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<UserSubscription(user_id={self.user_id}, plan={self.plan_type}, expires={self.expires_at})>"

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    role = Column(String)  # 'user' or 'assistant'
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

class UserMessageCount(Base):
    __tablename__ = "user_message_counts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)
    message_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

# Создаем таблицы
try:
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables created successfully")
except Exception as e:
    logger.error(f"❌ Error creating tables: {e}")

class DatabaseManager:
    def __init__(self):
        self.SessionLocal = SessionLocal
    
    @contextmanager
    def get_session(self):
        """Контекстный менеджер для сессий"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def update_subscription(self, user_id, plan_type, days):
        """Обновление или создание подписки с правильным расчетом времени"""
        try:
            with self.get_session() as session:
                # Удаляем старую подписку если есть
                old_sub = session.query(UserSubscription).filter(UserSubscription.user_id == user_id).first()
                if old_sub:
                    session.delete(old_sub)
                    session.commit()
                
                # Создаем новую подписку
                created_at = datetime.utcnow()
                expires_at = created_at + timedelta(days=days)
                
                subscription = UserSubscription(
                    user_id=user_id,
                    plan_type=plan_type,
                    created_at=created_at,
                    expires_at=expires_at,
                    is_active=True
                )
                
                session.add(subscription)
                session.commit()
                
                logger.info(f"✅ Subscription CREATED: user={user_id}, plan={plan_type}, expires={expires_at}")
                return subscription
                
        except Exception as e:
            logger.error(f"❌ Error updating subscription: {e}")
            return None
    
    def get_subscription(self, user_id):
        """Получение активной подписки пользователя"""
        try:
            with self.get_session() as session:
                subscription = session.query(UserSubscription).filter(
                    UserSubscription.user_id == user_id
                ).first()
                
                if subscription:
                    is_active = subscription.is_active
                    is_valid = subscription.expires_at > datetime.utcnow()
                    
                    logger.info(f"📊 Subscription check: user={user_id}, active={is_active}, valid={is_valid}, expires={subscription.expires_at}")
                    
                    if is_active and is_valid:
                        return subscription
                    else:
                        logger.warning(f"⚠️ Subscription expired or inactive: user={user_id}")
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting subscription: {e}")
            return None
    
    def save_conversation(self, user_id, role, content):
        """Сохранение сообщения в историю"""
        try:
            with self.get_session() as session:
                conversation = Conversation(
                    user_id=user_id,
                    role=role,
                    content=content
                )
                session.add(conversation)
                session.commit()
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
    
    def get_conversation_history(self, user_id, limit=10):
        """Получение истории разговора"""
        try:
            with self.get_session() as session:
                conversations = session.query(Conversation).filter(
                    Conversation.user_id == user_id
                ).order_by(Conversation.timestamp.desc()).limit(limit).all()
                
                return [
                    {"role": conv.role, "content": conv.content}
                    for conv in reversed(conversations)
                ]
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def get_message_count(self, user_id):
        """Получение количества отправленных сообщений"""
        try:
            with self.get_session() as session:
                user_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                return user_count.message_count if user_count else 0
                
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
            return 0
    
    def update_message_count(self, user_id, count):
        """Обновление счетчика сообщений"""
        try:
            with self.get_session() as session:
                user_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                if user_count:
                    user_count.message_count = count
                    user_count.last_updated = datetime.utcnow()
                else:
                    user_count = UserMessageCount(
                        user_id=user_id,
                        message_count=count
                    )
                    session.add(user_count)
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Error updating message count: {e}")
    
    def decrement_message_count(self, user_id):
        """Уменьшение счетчика сообщений на 1"""
        try:
            with self.get_session() as session:
                user_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                if user_count:
                    # Уменьшаем счетчик, но не ниже 0
                    new_count = max(0, user_count.message_count - 1)
                    user_count.message_count = new_count
                    user_count.last_updated = datetime.utcnow()
                    logger.info(f"📉 Message count DECREMENTED for user {user_id}: {user_count.message_count + 1} -> {new_count}")
                else:
                    # Если записи нет, создаем с нулевым счетчиком
                    user_count = UserMessageCount(
                        user_id=user_id,
                        message_count=0
                    )
                    session.add(user_count)
                    logger.info(f"📝 Created new message count record for user {user_id} with count=0")
                
                session.commit()
                return user_count.message_count if user_count else 0
                
        except Exception as e:
            logger.error(f"❌ Error decrementing message count: {e}")
            return 0
    
    def increment_message_count(self, user_id):
        """Увеличение счетчика сообщений на 1"""
        try:
            with self.get_session() as session:
                user_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                if user_count:
                    user_count.message_count += 1
                    user_count.last_updated = datetime.utcnow()
                    logger.info(f"📈 Message count INCREMENTED for user {user_id}: {user_count.message_count - 1} -> {user_count.message_count}")
                else:
                    user_count = UserMessageCount(
                        user_id=user_id,
                        message_count=1
                    )
                    session.add(user_count)
                    logger.info(f"📝 Created new message count record for user {user_id} with count=1")
                
                session.commit()
                return user_count.message_count
                
        except Exception as e:
            logger.error(f"❌ Error incrementing message count: {e}")
            return 0
    
    def reset_message_count(self, user_id):
        """Сброс счетчика сообщений до 0"""
        try:
            with self.get_session() as session:
                user_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                if user_count:
                    user_count.message_count = 0
                    user_count.last_updated = datetime.utcnow()
                    logger.info(f"🔄 Message count RESET for user {user_id}")
                else:
                    user_count = UserMessageCount(
                        user_id=user_id,
                        message_count=0
                    )
                    session.add(user_count)
                    logger.info(f"📝 Created new message count record for user {user_id} with count=0")
                
                session.commit()
                return 0
                
        except Exception as e:
            logger.error(f"❌ Error resetting message count: {e}")
            return 0
    
    def cleanup_expired_subscriptions(self):
        """Очистка истекших подписок"""
        try:
            with self.get_session() as session:
                expired_count = session.query(UserSubscription).filter(
                    UserSubscription.expires_at <= datetime.utcnow(),
                    UserSubscription.is_active == True
                ).update({"is_active": False})
                
                session.commit()
                logger.info(f"🧹 Cleaned up {expired_count} expired subscriptions")
                
        except Exception as e:
            logger.error(f"Error cleaning expired subscriptions: {e}")
    
    def debug_all_subscriptions(self):
        """Отладочная функция: показать все подписки"""
        try:
            with self.get_session() as session:
                subscriptions = session.query(UserSubscription).all()
                result = []
                for sub in subscriptions:
                    result.append({
                        "user_id": sub.user_id,
                        "plan_type": sub.plan_type,
                        "created_at": sub.created_at.isoformat(),
                        "expires_at": sub.expires_at.isoformat(),
                        "is_active": sub.is_active,
                        "is_valid": sub.expires_at > datetime.utcnow()
                    })
                return result
        except Exception as e:
            logger.error(f"Error getting all subscriptions: {e}")
            return []
    
    def get_user_stats(self, user_id):
        """Получение статистики пользователя"""
        try:
            with self.get_session() as session:
                subscription = session.query(UserSubscription).filter(
                    UserSubscription.user_id == user_id
                ).first()
                
                message_count = session.query(UserMessageCount).filter(
                    UserMessageCount.user_id == user_id
                ).first()
                
                return {
                    "has_subscription": subscription is not None,
                    "subscription_active": subscription.is_active if subscription else False,
                    "subscription_valid": subscription.expires_at > datetime.utcnow() if subscription else False,
                    "plan_type": subscription.plan_type if subscription else None,
                    "expires_at": subscription.expires_at if subscription else None,
                    "expires_in_days": (subscription.expires_at - datetime.utcnow()).days if subscription and subscription.expires_at else None,
                    "message_count": message_count.message_count if message_count else 0,
                    "last_updated": message_count.last_updated if message_count else None
                }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return None

# Глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()
