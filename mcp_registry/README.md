# mcp_registry

Модуль для хранения списка подключённых MCP-серверов (плагинов агента).

Модуль отвечает только за хранение: таблицу в базе данных и класс для работы с ней. Само подключение к MCP-серверам (проверка связи, получение списка инструментов, вызов инструментов) в данном модуле не выполняется.

## Публичный интерфейс

```python
from mcp_registry import McpServer, McpServerStore
```


## Схема данных — таблица `mcp_servers`

| Поле | Тип | Что хранит |
|---|---|---|
| `server_id` | текст, первичный ключ | Уникальный id записи, генерируется автоматически (UUID) при добавлении сервера |
| `name` | текст | Понятное имя сервера для людей, например "Бронирование TravelLine" |
| `transport_type` | текст | Способ подключения к серверу. Разрешены только строго определённые значения — см. раздел ниже |
| `url` | текст | Адрес сервера, например `https://booking-plugin.example.com/sse` |
| `headers_encrypted` | текст | Заголовки HTTP-запроса (например, токен авторизации) — **хранятся в зашифрованном виде** |
| `query_params_encrypted` | текст | Параметры запроса в адресной строке — **хранятся в зашифрованном виде** |
| `is_active` | да/нет | Включён сервер или отключён администратором |
| `last_connected_at` | дата и время | Когда в последний раз удалось успешно подключиться к серверу |
| `error_message` | текст | Текст последней ошибки подключения, если сервер сейчас недоступен |
| `created_at` | дата и время | Когда запись создана |
| `updated_at` | дата и время | Когда запись последний раз менялась |

## Важный нюанс: `headers_encrypted` и `query_params_encrypted`

В этих двух полях может лежать чувствительная информация — например, токен доступа к серверу плагина. Поэтому они хранятся в базе в зашифрованном виде.
Шифрование и расшифрование происходят автоматически внутри модуля.

### Обязательная переменная окружения

Для шифрования нужен ключ. Он задаётся через переменную окружения:

```
MCP_SECRETS_ENCRYPTION_KEY=...
```

Получить ключ (выполнить один раз в терминале):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Полученную строку положить в `.env`

**Важно:** если этот ключ поменять — все уже сохранённые в базе `headers`/`query_params` станет невозможно расшифровать. Модуль в этом случае не выдаст ошибку, а вернёт пустой словарь `{}` вместо реальных данных — то есть данные не потеряются физически, но станут недоступны для чтения. Ключ менять не рекомендуется, он обязателен всегда, даже для серверов без секретов.


## `McpServerStore`

Класс для работы с таблицей. Все методы работают с обычными Python-объектами, всё шифрование скрыто внутри.

| Метод | Что делает |
|---|---|
| `add_server(name, url, transport_type, headers, query_params)` | Добавляет новый сервер, возвращает его `server_id` |
| `get_server(server_id)` | Возвращает один сервер по id, или `None`, если не найден |
| `list_servers(only_active=...)` | Возвращает список всех серверов. Можно попросить только включённые (`only_active=True`) |
| `set_active(server_id, is_active)` | Включает или выключает сервер |
| `update_connection_status(server_id, success, error_message)` | Записывает результат попытки подключения к серверу — успех или ошибку |
| `update_credentials(server_id, headers, query_params)` | Меняет заголовки или параметры запроса, например при смене токена доступа |
| `delete_server(server_id)` | Удаляет сервер из базы полностью |

Результат чтения (`get_server`, `list_servers`) — объект `McpServer`, у которого `headers` и `query_params` уже расшифрованы и представлены как обычные словари.


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
print(server.headers)  # {"Authorization": "Bearer xyz123secret"} — уже расшифровано

store.update_connection_status(server_id, success=True)

active_servers = store.list_servers(only_active=True)
```

## Миграции

Таблица `mcp_servers` создаётся Alembic-миграцией `DB/alembic/versions/0005_mcp_servers.py`.

## Файлы модуля

```
mcp_registry/
    __init__.py     — публичный вход: McpServer, McpServerStore
    _crypto.py      — шифрование и расшифровка headers/query_params, очистка секретов из текста ошибки
    _models.py      — описание таблицы mcp_servers для базы данных
    store.py        — McpServerStore и класс McpServer
```
