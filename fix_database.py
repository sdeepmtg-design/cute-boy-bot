#!/usr/bin/env python3
"""
Скрипт для исправления базы данных - изменение типа всех user_id на BIGINT
"""
import os
import sys
sys.path.append('.')

from database import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_database():
    """Исправляет типы данных в базе данных"""
    connection = engine.connect()
    
    try:
        # Определяем тип СУБД
        db_url = str(engine.url)
        
        if 'postgresql' in db_url:
            logger.info("🔧 Fixing PostgreSQL database...")
            
            # Таблицы для исправления
            tables = [
                'user_subscriptions',
                'conversations', 
                'user_message_counts'
            ]
            
            for table in tables:
                # Проверяем существует ли таблица
                result = connection.execute(text(
                    f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')"
                )).fetchone()
                
                if result and result[0]:
                    # Проверяем тип колонки user_id
                    result = connection.execute(text(
                        f"SELECT data_type FROM information_schema.columns "
                        f"WHERE table_name = '{table}' AND column_name = 'user_id'"
                    )).fetchone()
                    
                    if result:
                        current_type = result[0]
                        if current_type == 'integer':
                            logger.warning(f"⚠️ {table}.user_id is INTEGER, converting to BIGINT")
                            try:
                                connection.execute(text(
                                    f"ALTER TABLE {table} ALTER COLUMN user_id TYPE BIGINT"
                                ))
                                logger.info(f"✅ Converted {table}.user_id to BIGINT")
                            except Exception as e:
                                logger.error(f"❌ Failed to convert {table}.user_id: {e}")
                        else:
                            logger.info(f"✅ {table}.user_id is already {current_type}")
                    else:
                        logger.warning(f"⚠️ Table {table} exists but has no user_id column")
                else:
                    logger.warning(f"⚠️ Table {table} does not exist")
            
            logger.info("✅ PostgreSQL database fix completed")
            
        elif 'sqlite' in db_url:
            logger.info("🔧 SQLite database - recreating tables...")
            # Для SQLite нужно пересоздать таблицы
            from database import Base
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            logger.info("✅ SQLite tables recreated with correct types")
            
        else:
            logger.warning(f"⚠️ Unknown database type: {db_url}")
            
    except Exception as e:
        logger.error(f"❌ Error fixing database: {e}")
    finally:
        connection.close()

if __name__ == '__main__':
    fix_database()
    print("\n✅ Database fix script completed!")
    print("📊 Now test your bot with /start command")
