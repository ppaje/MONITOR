"""
Менеджер базы данных - ОБРАЗЕЦ
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import threading
from contextlib import contextmanager

from config.settings import DATABASE

class DatabaseManager:
    """Управление базой данных системы"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.db_path = DATABASE['path']
        self.backup_dir = DATABASE['backup_dir']
        self.backup_dir.mkdir(exist_ok=True)
        
        self._init_database()
        self._initialized = True
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для подключения к БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_database(self):
        """Инициализация структуры базы данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    phone_hash TEXT UNIQUE,
                    phone TEXT,
                    session_data_encrypted TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    consent_given BOOLEAN DEFAULT 0,
                    consent_date TIMESTAMP,
                    metadata TEXT DEFAULT '{}'
                )
            ''')
            
            # Таблица чатов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_chat_id INTEGER UNIQUE NOT NULL,
                    chat_type TEXT CHECK(chat_type IN ('private', 'group', 'channel', 'supergroup')),
                    title TEXT,
                    username TEXT,
                    participant_count INTEGER DEFAULT 1,
                    owner_user_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_message_date TIMESTAMP,
                    is_monitored BOOLEAN DEFAULT 1,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (owner_user_id) REFERENCES users(id)
                )
            ''')
            
            # Таблица сообщений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_message_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    sender_user_id INTEGER,
                    message_date TIMESTAMP NOT NULL,
                    edit_date TIMESTAMP,
                    message_text TEXT,
                    media_type TEXT,
                    media_path TEXT,
                    forwarded_to_admin BOOLEAN DEFAULT 0,
                    forward_date TIMESTAMP,
                    is_deleted BOOLEAN DEFAULT 0,
                    delete_date TIMESTAMP,
                    raw_data TEXT,  # JSON с полными данными
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES chats(id),
                    FOREIGN KEY (sender_user_id) REFERENCES users(id),
                    UNIQUE(telegram_message_id, chat_id)
                )
            ''')
            
            # Таблица сессий авторизации
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_token TEXT UNIQUE,
                    phone_hash TEXT NOT NULL,
                    phone_code_hash TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_verified BOOLEAN DEFAULT 0,
                    verified_at TIMESTAMP,
                    user_id INTEGER,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Таблица настроек пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    forward_media BOOLEAN DEFAULT 1,
                    forward_edited BOOLEAN DEFAULT 1,
                    keywords_filter TEXT DEFAULT '[]',
                    excluded_chats TEXT DEFAULT '[]',
                    notification_enabled BOOLEAN DEFAULT 1,
                    auto_delete_days INTEGER DEFAULT 30,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Таблица логов действий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS action_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action_type TEXT NOT NULL,
                    target_id INTEGER,
                    target_type TEXT,
                    details TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            
            # Создание индексов для производительности
            indexes = [
                'CREATE INDEX IF NOT EXISTS idx_messages_chat_date ON messages(chat_id, message_date)',
                'CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_user_id, message_date)',
                'CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)',
                'CREATE INDEX IF NOT EXISTS idx_chats_telegram_id ON chats(telegram_chat_id)',
                'CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_sessions(session_token)',
                'CREATE INDEX IF NOT EXISTS idx_logs_user_action ON action_logs(user_id, action_type)'
            ]
            
            for index_sql in indexes:
                cursor.execute(index_sql)
    
    # Методы работы с пользователями
    def add_user(self, telegram_id: int, phone: str, session_data: str, 
                 user_info: Dict[str, Any]) -> int:
        """Добавление нового пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (telegram_id, phone, phone_hash, session_data_encrypted,
                 first_name, last_name, username, last_active, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                telegram_id,
                phone,
                self._hash_phone(phone),
                session_data,
                user_info.get('first_name'),
                user_info.get('last_name'),
                user_info.get('username'),
                datetime.now(),
                1
            ))
            
            user_id = cursor.lastrowid
            
            # Добавляем настройки по умолчанию
            cursor.execute('''
                INSERT OR REPLACE INTO user_settings (user_id)
                VALUES (?)
            ''', (user_id,))
            
            # Логируем действие
            self.log_action(
                user_id, 'USER_ADDED', 
                target_id=telegram_id,
                details=json.dumps({'phone': self._mask_phone(phone)})
            )
            
            return user_id
    
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Получение пользователя по Telegram ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.*, us.* 
                FROM users u
                LEFT JOIN user_settings us ON u.id = us.user_id
                WHERE u.telegram_id = ? AND u.is_active = 1
            ''', (telegram_id,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_user_activity(self, telegram_id: int):
        """Обновление времени последней активности"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET last_active = CURRENT_TIMESTAMP 
                WHERE telegram_id = ?
            ''', (telegram_id,))
    
    # Методы работы с сообщениями
    def save_message(self, message_data: Dict[str, Any]) -> int:
        """Сохранение сообщения в БД"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Проверяем, существует ли уже сообщение
            cursor.execute('''
                SELECT id FROM messages 
                WHERE telegram_message_id = ? AND chat_id = ?
            ''', (message_data['message_id'], message_data['chat_id']))
            
            existing = cursor.fetchone()
            
            if existing:
                # Обновляем существующее сообщение
                cursor.execute('''
                    UPDATE messages 
                    SET message_text = ?, edit_date = ?, 
                        forwarded_to_admin = ?, forward_date = ?,
                        raw_data = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (
                    message_data.get('text'),
                    message_data.get('edit_date'),
                    message_data.get('forwarded', 0),
                    message_data.get('forward_date'),
                    json.dumps(message_data),
                    existing['id']
                ))
                return existing['id']
            else:
                # Добавляем новое сообщение
                cursor.execute('''
                    INSERT INTO messages 
                    (telegram_message_id, chat_id, sender_user_id, 
                     message_date, message_text, media_type, 
                     media_path, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    message_data['message_id'],
                    message_data['chat_id'],
                    message_data.get('sender_id'),
                    message_data['date'],
                    message_data.get('text'),
                    message_data.get('media_type'),
                    message_data.get('media_path'),
                    json.dumps(message_data)
                ))
                return cursor.lastrowid
    
    def mark_message_forwarded(self, message_id: int, db_message_id: int):
        """Отметка сообщения как пересланного"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE messages 
                SET forwarded_to_admin = 1, forward_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (db_message_id,))
    
    # Методы работы с чатами
    def add_or_update_chat(self, chat_data: Dict[str, Any]) -> int:
        """Добавление или обновление чата"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO chats 
                (telegram_chat_id, chat_type, title, username, 
                 participant_count, last_message_date, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                chat_data['id'],
                chat_data.get('type', 'private'),
                chat_data.get('title'),
                chat_data.get('username'),
                chat_data.get('participant_count', 1),
                chat_data.get('last_message_date', datetime.now()),
                json.dumps(chat_data.get('metadata', {}))
            ))
            
            return cursor.lastrowid
    
    # Методы авторизации
    def create_auth_session(self, phone_hash: str, phone_code_hash: str, 
                           expires_minutes: int = 10) -> str:
        """Создание сессии авторизации"""
        import secrets
        session_token = secrets.token_urlsafe(32)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            expires_at = datetime.now() + timedelta(minutes=expires_minutes)
            
            cursor.execute('''
                INSERT INTO auth_sessions 
                (session_token, phone_hash, phone_code_hash, expires_at)
                VALUES (?, ?, ?, ?)
            ''', (session_token, phone_hash, phone_code_hash, expires_at))
            
            return session_token
    
    def verify_auth_session(self, session_token: str, user_id: int) -> bool:
        """Верификация сессии авторизации"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE auth_sessions 
                SET is_verified = 1, verified_at = CURRENT_TIMESTAMP, user_id = ?
                WHERE session_token = ? AND expires_at > CURRENT_TIMESTAMP
                AND is_verified = 0
            ''', (user_id, session_token))
            
            return cursor.rowcount > 0
    
    # Методы логирования
    def log_action(self, user_id: Optional[int], action_type: str,
                   target_id: Optional[int] = None, 
                   target_type: Optional[str] = None,
                   details: Optional[str] = None,
                   ip_address: Optional[str] = None,
                   user_agent: Optional[str] = None):
        """Логирование действия"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO action_logs 
                (user_id, action_type, target_id, target_type, 
                 details, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, action_type, target_id, target_type,
                details, ip_address, user_agent
            ))
    
    # Вспомогательные методы
    @staticmethod
    def _hash_phone(phone: str) -> str:
        """Хеширование номера телефона"""
        import hashlib
        return hashlib.sha256(phone.encode()).hexdigest()
    
    @staticmethod
    def _mask_phone(phone: str) -> str:
        """Маскирование номера телефона для логов"""
        if len(phone) > 4:
            return phone[:2] + '*' * (len(phone) - 4) + phone[-2:]
        return phone
    
    def cleanup_expired_data(self):
        """Очистка устаревших данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Удаляем просроченные сессии авторизации
            cursor.execute('''
                DELETE FROM auth_sessions 
                WHERE expires_at < datetime('now', '-1 day')
            ''')
            
            # Удаляем старые логи (старше 90 дней)
            cursor.execute('''
                DELETE FROM action_logs 
                WHERE created_at < datetime('now', '-90 days')
            ''')
            
            # Деактивируем неактивных пользователей (30 дней неактивности)
            cursor.execute('''
                UPDATE users 
                SET is_active = 0 
                WHERE last_active < datetime('now', '-30 days')
                AND is_active = 1
            ''')
    
    def create_backup(self) -> Path:
        """Создание резервной копии базы данных"""
        backup_path = self.backup_dir / f"backup_{datetime.now():%Y%m%d_%H%M%S}.db"
        
        import shutil
        shutil.copy2(self.db_path, backup_path)
        
        # Удаляем старые бэкапы (оставляем последние 10)
        backups = sorted(self.backup_dir.glob("backup_*.db"))
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                old_backup.unlink()
        
        return backup_path
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики системы"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Количество пользователей
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_active = 1')
            stats['active_users'] = cursor.fetchone()['count']
            
            # Количество сообщений
            cursor.execute('SELECT COUNT(*) as count FROM messages')
            stats['total_messages'] = cursor.fetchone()['count']
            
            # Количество пересланных сообщений
            cursor.execute('SELECT COUNT(*) as count FROM messages WHERE forwarded_to_admin = 1')
            stats['forwarded_messages'] = cursor.fetchone()['count']
            
            # Количество чатов
            cursor.execute('SELECT COUNT(*) as count FROM chats WHERE is_monitored = 1')
            stats['monitored_chats'] = cursor.fetchone()['count']
            
            # Последняя активность
            cursor.execute('SELECT MAX(last_active) as last FROM users')
            stats['last_activity'] = cursor.fetchone()['last']
            
            return stats