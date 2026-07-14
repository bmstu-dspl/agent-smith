from contextlib import asynccontextmanager

from fastapi import FastAPI

from memory import MemoryManager
from ai_core.graph.builder import build_graph
from ai_core.api.routes import messages


@asynccontextmanager
async def lifespan(app: FastAPI):
    memory = MemoryManager()
    await memory.init()

    app.state.memory = memory
    app.state.graph = build_graph(checkpointer=memory.checkpointer)

    yield

    await memory.close()


app = FastAPI(lifespan=lifespan)
app.include_router(messages.router)
