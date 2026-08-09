from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot, Router
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)


logger = logging.getLogger(__name__)
BOT_COMMAND_FLAG = "bot_command"


@dataclass(frozen=True, slots=True)
class RegisteredCommand:
    command: str
    description: str
    scope: str


def collect_bot_commands(router: Router) -> list[RegisteredCommand]:
    """Collect menu metadata from handlers, including nested routers."""
    commands: list[RegisteredCommand] = []
    for handler in router.message.handlers:
        metadata = handler.flags.get(BOT_COMMAND_FLAG)
        if not isinstance(metadata, dict):
            continue
        commands.append(
            RegisteredCommand(
                command=str(metadata["command"]),
                description=str(metadata["description"]),
                scope=str(metadata["scope"]),
            )
        )
    for child in router.sub_routers:
        commands.extend(collect_bot_commands(child))
    return commands


async def register_bot_commands(bot: Bot, router: Router, manager_group_id: int | None) -> None:
    """Publish command menus for private chats and the configured manager group."""
    collected = collect_bot_commands(router)
    private_commands = [
        BotCommand(command=item.command, description=item.description)
        for item in collected
        if item.scope == "private"
    ]
    manager_commands = [
        BotCommand(command=item.command, description=item.description)
        for item in collected
        if item.scope == "manager_group"
    ]

    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.set_my_commands(
        commands=private_commands,
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
    if manager_group_id:
        await bot.set_my_commands(
            commands=manager_commands,
            scope=BotCommandScopeChat(chat_id=manager_group_id),
        )

    logger.info(
        "Registered Telegram commands: private=%s manager_group=%s group_id=%s",
        [item.command for item in private_commands],
        [item.command for item in manager_commands],
        manager_group_id,
    )
