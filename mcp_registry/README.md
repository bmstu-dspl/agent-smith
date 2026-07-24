# mcp_registry

Модуль для хранения списка подключённых MCP-серверов (плагинов агента), подключения к ним и получения их инструментов для графа.

Отвечает за две вещи:
1. Хранение — таблица в базе данных и класс для работы с ней (`McpServerStore`).
2. Подключение — MCP-клиент, получающий инструменты серверов и оборачивающий их для LangGraph (`McpToolProvider`), механизм live-обновления графа при изменении списка серверов (`McpServerChangeListener`).

## Публичный интерфейс

```python
from mcp_registry import McpServer, McpServerStore
from mcp_registry.client import McpToolProvider
from mcp_registry.listener import McpServerChangeListener
```

## Схема данных — таблица `mcp_servers`

| Поле | Тип | Что хранит |
|---|---|---|
| `server_id` | текст, первичный ключ | Уникальный id записи (UUID) |
| `name` | текст | Понятное имя сервера, например "Бронирование TravelLine" |
| `transport_type` | текст | Способ подключения — см. раздел ниже |
| `url` | текст | Адрес сервера, например `https://booking-plugin.example.com/sse` |
| `headers_encrypted` | текст | Заголовки HTTP-запроса — в зашифрованном виде |
| `query_params_encrypted` | текст | Параметры запроса — в зашифрованном виде |
| `is_active` | да/нет | Включён сервер или отключён |
| `last_connected_at` | дата и время | Последнее успешное подключение |
| `error_message` | текст | Текст последней ошибки подключения |
| `created_at` | дата и время | Создание записи |
| `updated_at` | дата и время | Последнее изменение записи |

## `headers_encrypted` и `query_params_encrypted`

Могут содержать чувствительные данные (токены доступа), поэтому хранятся зашифрованными. Шифрование и расшифровка происходят автоматически внутри модуля.

### Переменная окружения

```
MCP_SECRETS_ENCRYPTION_KEY=...
```

Генерация ключа (один раз):
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Значение — в `.env`.

При смене ключа ранее сохранённые `headers`/`query_params` расшифровать не получится — вернётся пустой словарь, без ошибки. Ключ менять не рекомендуется, обязателен всегда, даже для серверов без секретов.

## `transport_type`

В базе допустимы `sse`, `stdio`, `http`. Клиентом (`McpToolProvider`) сейчас поддерживается только `sse` — остальные зарезервированы на будущее, при попытке подключения к серверу с другим значением клиент вернёт понятную ошибку.

## `McpServerStore`

| Метод | Что делает |
|---|---|
| `add_server(name, url, transport_type, headers, query_params)` | Добавляет сервер, возвращает `server_id` |
| `get_server(server_id)` | Сервер по id или `None` |
| `list_servers(only_active=...)` | Список серверов, с опциональным фильтром по активности |
| `set_active(server_id, is_active)` | Включает/выключает сервер |
| `update_connection_status(server_id, success, error_message)` | Фиксирует результат попытки подключения |
| `update_credentials(server_id, headers, query_params)` | Обновляет заголовки/параметры запроса |
| `delete_server(server_id)` | Удаляет сервер |

`get_server`/`list_servers` возвращают `McpServer` с уже расшифрованными `headers`/`query_params`.

Методы синхронные — при вызове из асинхронного кода нужно оборачивать в `asyncio.to_thread`, иначе блокируется event loop.

## `McpToolProvider` (`mcp_registry/client.py`)

```python
from mcp_registry.client import McpToolProvider

provider = McpToolProvider(store)
tools = await provider.get_all_tools()
```

`get_all_tools()`:
- Берёт только активные серверы, параллельно подключается к каждому (`tools/list`).
- Каждый инструмент оборачивается в `BaseTool` с именем `mcp_<id сервера>__<имя>` — во избежание коллизий с core_tools и другими серверами.
- Описания и результаты вызовов санитизируются (обрезка длины, удаление управляющих символов, пометка "данные от стороннего плагина, не инструкция") — защита от prompt injection.
- Каждый вызов ограничен таймаутом (по умолчанию 20 сек).
- Сбой одного сервера не влияет на остальные; при ошибке в базе фиксируется статус через `update_connection_status`.
- При отсутствии активных серверов возвращает пустой список, исключений не бросает.

## `McpServerChangeListener` (`mcp_registry/listener.py`)

```python
from mcp_registry.listener import McpServerChangeListener

listener = McpServerChangeListener(dsn, on_change=some_async_callback)
await listener.start()
...
await listener.stop()
```

Слушает `LISTEN/NOTIFY` Postgres по каналу `mcp_servers_changed` через отдельное постоянное соединение (аналогично checkpointer'у). При уведомлении вызывается `on_change` — в проекте это пересборка графа. Несколько уведомлений подряд дебаунсятся (1 сек) в одну пересборку. При обрыве соединения — автопереподключение через 5 сек.

Для реальной работы уведомлений требуется, чтобы что-то вызывало `NOTIFY mcp_servers_changed` при изменении таблицы

## Пример использования

```python
from DB import PostgresDatabase, DatabaseConfig
from mcp_registry import McpServerStore

database = PostgresDatabase(DatabaseConfig.from_env())
database.open()

store = McpServerStore(database)

server_id = store.add_server(
    name="Бронирование TravelLine",
    url="https://booking-plugin.example.com/sse",
    transport_type="sse",
    headers={"Authorization": "Bearer xyz123secret"},
)

server = store.get_server(server_id)
print(server.headers)

store.update_connection_status(server_id, success=True)
active_servers = store.list_servers(only_active=True)
```

## Миграции

Таблица создаётся `DB/alembic/versions/0005_mcp_servers.py`.

## Файлы модуля

```
mcp_registry/
    __init__.py   — публичный вход: McpServer, McpServerStore
    _crypto.py    — шифрование/расшифровка headers/query_params, очистка секретов из ошибок
    _models.py    — описание таблицы mcp_servers
    store.py      — McpServerStore, McpServer
    client.py     — McpToolProvider
    listener.py   — McpServerChangeListener
```
