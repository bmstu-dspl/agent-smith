import logging
from typing import Dict, Optional, List
from aiogram import Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class EscalationService:
    """Сервис для эскалации чата на менеджеров в группе"""
    
    def __init__(self, bot: Bot, manager_group_id: int):
        self.bot = bot
        self.manager_group_id = manager_group_id
        self.active_escalations: Dict[int, Dict] = {}  # user_id -> {thread_id, status, ...}
        self.user_threads: Dict[int, int] = {}  # user_id -> thread_id
        self.thread_users: Dict[int, int] = {}  # thread_id -> user_id
        self.is_initialized = bool(manager_group_id)
        
        if self.is_initialized:
            logger.info(f"EscalationService created with group {manager_group_id}")
        else:
            logger.warning("EscalationService created WITHOUT manager group ID!")
    
    async def escalate_to_managers(
        self, 
        user_message: Message, 
        reason: str = "Пользователь запросил помощь менеджера"
    ) -> bool:
        """Создает запрос в общем чате группы менеджеров"""
        
        if not self.is_initialized:
            logger.error("Escalation service not initialized")
            await user_message.answer("Сервис поддержки временно недоступен.")
            return False
        
        user_id = user_message.from_user.id
        
        # Проверяем, есть ли уже активная эскалация
        if user_id in self.active_escalations:
            if self.active_escalations[user_id]["status"] in ["pending", "active"]:
                await user_message.answer("У вас уже есть активный запрос к менеджеру.")
                return False
        
        try:
            user_name = user_message.from_user.full_name or "Неизвестно"
            user_text = user_message.text or "Нет текста"
            user_username = user_message.from_user.username or "нет username"
            
            logger.info(f"Создаем запрос в группе {self.manager_group_id} для пользователя {user_id}")
            
            # Отправляем сообщение в общий чат (general)
            group_message = await self.bot.send_message(
                chat_id=self.manager_group_id,
                text=(
                    f"НОВЫЙ ЗАПРОС ОТ ПОЛЬЗОВАТЕЛЯ\n\n"
                    f"Пользователь: {user_name}\n"
                    f"ID: {user_id}\n"
                    f"Username: @{user_username}\n"
                    f"Сообщение: {user_text}\n"
                    f"Время: {user_message.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"Для начала работы с запросом:\n"
                    f"Нажмите кнопку 'Принять запрос' для создания отдельного треда.\n\n"
                    f"После принятия запроса будет создан отдельный тред для общения с пользователем."
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Принять запрос",
                                callback_data=f"take_ticket_{user_id}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="Отклонить",
                                callback_data=f"reject_ticket_{user_id}"
                            )
                        ]
                    ]
                )
            )
            
            # Сохраняем информацию об эскалации (пока без треда)
            self.active_escalations[user_id] = {
                "status": "pending",
                "user_message_id": user_message.message_id,
                "user_chat_id": user_message.chat.id,
                "user_full_name": user_name,
                "user_username": user_username,
                "reason": reason,
                "timestamp": user_message.date,
                "group_message_id": group_message.message_id,
                "group_chat_id": self.manager_group_id,
                "thread_id": None,  # Тред будет создан позже
                "thread_name": None
            }
            
            await user_message.answer(
                "Ваш запрос передан менеджерам. Ожидайте ответа специалиста."
            )
            
            logger.info(f"Запрос создан: user={user_id}, group_message_id={group_message.message_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при создании запроса: {e}", exc_info=True)
            await user_message.answer(
                "Произошла ошибка при передаче запроса менеджерам. Попробуйте позже."
            )
            return False
    
    async def take_ticket(self, callback: CallbackQuery, user_id: int) -> bool:
        """Менеджер принимает запрос и создает отдельный тред"""
        if user_id not in self.active_escalations:
            await callback.answer("Запрос уже закрыт или не существует")
            return False
        
        escalation = self.active_escalations[user_id]
        if escalation["status"] != "pending":
            await callback.answer(f"Запрос уже {escalation['status']}")
            return False
        
        try:
            manager_name = callback.from_user.full_name
            manager_id = callback.from_user.id
            
            # Создаем название треда
            thread_name = f"Пользователь {escalation['user_full_name']} ({user_id})"
            
            logger.info(f"Создаем тред '{thread_name}' для пользователя {user_id}")
            
            # Шаг 1: Создаем тред
            try:
                topic = await self.bot.create_forum_topic(
                    chat_id=self.manager_group_id,
                    name=thread_name
                )
                thread_id = topic.message_thread_id
                logger.info(f"Тред создан: thread_id={thread_id}")
            except Exception as e:
                logger.error(f"Ошибка при создании треда: {e}")
                await callback.answer("Не удалось создать тред. Проверьте настройки группы.")
                return False
            
            # Шаг 2: Отправляем приветственное сообщение в тред
            await self.bot.send_message(
                chat_id=self.manager_group_id,
                message_thread_id=thread_id,
                text=(
                    f"Пользователь: {escalation['user_full_name']}\n"
                    f"ID: {user_id}\n"
                    f"Username: @{escalation['user_username']}\n\n"
                    f"Это тред для общения с пользователем.\n"
                    f"Все сообщения, которые вы напишете в этом треде, "
                    f"будут пересылаться пользователю.\n\n"
                    f"Для завершения диалога используйте /close_ticket"
                )
            )
            
            # Шаг 3: Обновляем исходное сообщение в general (УДАЛЯЕМ КНОПКИ)
            try:
                new_text = callback.message.text + f"\n\nПринял в работу: {manager_name}\n"
                new_text += f"Ссылка на тред: https://t.me/c/{str(self.manager_group_id).replace('-100', '')}/{thread_id}"
                await callback.message.edit_text(
                    text=new_text,
                    reply_markup=None
                )
                logger.info(f"Сообщение в general обновлено, кнопки удалены")
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения: {e}")
            
            # Шаг 4: Обновляем информацию об эскалации
            escalation["status"] = "active"
            escalation["manager_id"] = manager_id
            escalation["manager_name"] = manager_name
            escalation["thread_id"] = thread_id
            escalation["thread_name"] = thread_name
            
            # ВАЖНО: Сохраняем связи для поиска пользователя по thread_id
            self.user_threads[user_id] = thread_id
            self.thread_users[thread_id] = user_id
            
            logger.info(f"Связи обновлены: user_threads[{user_id}]={thread_id}, thread_users[{thread_id}]={user_id}")
            
            # Шаг 5: Уведомляем пользователя
            try:
                await self.bot.send_message(
                    chat_id=escalation["user_chat_id"],
                    text=f"Менеджер {manager_name} принял ваш запрос и создал отдельный чат для общения."
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя: {e}")
            
            await callback.answer("Запрос принят, тред создан")
            logger.info(f"Запрос принят: user={user_id}, manager={manager_id}, thread={thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при принятии запроса: {e}", exc_info=True)
            await callback.answer("Ошибка при принятии запроса")
            return False
    
    async def reject_ticket(self, callback: CallbackQuery, user_id: int) -> bool:
        """Менеджер отклоняет запрос"""
        if user_id not in self.active_escalations:
            await callback.answer("Запрос уже закрыт или не существует")
            return False
        
        escalation = self.active_escalations[user_id]
        if escalation["status"] != "pending":
            await callback.answer(f"Запрос уже {escalation['status']}")
            return False
        
        try:
            manager_name = callback.from_user.full_name
            
            # Обновляем сообщение в general (УДАЛЯЕМ КНОПКИ)
            try:
                new_text = callback.message.text + f"\n\nОтклонен: {manager_name}"
                await callback.message.edit_text(
                    text=new_text,
                    reply_markup=None
                )
                logger.info(f"Сообщение в general обновлено, кнопки удалены")
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения: {e}")
            
            # Закрываем запрос
            await self.close_escalation(user_id, f"отклонен менеджером {manager_name}")
            
            # Уведомляем пользователя
            try:
                await self.bot.send_message(
                    chat_id=escalation["user_chat_id"],
                    text="Ваш запрос был отклонен менеджером. Попробуйте позже."
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя: {e}")
            
            await callback.answer("Запрос отклонен")
            logger.info(f"Запрос отклонен: user={user_id}, manager={callback.from_user.id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отклонении запроса: {e}", exc_info=True)
            await callback.answer("Ошибка при отклонении запроса")
            return False
    
    async def forward_message_to_user(self, manager_message: Message) -> bool:
        """Пересылает сообщение от менеджера пользователю"""
        thread_id = manager_message.message_thread_id
        
        # Проверяем, не является ли сообщение от бота
        bot_id = (await self.bot.me()).id
        if manager_message.from_user and manager_message.from_user.id == bot_id:
            logger.info(f"Игнорируем сообщение от бота в треде {thread_id}")
            return False
        
        logger.info(f"Попытка пересылки сообщения из треда {thread_id}")
        
        if not thread_id:
            await manager_message.reply(
                "Это сообщение не в треде.\n"
                "Чтобы ответить пользователю, напишите сообщение в его треде."
            )
            return False
        
        # Ищем пользователя по thread_id
        user_id = self.thread_users.get(thread_id)
        
        logger.info(f"Поиск пользователя по thread_id {thread_id}: user_id={user_id}")
        logger.info(f"Текущие связи thread_users: {self.thread_users}")
        
        if not user_id:
            # Не отправляем сообщение об ошибке, если это сообщение от бота
            if manager_message.from_user and manager_message.from_user.id != bot_id:
                await manager_message.reply(
                    f"Тред {thread_id} не привязан к пользователю.\n"
                    f"Используйте /tickets_status для проверки активных запросов."
                )
            return False
        
        if user_id not in self.active_escalations:
            await manager_message.reply("Запрос уже закрыт.")
            return False
        
        escalation = self.active_escalations[user_id]
        if escalation["status"] != "active":
            await manager_message.reply(f"Запрос не активен (статус: {escalation['status']})")
            return False
        
        try:
            # Проверяем, не является ли сообщение командой
            if manager_message.text and manager_message.text.startswith('/'):
                return False
            
            # Пересылаем сообщение пользователю
            await self.bot.send_message(
                chat_id=escalation["user_chat_id"],
                text=f"Менеджер {manager_message.from_user.full_name}:\n{manager_message.text}"
            )
            
            logger.info(f"Сообщение переслано пользователю {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при пересылке: {e}")
            if manager_message.from_user and manager_message.from_user.id != bot_id:
                await manager_message.reply("Не удалось отправить сообщение пользователю.")
            return False
    
    async def forward_message_to_manager(self, user_message: Message) -> bool:
        """Пересылает сообщение от пользователя менеджеру в тред"""
        user_id = user_message.from_user.id
        
        if user_id not in self.active_escalations:
            logger.warning(f"Пользователь {user_id} не в активных эскалациях")
            return False
        
        escalation = self.active_escalations[user_id]
        if escalation["status"] != "active":
            logger.warning(f"Эскалация для {user_id} не активна: {escalation['status']}")
            return False
        
        thread_id = escalation.get("thread_id")
        if not thread_id:
            logger.warning(f"Нет треда для пользователя {user_id}")
            await user_message.answer(
                "Менеджер еще не создал тред для общения. Подождите, пока менеджер примет запрос."
            )
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.manager_group_id,
                message_thread_id=thread_id,
                text=f"{escalation['user_full_name']}:\n{user_message.text}"
            )
            
            logger.info(f"Сообщение переслано менеджеру: user={user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при пересылке: {e}")
            return False
    
    async def close_escalation(self, user_id: int, reason: str = "закрыт менеджером") -> bool:
        """Закрывает эскалацию"""
        if user_id not in self.active_escalations:
            return False
        
        escalation = self.active_escalations[user_id]
        thread_id = escalation.get("thread_id")
        
        try:
            # Если есть тред - отправляем сообщение о закрытии
            if thread_id:
                try:
                    await self.bot.send_message(
                        chat_id=self.manager_group_id,
                        message_thread_id=thread_id,
                        text=f"Диалог закрыт ({reason})"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение в тред: {e}")
            
            escalation["status"] = "closed"
            
            # Удаляем связи
            if user_id in self.user_threads:
                del self.user_threads[user_id]
            if thread_id and thread_id in self.thread_users:
                del self.thread_users[thread_id]
            
            logger.info(f"Эскалация закрыта: user={user_id}, причина: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при закрытии эскалации: {e}")
            return False
    
    async def get_manager_status(self) -> str:
        """Получить статус всех запросов"""
        if not self.active_escalations:
            return "Нет активных запросов."
        
        status_text = "Статус запросов:\n\n"
        
        pending = []
        active = []
        closed = []
        
        for user_id, esc in self.active_escalations.items():
            user_info = f"Пользователь: {esc['user_full_name']} (ID: {user_id})"
            thread_info = f"Тред: {esc.get('thread_name', 'Не создан') if esc.get('thread_id') else 'Не создан'}"
            
            if esc["status"] == "pending":
                pending.append(f"{user_info} - {thread_info}")
            elif esc["status"] == "active":
                manager = esc.get("manager_name", "неизвестен")
                active.append(f"{user_info} - менеджер: {manager} - {thread_info}")
            elif esc["status"] == "closed":
                closed.append(f"{user_info} - {thread_info}")
        
        if pending:
            status_text += "В ожидании (" + str(len(pending)) + "):\n" + "\n".join(f"• {p}" for p in pending) + "\n\n"
        if active:
            status_text += "Активные (" + str(len(active)) + "):\n" + "\n".join(f"• {a}" for a in active) + "\n\n"
        if closed:
            status_text += "Закрытые (" + str(len(closed)) + "):\n" + "\n".join(f"• {c}" for c in closed) + "\n\n"
        
        status_text += f"Всего: {len(self.active_escalations)} запросов"
        
        return status_text