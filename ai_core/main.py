from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from memory import MemoryManager
from ai_core.graph.builder import build_graph
from ai_core.api.routes import messages
from ai_core.runtime_config import LiveGraphProvider
from app_runtime import AppRuntime
from admin_panel.settings import SettingsStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация Memory
    memory = MemoryManager()
    await memory.init()

    runtime = AppRuntime.from_env()
    encryption_key = os.getenv("CONFIG_SECRETS_ENCRYPTION_KEY") or os.getenv(
        "MCP_SECRETS_ENCRYPTION_KEY"
    )
    if not encryption_key:
        raise RuntimeError("CONFIG_SECRETS_ENCRYPTION_KEY is required")
    settings_store = SettingsStore(
        sessionmaker(bind=runtime.database.engine, expire_on_commit=False),
        encryption_key,
    )

    async def graph_factory(agent_settings, rag_settings):
        return build_graph(
            checkpointer=memory.checkpointer,
            rag_memory=runtime.memory,
            agent_settings=agent_settings,
            rag_settings=rag_settings,
        )

    app.state.memory = memory
    app.state.rag_memory = runtime.memory
    app.state.runtime = runtime
    app.state.graph_provider = LiveGraphProvider(settings_store, graph_factory)
    app.state.graph = await app.state.graph_provider.get_graph()

    yield

    # Закрываем соединения
    await memory.close()
    runtime.close()


app = FastAPI(lifespan=lifespan)

# Добавляем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(messages.router)


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
