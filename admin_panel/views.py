"""Представления для Starlette-Admin"""

import os
import json
import logging
import time
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from starlette_admin import BaseAdmin
from starlette_admin.views import CustomView

from .auth import SimpleAdminAuth
from .storage import AdminStorage
from .models import BotConfig
from .plugin_system import plugin_registry

logger = logging.getLogger(__name__)


class BotConfigView(CustomView):
    """Страница конфигурации бота"""
    
    def __init__(self, storage: AdminStorage):
        super().__init__(
            label="Bot Configuration",
            icon="gear",
            path="/bot-config"
        )
        self.storage = storage
    
    async def render(self, request: Request, templates: Jinja2Templates) -> HTMLResponse:  # <-- ДОБАВЛЯЕМ templates
        config = await self.storage.get_bot_config()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Bot Configuration</title>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/css/bootstrap.min.css">
            <style>
                body {{ background: #f5f5f5; padding: 20px; }}
                .container {{ max-width: 800px; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .form-group {{ margin-bottom: 20px; }}
                .form-group label {{ font-weight: 600; }}
                .form-text {{ font-size: 12px; color: #6c757d; }}
                .btn-save {{ width: 100%; padding: 12px; }}
                .alert {{ margin-top: 20px; display: none; }}
                .checkbox-group label {{ font-weight: normal; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="mb-4"> Bot Configuration</h1>
                
                <div id="alert" class="alert" role="alert"></div>
                
                <form id="config-form">
                    <div class="form-group">
                        <label for="token">Bot Token *</label>
                        <input type="text" class="form-control" id="token" name="token" 
                               value="{config.token or ''}" required>
                        <div class="form-text">Токен от @BotFather</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="webhook_host">Webhook Host *</label>
                        <input type="url" class="form-control" id="webhook_host" name="webhook_host" 
                               value="{config.webhook_host or ''}" required>
                        <div class="form-text">Публичный URL (например, https://your-domain.ngrok-free.dev)</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="manager_group_id">Manager Group ID</label>
                        <input type="number" class="form-control" id="manager_group_id" name="manager_group_id" 
                               value="{config.manager_group_id or ''}">
                        <div class="form-text">Отрицательное число для супергруппы</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="ai_agent_url">AI Agent URL</label>
                        <input type="url" class="form-control" id="ai_agent_url" name="ai_agent_url" 
                               value="{config.ai_agent_url}">
                    </div>
                    
                    <div class="form-group">
                        <label for="log_level">Log Level</label>
                        <select class="form-control" id="log_level" name="log_level">
                            <option value="DEBUG" {'selected' if config.log_level == 'DEBUG' else ''}>DEBUG</option>
                            <option value="INFO" {'selected' if config.log_level == 'INFO' else ''}>INFO</option>
                            <option value="WARNING" {'selected' if config.log_level == 'WARNING' else ''}>WARNING</option>
                            <option value="ERROR" {'selected' if config.log_level == 'ERROR' else ''}>ERROR</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="port">Port</label>
                        <input type="number" class="form-control" id="port" name="port" 
                               value="{config.port or 8080}">
                    </div>
                    
                    <div class="form-group checkbox-group">
                        <div class="form-check">
                            <input type="checkbox" class="form-check-input" id="enable_rag" name="enable_rag" 
                                   {'checked' if config.enable_rag else ''}>
                            <label class="form-check-label" for="enable_rag">Enable RAG</label>
                        </div>
                        <div class="form-check">
                            <input type="checkbox" class="form-check-input" id="enable_escalation" name="enable_escalation" 
                                   {'checked' if config.enable_escalation else ''}>
                            <label class="form-check-label" for="enable_escalation">Enable Escalation</label>
                        </div>
                        <div class="form-check">
                            <input type="checkbox" class="form-check-input" id="enable_redis_fsm" name="enable_redis_fsm" 
                                   {'checked' if config.enable_redis_fsm else ''}>
                            <label class="form-check-label" for="enable_redis_fsm">Use Redis for FSM</label>
                        </div>
                    </div>
                    
                    <button type="submit" class="btn btn-primary btn-save">💾 Save Configuration</button>
                </form>
            </div>
            
            <script>
                document.getElementById('config-form').addEventListener('submit', async (e) => {{
                    e.preventDefault();
                    
                    const formData = new FormData(e.target);
                    const config = {{
                        token: formData.get('token'),
                        webhook_host: formData.get('webhook_host'),
                        manager_group_id: parseInt(formData.get('manager_group_id')) || null,
                        ai_agent_url: formData.get('ai_agent_url'),
                        log_level: formData.get('log_level'),
                        port: parseInt(formData.get('port')) || 8080,
                        enable_rag: formData.get('enable_rag') === 'on',
                        enable_escalation: formData.get('enable_escalation') === 'on',
                        enable_redis_fsm: formData.get('enable_redis_fsm') === 'on',
                    }};
                    
                    const alert = document.getElementById('alert');
                    
                    try {{
                        const response = await fetch('/admin/api/bot-config', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify(config)
                        }});
                        
                        const result = await response.json();
                        
                        if (response.ok) {{
                            alert.className = 'alert alert-success';
                            alert.textContent = '✅ ' + (result.message || 'Configuration saved successfully!');
                            alert.style.display = 'block';
                        }} else {{
                            alert.className = 'alert alert-danger';
                            alert.textContent = '❌ ' + (result.error || 'Error saving configuration');
                            alert.style.display = 'block';
                        }}
                    }} catch (err) {{
                        alert.className = 'alert alert-danger';
                        alert.textContent = '❌ Error: ' + err.message;
                        alert.style.display = 'block';
                    }}
                    
                    setTimeout(() => {{
                        alert.style.display = 'none';
                    }}, 5000);
                }});
            </script>
        </body>
        </html>
        """
        return HTMLResponse(html)
    
    async def handle_post(self, request: Request) -> JSONResponse:
        try:
            data = await request.json()
            config = BotConfig(**data)
            success = await self.storage.save_bot_config(config)
            
            if success:
                return JSONResponse({"status": "success", "message": "Configuration saved"})
            else:
                return JSONResponse({"status": "error", "error": "Failed to save"}, status_code=500)
                
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return JSONResponse({"status": "error", "error": str(e)}, status_code=400)


class PluginDetailView(CustomView):
    """Страница конфигурации встроенного компонента (RAG, AI Agent и т.п.)

    В отличие от старой связки PluginListView + PluginConfigView(plugin_id),
    каждый компонент теперь получает свой собственный фиксированный пункт
    меню в админке, без промежуточного общего списка "Plugins".
    """

    def __init__(self, storage: AdminStorage, plugin_id: str, label: str, icon: str, path: str):
        super().__init__(
            label=label,
            icon=icon,
            path=path
        )
        self.storage = storage
        self.plugin_id = plugin_id

    async def render(self, request: Request, templates: Jinja2Templates) -> HTMLResponse:  # <-- ДОБАВЛЯЕМ templates
        plugin_id = self.plugin_id
        definition = plugin_registry.get(plugin_id)
        
        if not definition:
            return HTMLResponse(f"""
            <html><body>
                <h1>Component not found</h1>
                <p>Component '{plugin_id}' is not registered</p>
                <a href="/admin">← Back to Admin</a>
            </body></html>
            """, status_code=404)
        
        saved = await self.storage.get_plugin_config(plugin_id)
        config = saved.config if saved else definition.default_config
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{definition.name} Config</title>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/css/bootstrap.min.css">
            <style>
                body {{ background: #f5f5f5; padding: 20px; }}
                .container {{ max-width: 700px; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="mb-4">⚙️ {definition.name}</h1>
                <p class="text-muted">{definition.description}</p>
                
                <div id="alert" class="alert" style="display:none;" role="alert"></div>
                
                <form id="config-form">
        """
        
        for field_name, field_config in definition.config_schema.items():
            field_type = field_config.get("type", "string")
            field_label = field_config.get("label", field_name)
            field_default = config.get(field_name, field_config.get("default"))
            
            if field_type == "boolean":
                html += f"""
                <div class="form-check mb-3">
                    <input type="checkbox" class="form-check-input" id="{field_name}" name="{field_name}" 
                           {'checked' if field_default else ''}>
                    <label class="form-check-label" for="{field_name}">{field_label}</label>
                </div>
                """
            elif field_type == "integer":
                html += f"""
                <div class="form-group mb-3">
                    <label for="{field_name}">{field_label}</label>
                    <input type="number" class="form-control" id="{field_name}" name="{field_name}" 
                           value="{field_default or ''}">
                    <div class="form-text">{field_config.get('description', '')}</div>
                </div>
                """
            elif field_type == "text":
                import html as _html
                escaped_value = _html.escape(str(field_default or ''))
                html += f"""
                <div class="form-group mb-3">
                    <label for="{field_name}">{field_label}</label>
                    <textarea class="form-control" id="{field_name}" name="{field_name}" 
                              rows="12">{escaped_value}</textarea>
                    <div class="form-text">{field_config.get('description', '')}</div>
                </div>
                """
            elif field_type == "select":
                options = field_config.get("options", [])
                options_html = "".join(
                    f'<option value="{opt}" {"selected" if opt == field_default else ""}>{opt}</option>'
                    for opt in options
                )
                html += f"""
                <div class="form-group mb-3">
                    <label for="{field_name}">{field_label}</label>
                    <select class="form-control" id="{field_name}" name="{field_name}">
                        {options_html}
                    </select>
                    <div class="form-text">{field_config.get('description', '')}</div>
                </div>
                """
            else:
                html += f"""
                <div class="form-group mb-3">
                    <label for="{field_name}">{field_label}</label>
                    <input type="text" class="form-control" id="{field_name}" name="{field_name}" 
                           value="{field_default or ''}">
                    <div class="form-text">{field_config.get('description', '')}</div>
                </div>
                """
        
        html += f"""
                    <input type="hidden" name="plugin_id" value="{plugin_id}">
                    <button type="submit" class="btn btn-primary w-100">💾 Save Configuration</button>
                </form>
                
                <div class="mt-3">
                    <a href="/admin" class="btn btn-secondary">← Back to Admin</a>
                </div>
            </div>
            
            <script>
                document.getElementById('config-form').addEventListener('submit', async (e) => {{
                    e.preventDefault();
                    
                    const formData = new FormData(e.target);
                    const config = {{}};
                    
                    for (let [key, value] of formData.entries()) {{
                        if (key !== 'plugin_id') {{
                            if (value === 'on') {{
                                config[key] = true;
                            }} else if (!isNaN(value) && value !== '') {{
                                config[key] = Number(value);
                            }} else {{
                                config[key] = value;
                            }}
                        }}
                    }}
                    
                    const pluginId = formData.get('plugin_id');
                    const alert = document.getElementById('alert');
                    
                    try {{
                        const response = await fetch(`/admin/api/plugins/${{pluginId}}/config`, {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify(config)
                        }});
                        
                        const result = await response.json();
                        
                        if (response.ok) {{
                            alert.className = 'alert alert-success';
                            alert.textContent = '✅ ' + (result.message || 'Configuration saved!');
                            alert.style.display = 'block';
                        }} else {{
                            alert.className = 'alert alert-danger';
                            alert.textContent = '❌ ' + (result.error || 'Error');
                            alert.style.display = 'block';
                        }}
                    }} catch (err) {{
                        alert.className = 'alert alert-danger';
                        alert.textContent = '❌ Error: ' + err.message;
                        alert.style.display = 'block';
                    }}
                    
                    setTimeout(() => {{
                        alert.style.display = 'none';
                    }}, 5000);
                }});
            </script>
        </body>
        </html>
        """
        return HTMLResponse(html)


# ==================== ОТДЕЛЬНЫЕ РОУТЫ ДЛЯ ЛОГИНА ====================

async def login_page(request: Request):
    """Страница входа"""
    error = request.query_params.get("error")
    error_message = ""
    if error == "invalid":
        error_message = '<div class="alert alert-danger">Invalid username or password</div>'
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Login</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/css/bootstrap.min.css">
        <style>
            body {{ background: #f5f5f5; display: flex; align-items: center; justify-content: center; height: 100vh; }}
            .login-container {{ max-width: 400px; width: 100%; padding: 30px; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .login-container h1 {{ text-align: center; margin-bottom: 30px; }}
        </style>
    </head>
    <body>
        <div class="login-container">
            <h1>🔐 Admin Login</h1>
            {error_message}
            <form method="post" action="/admin/login">
                <div class="form-group mb-3">
                    <label for="username">Username</label>
                    <input type="text" class="form-control" id="username" name="username" value="admin" required>
                </div>
                <div class="form-group mb-3">
                    <label for="password">Password</label>
                    <input type="password" class="form-control" id="password" name="password" value="admin123" required>
                </div>
                <div class="form-group mb-3">
                    <div class="form-check">
                        <input type="checkbox" class="form-check-input" id="remember_me" name="remember_me">
                        <label class="form-check-label" for="remember_me">Remember me</label>
                    </div>
                </div>
                <button type="submit" class="btn btn-primary w-100">Login</button>
            </form>
            <div class="mt-3 text-muted text-center small">
                Default: admin / admin123
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


async def login_post(request: Request):
    """Обработка логина"""
    form = await request.form()
    username = form.get("username")
    password = form.get("password")
    remember_me = form.get("remember_me") == "on"
    next_url = request.query_params.get("next", "/admin")
    
    logger.info(f"🔐 Login POST: username={username}, remember_me={remember_me}")
    
    # Проверяем логин и пароль из .env
    admin_login = os.getenv("ADMIN_LOGIN", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    
    logger.info(f"🔐 Expected: login={admin_login}")
    
    if username == admin_login and password == admin_password:
        logger.info(f"✅ Login successful: {username}")
        
        # Создаем сессию в Redis
        session_id = f"admin_{int(time.time())}_{os.urandom(16).hex()}"
        
        # Получаем Redis клиент
        from shared.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            await redis.setex(
                f"admin_session:{session_id}",
                3600 if not remember_me else 86400 * 7,
                json.dumps({"authenticated": True, "login": username})
            )
            logger.info(f"🔐 Session saved to Redis")
        
        response = RedirectResponse(url=next_url, status_code=302)
        response.set_cookie(
            key="admin_session",
            value=session_id,
            max_age=3600 if not remember_me else 86400 * 7,
            httponly=True,
            path="/admin"
        )
        return response
    
    logger.warning(f"❌ Login failed: username={username}")
    return RedirectResponse(url="/admin/login?error=invalid", status_code=302)


async def logout(request: Request):
    """Выход из админки"""
    session_id = request.cookies.get("admin_session")
    if session_id:
        from shared.redis_client import get_redis_client
        redis = await get_redis_client()
        if redis:
            await redis.delete(f"admin_session:{session_id}")
            logger.info(f"🔐 Session deleted")
    
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(key="admin_session", path="/admin")
    return response


def create_admin_app(storage: AdminStorage, redis_client=None) -> BaseAdmin:
    """Создание и настройка админ-приложения с отдельными роутами для логина"""
    
    # Создаем админку с auth_provider=None (отключаем встроенную аутентификацию)
    admin = BaseAdmin(
        title="Agent Smith Admin",
        auth_provider=None,
        base_url="/admin",
    )
    
    admin.add_view(BotConfigView(storage))
    admin.add_view(PluginDetailView(
        storage, plugin_id="rag", label="RAG", icon="database", path="/rag"
    ))
    admin.add_view(PluginDetailView(
        storage, plugin_id="ai_agent", label="AI Agent", icon="cpu", path="/ai-agent"
    ))

    return admin