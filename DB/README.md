# DB

Общий инфраструктурный модуль для работы с `PostgreSQL` в проекте.

Модуль дает:
- pooled соединения через `psycopg_pool`
- единый `PostgresDatabase` для query/transaction flow
- конфиг из env
- миграции через `schema_migrations`
- graph storage поверх PostgreSQL
- typed exceptions для инфраструктурного слоя

## Публичный интерфейс

Использовать нужно только публичные импорты:

```python
from DB import (
    DatabaseConfig,
    DatabaseConnectionError,
    DatabaseQueryError,
    GraphEdge,
    GraphNode,
    GraphStore,
    Migrator,
    PostgresDatabase,
)
```

Внутренние модули вида `_database.py`, `_graph.py` напрямую не импортируются.

## Переменные окружения

`DatabaseConfig.from_env()` по умолчанию читает переменные с префиксом `POSTGRES_`.

Обязательные:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Опциональные:

- `POSTGRES_DSN`
- `POSTGRES_MIN_POOL_SIZE`
- `POSTGRES_MAX_POOL_SIZE`
- `POSTGRES_CONNECT_TIMEOUT`
- `POSTGRES_POOL_WAIT_TIMEOUT`
- `POSTGRES_MAX_IDLE_SECONDS`
- `POSTGRES_MAX_LIFETIME_SECONDS`
- `POSTGRES_MAX_WAITING`
- `POSTGRES_POOL_WORKERS`
- `POSTGRES_SESSION_STATEMENTS`

Если задан `POSTGRES_DSN`, он используется приоритетно.

Пример:

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=agent_smith
POSTGRES_USER=agent_smith
POSTGRES_PASSWORD=secret
POSTGRES_MIN_POOL_SIZE=1
POSTGRES_MAX_POOL_SIZE=10
POSTGRES_SESSION_STATEMENTS=SET search_path TO public;SET TIME ZONE 'UTC'
```

## Базовое использование

```python
from DB import DatabaseConfig, Migrator, PostgresDatabase

config = DatabaseConfig.from_env()
database = PostgresDatabase(config)

database.open()
try:
    database.apply_migrations(Migrator().load())

    health = database.healthcheck()
    print(health["database_name"], health["schema_name"])

    database.execute(
        """
        INSERT INTO app_events (event_id, event_type)
        VALUES (%s, %s);
        """,
        ("evt-1", "document.created"),
    )

    row = database.fetch_one(
        "SELECT event_id, event_type FROM app_events WHERE event_id = %s;",
        ("evt-1",),
    )
finally:
    database.close()
```

## Lifecycle

Рекомендуемый порядок:

1. Создать `DatabaseConfig`
2. Создать `PostgresDatabase`
3. Вызвать `open()`
4. Применить миграции через `apply_migrations()`
5. Использовать `execute/fetch/transaction`
6. На shutdown вызвать `close()`

`initialize(ensure_vector_extension=True)` можно использовать, если нужен только ранний bootstrap пула и `vector` extension.

## Транзакции

```python
from DB import DatabaseConfig, PostgresDatabase

database = PostgresDatabase(DatabaseConfig.from_env())
database.open()

try:
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO graph_nodes (node_id, node_type, properties) VALUES (%s, %s, %s::jsonb);",
            ("node-1", "user", "{}"),
        )
        connection.execute(
            "INSERT INTO graph_nodes (node_id, node_type, properties) VALUES (%s, %s, %s::jsonb);",
            ("node-2", "project", "{}"),
        )
finally:
    database.close()
```

Если внутри транзакции возникает исключение, изменения откатываются, а наружу выбрасывается ошибка.

## Миграции

Миграции лежат в [migrations](/mnt/c/users/geoka_ma3cw4e/project/agent-smith/DB/migrations:1) и загружаются `Migrator()`.

Формат имени файла:

- `0001_core_extensions.sql`
- `0002_graph_store.sql`

Требования:

- только `.sql`
- в имени обязателен шаблон `version_name.sql`
- версии должны быть упорядочиваемыми лексикографически

Пример запуска:

```python
from DB import Migrator, PostgresDatabase, DatabaseConfig

database = PostgresDatabase(DatabaseConfig.from_env())
database.open()
try:
    applied = database.apply_migrations(Migrator().load())
    print(applied)
finally:
    database.close()
```

Информация о применении хранится в таблице `schema_migrations`.

## Graph Store

Graph storage предназначен для модулей, которым нужны сущности и связи поверх PostgreSQL.

Пример:

```python
from DB import DatabaseConfig, GraphEdge, GraphNode, GraphStore, Migrator, PostgresDatabase

database = PostgresDatabase(DatabaseConfig.from_env())
database.open()

try:
    database.apply_migrations(Migrator().load())

    graph = GraphStore(database)

    graph.upsert_node(
        GraphNode(
            node_id="user-1",
            node_type="user",
            properties={"name": "Alice"},
        )
    )
    graph.upsert_node(
        GraphNode(
            node_id="project-1",
            node_type="project",
            properties={"name": "Agent Smith"},
        )
    )
    graph.upsert_edge(
        GraphEdge(
            edge_id="edge-1",
            from_node_id="user-1",
            to_node_id="project-1",
            edge_type="owns",
            properties={"role": "owner"},
        )
    )

    node = graph.get_node("user-1")
    neighbors = graph.get_neighbors("user-1")
    traversal = graph.traverse("user-1", max_depth=3)
finally:
    database.close()
```

Под капотом используются таблицы:

- `graph_nodes`
- `graph_edges`

Они создаются миграцией `0002_graph_store.sql`.

## Исключения

Основные исключения:

- `DatabaseConfigurationError`
- `DatabaseConnectionError`
- `DatabaseQueryError`
- `MigrationError`

Типичный шаблон:

```python
from DB import (
    DatabaseConfig,
    DatabaseConnectionError,
    DatabaseQueryError,
    Migrator,
    MigrationError,
    PostgresDatabase,
)

try:
    database = PostgresDatabase(DatabaseConfig.from_env())
    database.open()
    database.apply_migrations(Migrator().load())
except DatabaseConnectionError:
    ...
except MigrationError:
    ...
except DatabaseQueryError:
    ...
finally:
    if "database" in locals():
        database.close()
```

## Что важно

- `PostgresDatabase` должен быть открыт через `open()` до любых query-операций
- после завершения работы pool нужно закрывать через `close()`
- миграции нужно применять до первого использования graph schema
- `GraphStore` не создает схему сам, он работает поверх уже примененных миграций

## Проверка

Модуль покрыт:

- unit tests: [DB/tests/test_database.py](/mnt/c/users/geoka_ma3cw4e/project/agent-smith/DB/tests/test_database.py:1)
- integration tests against docker PostgreSQL: [DB/tests/test_database_integration.py](/mnt/c/users/geoka_ma3cw4e/project/agent-smith/DB/tests/test_database_integration.py:1)
