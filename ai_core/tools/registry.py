from langchain_core.tools import BaseTool

from ai_core.tools.core_tools import get_core_tools


class ToolRegistry:
    def __init__(self, *, primary_timezone: str = "UTC") -> None:
        self._primary_timezone = primary_timezone
        self._plugin_tools: list[BaseTool] = []

    def register_many(self, tools: list[BaseTool]) -> None:
        self._plugin_tools.extend(tools)

    def get_tools(self) -> list[BaseTool]:
        return [
            *get_core_tools(self._primary_timezone),
            *self._plugin_tools,
        ]

    def describe_tools(self) -> list[dict[str, str]]:
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
            }
            for tool in self.get_tools()
        ]
