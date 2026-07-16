from __future__ import annotations

import json
import math
import os
from unittest import TestCase, skipUnless
from unittest.mock import patch

import httpx

from RAG import EmbeddingError, GoogleEmbeddingConfig, GoogleEmbeddingProvider


class _FakeCredentials:
    valid = True
    token = "test-token"
    project_id = "test-project"

    def refresh(self, request) -> None:
        self.valid = True


def _config(**kwargs) -> GoogleEmbeddingConfig:
    return GoogleEmbeddingConfig(
        credentials_file="/unused/service-account.json",
        api_endpoint="http://embedding.test/v1",
        model="test",
        **kwargs,
    )


def _response(values: list[float]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"predictions": [{"embeddings": {"values": values}}]},
    )


class GoogleEmbeddingProviderTestCase(TestCase):
    @patch.dict(
        os.environ,
        {
            "GOOGLE_APPLICATION_CREDENTIALS": "/credentials.json",
            "GOOGLE_CLOUD_LOCATION": "global",
            "GOOGLE_EMBEDDING_LOCATION": "us-central1",
        },
        clear=True,
    )
    def test_embedding_location_overrides_shared_agent_location(self) -> None:
        self.assertEqual(GoogleEmbeddingConfig.from_env().location, "us-central1")

    def test_documents_use_vertex_predict_contract(self) -> None:
        requests: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url.path,
                "/v1/projects/test-project/locations/us-central1/"
                "publishers/google/models/test:predict",
            )
            self.assertEqual(request.headers["authorization"], "Bearer test-token")
            requests.append(json.loads(request.content))
            return _response([3.0, 4.0, *([0.0] * 1534)])

        provider = GoogleEmbeddingProvider(
            _config(),
            transport=httpx.MockTransport(handler),
            credentials=_FakeCredentials(),
        )
        try:
            vectors = provider.embed_documents(("one", "two"))
        finally:
            provider.close()

        self.assertEqual(
            [payload["instances"][0]["content"] for payload in requests],
            ["one", "two"],
        )
        self.assertTrue(
            all(
                payload["instances"][0]["task_type"] == "RETRIEVAL_DOCUMENT"
                and payload["parameters"]
                == {"autoTruncate": True, "outputDimensionality": 1536}
                for payload in requests
            )
        )
        self.assertEqual([vector[:2] for vector in vectors], [(0.6, 0.8)] * 2)
        self.assertEqual(provider.model, "vertex-ai/test-project/us-central1/test")

    def test_query_uses_retrieval_query(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertEqual(
                payload["instances"][0]["task_type"],
                "RETRIEVAL_QUERY",
            )
            return _response([3.0, 4.0, *([0.0] * 1534)])

        provider = GoogleEmbeddingProvider(
            _config(),
            transport=httpx.MockTransport(handler),
            credentials=_FakeCredentials(),
        )
        try:
            vector = provider.embed_query("query")
        finally:
            provider.close()

        self.assertAlmostEqual(vector[0], 0.6)
        self.assertAlmostEqual(vector[1], 0.8)

    def test_rejects_invalid_vector_dimensions(self) -> None:
        provider = GoogleEmbeddingProvider(
            _config(),
            transport=httpx.MockTransport(lambda _: _response([1.0])),
            credentials=_FakeCredentials(),
        )
        try:
            with self.assertRaises(EmbeddingError):
                provider.embed_query("query")
        finally:
            provider.close()

    @patch("RAG.embeddings.time.sleep")
    def test_retries_rate_limit(self, sleep) -> None:
        attempts = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429)
            return _response([1.0, *([0.0] * 1535)])

        provider = GoogleEmbeddingProvider(
            _config(max_retries=1),
            transport=httpx.MockTransport(handler),
            credentials=_FakeCredentials(),
        )
        try:
            provider.embed_query("query")
        finally:
            provider.close()

        self.assertEqual(attempts, 2)
        sleep.assert_called_once()

    @patch("RAG.embeddings.time.sleep")
    def test_retries_transport_errors(self, sleep) -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise httpx.RemoteProtocolError("disconnected", request=request)
            return _response([1.0, *([0.0] * 1535)])

        provider = GoogleEmbeddingProvider(
            _config(max_retries=1),
            transport=httpx.MockTransport(handler),
            credentials=_FakeCredentials(),
        )
        try:
            provider.embed_query("query")
        finally:
            provider.close()

        self.assertEqual(attempts, 2)
        sleep.assert_called_once()


@skipUnless(
    os.getenv("RUN_VERTEX_EMBEDDING_INTEGRATION") == "1",
    "set RUN_VERTEX_EMBEDDING_INTEGRATION=1 to call Vertex AI",
)
class GoogleEmbeddingProviderIntegrationTestCase(TestCase):
    def test_real_vertex_api_embeds_document_and_query(self) -> None:
        provider = GoogleEmbeddingProvider(GoogleEmbeddingConfig.from_env())
        try:
            document = provider.embed_documents(
                ("Users must not publish credentials or private access tokens.",)
            )[0]
            query = provider.embed_query("Are secret tokens allowed?")
        finally:
            provider.close()

        self.assertEqual(len(document), 1536)
        self.assertEqual(len(query), 1536)
        self.assertAlmostEqual(math.hypot(*document), 1.0, places=6)
        self.assertAlmostEqual(math.hypot(*query), 1.0, places=6)
