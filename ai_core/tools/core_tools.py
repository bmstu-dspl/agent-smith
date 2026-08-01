from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from pydantic import BaseModel, Field


def create_current_datetime_tool(
    primary_timezone: str,
    *,
    clock: Callable[[], datetime] | None = None,
):
    zone = ZoneInfo(primary_timezone)
    now = clock or (lambda: datetime.now(timezone.utc))

    @tool("get_current_datetime")
    async def get_current_datetime() -> dict:
        """Return the actual current date and time in UTC and the configured primary timezone.

        Call this before interpreting relative or incomplete dates, deciding whether
        a date is in the past or future, or invoking a date-sensitive external tool.
        """
        utc_now = now().astimezone(timezone.utc).replace(microsecond=0)
        primary_now = utc_now.astimezone(zone)
        return {
            "utc_datetime": utc_now.isoformat(),
            "primary_datetime": primary_now.isoformat(),
            "primary_date": primary_now.date().isoformat(),
            "primary_time": primary_now.time().isoformat(),
            "primary_timezone": primary_timezone,
        }

    return get_current_datetime


class RequestClarificationInput(BaseModel):
    question: str = Field(..., description="Короткий уточняющий вопрос пользователю")
    missing_fields: list[str] = Field(default_factory=list, description="Каких данных не хватает")


class HandoffToOperatorInput(BaseModel):
    reason: str = Field(..., description="Почему нужен оператор")
    summary: str = Field(..., description="Краткое резюме ситуации для оператора")


class SummarizeDialogInput(BaseModel):
    summary: str = Field(..., description="Краткое резюме текущего диалога")
    important_facts: list[str] = Field(default_factory=list, description="Ключевые факты, которые важно сохранить")


class MarkTaskStatusInput(BaseModel):
    status: Literal["unresolved", "waiting_user", "completed"] = Field(..., description="Текущее состояние задачи")
    reason: str | None = Field(None, description="Причина выбранного статуса")


class AskUserOption(BaseModel):
    label: str = Field(..., description="Короткий текст кнопки для пользователя")
    value: str = Field(..., description="Короткий идентификатор выбора латиницей")
    user_message: str = Field(..., description="Фраза от лица пользователя, которую агент получит при выборе")


class AskUserInput(BaseModel):
    question: str = Field(..., description="Вопрос, который нужно задать пользователю")
    options: list[AskUserOption] = Field(default_factory=list, description="Варианты быстрого ответа")
    allow_free_text: bool = Field(True, description="Можно ли пользователю ответить произвольным текстом")


def _dump_option(option) -> dict:
    if hasattr(option, "model_dump"):
        return option.model_dump()
    if isinstance(option, dict):
        return option
    return {}


@tool(args_schema=AskUserInput)
async def ask_user(question: str, options: list[dict] | None = None, allow_free_text: bool = True) -> dict:
    """Задает пользователю уточняющий вопрос и предлагает варианты быстрого ответа."""
    return {
        "status": "waiting_user",
        "question": question,
        "options": [_dump_option(option) for option in (options or [])],
        "allow_free_text": allow_free_text,
    }


@tool(args_schema=RequestClarificationInput)
async def request_clarification(question: str, missing_fields: list[str] | None = None) -> dict:
    """Формирует запрос на уточнение недостающих данных у пользователя."""
    return {
        "status": "waiting_user",
        "question": question,
        "missing_fields": missing_fields or [],
    }


@tool(args_schema=HandoffToOperatorInput)
async def handoff_to_operator(reason: str, summary: str) -> dict:
    """Передает диалог человеку, если агент не может продолжить самостоятельно."""
    return {
        "status": "handoff_requested",
        "reason": reason,
        "summary": summary,
    }


@tool(args_schema=SummarizeDialogInput)
async def summarize_dialog(summary: str, important_facts: list[str] | None = None) -> dict:
    """Создает краткое резюме диалога для дальнейшего использования агентом."""
    return {
        "status": "summarized",
        "summary": summary,
        "important_facts": important_facts or [],
    }


@tool(args_schema=MarkTaskStatusInput)
async def mark_task_status(status: str, reason: str | None = None) -> dict:
    """Помечает текущее состояние пользовательской задачи."""
    return {
        "status": status,
        "reason": reason,
    }


def get_core_tools(primary_timezone: str = "UTC"):
    return [
        create_current_datetime_tool(primary_timezone),
        ask_user,
        request_clarification,
        handoff_to_operator,
        summarize_dialog,
        mark_task_status,
    ]
