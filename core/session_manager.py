"""
Менеджер сессий Telegram - ОБРАЗЕЦ
"""

import asyncio
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime
import pickle
import base64

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl import types
import aiofiles

from config.settings import API_ID, API_HASH
from core.database import DatabaseManager
from core.security_layer import SecurityLayer

class SessionManager:
    """Управление сессиями пользователей"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.security = SecurityLayer()
        self.active_sessions: Dict[int, TelegramClient] = {}
        self.session_tasks: Dict[int, asyncio.Task] = {}
        self.logger = logging.getLogger(__name__)
    
    async def create_user_session(self, phone: str, phone_code_hash: str, 
                                 code: str) -> Optional[str]:
        """Создание новой сессии пользователя"""
        try:
            # Создаем временную сессию
            session = StringSession()
            client = TelegramClient(session, API_ID, API_HASH)
            
            await client.connect()
            
            # Авторизуемся
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
            
            # Получаем информацию о пользователе
            me = await client.get_me()
            
            # Сохраняем сессию
            session_string = session.save()
            
            # Шифруем данные сессии
            encrypted_session = self.security.encrypt_session(
                session_string, me.id
            )
            
            # Сохраняем в базу
            user_info = {
                'first_name': me.first_name,
                'last_name': me.last_name,
                'username': me.username,
                'phone': phone
            }
            
            self.db.add_user(me.id, phone, encrypted_session, user_info)
            
            await client.disconnect()
            
            self.logger.info(f"Created session for user {me.id} ({phone})")
            
            return session_string
            
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            return None
    
    async def start_user_monitoring(self, telegram_id: int) -> bool:
        """Запуск мониторинга для пользователя"""
        try:
            # Проверяем, не запущен ли уже мониторинг
            if telegram_id in self.active_sessions:
                self.logger.warning(f"Monitoring already running for user {telegram_id}")
                return True
            
            # Получаем данные пользователя
            user = self.db.get_user_by_telegram_id(telegram_id)
            if not user:
                self.logger.error(f"User {telegram_id} not found")
                return False
            
            # Дешифруем сессию
            session_string = self.security.decrypt_session(
                user['session_data_encrypted'], telegram_id
            )
            
            if not session_string:
                self.logger.error(f"Failed to decrypt session for user {telegram_id}")
                return False
            
            # Создаем клиент
            session = StringSession(session_string)
            client = TelegramClient(session, API_ID, API_HASH)
            
            # Настраиваем обработчики
            await self._setup_client_handlers(client, telegram_id)
            
            # Запускаем клиент
            await client.start()
            
            # Сохраняем в активных сессиях
            self.active_sessions[telegram_id] = client
            
            # Создаем задачу для мониторинга
            task = asyncio.create_task(
                self._monitoring_loop(client, telegram_id)
            )
            self.session_tasks[telegram_id] = task
            
            self.logger.info(f"Started monitoring for user {telegram_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start monitoring for {telegram_id}: {e}")
            return False
    
    async def _setup_client_handlers(self, client: TelegramClient, user_id: int):
        """Настройка обработчиков событий для клиента"""
        
        @client.on(events.NewMessage(incoming=True))
        async def new_message_handler(event):
            await self._handle_new_message(event, user_id)
        
        @client.on(events.MessageEdited(incoming=True))
        async def edited_message_handler(event):
            await self._handle_edited_message(event, user_id)
        
        @client.on(events.MessageDeleted(incoming=True))
        async def deleted_message_handler(event):
            await self._handle_deleted_message(event, user_id)
        
        @client.on(events.ChatAction())
        async def chat_action_handler(event):
            await self._handle_chat_action(event, user_id)
    
    async def _handle_new_message(self, event, user_id: int):
        """Обработка нового сообщения"""
        try:
            from core.message_handler import MessageHandler
            handler = MessageHandler(user_id)
            await handler.process_message(event)
            
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
    
    async def _handle_edited_message(self, event, user_id: int):
        """Обработка отредактированного сообщения"""
        try:
            from core.message_handler import MessageHandler
            handler = MessageHandler(user_id)
            await handler.process_edited_message(event)
            
        except Exception as e:
            self.logger.error(f"Error handling edited message: {e}")
    
    async def _handle_deleted_message(self, event, user_id: int):
        """Обработка удаленного сообщения"""
        try:
            from core.message_handler import MessageHandler
            handler = MessageHandler(user_id)
            await handler.process_deleted_message(event)
            
        except Exception as e:
            self.logger.error(f"Error handling deleted message: {e}")
    
    async def _handle_chat_action(self, event, user_id: int):
        """Обработка действий в чате"""
        try:
            # Логирование действий в чате
            action_type = str(event.action_message.action)
            self.logger.info(f"Chat action: {action_type} in chat {event.chat_id}")
            
        except Exception as e:
            self.logger.error(f"Error handling chat action: {e}")
    
    async def _monitoring_loop(self, client: TelegramClient, user_id: int):
        """Основной цикл мониторинга"""
        try:
            while True:
                try:
                    # Проверяем соединение
                    if not client.is_connected():
                        self.logger.warning(f"Client disconnected for user {user_id}, reconnecting...")
                        await client.connect()
                    
                    # Обновляем активность в БД
                    self.db.update_user_activity(user_id)
                    
                    # Пауза перед следующей проверкой
                    await asyncio.sleep(60)  # Каждую минуту
                    
                except asyncio.CancelledError:
                    self.logger.info(f"Monitoring loop cancelled for user {user_id}")
                    break
                    
                except Exception as e:
                    self.logger.error(f"Error in monitoring loop for user {user_id}: {e}")
                    await asyncio.sleep(30)  # Пауза при ошибке
        
        finally:
            # Очистка при завершении
            if user_id in self.active_sessions:
                del self.active_sessions[user_id]
            if user_id in self.session_tasks:
                del self.session_tasks[user_id]
    
    async def stop_user_monitoring(self, telegram_id: int) -> bool:
        """Остановка мониторинга для пользователя"""
        try:
            if telegram_id not in self.active_sessions:
                return True
            
            # Отменяем задачу мониторинга
            if telegram_id in self.session_tasks:
                self.session_tasks[telegram_id].cancel()
                try:
                    await self.session_tasks[telegram_id]
                except asyncio.CancelledError:
                    pass
                del self.session_tasks[telegram_id]
            
            # Отключаем клиент
            client = self.active_sessions[telegram_id]
            await client.disconnect()
            del self.active_sessions[telegram_id]
            
            self.logger.info(f"Stopped monitoring for user {telegram_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop monitoring for {telegram_id}: {e}")
            return False
    
    async def get_user_chats(self, telegram_id: int) -> List[Dict[str, Any]]:
        """Получение списка чатов пользователя"""
        try:
            if telegram_id not in self.active_sessions:
                self.logger.error(f"No active session for user {telegram_id}")
                return []
            
            client = self.active_sessions[telegram_id]
            
            chats = []
            async for dialog in client.iter_dialogs():
                chat = {
                    'id': dialog.id,
                    'title': dialog.title,
                    'type': 'private' if dialog.is_user else 'group',
                    'unread_count': dialog.unread_count,
                    'last_message_date': dialog.date,
                    'entity': str(dialog.entity)
                }
                chats.append(chat)
            
            return chats
            
        except Exception as e:
            self.logger.error(f"Failed to get chats for user {telegram_id}: {e}")
            return []
    
    async def send_message_as_user(self, telegram_id: int, chat_id: int, 
                                  text: str) -> bool:
        """Отправка сообщения от имени пользователя"""
        try:
            if telegram_id not in self.active_sessions:
                return False
            
            client = self.active_sessions[telegram_id]
            
            await client.send_message(chat_id, text)
            
            self.logger.info(f"Sent message from user {telegram_id} to chat {chat_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False
    
    def get_active_users(self) -> List[int]:
        """Получение списка активных пользователей"""
        return list(self.active_sessions.keys())
    
    async def cleanup(self):
        """Очистка всех сессий"""
        tasks = []
        for telegram_id in list(self.active_sessions.keys()):
            tasks.append(self.stop_user_monitoring(telegram_id))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self.logger.info("All sessions cleaned up")