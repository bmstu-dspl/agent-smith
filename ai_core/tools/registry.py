from langchain_core.tools import BaseTool

from ai_core.tools.core_tools import get_core_tools
from ai_core.skills import create_load_skill_tool
from admin_panel.skills import AgentSkill


class ToolRegistry:
    def __init__(
        self,
        *,
        primary_timezone: str = "UTC",
        skills: tuple[AgentSkill, ...] = (),
    ) -> None:
        self._primary_timezone = primary_timezone
        self._skills = tuple(skill for skill in skills if skill.enabled)
        self._plugin_tools: list[BaseTool] = []

    def register_many(self, tools: list[BaseTool]) -> None:
        self._plugin_tools.extend(tools)

    def get_tools(self) -> list[BaseTool]:
        skill_tools = (
            [create_load_skill_tool(self._skills)] if self._skills else []
        )
        return [
            *get_core_tools(self._primary_timezone),
            *skill_tools,
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
