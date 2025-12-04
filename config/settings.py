"""
Конфигурация системы - ОБРАЗЕЦ
"""

import os
from pathlib import Path

# Базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
LOGS_DIR = BASE_DIR / 'logs'

# Создание директорий
for directory in [DATA_DIR, LOGS_DIR]:
    directory.mkdir(exist_ok=True)

# Telegram API (получить на my.telegram.org)
API_ID = 1234567  # ПРИМЕР - нужно заменить
API_HASH = 'abcdef1234567890abcdef1234567890'  # ПРИМЕР

# Администратор системы
ADMIN_CHAT_ID = 123456789  # ID чата с админом @fish_qe
ADMIN_USERNAME = 'fish_qe'

# Настройки базы данных
DATABASE = {
    'path': DATA_DIR / 'monitoring.db',
    'backup_dir': DATA_DIR / 'backups',
    'backup_interval_hours': 24
}

# Настройки безопасности
SECURITY = {
    'session_encryption_key': '',  # Генерируется при первом запуске
    'max_login_attempts': 3,
    'session_timeout_minutes': 60,
    'require_2fa': True
}

# Настройки мониторинга
MONITORING = {
    'check_interval_seconds': 1,
    'max_messages_per_minute': 100,
    'excluded_chats': [],  # ID чатов для исключения
    'keywords_filter': [],  # Ключевые слова для фильтрации
    'forward_media': True,
    'forward_edited': True,
    'forward_deleted': False  # Нельзя переслать удаленные
}

# Настройки веб-сервера
WEB_SERVER = {
    'host': '0.0.0.0',
    'port': 8080,
    'debug': False,
    'secret_key': 'change-this-in-production',
    'session_cookie_secure': True
}

# Настройки логирования
LOGGING = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': LOGS_DIR / 'monitoring.log',
    'max_size_mb': 10,
    'backup_count': 5
}

# Юридические настройки
LEGAL = {
    'require_consent_form': True,
    'consent_text': """
    Я даю согласие на мониторинг моих Telegram-чатов.
    Все данные будут обрабатываться в соответствии с политикой конфиденциальности.
    """,
    'data_retention_days': 30,
    'auto_delete_expired': True
}

# Экспериментальные функции (выключены по умолчанию)
EXPERIMENTAL = {
    'ai_analysis': False,
    'sentiment_analysis': False,
    'pattern_detection': False,
    'auto_categorization': False
}
