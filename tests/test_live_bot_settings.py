from __future__ import annotations

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from DB import OrmBase
from admin_panel.db_models import AdminUserModel, ServiceSettingsModel
from admin_panel.settings import SettingsStore, TelegramSettingsUpdate
from app.live_config import LiveTelegramSettingsProvider


@pytest.mark.asyncio
async def test_bot_reads_durable_settings_before_start_and_refreshes_runtime_values() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrmBase.metadata.create_all(
        engine,
        tables=[AdminUserModel.__table__, ServiceSettingsModel.__table__],
    )
    store = SettingsStore(
        sessionmaker(bind=engine, expire_on_commit=False),
        Fernet.generate_key().decode(),
    )
    store.save_telegram(
        TelegramSettingsUpdate(
            revision=0,
            bot_token="db-token",
            webhook_host="https://bot.example.test",
            manager_group_id=-1001,
            ai_agent_url="http://ai-one:8000",
            enable_escalation=True,
        ),
        updated_by="test-admin",
    )
    provider = LiveTelegramSettingsProvider(store)

    initial = provider.load_initial()
    assert initial.bot_token == "db-token"
    assert initial.webhook_url == (
        "https://bot.example.test/webhook/"
        "caf4beb67df21e835c8514c03217c01f9a24bbb43cd4e0ed85dcd48b8edbe495"
    )
    assert "db-token" not in initial.webhook_url

    store.save_telegram(
        TelegramSettingsUpdate(
            revision=1,
            webhook_host="https://bot.example.test",
            manager_group_id=-1002,
            ai_agent_url="http://ai-two:8000",
            enable_escalation=True,
        ),
        updated_by="test-admin",
    )
    refreshed = await provider.get()
    assert refreshed.manager_group_id == -1002
    assert refreshed.ai_agent_url == "http://ai-two:8000"
    assert refreshed.bot_token == "db-token"
