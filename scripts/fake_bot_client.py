"""Имитирует поведение будущего бота: шлёт запрос и построчно читает NDJSON-поток.
Запуск: uv run python scripts/fake_bot_client.py "текст сообщения"
"""
import asyncio
import json
import sys

import httpx

AI_CORE_URL = "http://localhost:8000/agent/process"


async def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "Привет, есть свободные номера?"

    payload = {
        "session_id": "user_12345_debug",
        "user_message": text,
        "metadata": {"username": "test_user"},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", AI_CORE_URL, json=payload) as response:
            response.raise_for_status()
            accumulated_text = ""

            async for line in response.aiter_lines():
                if not line:
                    continue
                event = json.loads(line)

                if event["type"] == "buttons":
                    if event["buttons"]:
                        print("Кнопки:", [b["text"] for b in event["buttons"]])
                    else:
                        print("Кнопок нет")

                elif event["type"] == "text_chunk":
                    accumulated_text += event["content"]
                    print(event["content"], end="", flush=True)  # печатаем по мере поступления

                elif event["type"] == "end":
                    print("\n--- поток завершён ---")

    print("Итоговый текст (то, что получил бот):", accumulated_text)


if __name__ == "__main__":
    asyncio.run(main())