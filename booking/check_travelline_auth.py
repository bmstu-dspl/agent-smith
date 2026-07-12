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

    target_ids = {"899279", "898087", "903882", "903656"}
    filtered = [rs for rs in rooms if rs["ratePlan"]["id"] in target_ids]


    import json
    from pathlib import Path

    Path("travelline_raw_response.json").write_text(
    json.dumps(rooms, ensure_ascii=False, indent=2), encoding="utf-8"
    )  
    print(f"Сохранено {len(rooms)} вариантов в travelline_raw_response.json")


if __name__ == "__main__":
    asyncio.run(main())

