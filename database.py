import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, BigInteger
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
    user_id = Column(BigInteger, unique=True, index=True, nullable=False)
    plan_type = Column(String(50), nullable=False)  # 'week' or 'month'
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    def __repr__(self):
        return f"<UserSubscription(user_id={self.user_id}, plan={self.plan_type}, expires={self.expires_at})>"

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<Conversation(user_id={self.user_id}, role={self.role}, content={self.content[:50]}...)"

class UserMessageCount(Base):
    __tablename__ = "user_message_counts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True, nullable=False)
    message_count = Column(Integer, default=0, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<UserMessageCount(user_id={self.user_id}, count={self.message_count})>"

# Создаем таблицы с force_recreate если нужно
def create_tables_with_retry():
    """Создание таблиц с возможностью пересоздания"""
    try:
        # Проверяем, существует ли таблица conversations с правильным типом
        connection = engine.connect()
        
        # Пытаемся создать таблицы
        Base.metadata.create_all(bind=engine)
        
        # Проверяем структуру таблицы conversations
        inspector = inspect(engine)
        if 'conversations' in inspector.get_table_names():
            columns = inspector.get_columns('conversations')
            user_id_col = next((col for col in columns if col['name'] == 'user_id'), None)
            if user_id_col and str(user_id_col['type']) == 'INTEGER':
                logger.warning("⚠️ Table 'conversations' has INTEGER user_id, dropping and recreating...")
                # Удаляем и пересоздаем таблицу
                Conversation.__table__.drop(engine)
                Base.metadata.create_all(bind=engine)
                logger.info("✅ Recreated 'conversations' table with BigInteger")
        
        connection.close()
        logger.info("✅ Database tables created/recreated successfully")
        
    except Exception as e:
        logger.error(f"❌ Error creating tables: {e}")
        # В случае ошибки пробуем создать заново
        try:
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Tables dropped and recreated successfully")
        except Exception as e2:
            logger.error(f"❌ Failed to recreate tables: {e2}")

try:
    from sqlalchemy import inspect
    create_tables_with_retry()
except ImportError:
    # Просто создаем таблицы если не можем импортировать inspect
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
                logger.info(f"🗑️ Deleted old subscription for user {user_id}")
            
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
            # Логируем данные для отладки
            logger.info(f"💾 Saving conversation: user_id={user_id} (type: {type(user_id)}), role={role}, content_length={len(content)}")
            
            conversation = Conversation(
                user_id=int(user_id),  # Убеждаемся что это int
                role=role,
                content=content
            )
            self.session.add(conversation)
            self.session.commit()
            logger.info(f"✅ Conversation saved for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Error saving conversation for user {user_id}: {e}")
            self.session.rollback()
    
    def get_conversation_history(self, user_id, limit=10):
        """Получение истории разговора"""
        try:
            conversations = self.session.query(Conversation).filter(
                Conversation.user_id == user_id
            ).order_by(Conversation.timestamp.desc()).limit(limit).all()
            
            history = [
                {"role": conv.role, "content": conv.content}
                for conv in reversed(conversations)
            ]
            logger.info(f"📜 Retrieved {len(history)} messages for user {user_id}")
            return history
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def get_message_count(self, user_id):
        """Получение количества отправленных сообщений"""
        try:
            user_count = self.session.query(UserMessageCount).filter(
                UserMessageCount.user_id == user_id
            ).first()
            
            if user_count:
                logger.info(f"📊 Message count for user {user_id}: {user_count.message_count}")
                return user_count.message_count
            else:
                logger.info(f"📊 No message count record for user {user_id}, returning 0")
                return 0
            
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
            return 0
    
    def update_message_count(self, user_id, count):
        """Обновление счетчика сообщений"""
        try:
            logger.info(f"🔄 Updating message count for user {user_id} to {count}")
            
            user_count = self.session.query(UserMessageCount).filter(
                UserMessageCount.user_id == user_id
            ).first()
            
            if user_count:
                user_count.message_count = count
                user_count.last_updated = datetime.utcnow()
                logger.info(f"📝 Updated existing count for user {user_id}")
            else:
                user_count = UserMessageCount(
                    user_id=int(user_id),  # Убеждаемся что это int
                    message_count=count
                )
                self.session.add(user_count)
                logger.info(f"📝 Created new count record for user {user_id}")
            
            self.session.commit()
            logger.info(f"✅ Successfully saved count {count} for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error updating message count for user {user_id}: {e}")
            self.session.rollback()
    
    def increment_message_count(self, user_id):
        """Увеличить счетчик сообщений на 1"""
        try:
            current_count = self.get_message_count(user_id)
            new_count = current_count + 1
            self.update_message_count(user_id, new_count)
            logger.info(f"➕ Incremented message count for user {user_id}: {current_count} -> {new_count}")
            return new_count
        except Exception as e:
            logger.error(f"Error incrementing message count: {e}")
            return current_count
    
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
    
    def fix_user_id_types(self):
        """Исправление типов user_id если они неправильные"""
        try:
            # Эта функция только для экстренного исправления
            logger.warning("⚠️ Attempting to fix user_id types...")
            
            # Проверяем структуру таблиц
            from sqlalchemy import text
            
            # Для PostgreSQL
            if 'postgresql' in DATABASE_URL:
                # Проверяем тип колонки user_id в conversations
                result = self.session.execute(text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'conversations' AND column_name = 'user_id'"
                )).fetchone()
                
                if result and result[1] == 'integer':
                    logger.warning("⚠️ conversations.user_id is INTEGER, converting to BIGINT")
                    # Конвертируем тип
                    self.session.execute(text(
                        "ALTER TABLE conversations ALTER COLUMN user_id TYPE BIGINT"
                    ))
                    self.session.commit()
                    logger.info("✅ Converted conversations.user_id to BIGINT")
            
            logger.info("✅ User ID type check completed")
            
        except Exception as e:
            logger.error(f"❌ Error fixing user_id types: {e}")
            self.session.rollback()

# Глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()

# При первом запуске проверяем и исправляем типы если нужно
try:
    db_manager.fix_user_id_types()
except Exception as e:
    logger.warning(f"Could not check user_id types: {e}")
