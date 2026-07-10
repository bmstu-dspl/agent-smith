# RAG

Модуль долгосрочной памяти для RAG-сценариев.

Модуль дает:
- доменную модель документа, версии и чанков
- use-case слой для ingestion/review/publish/search flow
- стабильный chunking текста
- in-memory store для тестов и локальной разработки
- PostgreSQL-backed store поверх общего модуля `DB`
- поиск по опубликованной памяти
- сбор текстового контекста для LLM-агента

## Публичный интерфейс

Использовать нужно только публичные импорты из `RAG`:

```python
from RAG import (
    IngestTextDocumentCommand,
    MemoryModule,
    PostgresDocumentStore,
    PublishVersionCommand,
    SearchPublishedMemoryQuery,
)
```

Внутренние модули вида `_domain.py`, `_repository.py`, `_service.py` и файлы в `application/`
напрямую не импортируются из внешнего кода.

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

Статусы версии:

- `draft`
- `processed`
- `approved`
- `rejected`
- `published`
- `archived`

Опубликованной считается только версия со статусом `published` и привязкой
`published_version_id` на документе.

## Быстрый старт с PostgreSQL

```python
from DB import DatabaseConfig, Migrator, PostgresDatabase
from RAG import (
    ApproveVersionCommand,
    IngestTextDocumentCommand,
    MemoryModule,
    PostgresDocumentStore,
    PublishVersionCommand,
    SearchPublishedMemoryQuery,
)

database = PostgresDatabase(DatabaseConfig.from_env())
database.open()

try:
    database.apply_migrations(Migrator().load())

    memory = MemoryModule(PostgresDocumentStore(database))

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
    database.close()
```

## Ingestion и chunking

`IngestTextDocumentCommand` создает документ при необходимости, добавляет версию,
делит текст на чанки и переводит версию в статус `processed`.

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

## Поиск и контекст агента

```python
from RAG import BuildAgentContextQuery, SearchPublishedMemoryQuery

results = memory.search_published_memory(
    SearchPublishedMemoryQuery(
        tenant_id="tenant-1",
        query="architecture decision",
        source_type="text",
        visibility="tenant",
        limit=8,
    )
)

context = memory.build_agent_context(
    BuildAgentContextQuery(
        tenant_id="tenant-1",
        query="architecture decision",
        limit=8,
    )
)
```

`build_agent_context` возвращает:

- исходный query
- готовый `context_text`
- список найденных `MemorySearchResultDTO`

## PostgreSQL schema

Миграции находятся в [../DB/migrations](/mnt/c/Users/geoka_ma3cw4e/project/agent-smith/DB/migrations:1).

RAG использует таблицы:

- `rag_documents`
- `rag_document_versions`
- `rag_chunks`

Поиск по чанкам использует PostgreSQL full-text search index:

- `idx_rag_chunks_text_fts`

## Тесты

```bash
uv run python -m unittest discover -s RAG/tests -v
```

Integration-тесты ожидают доступный PostgreSQL из `docker-compose.yaml`.

Если PostgreSQL не запущен:

```bash
docker compose up -d postgres
```

## Текущие ограничения

- ORM пока не используется: repository layer работает через общий DB-модуль и raw SQL.
- SQLAlchemy 2.x + Alembic стоит добавить отдельной задачей для persistence layer.
- Сейчас поддержан ingestion только plain text; PDF/DOCX/HTML extraction должен быть отдельным adapter layer.
- Vector search пока не реализован; текущий PostgreSQL-поиск использует FTS и fallback на `ILIKE`.

