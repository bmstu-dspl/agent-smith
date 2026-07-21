"""Административная панель для управления ботом"""

from .auth import SimpleAdminAuth
from .storage import AdminStorage
from .models import BotConfig, PluginConfig
from .plugin_system import PluginRegistry, plugin_registry
from .views import create_admin_app

__all__ = [
    "SimpleAdminAuth",
    "AdminStorage",
    "BotConfig",
    "PluginConfig",
    "PluginRegistry",
    "plugin_registry",
    "create_admin_app",
]