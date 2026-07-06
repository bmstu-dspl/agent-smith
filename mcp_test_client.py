import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# запуск - uv run python mcp_test_client.py

server_params = StdioServerParameters(
    command="python",
    args=["mcp_demo_server.py"],
)


async def main() -> None:
    # запуск сервера
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # запрос у сервера, какие инструменты у него есть
            tools = await session.list_tools()
            print("Доступные инструменты:", [t.name for t in tools.tools])


            # вызов инструмента с тестовыми параметрами
            result = await session.call_tool(
                "search_available_rooms",
                {"check_in": "05-08-2026", "check_out": "12-08-2026", "guests": 2},
            )
            for content in result.content:
                print("Результат поиска:", content.text)

            result = await session.call_tool(
                "generate_booking_link",
                {
                    "room_type": "1270",
                    "offer_id": "439000",
                    "check_in": "05-08-2026",
                    "check_out": "12-08-2026",
                },
            )
            for content in result.content:
                print("Ссылка на бронь:", content.text)


if __name__ == "__main__":
    asyncio.run(main())