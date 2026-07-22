# RAG

Модуль долгосрочной памяти для RAG-сценариев.

Модуль дает:
- доменную модель документа, версии и чанков
- use-case слой для ingestion/review/publish/search flow
- извлечение текста из DOCX, PDF, TXT, Markdown и HTML
- стабильный chunking текста
- in-memory store для тестов и локальной разработки
- PostgreSQL-backed store поверх общего модуля `DB`
- lexical, semantic и hybrid поиск по опубликованной памяти
- Vertex AI embedding provider с OAuth, retry и валидацией ответов
- хранение векторов в `pgvector` и HNSW cosine index
- сбор текстового контекста для LLM-агента

## Публичный интерфейс

Использовать нужно только публичные импорты из `RAG`:

```python
from RAG import (
    ArchiveVersionCommand,
    DeleteDocumentCommand,
    IngestFileDocumentCommand,
    IngestTextDocumentCommand,
    GoogleEmbeddingConfig,
    GoogleEmbeddingProvider,
    MemoryModule,
    PostgresDocumentStore,
    PublishVersionCommand,
    SearchPublishedMemoryQuery,
)
```

Внутренние модули вида `_domain.py`, `_repository.py`, `_service.py` и файлы в `application/`
напрямую не импортируются из внешнего кода.

Публичный фасад `MemoryModule` предоставляет операции:

- `create_document`, `add_document_version`, `ingest_text_document`, `ingest_file_document`;
- `mark_version_processed`, `approve_version`, `reject_version`, `publish_version`;
- `archive_version`, `delete_version`, `delete_document`;
- `get_document`, `list_documents`, `get_version_chunks`;
- `vectorize_version`, `search_published_memory`, `build_agent_context`.

## Основные сущности

- `Document` - агрегат документа в рамках tenant.
- `DocumentVersion` - версия документа с исходным текстом, статусом review и чанками.
- `Chunk` - фрагмент текста, который используется для поиска и сборки LLM-контекста.
- `MemoryModule` - фасад для прикладного Python API.
- `PostgresDocumentStore` - PostgreSQL-реализация хранилища.
- `InMemoryDocumentStore` - in-memory реализация для тестов.

## Lifecycle документа

Типовой flow:

1. `ingest_text_document`
2. `approve_version`
3. `publish_version`
4. `search_published_memory`
5. `build_agent_context`
6. `archive_version` или `delete_document`

Статусы версии:

- `draft`
- `processed`
- `approved`
- `rejected`
- `published`
- `archived`

Опубликованной считается только версия со статусом `published` и привязкой
`published_version_id` на документе.

Одновременно у документа может быть только одна опубликованная версия. Перед публикацией
другой версии текущую нужно архивировать. Опубликованную версию нельзя удалить без
архивации; удаление всего документа удаляет агрегат целиком.

## Быстрый старт с PostgreSQL

`DatabaseConfig.from_env()` и `GoogleEmbeddingConfig.from_env()` читают environment процесса и
не загружают `.env` автоматически. Для БД задайте `POSTGRES_DSN` либо полный набор
`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`/`POSTGRES_PASSWORD_FILE`.

```python
from DB import DatabaseConfig, PostgresDatabase
from RAG import (
    ApproveVersionCommand,
    GoogleEmbeddingConfig,
    GoogleEmbeddingProvider,
    IngestTextDocumentCommand,
    MemoryModule,
    PostgresDocumentStore,
    PublishVersionCommand,
    SearchPublishedMemoryQuery,
)

database = PostgresDatabase(DatabaseConfig.from_env())
embeddings = None

try:
    database.open()
    embeddings = GoogleEmbeddingProvider(GoogleEmbeddingConfig.from_env())
    database.migrate()

    memory = MemoryModule(
        PostgresDocumentStore(database),
        embedding_provider=embeddings,
    )

    result = memory.ingest_text_document(
        IngestTextDocumentCommand(
            document_id="doc-1",
            version_id="ver-1",
            tenant_id="tenant-1",
            title="Architecture notes",
            raw_text="Long-term memory text for the agent.",
            source_type="text",
            visibility="tenant",
            trust_level="trusted",
        )
    )

    memory.approve_version(
        ApproveVersionCommand(
            document_id=result.document.document_id,
            version_id=result.version.version_id,
            tenant_id=result.document.tenant_id,
        )
    )
    memory.publish_version(
        PublishVersionCommand(
            document_id=result.document.document_id,
            version_id=result.version.version_id,
            tenant_id=result.document.tenant_id,
        )
    )

    matches = memory.search_published_memory(
        SearchPublishedMemoryQuery(
            tenant_id="tenant-1",
            query="agent memory",
            limit=5,
        )
    )
finally:
    if embeddings is not None:
        embeddings.close()
    database.close()
```

Сохраните полный service account JSON вне Git и передайте путь через
`GOOGLE_APPLICATION_CREDENTIALS`. `project_id` читается из JSON; при необходимости его
можно переопределить через `GOOGLE_CLOUD_PROJECT`. В Compose один secret монтируется и в
`ai-agent`, и в `bot`. Для совместимости с AI agent в `.env` укажите
`GOOGLE_CLOUD_PROJECT`, равный `project_id` из JSON. Схема БД фиксирует размерность `1536`:

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/google_service_account.json
GOOGLE_CLOUD_PROJECT=
GOOGLE_EMBEDDING_LOCATION=us-central1
GOOGLE_EMBEDDING_MODEL=gemini-embedding-001
GOOGLE_EMBEDDING_DIMENSIONS=1536
GOOGLE_EMBEDDING_TIMEOUT=30
GOOGLE_EMBEDDING_MAX_RETRIES=3
```

Provider получает OAuth access token из service account JSON и вызывает Vertex AI
`POST /v1/projects/{project}/locations/{location}/publishers/google/models/{model}:predict`.
Используется `RETRIEVAL_DOCUMENT` для чанков, `RETRIEVAL_QUERY` для поискового запроса и
`outputDimensionality=1536`. `gemini-embedding-001` в Vertex AI принимает один текст на
вызов, поэтому документы отправляются последовательно. Ответ дополнительно валидируется
и L2-нормализуется. Retry выполняется для transport errors и HTTP `408`, `409`, `429`,
`500`, `502`, `503`, `504` с exponential backoff.

Opt-in smoke-тест реального Google API:

```bash
GOOGLE_APPLICATION_CREDENTIALS="$PWD/secrets/google_service_account.json" \
GOOGLE_EMBEDDING_LOCATION=us-central1 \
RUN_VERTEX_EMBEDDING_INTEGRATION=1 \
uv run python -m unittest \
  RAG.tests.test_embeddings.GoogleEmbeddingProviderIntegrationTestCase -v
```

Обычный test suite этот платный внешний вызов пропускает.

## Ingestion и chunking

`IngestTextDocumentCommand` создает документ при необходимости, добавляет версию,
делит текст на чанки и переводит версию в статус `processed`.

`IngestFileDocumentCommand` принимает загруженный файл в виде `bytes`, извлекает текст и
передает его в тот же ingestion flow. Поэтому chunking, embeddings, review, публикация,
поиск и сохранение работают так же, как для обычного текста:

```python
from pathlib import Path

from RAG import IngestFileDocumentCommand

file_path = Path("terms.pdf")
result = memory.ingest_file_document(
    IngestFileDocumentCommand(
        document_id="terms",
        version_id="terms-v1",
        tenant_id="tenant-1",
        title="Terms of service",
        file_name=file_path.name,
        file_content=file_path.read_bytes(),
        trust_level="trusted",
    )
)
```

Поддерживаемые форматы:

- `.txt` - UTF-8, сохраняется как `source_type="text"`;
- `.md`/`.markdown` - UTF-8, Markdown-разметка остается текстом;
- `.html`/`.htm` - берется видимый текст, `head`, `script`, `style`, `template` и
  `noscript` исключаются;
- `.docx` - извлекаются абзацы и таблицы в порядке документа;
- `.pdf` - извлекается существующий текстовый слой по страницам.

Тип определяется по расширению `file_name`, а безопасное базовое имя сохраняется в
`original_name`. Пустые, поврежденные, зашифрованные и неподдерживаемые файлы вызывают
`FileParsingError`/`UnsupportedFileTypeError` до записи документа. OCR не выполняется:
сканированный PDF без текстового слоя считается пустым.

Настройки chunking:

```python
from RAG import IngestTextDocumentCommand

command = IngestTextDocumentCommand(
    document_id="doc-1",
    version_id="ver-1",
    tenant_id="tenant-1",
    title="Notes",
    raw_text="First fact. Second fact. Third fact.",
    max_chunk_chars=1200,
    chunk_overlap_chars=150,
)
```

Chunker:

- режет текст по абзацам и предложениям
- добавляет overlap между чанками
- генерирует стабильные `chunk_id`
- сохраняет UTF-8 byte offsets исходного текста

`chunk_overlap_chars` применяется и между semantic chunks, и при разбиении больших фрагментов.

Если provider передан в `MemoryModule`, ingestion получает эмбеддинги до сохранения
обработанной версии. Ошибка provider не оставляет частично векторизованную версию.
Для старых версий используйте `VectorizeVersionCommand`:

```python
from RAG import VectorizeVersionCommand

chunks = memory.vectorize_version(
    VectorizeVersionCommand(
        document_id="doc-1",
        version_id="ver-1",
        tenant_id="tenant-1",
    )
)
```

Для векторизации provider обязателен, а версия уже должна содержать чанки. Архивированную
версию менять нельзя. Успешная операция обновляет embedding metadata и timestamps версии
и документа.

## Review и публикация

Версия должна быть обработана перед review:

```python
from RAG import ApproveVersionCommand, PublishVersionCommand

memory.approve_version(
    ApproveVersionCommand(
        document_id="doc-1",
        version_id="ver-1",
        tenant_id="tenant-1",
    )
)
memory.publish_version(
    PublishVersionCommand(
        document_id="doc-1",
        version_id="ver-1",
        tenant_id="tenant-1",
    )
)
```

Поиск работает только по опубликованным версиям.

Опубликованную версию можно архивировать через `ArchiveVersionCommand`. Архивация снимает
`published_version_id`, после чего версия исчезает из поиска и может быть удалена.

## Поиск и контекст агента

```python
from RAG import BuildAgentContextQuery, SearchPublishedMemoryQuery

results = memory.search_published_memory(
    SearchPublishedMemoryQuery(
        tenant_id="tenant-1",
        query="architecture decision",
        source_type="text",
        visibility="tenant",
        retrieval_mode="hybrid",
        limit=8,
    )
)

context = memory.build_agent_context(
    BuildAgentContextQuery(
        tenant_id="tenant-1",
        query="architecture decision",
        limit=8,
        max_context_chars=12000,
    )
)
```

`build_agent_context` возвращает:

- исходный query
- готовый `context_text`
- список найденных `MemorySearchResultDTO`

`max_context_chars` ограничивает размер готового контекста.

Каждый `MemorySearchResultDTO` содержит итоговый `score`, а также необязательные
`semantic_score` и `lexical_score`. Итоговый `score` является RRF-score и не равен cosine
similarity. Исходная cosine similarity доступна в `semantic_score`, PostgreSQL FTS/substring
оценка — в `lexical_score`.

Режимы retrieval:

- `semantic` - поиск по cosine similarity;
- `lexical` - текстовый поиск;
- `hybrid` - независимые semantic/lexical кандидаты и Reciprocal Rank Fusion.

`PostgresDocumentStore` выполняет semantic search через `pgvector`, а lexical search —
через PostgreSQL FTS с точным substring fallback. `InMemoryDocumentStore` вычисляет cosine
similarity в Python и поддерживает только case-insensitive exact substring lexical search.
In-memory адаптер подходит для тестов и локальной разработки, но набор lexical-кандидатов
может отличаться от PostgreSQL. Hybrid ranking в обоих адаптерах использует Reciprocal Rank
Fusion.

Semantic search выбирает только векторы, созданные текущей embedding-моделью. После
смены модели старые версии нужно повторно обработать через `VectorizeVersionCommand`.
Без provider режим `semantic` отклоняется, а `hybrid` безопасно деградирует до lexical.

## PostgreSQL schema

Alembic revisions находятся в [../DB/alembic/versions](../DB/alembic/versions).

RAG использует таблицы:

- `rag_documents`
- `rag_document_versions`
- `rag_chunks`

В `rag_chunks` хранятся nullable-поля `embedding vector(1536)`, `embedding_model` и
`embedded_at`. Миграция также включает расширение PostgreSQL `vector`.

Поиск по чанкам использует индексы:

- `idx_rag_chunks_text_fts` - GIN для full-text search;
- `idx_rag_chunks_embedding_hnsw` - HNSW с `vector_cosine_ops`.

## Тесты

```bash
uv run python -m unittest discover -s RAG/tests -v
```

Полный RAG E2E-набор с реальным PostgreSQL:

```bash
uv run python -m unittest RAG.tests.test_rag_e2e -v
```

E2E-тесты используют зафиксированные адаптации публичных GitHub Acceptable Use,
Mozilla Community Participation Guidelines и Python Software Foundation Code of Conduct.
URL источника сохраняется в `external_ref`. Сеть во время теста не нужна. Semantic и hybrid
сценарии используют детерминированный локальный embedding provider, поэтому проверяют RAG
flow независимо от доступности внешнего embedding API.

Integration-тесты запускаются с host и ожидают PostgreSQL на `127.0.0.1:POSTGRES_PORT`.
Production Compose намеренно не публикует порт БД, поэтому для локального тестового запуска
нужен временный override.

Минимальная настройка нового локального окружения. Существующие `.env` и secret-файлы
не перезаписывайте: сначала сверьте их значения.

```bash
test -f .env || cp .env.example .env
mkdir -p secrets
test -f secrets/postgres_password || \
  printf '%s' 'dev-postgres-password' > secrets/postgres_password
grep -q '^APP_DOMAIN=' .env || printf '\nAPP_DOMAIN=localhost\n' >> .env
grep -q '^POSTGRES_PASSWORD=' .env || \
  printf '\nPOSTGRES_PASSWORD=dev-postgres-password\n' >> .env
grep -q '^POSTGRES_PORT=' .env || printf '\nPOSTGRES_PORT=5432\n' >> .env
docker compose -f docker-compose.yaml -f - up -d postgres <<'YAML'
services:
  postgres:
    ports:
      - "127.0.0.1:${POSTGRES_PORT:-5432}:5432"
YAML
docker compose exec postgres pg_isready \
  -U "${POSTGRES_USER:-agent_smith}" \
  -d "${POSTGRES_DB:-agent_smith}"
uv run python -m unittest discover -s RAG/tests -v
```

Значение `POSTGRES_PASSWORD` в `.env` должно совпадать с содержимым
`secrets/postgres_password`: контейнер читает secret-файл, integration-тесты — `.env`.
`APP_DOMAIN` также должен быть задан, потому что Docker Compose интерполирует весь файл;
после копирования `.env.example` используется его placeholder-значение.
Временная публикация порта предназначена только для локального окружения; в production
используется исходный `docker-compose.yaml` без этого override.

## Текущие ограничения

- Persistence layer использует SQLAlchemy 2.x ORM и отделён от доменных сущностей mapper-функциями.
- Документы защищены optimistic locking через `revision`; stale aggregate не перезаписывает новые изменения.
- Сейчас поддержан ingestion только готового текста; извлечение PDF/DOCX/HTML должно быть отдельным adapter layer.
- Размерность вектора фиксирована на `1536`; её изменение требует новой миграции и полной повторной векторизации.
- Embedding provider синхронный; фоновые очереди ingestion и reranker пока не реализованы.
