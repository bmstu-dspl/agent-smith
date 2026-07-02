import asyncio
import json
import os

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

CONFIG_PATH = "mcp_servers.json"


def load_config() -> dict:
    """Читает реестр плагинов из JSON-файла."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_env(env_dict: dict) -> dict:
    """Заменяет плейсхолдеры вида ${VAR_NAME} на значения из .env."""
    resolved = {}
    for key, value in env_dict.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            resolved[key] = os.getenv(var_name, "")
        else:
            resolved[key] = value
    return resolved


async def connect_and_list_tools(name: str, server_config: dict) -> None:
    """Подключается к одному плагину и печатает его инструменты."""
    params = StdioServerParameters(
        command=server_config["command"],
        args=server_config.get("args", []),
        env=resolve_env(server_config.get("env", {})) or None,
    )

    print(f"\n=== Подключаюсь к плагину: {name} ===")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"[{name}] Инструменты: {[t.name for t in tools.tools]}")


async def main() -> None:
    config = load_config()
    servers = config.get("mcpServers", {})

    print(f"Найдено плагинов в реестре: {len(servers)}")

    for name, server_config in servers.items():
        await connect_and_list_tools(name, server_config)



if __name__ == "__main__":
    asyncio.run(main())