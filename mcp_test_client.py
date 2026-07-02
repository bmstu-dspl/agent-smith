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
                "check_room_availability",
                {"check_in": "05-07-2026", "check_out": "08-07-2026", "guests": 2},
            )
            for content in result.content:
                print("Результат вызова:", content.text)




            result = await session.call_tool(
                "create_booking",
                {"check_in": "05-07-2026", "check_out": "08-07-2026", "guests": 2, "room_number": 203},
            )
            for content in result.content:
                print("Результат create_booking:", content.text)

            result = await session.call_tool(
                "cancel_booking",
                {"booking_id": "BK-1234"},
            )
            for content in result.content:
                print("Результат cancel_booking:", content.text)


if __name__ == "__main__":
    asyncio.run(main())