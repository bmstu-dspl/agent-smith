from typing import Annotated, Any, Literal, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from ai_core.contracts.schemas import Button


class AgentState(TypedDict, total=False):
    session_id: str
    user_message: str
    message_type: Literal["text", "callback"]
    metadata: dict[str, Any]
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str | None
    buttons: list[Button]
    answer: str | None
    blocked: bool
    block_reason: str | None
    rag_context: str | None
    tool_result: str | None
