import asyncio
import json

from dotenv import load_dotenv

import booking_plugin as booking

# запуск: uv run python check_search_tool.py
# запуск: uv run python booking/check_search_tool.py

load_dotenv()


async def main() -> None:
    booking.initialize_plugin()

    result = await booking.search_available_rooms.ainvoke(
        {"check_in": "10-10-2026", "check_out": "13-10-2026", "adults": 2, "child_ages": [2, 9]}
    )

    print("Результат поиска (будет для ии):\n")
    print(json.dumps(json.loads(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())