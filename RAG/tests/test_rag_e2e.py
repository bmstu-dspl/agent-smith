from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy.schema import CreateSchema, DropSchema

from DB import DatabaseConfig, PostgresDatabase
from RAG import (
    ApproveVersionCommand,
    ArchiveVersionCommand,
    BuildAgentContextQuery,
    DeleteDocumentCommand,
    DeleteVersionCommand,
    DocumentNotFoundError,
    EmbeddingConfigurationError,
    GetDocumentQuery,
    IngestTextDocumentCommand,
    ListDocumentsQuery,
    MemoryModule,
    PostgresDocumentStore,
    PublishVersionCommand,
    RejectVersionCommand,
    SearchPublishedMemoryQuery,
    ValidationError,
    VectorizeVersionCommand,
)


@dataclass(slots=True, frozen=True)
class PolicyFixture:
    document_id: str
    title: str
    source_url: str
    text: str
    trust_level: str = "canonical"
    visibility: str = "tenant"


# Short, test-oriented adaptations of public policies. Kept in source control so E2E tests
# remain deterministic and do not depend on network availability or live policy changes.
# Sources checked 2026-07-16:
# - https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies
# - https://www.mozilla.org/en-US/about/governance/policies/participation/
# - https://policies.python.org/python.org/code-of-conduct/
GITHUB_ACCEPTABLE_USE = PolicyFixture(
    document_id="github-acceptable-use",
    title="GitHub Acceptable Use",
    source_url=(
        "https://docs.github.com/en/site-policy/acceptable-use-policies/"
        "github-acceptable-use-policies"
    ),
    text=(
        "Automated excessive bulk activity, phishing, and unauthorized access are prohibited. "
        "Users must protect privacy and avoid deceptive impersonation. Violations can lead to "
        "content removal or account suspension."
    ),
)

MOZILLA_PARTICIPATION = PolicyFixture(
    document_id="mozilla-participation",
    title="Mozilla Community Participation",
    source_url="https://www.mozilla.org/en-US/about/governance/policies/participation/",
    text=(
        "Community discussions must remain respectful and professional. Personal attacks, "
        "violence, threats, doxxing, and sustained disruption are unacceptable. Participants "
        "asked to stop harmful behavior must comply promptly."
    ),
)

PYTHON_CODE_OF_CONDUCT = PolicyFixture(
    document_id="python-code-of-conduct",
    title="Python Software Foundation Code of Conduct",
    source_url="https://policies.python.org/python.org/code-of-conduct/",
    text=(
        "Community members should be open, considerate, and respectful. Harassment, intimidation, "
        "publishing private information, violent threats, and continued unwanted communication "
        "are prohibited. Moderators may warn or expel offenders."
    ),
)

GITHUB_ACCEPTABLE_USE_V2 = PolicyFixture(
    document_id=GITHUB_ACCEPTABLE_USE.document_id,
    title=GITHUB_ACCEPTABLE_USE.title,
    source_url=GITHUB_ACCEPTABLE_USE.source_url,
    text=(
        "Promotional spam, fake accounts, cryptocurrency mining, and coordinated inauthentic "
        "activity are prohibited. Project advertising must remain relevant to the hosted project. "
        "Enforcement may include account suspension."
    ),
)


class RagEndToEndTestCase(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        env = {
            key: value
            for key, value in dotenv_values(env_path).items()
            if value is not None
        }
        cls._schema = f"test_rag_e2e_{uuid4().hex[:12]}"
        cls._database = PostgresDatabase(
            DatabaseConfig(
                dsn=_dsn_from_env(env),
                pool_size=4,
                max_overflow=0,
                session_statements=(f"SET search_path TO {cls._schema}, public",),
            )
        )
        cls._database.open()
        with cls._database.engine.begin() as connection:
            connection.execute(CreateSchema(cls._schema))
        cls._database.migrate()

    @classmethod
    def tearDownClass(cls) -> None:
        with cls._database.engine.begin() as connection:
            connection.execute(DropSchema(cls._schema, cascade=True, if_exists=True))
        cls._database.close()

    def setUp(self) -> None:
        self.tenant_id = f"tenant-{uuid4().hex}"
        self.now = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        self.provider = DeterministicPolicyEmbeddingProvider()
        self.memory = MemoryModule(
            PostgresDocumentStore(self._database),
            embedding_provider=self.provider,
            now_provider=lambda: self.now,
        )

    def test_ingest_moderate_publish_and_search_multiple_policies(self) -> None:
        github = self._ingest(GITHUB_ACCEPTABLE_USE, "github-v1")
        mozilla = self._ingest(MOZILLA_PARTICIPATION, "mozilla-v1")
        python = self._ingest(PYTHON_CODE_OF_CONDUCT, "python-v1")

        self.memory.approve_version(
            ApproveVersionCommand(github.document.document_id, "github-v1", self.tenant_id)
        )
        self.memory.publish_version(
            PublishVersionCommand(github.document.document_id, "github-v1", self.tenant_id)
        )
        self.memory.approve_version(
            ApproveVersionCommand(mozilla.document.document_id, "mozilla-v1", self.tenant_id)
        )
        self.memory.publish_version(
            PublishVersionCommand(mozilla.document.document_id, "mozilla-v1", self.tenant_id)
        )
        rejected = self.memory.reject_version(
            RejectVersionCommand(python.document.document_id, "python-v1", self.tenant_id)
        )

        self.assertEqual(rejected.review_status, "rejected")
        with self.assertRaises(ValidationError):
            self.memory.publish_version(
                PublishVersionCommand(python.document.document_id, "python-v1", self.tenant_id)
            )
        github_details = self.memory.get_document(
            GetDocumentQuery(self.tenant_id, GITHUB_ACCEPTABLE_USE.document_id)
        )
        self.assertEqual(
            github_details.versions[0].external_ref,
            GITHUB_ACCEPTABLE_USE.source_url,
        )

        phishing = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "phishing",
                retrieval_mode="lexical",
            )
        )
        attacks = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "personal attacks",
                retrieval_mode="lexical",
            )
        )
        rejected_policy = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "continued unwanted communication",
                retrieval_mode="lexical",
            )
        )

        self.assertEqual({item.document_id for item in phishing}, {GITHUB_ACCEPTABLE_USE.document_id})
        self.assertEqual({item.document_id for item in attacks}, {MOZILLA_PARTICIPATION.document_id})
        self.assertEqual(rejected_policy, ())

        published = self.memory.list_documents(
            ListDocumentsQuery(
                tenant_id=self.tenant_id,
                review_status="published",
                source_type="text",
                visibility="tenant",
            )
        )
        self.assertEqual(
            {item.document_id for item in published},
            {GITHUB_ACCEPTABLE_USE.document_id, MOZILLA_PARTICIPATION.document_id},
        )

    def test_semantic_hybrid_search_and_agent_context(self) -> None:
        for fixture, version_id in (
            (GITHUB_ACCEPTABLE_USE, "github-v1"),
            (MOZILLA_PARTICIPATION, "mozilla-v1"),
            (PYTHON_CODE_OF_CONDUCT, "python-v1"),
        ):
            self._ingest_approve_publish(fixture, version_id)

        semantic = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                tenant_id=self.tenant_id,
                query="credential theft and account break-ins",
                retrieval_mode="semantic",
                limit=1,
            )
        )
        hybrid = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                tenant_id=self.tenant_id,
                query="private information",
                retrieval_mode="hybrid",
                limit=2,
            )
        )
        context = self.memory.build_agent_context(
            BuildAgentContextQuery(
                tenant_id=self.tenant_id,
                query="how should communities handle harassment and threats",
                retrieval_mode="semantic",
                limit=2,
                max_context_chars=420,
            )
        )

        self.assertEqual(semantic[0].document_id, GITHUB_ACCEPTABLE_USE.document_id)
        self.assertIsNotNone(semantic[0].semantic_score)
        self.assertEqual(hybrid[0].document_id, PYTHON_CODE_OF_CONDUCT.document_id)
        self.assertIsNotNone(hybrid[0].semantic_score)
        self.assertIsNotNone(hybrid[0].lexical_score)
        self.assertLessEqual(len(context.context_text), 420)
        self.assertTrue(context.results)
        self.assertTrue(
            {item.document_id for item in context.results}
            <= {MOZILLA_PARTICIPATION.document_id, PYTHON_CODE_OF_CONDUCT.document_id}
        )

    def test_new_version_replaces_published_search_content(self) -> None:
        self._ingest_approve_publish(GITHUB_ACCEPTABLE_USE, "github-v1")
        old_results = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "phishing",
                retrieval_mode="lexical",
            )
        )
        self.assertTrue(old_results)

        self.memory.archive_version(
            ArchiveVersionCommand(
                GITHUB_ACCEPTABLE_USE.document_id,
                "github-v1",
                self.tenant_id,
            )
        )
        self._ingest(GITHUB_ACCEPTABLE_USE_V2, "github-v2")
        self.memory.approve_version(
            ApproveVersionCommand(
                GITHUB_ACCEPTABLE_USE.document_id,
                "github-v2",
                self.tenant_id,
            )
        )
        self.memory.publish_version(
            PublishVersionCommand(
                GITHUB_ACCEPTABLE_USE.document_id,
                "github-v2",
                self.tenant_id,
            )
        )

        old_results = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "phishing",
                retrieval_mode="lexical",
            )
        )
        new_results = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "cryptocurrency mining",
                retrieval_mode="lexical",
            )
        )
        details = self.memory.get_document(
            GetDocumentQuery(self.tenant_id, GITHUB_ACCEPTABLE_USE.document_id)
        )

        self.assertEqual(old_results, ())
        self.assertEqual({item.version_id for item in new_results}, {"github-v2"})
        self.assertEqual(details.document.published_version_id, "github-v2")
        self.assertEqual(
            {version.version_id: version.review_status for version in details.versions},
            {"github-v1": "archived", "github-v2": "published"},
        )

    def test_vectorize_legacy_version_then_archive_and_delete(self) -> None:
        legacy_memory = MemoryModule(
            PostgresDocumentStore(self._database),
            now_provider=lambda: self.now,
        )
        result = legacy_memory.ingest_text_document(
            _ingest_command(
                PYTHON_CODE_OF_CONDUCT,
                "python-legacy",
                self.tenant_id,
            )
        )
        legacy_memory.approve_version(
            ApproveVersionCommand(result.document.document_id, "python-legacy", self.tenant_id)
        )
        legacy_memory.publish_version(
            PublishVersionCommand(result.document.document_id, "python-legacy", self.tenant_id)
        )

        with self.assertRaises(EmbeddingConfigurationError):
            legacy_memory.search_published_memory(
                SearchPublishedMemoryQuery(
                    self.tenant_id,
                    "community safety",
                    retrieval_mode="semantic",
                )
            )

        chunks = self.memory.vectorize_version(
            VectorizeVersionCommand(
                PYTHON_CODE_OF_CONDUCT.document_id,
                "python-legacy",
                self.tenant_id,
            )
        )
        semantic = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "community safety and respectful participation",
                retrieval_mode="semantic",
                limit=1,
            )
        )

        self.assertTrue(all(chunk.is_embedded for chunk in chunks))
        self.assertEqual(semantic[0].document_id, PYTHON_CODE_OF_CONDUCT.document_id)

        self.memory.archive_version(
            ArchiveVersionCommand(
                PYTHON_CODE_OF_CONDUCT.document_id,
                "python-legacy",
                self.tenant_id,
            )
        )
        self.assertEqual(
            self.memory.search_published_memory(
                SearchPublishedMemoryQuery(
                    self.tenant_id,
                    "harassment",
                    retrieval_mode="lexical",
                )
            ),
            (),
        )
        self.memory.delete_version(
            DeleteVersionCommand(
                PYTHON_CODE_OF_CONDUCT.document_id,
                "python-legacy",
                self.tenant_id,
            )
        )
        self.memory.delete_document(
            DeleteDocumentCommand(PYTHON_CODE_OF_CONDUCT.document_id, self.tenant_id)
        )

        with self.assertRaises(DocumentNotFoundError):
            self.memory.get_document(
                GetDocumentQuery(self.tenant_id, PYTHON_CODE_OF_CONDUCT.document_id)
            )

    def test_tenant_source_and_visibility_filters_isolate_results(self) -> None:
        self._ingest_approve_publish(GITHUB_ACCEPTABLE_USE, "github-v1")
        private_fixture = PolicyFixture(
            document_id="private-mozilla-policy",
            title="Private Mozilla Policy",
            source_url=MOZILLA_PARTICIPATION.source_url,
            text=MOZILLA_PARTICIPATION.text,
            visibility="private",
        )
        self._ingest_approve_publish(private_fixture, "mozilla-private-v1")

        other_tenant = f"tenant-{uuid4().hex}"
        other_memory = MemoryModule(
            PostgresDocumentStore(self._database),
            embedding_provider=self.provider,
            now_provider=lambda: self.now,
        )
        other_result = other_memory.ingest_text_document(
            _ingest_command(MOZILLA_PARTICIPATION, "mozilla-other-v1", other_tenant)
        )
        other_memory.approve_version(
            ApproveVersionCommand(
                other_result.document.document_id,
                "mozilla-other-v1",
                other_tenant,
            )
        )
        other_memory.publish_version(
            PublishVersionCommand(
                other_result.document.document_id,
                "mozilla-other-v1",
                other_tenant,
            )
        )

        tenant_results = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "unacceptable",
                retrieval_mode="lexical",
            )
        )
        private_results = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "unacceptable",
                visibility="private",
                retrieval_mode="lexical",
            )
        )
        wrong_source = self.memory.search_published_memory(
            SearchPublishedMemoryQuery(
                self.tenant_id,
                "phishing",
                source_type="pdf",
                retrieval_mode="lexical",
            )
        )

        self.assertEqual({item.document_id for item in tenant_results}, {"private-mozilla-policy"})
        self.assertEqual({item.document_id for item in private_results}, {"private-mozilla-policy"})
        self.assertEqual(wrong_source, ())
        self.assertNotIn(
            MOZILLA_PARTICIPATION.document_id,
            {item.document_id for item in tenant_results},
        )

    def _ingest(self, fixture: PolicyFixture, version_id: str):
        return self.memory.ingest_text_document(
            _ingest_command(fixture, version_id, self.tenant_id)
        )

    def _ingest_approve_publish(self, fixture: PolicyFixture, version_id: str):
        result = self._ingest(fixture, version_id)
        self.memory.approve_version(
            ApproveVersionCommand(result.document.document_id, version_id, self.tenant_id)
        )
        self.memory.publish_version(
            PublishVersionCommand(result.document.document_id, version_id, self.tenant_id)
        )
        return result


class DeterministicPolicyEmbeddingProvider:
    model = "policy-e2e-embedding-v1"
    dimensions = 1536

    _TOPICS = (
        (
            "account-security",
            {
                "phishing",
                "unauthorized",
                "access",
                "credential",
                "credentials",
                "account",
                "break-ins",
            },
        ),
        (
            "community-conduct",
            {
                "community",
                "harassment",
                "threats",
                "violence",
                "respectful",
                "participation",
                "attacks",
                "doxxing",
                "intimidation",
            },
        ),
        (
            "privacy",
            {
                "privacy",
                "private",
                "information",
                "personal",
            },
        ),
        (
            "platform-abuse",
            {
                "spam",
                "bulk",
                "advertising",
                "cryptocurrency",
                "mining",
                "fake",
                "inauthentic",
            },
        ),
    )

    def embed_documents(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple(self._embed(text) for text in texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed(text)

    def _embed(self, text: str) -> tuple[float, ...]:
        tokens = {
            token.strip(".,:;!?()[]{}\"'").lower()
            for token in text.split()
        }
        vector = [0.0] * self.dimensions
        for index, (_, keywords) in enumerate(self._TOPICS):
            vector[index] = float(len(tokens & keywords))
        if not any(vector):
            vector[-1] = 1.0
        return tuple(vector)


def _ingest_command(
    fixture: PolicyFixture,
    version_id: str,
    tenant_id: str,
) -> IngestTextDocumentCommand:
    return IngestTextDocumentCommand(
        document_id=fixture.document_id,
        version_id=version_id,
        tenant_id=tenant_id,
        title=fixture.title,
        raw_text=fixture.text,
        source_type="text",
        visibility=fixture.visibility,
        chunk_visibility=fixture.visibility,
        trust_level=fixture.trust_level,
        external_ref=fixture.source_url,
        original_name=f"{fixture.document_id}.txt",
        max_chunk_chars=180,
        chunk_overlap_chars=30,
    )


def _dsn_from_env(env: dict[str, str]) -> str:
    direct_dsn = os.environ.get("DB_TEST_POSTGRES_DSN")
    if direct_dsn:
        return direct_dsn

    for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT"):
        if not env.get(key):
            raise ValueError(f"missing {key} in .env")

    host = os.environ.get("DB_TEST_POSTGRES_HOST") or os.environ.get("POSTGRES_HOST") or "127.0.0.1"
    port = os.environ.get("DB_TEST_POSTGRES_PORT") or env["POSTGRES_PORT"]
    user = os.environ.get("DB_TEST_POSTGRES_USER") or env["POSTGRES_USER"]
    password = os.environ.get("DB_TEST_POSTGRES_PASSWORD") or env["POSTGRES_PASSWORD"]
    database = os.environ.get("DB_TEST_POSTGRES_DB") or env["POSTGRES_DB"]
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"
