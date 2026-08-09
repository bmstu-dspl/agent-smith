from __future__ import annotations

import asyncio
import json
import logging
from datetime import timezone
from typing import Any

from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, User


logger = logging.getLogger(__name__)


class EscalationService:
    """Creates manager tickets and persists all open routing state in Redis."""

    USER_KEY_PREFIX = "agent-smith:escalation:v1:user:"

    def __init__(self, bot: Bot, manager_group_id: int | None, *, redis: Any) -> None:
        self.bot = bot
        self.manager_group_id = manager_group_id
        self.redis = redis
        self.active_escalations: dict[int, dict[str, Any]] = {}
        self.user_threads: dict[int, int] = {}
        self.thread_users: dict[int, int] = {}
        self.is_initialized = bool(manager_group_id and redis)
        self._lock = asyncio.Lock()

        if self.is_initialized:
            logger.info("EscalationService created with group %s and Redis storage", manager_group_id)
        else:
            logger.warning("EscalationService created without manager group or Redis")

    def update_manager_group_id(self, manager_group_id: int | None) -> None:
        self.manager_group_id = manager_group_id
        self.is_initialized = bool(manager_group_id and self.redis)

    async def initialize(self) -> None:
        """Restore pending/active tickets and thread routing after a restart."""
        if not self.is_initialized:
            raise RuntimeError("manager group and Redis are required for escalation")

        restored = 0
        async for raw_key in self.redis.scan_iter(match=f"{self.USER_KEY_PREFIX}*"):
            raw_value = await self.redis.get(raw_key)
            if not raw_value:
                continue
            try:
                payload = json.loads(self._decode(raw_value))
                user_id = int(payload["user_id"])
                if payload.get("status") not in {"pending", "active"}:
                    continue
                if int(payload.get("group_chat_id") or 0) != int(self.manager_group_id):
                    logger.warning("Skipping escalation %s from another manager group", user_id)
                    continue
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                logger.exception("Invalid persisted escalation at key %r", raw_key)
                continue

            self.active_escalations[user_id] = payload
            thread_id = payload.get("thread_id")
            if thread_id:
                thread_id = int(thread_id)
                self.user_threads[user_id] = thread_id
                self.thread_users[thread_id] = user_id
            restored += 1

        logger.info("Restored %s active escalation(s) from Redis", restored)

    async def escalate_to_managers(
        self,
        user_message: Message,
        reason: str = "Пользователь запросил помощь менеджера",
        *,
        summary: str = "",
        history: list[dict[str, Any]] | None = None,
        notify_user: bool = True,
        user: User | None = None,
        user_text: str | None = None,
    ) -> bool:
        """Create a durable pending ticket and notify the manager group."""
        if not self.is_initialized:
            logger.error("Escalation service not initialized")
            if notify_user:
                await user_message.answer("Сервис поддержки временно недоступен.")
            return False

        actual_user = user or user_message.from_user
        if actual_user is None:
            logger.error("Cannot escalate a message without a Telegram user")
            return False
        user_id = actual_user.id

        async with self._lock:
            existing = self.active_escalations.get(user_id)
            if existing and existing.get("status") in {"pending", "active"}:
                if notify_user:
                    await user_message.answer("У вас уже есть активный запрос к менеджеру.")
                return True

            user_name = actual_user.full_name or "Неизвестно"
            username = actual_user.username or "нет username"
            visible_text = user_text or user_message.text or "Нет текста"
            context = self._format_context(summary=summary, history=history or [])

            group_text = (
                "НОВЫЙ ЗАПРОС ОТ ПОЛЬЗОВАТЕЛЯ\n\n"
                f"Пользователь: {user_name}\n"
                f"ID: {user_id}\n"
                f"Username: @{username}\n"
                f"Сообщение: {visible_text}\n"
                f"Причина: {reason}\n"
                f"Время: {user_message.date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{context}\n\n"
                "Нажмите «Принять запрос», чтобы создать отдельный тред."
            )

            try:
                group_message = await self.bot.send_message(
                    chat_id=self.manager_group_id,
                    text=self._truncate(group_text),
                    parse_mode=None,
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="Принять запрос", callback_data=f"take_ticket_{user_id}")],
                            [InlineKeyboardButton(text="Отклонить", callback_data=f"reject_ticket_{user_id}")],
                        ]
                    ),
                )
                escalation = {
                    "user_id": user_id,
                    "status": "pending",
                    "user_message_id": user_message.message_id,
                    "user_chat_id": user_message.chat.id,
                    "user_full_name": user_name,
                    "user_username": username,
                    "reason": reason,
                    "summary": summary,
                    "timestamp": user_message.date.astimezone(timezone.utc).isoformat(),
                    "group_message_id": group_message.message_id,
                    "group_chat_id": self.manager_group_id,
                    "thread_id": None,
                    "thread_name": None,
                }
                self.active_escalations[user_id] = escalation
                await self._persist(user_id)
            except Exception:
                # Never leave a process-local ticket that Redis did not accept:
                # after a restart it would disappear, while retries would be
                # incorrectly treated as an already active escalation.
                self.active_escalations.pop(user_id, None)
                logger.exception("Failed to create escalation for user %s", user_id)
                if notify_user:
                    await user_message.answer(
                        "Произошла ошибка при передаче запроса менеджерам. Попробуйте позже."
                    )
                return False

        if notify_user:
            await user_message.answer("Ваш запрос передан менеджерам. Ожидайте ответа специалиста.")
        logger.info("Escalation created: user=%s, group_message_id=%s", user_id, group_message.message_id)
        return True

    async def take_ticket(self, callback: CallbackQuery, user_id: int) -> bool:
        async with self._lock:
            escalation = self.active_escalations.get(user_id)
            if not escalation:
                await callback.answer("Запрос уже закрыт или не существует")
                return False
            if escalation["status"] != "pending":
                await callback.answer(f"Запрос уже {escalation['status']}")
                return False

            manager_name = callback.from_user.full_name
            manager_id = callback.from_user.id
            thread_name = f"Пользователь {escalation['user_full_name']} ({user_id})"
            try:
                topic = await self.bot.create_forum_topic(chat_id=self.manager_group_id, name=thread_name)
                thread_id = topic.message_thread_id
                await self.bot.send_message(
                    chat_id=self.manager_group_id,
                    message_thread_id=thread_id,
                    parse_mode=None,
                    text=(
                        f"Пользователь: {escalation['user_full_name']}\n"
                        f"ID: {user_id}\n"
                        f"Username: @{escalation['user_username']}\n\n"
                        "Все сообщения в этом треде пересылаются пользователю.\n"
                        "Для завершения диалога используйте /close_ticket"
                    ),
                )

                escalation.update(
                    status="active",
                    manager_id=manager_id,
                    manager_name=manager_name,
                    thread_id=thread_id,
                    thread_name=thread_name,
                )
                self.user_threads[user_id] = thread_id
                self.thread_users[thread_id] = user_id
                await self._persist(user_id)

                try:
                    current_text = callback.message.text or "Запрос пользователя"
                    thread_link = f"https://t.me/c/{str(self.manager_group_id).replace('-100', '')}/{thread_id}"
                    await callback.message.edit_text(
                        text=f"{current_text}\n\nПринял в работу: {manager_name}\nСсылка на тред: {thread_link}",
                        parse_mode=None,
                        reply_markup=None,
                    )
                except Exception:
                    logger.exception("Failed to update manager-group ticket message")

                try:
                    await self.bot.send_message(
                        chat_id=escalation["user_chat_id"],
                        text=f"Менеджер {manager_name} принял ваш запрос и подключился к диалогу.",
                        parse_mode=None,
                    )
                except Exception:
                    logger.warning("Could not notify user %s that ticket was accepted", user_id, exc_info=True)
                await callback.answer("Запрос принят, тред создан")
                logger.info("Escalation accepted: user=%s manager=%s thread=%s", user_id, manager_id, thread_id)
                return True
            except Exception:
                logger.exception("Failed to accept escalation for user %s", user_id)
                await callback.answer("Не удалось принять запрос. Проверьте настройки группы.")
                return False

    async def reject_ticket(self, callback: CallbackQuery, user_id: int) -> bool:
        escalation = self.active_escalations.get(user_id)
        if not escalation:
            await callback.answer("Запрос уже закрыт или не существует")
            return False
        if escalation["status"] != "pending":
            await callback.answer(f"Запрос уже {escalation['status']}")
            return False

        manager_name = callback.from_user.full_name
        try:
            current_text = callback.message.text or "Запрос пользователя"
            await callback.message.edit_text(
                text=f"{current_text}\n\nОтклонен: {manager_name}",
                parse_mode=None,
                reply_markup=None,
            )
        except Exception:
            logger.exception("Failed to update rejected ticket message")

        await self.close_escalation(user_id, f"отклонен менеджером {manager_name}")
        try:
            await self.bot.send_message(
                chat_id=escalation["user_chat_id"],
                text="Ваш запрос был отклонен менеджером. Попробуйте позже.",
                parse_mode=None,
            )
        except Exception:
            logger.warning("Could not notify user %s that ticket was rejected", user_id, exc_info=True)
        await callback.answer("Запрос отклонен")
        return True

    async def forward_message_to_user(self, manager_message: Message) -> bool:
        thread_id = manager_message.message_thread_id
        bot_id = (await self.bot.me()).id
        if manager_message.from_user and manager_message.from_user.id == bot_id:
            return False
        if not thread_id:
            await manager_message.reply("Ответьте пользователю внутри его треда.")
            return False

        user_id = self.thread_users.get(thread_id)
        escalation = self.active_escalations.get(user_id) if user_id else None
        if not escalation or escalation.get("status") != "active":
            await manager_message.reply(f"Тред {thread_id} не привязан к активному запросу.")
            return False
        if manager_message.text and manager_message.text.startswith("/"):
            return False

        try:
            await self.bot.send_message(
                chat_id=escalation["user_chat_id"],
                text=f"Менеджер {manager_message.from_user.full_name}:\n{manager_message.text or ''}",
                parse_mode=None,
            )
            return True
        except Exception:
            logger.exception("Failed to forward manager message for thread %s", thread_id)
            await manager_message.reply("Не удалось отправить сообщение пользователю.")
            return False

    async def forward_message_to_manager(self, user_message: Message) -> bool:
        user_id = user_message.from_user.id
        escalation = self.active_escalations.get(user_id)
        if not escalation or escalation.get("status") != "active":
            return False
        thread_id = escalation.get("thread_id")
        if not thread_id:
            await user_message.answer("Менеджер еще не создал тред. Подождите принятия запроса.")
            return False
        try:
            await self.bot.send_message(
                chat_id=self.manager_group_id,
                message_thread_id=thread_id,
                text=f"{escalation['user_full_name']}:\n{user_message.text or ''}",
                parse_mode=None,
            )
            return True
        except Exception:
            logger.exception("Failed to forward user %s message", user_id)
            return False

    async def close_escalation(self, user_id: int, reason: str = "закрыт менеджером") -> bool:
        escalation = self.active_escalations.get(user_id)
        if not escalation:
            return False
        thread_id = escalation.get("thread_id")
        if thread_id:
            try:
                await self.bot.send_message(
                    chat_id=self.manager_group_id,
                    message_thread_id=thread_id,
                    text=f"Диалог закрыт ({reason})",
                    parse_mode=None,
                )
            except Exception:
                logger.warning("Could not post closure to thread %s", thread_id, exc_info=True)

        self.active_escalations.pop(user_id, None)
        self.user_threads.pop(user_id, None)
        if thread_id:
            self.thread_users.pop(int(thread_id), None)
        await self.redis.delete(self._user_key(user_id))
        logger.info("Escalation closed: user=%s reason=%s", user_id, reason)
        return True

    async def get_manager_status(self) -> str:
        if not self.active_escalations:
            return "Нет активных запросов."
        pending: list[str] = []
        active: list[str] = []
        for user_id, escalation in self.active_escalations.items():
            user = f"Пользователь: {escalation['user_full_name']} (ID: {user_id})"
            if escalation["status"] == "pending":
                pending.append(user)
            elif escalation["status"] == "active":
                active.append(f"{user} — менеджер: {escalation.get('manager_name', 'неизвестен')}")
        parts = []
        if pending:
            parts.append(f"В ожидании ({len(pending)}):\n" + "\n".join(f"• {item}" for item in pending))
        if active:
            parts.append(f"Активные ({len(active)}):\n" + "\n".join(f"• {item}" for item in active))
        parts.append(f"Всего: {len(self.active_escalations)} запросов")
        return "\n\n".join(parts)

    async def _persist(self, user_id: int) -> None:
        payload = self.active_escalations[user_id]
        await self.redis.set(
            self._user_key(user_id),
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    def _user_key(self, user_id: int) -> str:
        return f"{self.USER_KEY_PREFIX}{user_id}"

    @staticmethod
    def _decode(value: Any) -> str:
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    @staticmethod
    def _truncate(value: str, limit: int = 3900) -> str:
        return value if len(value) <= limit else value[: limit - 1] + "…"

    @staticmethod
    def _format_context(*, summary: str, history: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        if summary.strip():
            parts.append(f"\nКраткое резюме:\n{summary.strip()}")
        if history:
            labels = {"user": "Пользователь", "assistant": "Бот"}
            lines = []
            for item in history[-8:]:
                role = labels.get(str(item.get("role")), str(item.get("role") or "Сообщение"))
                content = " ".join(str(item.get("content") or "").split())
                if content:
                    lines.append(f"{role}: {content[:500]}")
            if lines:
                parts.append("\nПоследние сообщения:\n" + "\n".join(lines))
        return "".join(parts)
