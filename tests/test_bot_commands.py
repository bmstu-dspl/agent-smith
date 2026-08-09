from unittest.mock import AsyncMock

import pytest
from aiogram.types import (
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from app.bot_commands import collect_bot_commands, register_bot_commands
from app.handlers import router


def test_command_metadata_is_collected_from_handlers() -> None:
    commands = collect_bot_commands(router)

    assert [(item.command, item.description, item.scope) for item in commands] == [
        ("new", "Начать новый диалог", "private"),
        ("close_ticket", "Закрыть обращение гостя", "manager_group"),
    ]


@pytest.mark.asyncio
async def test_commands_are_registered_for_private_and_manager_scopes() -> None:
    bot = AsyncMock()

    await register_bot_commands(bot, router, -1004489968828)

    delete_scopes = [call.kwargs["scope"] for call in bot.delete_my_commands.await_args_list]
    assert any(isinstance(scope, BotCommandScopeDefault) for scope in delete_scopes)
    assert any(isinstance(scope, BotCommandScopeAllGroupChats) for scope in delete_scopes)

    private_call, manager_call = bot.set_my_commands.await_args_list
    assert isinstance(private_call.kwargs["scope"], BotCommandScopeAllPrivateChats)
    assert [item.command for item in private_call.kwargs["commands"]] == ["new"]
    assert isinstance(manager_call.kwargs["scope"], BotCommandScopeChat)
    assert manager_call.kwargs["scope"].chat_id == -1004489968828
    assert [item.command for item in manager_call.kwargs["commands"]] == ["close_ticket"]
