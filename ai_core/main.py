from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from memory import MemoryManager
from ai_core.graph.builder import build_graph
from ai_core.api.routes import messages
from app_runtime import AppRuntime

# Импорты для админки
from shared.redis_client import get_redis_client
from shared.config_storage import ConfigStorage
from admin_panel import create_admin_app, AdminStorage
from admin_panel.register_plugins import register_all_plugins
from admin_panel.views import login_page, login_post, logout


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация Redis
    redis = None
    try:
        redis = await get_redis_client()
        if redis:
            print("✅ Redis connected")
        else:
            print("⚠️ Redis not available")
    except Exception as e:
        print(f"⚠️ Redis connection error: {e}")
    
    # Инициализация Memory
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

    # Инициализация админки
    try:
        if redis:
            config_storage = ConfigStorage(redis)
            admin_storage = AdminStorage(config_storage)
            
            # Сохраняем в app.state для доступа из API
            app.state.admin_storage = admin_storage
            app.state.config_storage = config_storage
            
            # Создаем и монтируем админку
            admin_app = create_admin_app(admin_storage, redis)
            admin_app.mount_to(app)
            
            # Регистрируем API роуты
            from admin_panel.routes import router as admin_api_router
            app.include_router(admin_api_router)
            
            # Регистрируем плагины
            register_all_plugins()
            
            print("✅ Admin panel initialized")
            print(f"   Admin URL: /admin")
            print(f"   Login: {os.getenv('ADMIN_LOGIN', 'admin')}")
        else:
            print("⚠️ Redis not available, admin panel disabled")
    except Exception as e:
        print(f"⚠️ Failed to initialize admin panel: {e}")

    yield
    
    # Закрываем соединения
    await memory.close()
    runtime.close()
    if redis:
        from shared.redis_client import redis_client as shared_redis_client
        await shared_redis_client.close()
        print("✅ Redis connection closed")


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


# Добавляем отдельные роуты для логина (вне админки)
app.add_route("/admin/login", login_page, methods=["GET"])
app.add_route("/admin/login", login_post, methods=["POST"])
app.add_route("/admin/logout", logout, methods=["GET", "POST"])
