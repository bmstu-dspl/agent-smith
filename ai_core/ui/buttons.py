from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ai_core.contracts.schemas import Button, IncomingMessage
from ai_core.graph.prompts import BUTTONS_PROMPT


class ButtonsDecision(BaseModel):
    buttons: list[Button] = Field(default_factory=list)


class ButtonDecider:
    def __init__(self, llm) -> None:
        self.llm = llm.with_structured_output(ButtonsDecision)

    async def decide(
        self,
        payload: IncomingMessage,
        available_actions: list[dict[str, str]],
    ) -> list[Button]:
        actions_text = "\n".join(
            f"- {action['name']}: {action['description']}"
            for action in available_actions
        )

        if not actions_text:
            actions_text = "Нет доступных действий."

        decision = await self.llm.ainvoke(
            [
                SystemMessage(
                    content=f"{BUTTONS_PROMPT}\n\nДоступные действия:\n{actions_text}"
                ),
                HumanMessage(content=payload.user_message),
            ]
        )

        return decision.buttons