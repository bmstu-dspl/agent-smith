from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from google.auth.credentials import Credentials
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from ._embedding_constants import EMBEDDING_DIMENSIONS
from ._errors import EmbeddingConfigurationError, EmbeddingError

_DEFAULT_MODEL = "gemini-embedding-001"
_DEFAULT_LOCATION = "us-central1"
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


@dataclass(slots=True, frozen=True)
class GoogleEmbeddingConfig:
    credentials_file: str = ""
    project_id: str = ""
    location: str = _DEFAULT_LOCATION
    api_endpoint: str = ""
    model: str = _DEFAULT_MODEL
    dimensions: int = EMBEDDING_DIMENSIONS
    timeout_seconds: float = 30.0
    max_retries: int = 3

    def __post_init__(self) -> None:
        if not self.credentials_file.strip():
            raise EmbeddingConfigurationError(
                "GOOGLE_APPLICATION_CREDENTIALS is required"
            )
        if not self.location.strip():
            raise EmbeddingConfigurationError("Google Cloud location must not be empty")
        if not self.model.strip():
            raise EmbeddingConfigurationError("Google embedding model must not be empty")
        if self.dimensions != EMBEDDING_DIMENSIONS:
            raise EmbeddingConfigurationError(
                f"Google embedding dimensions must be {EMBEDDING_DIMENSIONS}"
            )
        if self.timeout_seconds <= 0:
            raise EmbeddingConfigurationError("Google embedding timeout must be positive")
        if self.max_retries < 0:
            raise EmbeddingConfigurationError(
                "Google embedding max_retries must not be negative"
            )

    @classmethod
    def from_env(cls, prefix: str = "GOOGLE_EMBEDDING_") -> GoogleEmbeddingConfig:
        return cls(
            credentials_file=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip(),
            project_id=os.getenv("GOOGLE_CLOUD_PROJECT", "").strip(),
            location=os.getenv(
                f"{prefix}LOCATION",
                os.getenv("GOOGLE_CLOUD_LOCATION", _DEFAULT_LOCATION),
            ).strip(),
            api_endpoint=os.getenv(f"{prefix}API_ENDPOINT", "").strip(),
            model=os.getenv(f"{prefix}MODEL", _DEFAULT_MODEL).strip(),
            dimensions=int(os.getenv(f"{prefix}DIMENSIONS", str(EMBEDDING_DIMENSIONS))),
            timeout_seconds=float(os.getenv(f"{prefix}TIMEOUT", "30")),
            max_retries=int(os.getenv(f"{prefix}MAX_RETRIES", "3")),
        )


class GoogleEmbeddingProvider:
    def __init__(
        self,
        config: GoogleEmbeddingConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        credentials: Credentials | None = None,
        auth_request: GoogleAuthRequest | None = None,
    ) -> None:
        self._config = config
        try:
            self._credentials = credentials or (
                service_account.Credentials.from_service_account_file(
                    config.credentials_file,
                    scopes=(_CLOUD_PLATFORM_SCOPE,),
                )
            )
        except (OSError, ValueError) as error:
            raise EmbeddingConfigurationError(
                "failed to load Google service account JSON"
            ) from error
        self._project_id = config.project_id or getattr(
            self._credentials, "project_id", ""
        )
        if not self._project_id:
            raise EmbeddingConfigurationError(
                "Google Cloud project_id is missing from configuration and credentials"
            )
        self._auth_request = auth_request or GoogleAuthRequest()
        api_endpoint = config.api_endpoint or (
            f"https://{config.location}-aiplatform.googleapis.com/v1"
        )
        self._client = httpx.Client(
            base_url=api_endpoint.rstrip("/") + "/",
            headers={"Content-Type": "application/json"},
            timeout=config.timeout_seconds,
            transport=transport,
        )

    @property
    def model(self) -> str:
        return (
            f"vertex-ai/{self._project_id}/{self._config.location}/"
            f"{self._config.model}"
        )

    @property
    def dimensions(self) -> int:
        return self._config.dimensions

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        normalized = tuple(text.strip() for text in texts)
        if any(not text for text in normalized):
            raise EmbeddingError("embedding input must not be empty")
        return tuple(
            self._request(text, task_type="RETRIEVAL_DOCUMENT")
            for text in normalized
        )

    def embed_query(self, text: str) -> tuple[float, ...]:
        normalized = text.strip()
        if not normalized:
            raise EmbeddingError("embedding input must not be empty")
        return self._request(normalized, task_type="RETRIEVAL_QUERY")

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        text: str,
        *,
        task_type: str,
    ) -> tuple[float, ...]:
        payload = {
            "instances": [
                {
                    "content": text,
                    "task_type": task_type,
                }
            ],
            "parameters": {
                "autoTruncate": True,
                "outputDimensionality": self._config.dimensions,
            },
        }
        path = (
            f"projects/{self._project_id}/locations/{self._config.location}/"
            f"publishers/google/models/{self._config.model}:predict"
        )
        response: httpx.Response | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                headers = self._authorization_headers()
                response = self._client.post(
                    path,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                retryable = (
                    not isinstance(error, httpx.UnsupportedProtocol)
                    if isinstance(error, httpx.TransportError)
                    else error.response.status_code
                    in {408, 409, 429, 500, 502, 503, 504}
                )
                if attempt >= self._config.max_retries or not retryable:
                    raise EmbeddingError("embedding request failed") from error
                time.sleep(min(0.25 * (2**attempt), 2.0))

        assert response is not None
        try:
            body: dict[str, Any] = response.json()
            return _normalized_vector(
                _validated_vector(
                    body["predictions"][0]["embeddings"]["values"],
                    self.dimensions,
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise EmbeddingError("invalid embedding response") from error

    def _authorization_headers(self) -> dict[str, str]:
        try:
            if not self._credentials.valid:
                self._credentials.refresh(self._auth_request)
        except GoogleAuthError as error:
            raise EmbeddingError("failed to obtain Google OAuth token") from error
        if not self._credentials.token:
            raise EmbeddingError("Google OAuth token is empty")
        return {"Authorization": f"Bearer {self._credentials.token}"}


def _validated_vector(values: Any, dimensions: int) -> tuple[float, ...]:
    if not isinstance(values, list) or len(values) != dimensions:
        raise EmbeddingError(f"embedding vector must have {dimensions} dimensions")
    vector = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingError("embedding vector contains a non-finite value")
    if not any(value != 0 for value in vector):
        raise EmbeddingError("embedding vector must not be zero")
    return vector


def _normalized_vector(vector: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.hypot(*vector)
    return tuple(value / norm for value in vector)
