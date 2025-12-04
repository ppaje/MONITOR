"""
Обработчик сообщений - ОБРАЗЕЦ
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import json
import hashlib

from telethon import events
from telethon.tl import types
import aiofiles
import aiofiles.os

from config.settings import MONITORING, ADMIN_CHAT_ID
from core.database import DatabaseManager
from utils.helpers import format_message_for_admin, download_media

class MessageHandler:
    """Обработка и пересылка сообщений"""
    
    def __init__(self, owner_user_id: int):
        self.owner_user_id = owner_user_id
        self.db = DatabaseManager()
        self.logger = logging.getLogger(__name__)
        
        # Получаем настройки пользователя
        self.user_settings = self._get_user_settings()
    
    def _get_user_settings(self) -> Dict[str, Any]:
        """Получение настроек пользователя"""
        user = self.db.get_user_by_telegram_id(self.owner_user_id)
        if user and 'user_id' in user:
            return {
                'forward_media': bool(user.get('forward_media', True)),
                'forward_edited': bool(user.get('forward_edited', True)),
                'keywords_filter': json.loads(user.get('keywords_filter', '[]')),
                'excluded_chats': json.loads(user.get('excluded_chats', '[]')),
                'notification_enabled': bool(user.get('notification_enabled', True))
            }
        return MONITORING
    
    async def process_message(self, event: events.NewMessage.Event):
        """Обработка нового сообщения"""
        try:
            # Проверяем, нужно ли обрабатывать этот чат
            if not await self._should_process_chat(event.chat_id):
                return
            
            # Проверяем фильтр по ключевым словам
            if not await self._passes_keyword_filter(event):
                return
            
            # Сохраняем сообщение в БД
            message_data = await self._extract_message_data(event)
            db_message_id = self.db.save_message(message_data)
            
            # Пересылаем админу
            await self._forward_to_admin(event, message_data, db_message_id)
            
            # Обновляем чат
            await self._update_chat_info(event)
            
            self.logger.debug(f"Processed message {event.message.id} from chat {event.chat_id}")
            
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    async def process_edited_message(self, event: events.MessageEdited.Event):
        """Обработка отредактированного сообщения"""
        try:
            if not self.user_settings['forward_edited']:
                return
            
            # Проверяем, нужно ли обрабатывать этот чат
            if not await self._should_process_chat(event.chat_id):
                return
            
            # Извлекаем данные
            message_data = await self._extract_message_data(event)
            message_data['edit_date'] = datetime.now()
            
            # Сохраняем в БД
            db_message_id = self.db.save_message(message_data)
            
            # Пересылаем админу
            await self._forward_edited_to_admin(event, message_data)
            
            self.logger.debug(f"Processed edited message {event.message.id}")
            
        except Exception as e:
            self.logger.error(f"Error processing edited message: {e}")
    
    async def process_deleted_message(self, event: events.MessageDeleted.Event):
        """Обработка удаленного сообщения"""
        try:
            # Помечаем сообщение как удаленное в БД
            for msg_id in event.deleted_ids:
                self.db.mark_message_deleted(event.chat_id, msg_id)
            
            self.logger.debug(f"Processed deleted messages in chat {event.chat_id}")
            
        except Exception as e:
            self.logger.error(f"Error processing deleted message: {e}")
    
    async def _should_process_chat(self, chat_id: int) -> bool:
        """Проверка, нужно ли обрабатывать сообщения из этого чата"""
        # Проверяем исключенные чаты
        if chat_id in self.user_settings['excluded_chats']:
            return False
        
        # Проверяем тип чата (только личные и группы)
        # В реальной системе нужно получать информацию о чате
        return True
    
    async def _passes_keyword_filter(self, event) -> bool:
        """Проверка фильтра по ключевым словам"""
        keywords = self.user_settings['keywords_filter']
        
        if not keywords:
            return True
        
        message_text = event.message.text or ''
        message_text_lower = message_text.lower()
        
        for keyword in keywords:
            if keyword.lower() in message_text_lower:
                return True
        
        return False
    
    async def _extract_message_data(self, event) -> Dict[str, Any]:
        """Извлечение данных из сообщения"""
        sender = await event.get_sender()
        chat = await event.get_chat()
        
        # Базовые данные
        message_data = {
            'owner_user_id': self.owner_user_id,
            'message_id': event.message.id,
            'chat_id': event.chat_id,
            'sender_id': sender.id if sender else None,
            'date': event.message.date,
            'text': event.message.text,
            'raw': event.message.to_dict() if hasattr(event.message, 'to_dict') else {}
        }
        
        # Информация об отправителе
        if sender:
            message_data['sender_info'] = {
                'id': sender.id,
                'first_name': sender.first_name,
                'last_name': sender.last_name,
                'username': sender.username,
                'phone': getattr(sender, 'phone', None)
            }
        
        # Информация о чате
        message_data['chat_info'] = {
            'id': chat.id,
            'title': getattr(chat, 'title', None),
            'username': getattr(chat, 'username', None),
            'type': 'private' if isinstance(chat, types.User) else 'group'
        }
        
        # Обработка медиа
        if event.message.media:
            media_info = await self._extract_media_info(event.message.media)
            message_data.update(media_info)
            
            # Скачивание медиа (если включено)
            if self.user_settings['forward_media']:
                media_path = await download_media(event.message.media, self.owner_user_id)
                if media_path:
                    message_data['media_path'] = str(media_path)
        
        return message_data
    
    async def _extract_media_info(self, media) -> Dict[str, Any]:
        """Извлечение информации о медиа"""
        media_info = {
            'has_media': True,
            'media_type': media.__class__.__name__
        }
        
        try:
            if isinstance(media, types.MessageMediaPhoto):
                media_info.update({
                    'media_type': 'photo',
                    'photo_id': getattr(media.photo, 'id', None),
                    'size': getattr(media.photo, 'size', 0)
                })
                
            elif isinstance(media, types.MessageMediaDocument):
                document = media.document
                media_info.update({
                    'media_type': 'document',
                    'mime_type': document.mime_type,
                    'size': document.size,
                    'filename': next(
                        (attr.file_name for attr in document.attributes 
                         if isinstance(attr, types.DocumentAttributeFilename)),
                        None
                    )
                })
                
            elif isinstance(media, types.MessageMediaGeo):
                geo = media.geo
                media_info.update({
                    'media_type': 'geo',
                    'lat': geo.lat,
                    'long': geo.long
                })
                
            elif isinstance(media, types.MessageMediaContact):
                contact = media.contact
                media_info.update({
                    'media_type': 'contact',
                    'phone_number': contact.phone_number,
                    'first_name': contact.first_name,
                    'last_name': contact.last_name
                })
                
        except Exception as e:
            self.logger.warning(f"Error extracting media info: {e}")
        
        return media_info
    
    async def _forward_to_admin(self, event, message_data: Dict[str, Any], 
                               db_message_id: int):
        """Пересылка сообщения админу"""
        try:
            # Форматируем сообщение для админа
            formatted_message = format_message_for_admin(
                message_data, self.owner_user_id
            )
            
            # Нужно получить активный клиент для отправки
            # В реальной системе здесь будет логика получения клиента
            from core.session_manager import SessionManager
            session_manager = SessionManager()
            
            active_users = session_manager.get_active_users()
            if active_users:
                # Используем первую активную сессию для отправки
                client = session_manager.active_sessions[active_users[0]]
                
                # Отправляем текстовую часть
                await client.send_message(
                    ADMIN_CHAT_ID,
                    formatted_message,
                    parse_mode='html'
                )
                
                # Отправляем медиа (если есть и включено)
                if (self.user_settings['forward_media'] and 
                    'media_path' in message_data and 
                    message_data['media_path']):
                    
                    await client.send_file(
                        ADMIN_CHAT_ID,
                        message_data['media_path'],
                        caption=f"Медиа из чата с {message_data.get('sender_info', {}).get('first_name', 'Unknown')}"
                    )
                
                # Помечаем как пересланное
                self.db.mark_message_forwarded(event.message.id, db_message_id)
                
                self.logger.info(f"Forwarded message {event.message.id} to admin")
            
        except Exception as e:
            self.logger.error(f"Error forwarding to admin: {e}")
    
    async def _forward_edited_to_admin(self, event, message_data: Dict[str, Any]):
        """Пересылка отредактированного сообщения админу"""
        try:
            formatted_message = f"""
✏️ <b>ОТРЕДАКТИРОВАНО СООБЩЕНИЕ</b>
━━━━━━━━━━━━━━━━━━━━
👤 От: {message_data.get('sender_info', {}).get('first_name', 'Unknown')}
💬 Чат: {message_data.get('chat_info', {}).get('title', 'Private chat')}

📝 Новый текст:
{message_data.get('text', '[No text]')}

🕒 Оригинал: {message_data.get('date')}
✏️ Редакция: {message_data.get('edit_date')}
━━━━━━━━━━━━━━━━━━━━
"""
            
            # Аналогично основной пересылке
            from core.session_manager import SessionManager
            session_manager = SessionManager()
            
            active_users = session_manager.get_active_users()
            if active_users:
                client = session_manager.active_sessions[active_users[0]]
                
                await client.send_message(
                    ADMIN_CHAT_ID,
                    formatted_message,
                    parse_mode='html'
                )
                
                self.logger.info(f"Forwarded edited message {event.message.id} to admin")
            
        except Exception as e:
            self.logger.error(f"Error forwarding edited message: {e}")
    
    async def _update_chat_info(self, event):
        """Обновление информации о чате"""
        try:
            chat = await event.get_chat()
            
            chat_data = {
                'id': chat.id,
                'type': 'private' if isinstance(chat, types.User) else 'group',
                'title': getattr(chat, 'title', None),
                'username': getattr(chat, 'username', None),
                'last_message_date': event.message.date
            }
            
            self.db.add_or_update_chat(chat_data)
            
        except Exception as e:
            self.logger.warning(f"Error updating chat info: {e}")