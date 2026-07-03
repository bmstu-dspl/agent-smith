import json
import logging
from typing import Any, Dict, List

import httpx
from app.models import IncomingMessage

logger = logging.getLogger(__name__)

AI_CORE_URL = "http://localhost:8000/agent/process"


class AIAgent:
    async def process_message(self, message: IncomingMessage) -> Dict[str, Any]:
        # Сериализуем модель. Для Pydantic v2 используем model_dump(mode="json")
        # Если у вас Pydantic v1, замените на message.dict()
        payload = message.model_dump(mode="json")

        full_text = ""
        buttons: List[Dict[str, str]] = []

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", AI_CORE_URL, json=payload) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError as e:
                            logger.error(f"Ошибка парсинга строки NDJSON: {line} | {e}")
                            continue

                        event_type = event.get("type")

                        if event_type == "buttons":
                            raw_buttons = event.get("buttons", [])
                            buttons = [
                                {"text": b["text"], "callback_data": b["callback_data"]}
                                for b in raw_buttons
                            ]
                            logger.info(f"Получено кнопок: {len(buttons)}")

                        elif event_type == "text_chunk":
                            chunk = event.get("content", "")
                            full_text += chunk
                            logger.debug(f"Чанк текста: {chunk}")

                        elif event_type == "end":
                            logger.info("Поток завершён")

        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при обращении к AI-ядру: {e.response.status_code} {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Ошибка сети при соединении с AI-ядром: {e}")
            raise
        except Exception as e:
            logger.error(f"Неизвестная ошибка в process_message: {e}", exc_info=True)
            raise

        return {"text": full_text.strip(), "buttons": buttons}


ai_agent = AIAgent()