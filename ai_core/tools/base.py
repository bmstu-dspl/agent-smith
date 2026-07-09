from typing import Protocol

from langchain_core.tools import BaseTool


class ToolProvider(Protocol):
    def get_tools(self) -> list[BaseTool]:
        ...
