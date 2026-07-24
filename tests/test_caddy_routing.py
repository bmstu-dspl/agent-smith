from pathlib import Path


def test_caddy_routes_admin_and_webhook_paths_to_separate_services() -> None:
    caddyfile = (
        Path(__file__).resolve().parents[1] / "deploy" / "Caddyfile"
    ).read_text(encoding="utf-8")

    admin_route = (
        "@admin path /admin /admin/*\n"
        "\thandle @admin {\n"
        "\t\treverse_proxy admin:8001\n"
        "\t}"
    )
    webhook_route = (
        "@webhook path /webhook/*\n"
        "\thandle @webhook {\n"
        "\t\treverse_proxy bot:8080\n"
        "\t}"
    )

    assert admin_route in caddyfile
    assert webhook_route in caddyfile
    assert caddyfile.index(admin_route) < caddyfile.index(webhook_route)
    assert "\trespond 404" in caddyfile
