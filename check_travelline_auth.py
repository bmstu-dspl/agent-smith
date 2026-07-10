import asyncio
import json
import os

from dotenv import load_dotenv

from travelline_client import TravelLineClient, TravelLineConfig

load_dotenv()


async def main() -> None:
    config = TravelLineConfig(
        client_id=os.getenv("TRAVELLINE_CLIENT_ID"),
        client_secret=os.getenv("TRAVELLINE_CLIENT_SECRET"),
        property_id=os.getenv("TRAVELLINE_PROPERTY_ID"),
    )
    client = TravelLineClient(config)

    token = await client._get_access_token()
    print("Авторизация прошла успешно!")
    print("Токен (начало):", token[:20] + "...")

    print("\nПробуем реальный поиск номеров...")
    rooms = await client.search_room_stays("2026-10-10", "2026-10-13", 2)
    print("Ответ TravelLine (сырой, как есть):")
    print(json.dumps(rooms, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

