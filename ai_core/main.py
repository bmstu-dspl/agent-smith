<<<<<<< HEAD
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
=======
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
>>>>>>> 7bf389080b460c37f68fd262b476e2a5d6a03dec
app.include_router(messages.router)