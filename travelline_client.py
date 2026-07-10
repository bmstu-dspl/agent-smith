"""Клиент для Search API TravelLine.

Пока нет доступа к реальной документации/тестовой среде — схема запроса
и структура ответа собраны по открытым источникам (best-effort).
Места с TODO нужно свериться, как только появится доступ.
"""
import time
from dataclasses import dataclass

import httpx

from errors import AuthenticationError, ExternalServiceError


@dataclass
class TravelLineConfig:
    client_id: str
    client_secret: str
    property_id: str
    base_url: str = "https://partner.tlintegration.com"
    auth_url: str = "https://partner.tlintegration.com/auth/token"


class TravelLineClient:
    """Обёртка над Search API TravelLine: авторизация + поиск номеров."""

    def __init__(self, config: TravelLineConfig, timeout: float = 10.0):
        self._config = config
        self._timeout = timeout
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_access_token(self) -> str:
        """Возвращает валидный access token, обновляя его при истечении.

        TravelLine не использует refresh token — при истечении нужно
        просто запросить новый токен теми же client credentials.
        """
        # запас в 30 секунд, чтобы не словить токен впритык к истечению
        if self._access_token and time.time() < self._token_expires_at - 30:
            return self._access_token

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    self._config.auth_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._config.client_id,
                        "client_secret": self._config.client_secret,
                    },
                )
            except httpx.RequestError as exc:
                raise ExternalServiceError(f"Не удалось связаться с TravelLine: {exc}") from exc

        if response.status_code == 401:
            raise AuthenticationError("Неверные client_id/client_secret для TravelLine")
        if response.status_code >= 500:
            raise ExternalServiceError(f"TravelLine недоступен (код {response.status_code})")
        if response.status_code != 200:
            raise ExternalServiceError(
                f"Неожиданный ответ при получении токена: {response.status_code}"
            )

        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in
        return self._access_token

    async def search_room_stays(self, check_in: str, check_out: str, guests: int) -> list[dict]:
        """Найти доступные номера в объекте размещения.

        check_in/check_out — в формате ГГГГ-ММ-ДД.
        TODO: уточнить точные параметры запроса и структуру ответа по документации.
        """
        token = await self._get_access_token()
        url = (
            f"{self._config.base_url}/api/search/v1/properties/"
            f"{self._config.property_id}/room-stays"
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"arrivalDate": check_in, "departureDate": check_out, "adults": guests},
                )
            except httpx.RequestError as exc:
                raise ExternalServiceError(f"Не удалось связаться с TravelLine: {exc}") from exc





        if response.status_code == 401:
            raise AuthenticationError("Токен TravelLine недействителен")
        if response.status_code == 429:
            raise ExternalServiceError("Превышен лимит запросов к TravelLine, попробуйте позже")
        if response.status_code >= 500:
            raise ExternalServiceError(f"TravelLine недоступен (код {response.status_code})")
        if response.status_code != 200:
            raise ExternalServiceError(
                f"Неожиданный ответ при поиске номеров: {response.status_code}"
            )

        data = response.json()
        return data.get("roomStays", [])  # TODO: свериться с реальной структурой ответа