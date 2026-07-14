from langchain_core.tools import BaseTool

from ai_core.tools.core_tools import get_core_tools


class ToolRegistry:
    def __init__(self) -> None:
        self._plugin_tools: list[BaseTool] = []

    def register_many(self, tools: list[BaseTool]) -> None:
        self._plugin_tools.extend(tools)

    def get_tools(self) -> list[BaseTool]:
        return [
            *get_core_tools(),
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

    def describe_button_actions(self) -> list[dict[str, str]]:
        hidden_actions = {"mark_task_status", "summarize_dialog"}
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
            }
            for tool in self.get_tools()
            if tool.name not in hidden_actions
        ]