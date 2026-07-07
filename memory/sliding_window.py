from __future__ import annotations


def format_messages_for_llm(raw_messages: list[dict]) -> list[dict[str, str]]:
    """Превращает строки из БД в формат {role, content}, который ожидает LangGraph/LLM."""
    return [
        {"role": row["role"], "content": row["content"]}
        for row in raw_messages
    ]