from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class IncomingMessage(BaseModel):
    session_id: str = Field(..., description="Уникальный ID сессии пользователя")
    user_message: str = Field(..., description="Текст сообщения от пользователя")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Доп. инфо (имя, username)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }