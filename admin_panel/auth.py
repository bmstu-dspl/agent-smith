"""Аутентификация для админки с использованием Redis"""

import bcrypt
import os
import logging
import json
import time
from typing import Optional
from starlette.requests import Request
from starlette.responses import RedirectResponse, HTMLResponse
from starlette_admin.auth import AuthProvider
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

class SimpleAdminAuth(AuthProvider):
    """Аутентификация с хранением сессий в Redis"""
    
    def __init__(self, redis_client: Redis = None):
        self._redis = redis_client
        
        # Читаем переменные из .env
        self._login = os.getenv("ADMIN_LOGIN", "admin")
        self._password = os.getenv("ADMIN_PASSWORD", "admin123")
        self._password_hash = os.getenv("ADMIN_PASSWORD_HASH")
        
        # Пути для входа и выхода - ОТНОСИТЕЛЬНЫЕ, без /admin
        self.login_path = "/login"
        self.logout_path = "/logout"
        
        # Разрешенные пути (без аутентификации) - ОТНОСИТЕЛЬНЫЕ
        self._allow_paths = ["/login", "/logout", "/static"]
        self._allow_routes = ["/login", "/logout", "/static"]
        
        logger.info(f"🔐 Admin auth configured:")
        logger.info(f"   Login: {self._login}")
        logger.info(f"   login_path: {self.login_path}")
        logger.info(f"   logout_path: {self.logout_path}")
        
        if self._password and not self._password_hash:
            self._password_hash = bcrypt.hashpw(
                self._password.encode('utf-8'),
                bcrypt.gensalt()
            ).decode('utf-8')
            logger.info("🔐 Password hash generated from ADMIN_PASSWORD")
        elif not self._password and not self._password_hash:
            logger.warning("⚠️ ADMIN_PASSWORD not set! Using default 'admin123'")
            self._password = "admin123"
            self._password_hash = bcrypt.hashpw(
                b"admin123",
                bcrypt.gensalt()
            ).decode('utf-8')
    
    @property
    def allow_paths(self):
        return self._allow_paths
    
    @property
    def allow_routes(self):
        return self._allow_routes
    
    async def authenticate(self, request: Request, username: str, password: str) -> bool:
        """Проверка логина и пароля"""
        logger.info(f"🔐 Auth attempt: username='{username}', expected='{self._login}'")
        
        if username != self._login:
            logger.warning(f"🔐 Username mismatch: '{username}' != '{self._login}'")
            return False
        
        if not password:
            logger.warning("🔐 No password provided")
            return False
        
        try:
            if self._password_hash:
                result = bcrypt.checkpw(
                    password.encode('utf-8'),
                    self._password_hash.encode('utf-8')
                )
                logger.info(f"🔐 Password check result: {result}")
                return result
            else:
                result = password == self._password
                logger.info(f"🔐 Direct password check result: {result}")
                return result
        except Exception as e:
            logger.error(f"🔐 Auth error: {e}", exc_info=True)
            return False
    
    async def login(
        self,
        request: Request,
        username: str,
        password: str,
        remember_me: bool = False,
        next_url: Optional[str] = None
    ) -> RedirectResponse:
        """Установка сессии после успешного входа"""
        logger.info(f"🔐 Login attempt: username='{username}', remember_me={remember_me}, next_url={next_url}")
        
        is_valid = await self.authenticate(request, username, password)
        if not is_valid:
            logger.warning(f"🔐 Login failed for username: {username}")
            return RedirectResponse(url="/admin/login?error=invalid", status_code=302)
        
        logger.info(f"✅ Login successful for username: {username}")
        
        session_id = request.cookies.get("admin_session")
        if not session_id:
            session_id = f"admin_{int(time.time())}_{os.urandom(16).hex()}"
        
        if self._redis:
            try:
                await self._redis.setex(
                    f"admin_session:{session_id}",
                    3600 if not remember_me else 86400 * 7,
                    json.dumps({"authenticated": True, "login": username})
                )
                logger.info(f"🔐 Session saved to Redis")
            except Exception as e:
                logger.error(f"🔐 Redis save error: {e}")
        
        redirect_url = next_url or "/admin"
        if redirect_url.startswith("/admin/login") or redirect_url.startswith("http"):
            # Если next_url содержит login, редиректим на админку
            redirect_url = "/admin"
        
        logger.info(f"🔐 Redirecting to: {redirect_url}")
        
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            key="admin_session",
            value=session_id,
            max_age=3600 if not remember_me else 86400 * 7,
            httponly=True,
            path="/admin"
        )
        return response
    
    async def logout(self, request: Request) -> RedirectResponse:
        """Выход из админки"""
        session_id = request.cookies.get("admin_session")
        if session_id and self._redis:
            await self._redis.delete(f"admin_session:{session_id}")
            logger.info(f"🔐 Session deleted")
        
        response = RedirectResponse(url="/admin/login", status_code=302)
        response.delete_cookie(key="admin_session", path="/admin")
        return response
    
    async def is_authenticated(self, request: Request) -> bool:
        """Проверка аутентификации через Redis"""
        session_id = request.cookies.get("admin_session")
        if not session_id:
            return False
        
        if not self._redis:
            return True
        
        try:
            data = await self._redis.get(f"admin_session:{session_id}")
            if data:
                session_data = json.loads(data)
                return session_data.get("authenticated", False)
        except Exception as e:
            logger.error(f"🔐 Session check error: {e}")
        
        return False
    
    async def get_login_page(self, request: Request) -> HTMLResponse:
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
                        <input type="text" class="form-control" id="username" name="username" required>
                    </div>
                    <div class="form-group mb-3">
                        <label for="password">Password</label>
                        <input type="password" class="form-control" id="password" name="password" required>
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