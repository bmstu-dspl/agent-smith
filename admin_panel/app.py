"""Точка входа для админки как отдельного сервиса.
"""

from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.redis_client import get_redis_client, redis_client as shared_redis_client
from shared.config_storage import ConfigStorage
from admin_panel import create_admin_app, AdminStorage
from admin_panel.register_plugins import register_all_plugins
from admin_panel.views import login_page, login_post, logout

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = None
    try:
        redis = await get_redis_client()
        if redis:
            logger.info("✅ Redis connected")
        else:
            logger.warning("⚠️ Redis not available")
    except Exception as e:
        logger.warning(f"⚠️ Redis connection error: {e}")

    if redis:
        config_storage = ConfigStorage(redis)
        admin_storage = AdminStorage(config_storage)

        app.state.admin_storage = admin_storage
        app.state.config_storage = config_storage

        admin_app = create_admin_app(admin_storage, redis)
        admin_app.mount_to(app)

        from admin_panel.routes import router as admin_api_router
        app.include_router(admin_api_router)

        register_all_plugins()

        logger.info("✅ Admin panel initialized")
        logger.info("   Admin URL: /admin")
        logger.info(f"   Login: {os.getenv('ADMIN_LOGIN', 'admin')}")
    else:
        logger.warning("⚠️ Redis not available, admin panel disabled")

    yield

    if redis:
        await shared_redis_client.close()
        logger.info("✅ Redis connection closed")


app = FastAPI(title="Agent Smith Admin", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_route("/admin/login", login_page, methods=["GET"])
app.add_route("/admin/login", login_post, methods=["POST"])
app.add_route("/admin/logout", logout, methods=["GET"])


@app.get("/health")
async def health():
    return {"status": "ok"}