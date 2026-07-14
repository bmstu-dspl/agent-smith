# DB

Общий persistence-модуль проекта для PostgreSQL на SQLAlchemy 2.x и Alembic.

Модуль отвечает за SQLAlchemy engine и пул соединений, транзакционный `Session` boundary, общий declarative base, Alembic-миграции и ORM-хранилище графа.

## Публичный интерфейс

```python
from DB import (
    DatabaseConfig,
    GraphEdge,
    GraphNode,
    GraphStore,
    Migrator,
    OrmBase,
    PostgresDatabase,
)
```

Модули с префиксом `_` являются внутренними. Прямые SQL helper-функции не экспортируются: прикладные модули работают через ORM и `Session`.

## Подключение

```python
from DB import DatabaseConfig, PostgresDatabase

database = PostgresDatabase(DatabaseConfig.from_env())
database.open()
try:
    database.migrate()
    print(database.healthcheck())
finally:
    database.close()
```

`open()` создаёт SQLAlchemy engine с пулом, `pool_pre_ping` и ограничениями из `DatabaseConfig`. `close()` освобождает пул.

## Конфигурация

`DatabaseConfig.from_env()` читает `POSTGRES_DSN` либо собирает DSN из `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` и `POSTGRES_PASSWORD`.

Настройки пула: `POSTGRES_POOL_SIZE`, `POSTGRES_MAX_OVERFLOW`, `POSTGRES_POOL_TIMEOUT`, `POSTGRES_POOL_RECYCLE`, `POSTGRES_CONNECT_TIMEOUT` и `POSTGRES_SESSION_STATEMENTS`.

## ORM-модель модуля

```python
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from DB import OrmBase


class AuditRecordModel(OrmBase):
    __tablename__ = "audit_records"

    record_id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
```

ORM-модель остаётся во внутреннем infrastructure-слое своего модуля. Доменная сущность не наследуется от `OrmBase`. Чтобы Alembic видел новую модель при autogenerate, её модуль нужно импортировать в `DB/alembic/env.py`.

## Транзакции

```python
from sqlalchemy import select

with database.session() as session:
    session.add(AuditRecordModel(record_id="record-1", event_type="memory.created"))

with database.session() as session:
    record = session.scalar(
        select(AuditRecordModel).where(AuditRecordModel.record_id == "record-1")
    )
```

Контекст `session()` фиксирует успешную транзакцию, откатывает её при исключении и всегда закрывает Session. SQLAlchemy-ошибки преобразуются в `DatabaseQueryError`.

## Миграции

Runtime-применение всех revision:

```python
database.migrate()
```

Проверка состояния:

```python
from DB import Migrator

if not Migrator(database).is_current():
    raise RuntimeError("database schema is outdated")
```

Создание и применение migration после изменения ORM-моделей:

```bash
POSTGRES_HOST=127.0.0.1 uv run alembic -c DB/alembic.ini revision --autogenerate -m "add audit records"
POSTGRES_HOST=127.0.0.1 uv run alembic -c DB/alembic.ini upgrade head
POSTGRES_HOST=127.0.0.1 uv run alembic -c DB/alembic.ini current --check-heads
```

Alembic CLI загружает корневой `.env`; при запуске с хоста compose hostname `postgres` нужно переопределить на `127.0.0.1`. Runtime передаёт Alembic уже открытое SQLAlchemy-соединение.

Каталог `DB/migrations` содержит legacy SQL baseline предыдущей реализации. Runtime его не читает; Alembic baseline безопасно принимает уже созданные таблицы без потери данных.

## GraphStore

```python
from DB import GraphEdge, GraphNode, GraphStore

graph = GraphStore(database)
graph.upsert_node(GraphNode("user-1", "user", {"name": "Alice"}))
graph.upsert_node(GraphNode("project-1", "project", {"name": "Agent Smith"}))
graph.upsert_edge(GraphEdge("edge-1", "user-1", "project-1", "owns", {}))

node = graph.get_node("user-1")
neighbors = graph.get_neighbors("user-1", edge_type="owns")
path = graph.traverse("user-1", max_depth=3)
```

Upsert выполняется PostgreSQL `ON CONFLICT` через SQLAlchemy DML, чтение через ORM expressions, обход графа через recursive CTE expression.

## Проверка

```bash
docker compose up -d postgres
uv run python -m unittest discover -s DB/tests -v
uv run python -m unittest discover -s RAG/tests -v
```
