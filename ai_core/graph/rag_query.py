from __future__ import annotations
from pydantic import BaseModel, Field

class RagSearchRequest(BaseModel):
    topic: str = Field(default="", description="Краткая тема запроса пользователя для поиска в базе знаний.")
    keywords: list[str] = Field(default_factory=list, description="Ключевые слова, сущности и термины для поиска.")
    constraints: list[str] = Field(default_factory=list, description="Важные ограничения, параметры, даты, имена, типы объектов.")

    def to_query(self) -> str:
        parts = [self.topic, *self.keywords, *self.constraints]
        normalized_parts = []
        seen = set()
        for part in parts:
            value = " ".join(str(part).strip().split())
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized_parts.append(value)
        return " ".join(normalized_parts)