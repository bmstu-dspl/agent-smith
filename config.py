from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)


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


try:
    BOT_TOKEN = _secret("BOT_TOKEN")
except ValueError:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Базовые настройки (могут быть переопределены из Redis)
MANAGER_GROUP_ID = int(os.getenv('MANAGER_GROUP_ID', 0))
AI_AGENT_URL = os.getenv('AI_AGENT_URL', 'http://ai_agent:8000')
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', 'https://sycamore-glaucoma-citadel.ngrok-free.dev')
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.getenv('PORT', 8080))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
REDIS_URL = os.getenv('REDIS_URL', f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")

# ID менеджеров (опционально, для дополнительных проверок)
MANAGER_IDS = [int(id.strip()) for id in os.getenv('MANAGER_IDS', '').split(',') if id.strip()]


def apply_config_from_redis(config: dict):
    """Применить конфигурацию из Redis"""
    global BOT_TOKEN, MANAGER_GROUP_ID, AI_AGENT_URL, WEBHOOK_HOST, WEBHOOK_PATH, WEBHOOK_URL, PORT, LOG_LEVEL
    
    if config.get('token'):
        BOT_TOKEN = config['token']
    if config.get('manager_group_id') is not None:
        MANAGER_GROUP_ID = config['manager_group_id']
    if config.get('ai_agent_url'):
        AI_AGENT_URL = config['ai_agent_url']
    if config.get('webhook_host'):
        WEBHOOK_HOST = config['webhook_host']
    if config.get('port'):
        PORT = config['port']
    if config.get('log_level'):
        LOG_LEVEL = config['log_level']
    
    # Обновляем зависимые переменные
    WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
    WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
    
    logger.info(f"Config updated from Redis: webhook={WEBHOOK_URL}")
