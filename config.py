from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _secret(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value.strip()

    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        try:
            value = Path(file_path).read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ValueError(f"failed to read {name}_FILE") from error
    if not value:
        raise ValueError(f"{name} is not configured")
    return value


BOT_TOKEN = _secret("BOT_TOKEN")

# ID группы менеджеров (должен быть отрицательным для супергруппы)
MANAGER_GROUP_ID = int(os.getenv('MANAGER_GROUP_ID', 0))

# ID менеджеров (опционально, для дополнительных проверок)
MANAGER_IDS = [int(id.strip()) for id in os.getenv('MANAGER_IDS', '').split(',') if id.strip()]

# URL AI агента
AI_AGENT_URL = os.getenv('AI_AGENT_URL', 'http://ai_agent:8000')

# Настройки вебхука
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', 'https://sycamore-glaucoma-citadel.ngrok-free.dev')
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Порт для вебхука
PORT = int(os.getenv('PORT', 8080))

# Логирование
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
# Redis настройки (с значениями по умолчанию)
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
REDIS_URL = os.getenv('REDIS_URL', f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
