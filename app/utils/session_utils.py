import logging
from typing import Optional, Dict, List
from redis.asyncio import Redis
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class SessionManager:
    """Утилита для управления сессиями в Redis"""
    
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Получает информацию о сессии"""
        try:
            data = await self.redis.get(f"session:{session_id}")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error getting session info: {e}")
        return None
    
    async def get_user_sessions(self, user_id: int) -> Optional[str]:
        """Получает текущую сессию пользователя"""
        try:
            session_id = await self.redis.get(f"user_session:{user_id}")
            return session_id.decode('utf-8') if session_id else None
        except Exception as e:
            logger.error(f"Error getting user session: {e}")
        return None
    
    async def get_all_active_sessions(self) -> Dict[str, Dict]:
        """Получает все активные сессии (для администрирования)"""
        sessions = {}
        try:
            pattern = "session:*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                for key in keys:
                    data = await self.redis.get(key)
                    if data:
                        info = json.loads(data)
                        session_id = key.decode('utf-8').replace('session:', '')
                        sessions[session_id] = info
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Error getting all sessions: {e}")
        return sessions
    
    async def get_active_users_count(self) -> int:
        """Получает количество активных пользователей за последние 5 минут"""
        try:
            pattern = "user_last_seen:*"
            count = 0
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception as e:
            logger.error(f"Error getting active users count: {e}")
            return 0
    
    async def get_session_stats(self) -> Dict:
        """Получает статистику по сессиям"""
        stats = {
            "total_sessions": 0,
            "active_users": 0,
            "sessions_by_age": {
                "1h": 0,
                "24h": 0,
                "7d": 0,
                "30d": 0
            }
        }
        
        now = int(datetime.now().timestamp())
        
        try:
            sessions = await self.get_all_active_sessions()
            stats["total_sessions"] = len(sessions)
            
            for session_id, info in sessions.items():
                created = info.get('created_at', 0)
                age = now - created
                
                if age < 3600:
                    stats["sessions_by_age"]["1h"] += 1
                elif age < 86400:
                    stats["sessions_by_age"]["24h"] += 1
                elif age < 604800:
                    stats["sessions_by_age"]["7d"] += 1
                else:
                    stats["sessions_by_age"]["30d"] += 1
            
            stats["active_users"] = await self.get_active_users_count()
            
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
        
        return stats
    
    async def delete_session(self, session_id: str) -> bool:
        """Удаляет сессию"""
        try:
            # Получаем информацию о сессии
            info = await self.get_session_info(session_id)
            if info:
                user_id = info.get('user_id')
                if user_id:
                    await self.redis.delete(f"user_session:{user_id}")
            
            # Удаляем саму сессию
            await self.redis.delete(f"session:{session_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False
    
    async def cleanup_inactive_sessions(self, days_old: int = 30) -> int:
        """Очищает неактивные сессии"""
        cleaned = 0
        cutoff = int(datetime.now().timestamp()) - (days_old * 24 * 3600)
        
        try:
            sessions = await self.get_all_active_sessions()
            for session_id, info in sessions.items():
                created = info.get('created_at', 0)
                if created < cutoff:
                    if await self.delete_session(session_id):
                        cleaned += 1
            
            logger.info(f"Cleaned up {cleaned} sessions older than {days_old} days")
        except Exception as e:
            logger.error(f"Error cleaning sessions: {e}")
        
        return cleaned