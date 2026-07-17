from contextlib import asynccontextmanager

from fastapi import FastAPI

from memory import MemoryManager
from ai_core.graph.builder import build_graph
from ai_core.api.routes import messages

from app_runtime import AppRuntime


@asynccontextmanager
async def lifespan(app: FastAPI):
    memory = MemoryManager()
    await memory.init()

    runtime = AppRuntime.from_env()

    app.state.memory = memory
    app.state.rag_memory = runtime.memory
    app.state.runtime = runtime
    app.state.graph = build_graph(
        checkpointer=memory.checkpointer,
        rag_memory=runtime.memory,
    )

    yield

    await memory.close()
    runtime.close()


app = FastAPI(lifespan=lifespan)
app.include_router(messages.router)


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
