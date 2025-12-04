"""
Менеджер безопасности и шифрования - ОБРАЗЕЦ
"""

import base64
import hashlib
import secrets
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import json
import pickle
from typing import Any, Optional

class SecurityManager:
    """Управление шифрованием и безопасностью"""
    
    def __init__(self, master_key: Optional[str] = None):
        self.master_key = master_key or self.generate_master_key()
        self.session_keys = {}
        
    @staticmethod
    def generate_master_key() -> str:
        """Генерация мастер-ключа"""
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    
    def derive_key(self, salt: bytes, key_length: int = 32) -> bytes:
        """Создание производного ключа"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=key_length,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(self.master_key.encode()))
    
    def encrypt_data(self, data: Any, user_id: int) -> str:
        """Шифрование данных пользователя"""
        # Создаем уникальную соль для пользователя
        salt = hashlib.sha256(str(user_id).encode()).digest()[:16]
        
        # Получаем ключ для пользователя
        if user_id not in self.session_keys:
            self.session_keys[user_id] = Fernet(self.derive_key(salt))
        
        # Сериализуем данные
        if isinstance(data, (dict, list)):
            serialized = json.dumps(data).encode()
        elif isinstance(data, str):
            serialized = data.encode()
        else:
            serialized = pickle.dumps(data)
        
        # Шифруем
        encrypted = self.session_keys[user_id].encrypt(serialized)
        return base64.urlsafe_b64encode(encrypted).decode()
    
    def decrypt_data(self, encrypted_data: str, user_id: int) -> Any:
        """Дешифрование данных пользователя"""
        try:
            # Создаем соль
            salt = hashlib.sha256(str(user_id).encode()).digest()[:16]
            
            # Получаем ключ
            if user_id not in self.session_keys:
                self.session_keys[user_id] = Fernet(self.derive_key(salt))
            
            # Дешифруем
            encrypted = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self.session_keys[user_id].decrypt(encrypted)
            
            # Пытаемся десериализовать
            try:
                return json.loads(decrypted.decode())
            except:
                try:
                    return pickle.loads(decrypted)
                except:
                    return decrypted.decode()
                    
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")
    
    def hash_sensitive_data(self, data: str) -> str:
        """Хеширование конфиденциальных данных"""
        return hashlib.sha256(
            data.encode() + self.master_key.encode()
        ).hexdigest()
    
    def generate_session_token(self, user_id: int) -> str:
        """Генерация токена сессии"""
        raw_token = f"{user_id}:{secrets.token_hex(16)}:{int(time.time())}"
        return self.encrypt_data(raw_token, user_id)
    
    def verify_session_token(self, token: str, user_id: int) -> bool:
        """Проверка токена сессии"""
        try:
            decrypted = self.decrypt_data(token, user_id)
            parts = decrypted.split(':')
            return len(parts) == 3 and int(parts[0]) == user_id
        except:
            return False
