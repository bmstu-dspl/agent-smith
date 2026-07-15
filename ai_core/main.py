from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_core.graph.builder import build_graph
from ai_core.api.routes import messages


@asynccontextmanager
async def lifespan(app: FastAPI):
    # позже здесь появится init_checkpointer(settings.postgres_dsn)
    app.state.graph = build_graph()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(messages.router)


@app.get("/healthz", include_in_schema=False)
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
