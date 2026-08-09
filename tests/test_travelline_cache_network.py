from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_redis_joins_a_dedicated_external_travelline_cache_network() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yaml").read_text(encoding="utf-8")

    redis_section = compose[compose.index("  redis:"):compose.index("  migrate:")]
    assert "      - backend" in redis_section
    assert "      - travelline-cache" in redis_section
    assert "  travelline-cache:\n    external: true" in compose


def test_deploy_script_ensures_travelline_cache_network_exists() -> None:
    script = (PROJECT_ROOT / "deploy" / "update.sh").read_text(encoding="utf-8")

    assert "docker network inspect travelline-cache" in script
    assert "docker network create travelline-cache" in script
