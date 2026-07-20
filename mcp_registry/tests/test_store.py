import pytest

from DB import DatabaseQueryError
from mcp_registry import McpServerStore

pytestmark = pytest.mark.asyncio if False else None 

# --- add_server / get_server ---


def test_add_and_get_server(store: McpServerStore):
    server_id = store.add_server(
        name="Бронирование TravelLine",
        url="https://booking-plugin.example.com/sse",
        transport_type="sse",
        headers={"Authorization": "Bearer xyz123secret"},
    )

    server = store.get_server(server_id)

    assert server is not None
    assert server.server_id == server_id
    assert server.name == "Бронирование TravelLine"
    assert server.url == "https://booking-plugin.example.com/sse"
    assert server.transport_type == "sse"
    assert server.headers == {"Authorization": "Bearer xyz123secret"}
    assert server.query_params == {}
    assert server.is_active is True
    assert server.last_connected_at is None
    assert server.error_message is None


def test_get_server_returns_none_when_missing(store: McpServerStore):
    assert store.get_server("does-not-exist") is None


def test_add_server_without_headers_defaults_to_empty_dict(store: McpServerStore):
    """headers/query_params не переданы вообще — не должно падать, должны стать пустыми словарями."""
    server_id = store.add_server(name="Minimal", url="https://example.com/sse")

    server = store.get_server(server_id)

    assert server.headers == {}
    assert server.query_params == {}
    assert server.transport_type == "sse"  # значение по умолчанию


def test_add_server_with_query_params(store: McpServerStore):
    server_id = store.add_server(
        name="With query",
        url="https://example.com/sse",
        query_params={"tenant": "hotel-42"},
    )

    server = store.get_server(server_id)

    assert server.query_params == {"tenant": "hotel-42"}


def test_add_server_generates_unique_ids(store: McpServerStore):
    """Два сервера с одинаковыми полями всё равно должны получить разные id и не конфликтовать."""
    first_id = store.add_server(name="Same name", url="https://example.com/sse")
    second_id = store.add_server(name="Same name", url="https://example.com/sse")

    assert first_id != second_id
    assert store.get_server(first_id) is not None
    assert store.get_server(second_id) is not None


# --- list_servers ---


def test_list_servers_returns_all_by_default(store: McpServerStore):
    store.add_server(name="A", url="https://a.example.com/sse")
    store.add_server(name="B", url="https://b.example.com/sse")

    servers = store.list_servers()

    assert len(servers) == 2
    assert {s.name for s in servers} == {"A", "B"}


def test_list_servers_only_active_filters_disabled(store: McpServerStore):
    active_id = store.add_server(name="Active", url="https://active.example.com/sse")
    inactive_id = store.add_server(name="Inactive", url="https://inactive.example.com/sse")
    store.set_active(inactive_id, False)

    servers = store.list_servers(only_active=True)

    assert [s.server_id for s in servers] == [active_id]


def test_list_servers_empty_when_none_added(store: McpServerStore):
    assert store.list_servers() == []


def test_list_servers_headers_are_decrypted(store: McpServerStore):
    """Убедиться, что при чтении списка (не одного сервера) шифрование тоже прозрачно снимается."""
    store.add_server(
        name="Secret server",
        url="https://example.com/sse",
        headers={"Authorization": "Bearer secret-token"},
    )

    servers = store.list_servers()

    assert servers[0].headers == {"Authorization": "Bearer secret-token"}


# --- set_active ---


def test_set_active_toggles_flag(store: McpServerStore):
    server_id = store.add_server(name="Toggle me", url="https://example.com/sse")

    store.set_active(server_id, False)
    assert store.get_server(server_id).is_active is False

    store.set_active(server_id, True)
    assert store.get_server(server_id).is_active is True


def test_set_active_on_missing_server_does_not_raise(store: McpServerStore):
    """UPDATE на несуществующий id просто ничего не меняет, не должно падать с ошибкой."""
    store.set_active("does-not-exist", False)  # не должно бросить исключение


# --- update_connection_status ---


def test_update_connection_status_success_sets_last_connected_and_clears_error(store: McpServerStore):
    server_id = store.add_server(name="X", url="https://example.com/sse")
    store.update_connection_status(server_id, success=False, error_message="first failure")

    store.update_connection_status(server_id, success=True)

    server = store.get_server(server_id)
    assert server.last_connected_at is not None
    assert server.error_message is None


def test_update_connection_status_failure_stores_sanitized_message(store: McpServerStore):
    server_id = store.add_server(
        name="X",
        url="https://example.com/sse",
        headers={"Authorization": "Bearer top-secret-value"},
    )

    store.update_connection_status(
        server_id,
        success=False,
        error_message="request failed: Authorization=Bearer top-secret-value",
    )

    server = store.get_server(server_id)
    assert "top-secret-value" not in server.error_message
    assert "***REDACTED***" in server.error_message
    assert server.last_connected_at is None


def test_update_connection_status_failure_without_message_leaves_error_message_untouched(store: McpServerStore):
    """success=False, error_message=None — ничего не падает, поле не трогается."""
    server_id = store.add_server(name="X", url="https://example.com/sse")

    store.update_connection_status(server_id, success=False, error_message=None)

    server = store.get_server(server_id)
    assert server.error_message is None


def test_update_connection_status_on_missing_server_does_not_raise(store: McpServerStore):
    """get_server внутри update_connection_status вернёт None — secrets должны стать {} и не упасть."""
    store.update_connection_status("does-not-exist", success=False, error_message="some error")


def test_update_connection_status_overwrites_previous_error(store: McpServerStore):
    server_id = store.add_server(name="X", url="https://example.com/sse")

    store.update_connection_status(server_id, success=False, error_message="first error")
    store.update_connection_status(server_id, success=False, error_message="second error")

    server = store.get_server(server_id)
    assert server.error_message == "second error"


# --- update_credentials ---


def test_update_credentials_replaces_headers(store: McpServerStore):
    server_id = store.add_server(
        name="X", url="https://example.com/sse", headers={"Authorization": "Bearer old"}
    )

    store.update_credentials(server_id, headers={"Authorization": "Bearer new"})

    server = store.get_server(server_id)
    assert server.headers == {"Authorization": "Bearer new"}


def test_update_credentials_only_headers_leaves_query_params_untouched(store: McpServerStore):
    server_id = store.add_server(
        name="X",
        url="https://example.com/sse",
        headers={"Authorization": "Bearer old"},
        query_params={"tenant": "hotel-1"},
    )

    store.update_credentials(server_id, headers={"Authorization": "Bearer new"})

    server = store.get_server(server_id)
    assert server.query_params == {"tenant": "hotel-1"}


def test_update_credentials_with_nothing_passed_changes_nothing(store: McpServerStore):
    server_id = store.add_server(
        name="X", url="https://example.com/sse", headers={"Authorization": "Bearer keep-me"}
    )

    store.update_credentials(server_id)

    server = store.get_server(server_id)
    assert server.headers == {"Authorization": "Bearer keep-me"}


# --- delete_server ---


def test_delete_server_removes_it(store: McpServerStore):
    server_id = store.add_server(name="To delete", url="https://example.com/sse")

    store.delete_server(server_id)

    assert store.get_server(server_id) is None


def test_delete_server_on_missing_id_does_not_raise(store: McpServerStore):
    store.delete_server("does-not-exist")  # не должно бросить исключение


def test_delete_server_does_not_affect_others(store: McpServerStore):
    keep_id = store.add_server(name="Keep", url="https://keep.example.com/sse")
    delete_id = store.add_server(name="Delete", url="https://delete.example.com/sse")

    store.delete_server(delete_id)

    assert store.get_server(keep_id) is not None
    assert store.get_server(delete_id) is None


# --- ограничение на transport_type (constraint на уровне базы) ---


def test_invalid_transport_type_is_rejected_by_database(store: McpServerStore):
    """База не должна принимать произвольные значения transport_type — только то,
    что разрешено constraint'ом. Если тест падает из-за изменения списка разрешённых
    значений — значит нужно обновить и этот тест, и README."""
    with pytest.raises(DatabaseQueryError):
        store.add_server(name="Bad transport", url="https://example.com/sse", transport_type="not_a_real_transport")
