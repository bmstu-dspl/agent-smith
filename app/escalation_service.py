# app/escalation_service.py - с поддержкой прокси-режима

import logging
from typing import Dict, Optional, List
from aiogram import Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from datetime import datetime

logger = logging.getLogger(__name__)

class EscalationService:
    """Сервис для эскалации чата на менеджера"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.active_escalations: Dict[int, Dict] = {}  # user_id -> {manager_id, status, ...}
        self.manager_availability: Dict[int, bool] = {}
        logger.info(f"EscalationService created")
        
    def get_available_manager(self) -> Optional[int]:
        """Выбирает доступного менеджера"""
        from config import MANAGER_IDS
        
        if not MANAGER_IDS:
            return None
        
        available_managers = [
            mgr_id for mgr_id in MANAGER_IDS 
            if self.manager_availability.get(mgr_id, True)
        ]
        
        if available_managers:
            manager_loads = {}
            for mgr_id in available_managers:
                load = sum(1 for e in self.active_escalations.values() 
                          if e["manager_id"] == mgr_id and e["status"] == "active")
                manager_loads[mgr_id] = load
            
            if manager_loads:
                return min(manager_loads, key=manager_loads.get)
        
        return None
    
    async def escalate_to_manager(
        self, 
        user_message: Message, 
        reason: str = "Пользователь запросил помощь менеджера"
    ) -> bool:
        """Перекидываем диалог на менеджера"""
        user_id = user_message.from_user.id
        
        if user_id in self.active_escalations:
            await user_message.answer("Запрос уже передан менеджеру. Ожидайте ответа.")
            return False
        
        manager_id = self.get_available_manager()
        if manager_id is None:
            await user_message.answer("Сейчас нет доступных менеджеров. Попробуйте позже.")
            return False

        try:
            user_text = user_message.text or "Нет текста"
            user_name = user_message.from_user.full_name or "Неизвестно"
            
            manager_message = (
                f"НОВЫЙ ЗАПРОС ОТ ПОЛЬЗОВАТЕЛЯ\n\n"
                f"Пользователь: {user_name}\n"
                f"ID: {user_id}\n"
                f"Сообщение: {user_text}\n"
                f"Время: {user_message.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Все сообщения, которые вы напишете сюда, будут пересылаться пользователю."
            )
            
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Принять запрос",
                            callback_data=f"accept_escalation_{user_id}"
                        )
                    ]
                ]
            )
            
            await self.bot.send_message(
                chat_id=manager_id,
                text=manager_message,
                reply_markup=keyboard
            )
            
            self.active_escalations[user_id] = {
                "manager_id": manager_id,
                "status": "pending",
                "user_message_id": user_message.message_id,
                "user_chat_id": user_message.chat.id,
                "user_full_name": user_name,
                "reason": reason,
                "timestamp": user_message.date,
                "manager_chat_id": manager_id
            }
            
            await user_message.answer(
                "Ваш запрос передан менеджеру.\n"
                "Ожидайте ответа."
            )
            
            logger.info(f"Эскалация создана: user={user_id} -> manager={manager_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при эскалации: {e}", exc_info=True)
            await user_message.answer("Произошла ошибка.")
            return False
    
    async def accept_escalation(self, manager_id: int, user_id: int) -> bool:
        """Менеджер принимает запрос"""
        if user_id not in self.active_escalations:
            logger.warning(f"Эскалация для user {user_id} не найдена")
            return False
        
        escalation = self.active_escalations[user_id]
        if escalation["status"] != "pending":
            logger.warning(f"Эскалация для user {user_id} уже имеет статус {escalation['status']}")
            return False
        
        try:
            escalation["status"] = "active"
            escalation["manager_id"] = manager_id
            
            logger.info(f"Эскалация принята: user={user_id} -> manager={manager_id}")
            
            await self.bot.send_message(
                chat_id=manager_id,
                text=(
                    f"Вы приняли запрос от пользователя {escalation['user_full_name']}.\n\n"
                    f"Когда вопрос решен, используйте /close_escalation\n"
                    f"Для просмотра статуса используйте /manager_status"
                )
            )
            
            await self.bot.send_message(
                chat_id=escalation["user_chat_id"],
                text="Менеджер принял ваш запрос и скоро ответит."
            )
            
            self.manager_availability[manager_id] = False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при принятии эскалации: {e}", exc_info=True)
            return False
    
    async def forward_message_to_user(self, manager_message: Message) -> bool:
        """Пересылает сообщение от менеджера пользователю"""
        manager_id = manager_message.from_user.id
        
        user_id = None
        escalation = None
        for uid, esc in self.active_escalations.items():
            if esc["manager_id"] == manager_id and esc["status"] == "active":
                user_id = uid
                escalation = esc
                break
        
        if not user_id or not escalation:
            await manager_message.answer(
                "У вас нет активных запросов.\n"
                "Используйте /manager_status для просмотра."
            )
            return False
        
        try:
            await self.bot.send_message(
                chat_id=escalation["user_chat_id"],
                text=f"Менеджер:\n{manager_message.text}"
            )
            
            await manager_message.reply("Сообщение отправлено пользователю.")
            
            logger.info(f"Сообщение переслано: manager={manager_id} -> user={user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при пересылке: {e}")
            await manager_message.answer("Не удалось отправить сообщение.")
            return False
    
    async def forward_message_to_manager(self, user_message: Message) -> bool:
        """Пересылает сообщение от пользователя менеджеру"""
        user_id = user_message.from_user.id
        
        if user_id not in self.active_escalations:
            logger.warning(f"Пользователь {user_id} не в активных эскалациях")
            return False
        
        escalation = self.active_escalations[user_id]
        if escalation["status"] != "active":
            logger.warning(f"Эскалация для {user_id} не активна: {escalation['status']}")
            return False
        
        manager_id = escalation["manager_id"]
        
        try:
            await self.bot.send_message(
                chat_id=manager_id,
                text=f"Пользователь:\n{user_message.text}"
            )
            
            logger.info(f"Сообщение переслано: user={user_id} -> manager={manager_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при пересылке: {e}")
            return False
    
    async def close_escalation(self, user_id: int) -> bool:
        """Закрывает эскалацию"""
        if user_id in self.active_escalations:
            escalation = self.active_escalations[user_id]
            manager_id = escalation["manager_id"]
            
            self.manager_availability[manager_id] = True
            
            await self.bot.send_message(
                chat_id=manager_id,
                text=f"Эскалация для пользователя {user_id} закрыта."
            )
            
            del self.active_escalations[user_id]
            
            logger.info(f"Эскалация закрыта: user={user_id}, manager={manager_id}")
            return True
        return False
    
    async def get_manager_status(self, manager_id: int) -> str:
        """Получить статус для менеджера"""
        status_text = "Ваш статус:\n\n"
        
        is_available = self.manager_availability.get(manager_id, True)
        status = "Доступен" if is_available else "Занят"
        status_text += f"Статус: {status}\n\n"
        
        active_esc = []
        for uid, esc in self.active_escalations.items():
            if esc["manager_id"] == manager_id:
                if esc["status"] == "active":
                    active_esc.append(uid)
        
        if active_esc:
            status_text += f"Активные запросы: {len(active_esc)}\n"
            for uid in active_esc:
                status_text += f"Пользователь {uid}\n"
        else:
            status_text += "Нет активных запросов\n"
        
        total = len(self.active_escalations)
        pending = sum(1 for e in self.active_escalations.values() if e["status"] == "pending")
        
        status_text += f"Общая статистика:"
        #добавим позже 
        
        return status_text
