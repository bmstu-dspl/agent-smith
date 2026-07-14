from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field


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


def get_core_tools():
    return [
        request_clarification,
        handoff_to_operator,
        summarize_dialog,
        mark_task_status,
    ]