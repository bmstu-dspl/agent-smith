from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


def _deployment_fixture(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    remote = tmp_path / "origin.git"
    checkout = tmp_path / "checkout"
    mock_bin = tmp_path / "bin"
    command_log = tmp_path / "commands.jsonl"
    remote.mkdir()
    checkout.mkdir()
    mock_bin.mkdir()

    _run("git", "init", "--bare", str(remote), cwd=tmp_path)
    _run("git", "init", "-b", "main", cwd=checkout)
    _run("git", "config", "user.name", "Deploy Test", cwd=checkout)
    _run("git", "config", "user.email", "deploy-test@example.test", cwd=checkout)

    script_target = checkout / "deploy" / "update.sh"
    script_target.parent.mkdir()
    shutil.copy2(PROJECT_ROOT / "deploy" / "update.sh", script_target)
    (checkout / "docker-compose.yaml").write_text("services: {}\n", encoding="utf-8")
    _run("git", "add", ".", cwd=checkout)
    _run("git", "commit", "-m", "deployment fixture", cwd=checkout)
    _run("git", "remote", "add", "origin", str(remote), cwd=checkout)
    _run("git", "push", "-u", "origin", "main", cwd=checkout)

    docker_mock = mock_bin / "docker"
    docker_mock.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            from pathlib import Path
            import sys

            args = sys.argv[1:]
            with Path(os.environ["DEPLOY_TEST_COMMAND_LOG"]).open("a", encoding="utf-8") as log:
                log.write(json.dumps(["docker", *args]) + "\\n")

            if args[:3] == ["compose", "config", "--environment"]:
                print("APP_DOMAIN=deploy.example.test")
                print("ADMIN_PORT=8001")
            elif args[:3] == ["compose", "ps", "-q"]:
                pass
            elif args[:2] == ["compose", "ps"]:
                print("NAME STATUS")
                print("agent-smith healthy")
            elif args[:2] == ["compose", "up"] and os.getenv("DEPLOY_TEST_FAIL_UP") == "1":
                sys.exit(42)
            elif args[:2] == ["compose", "version"]:
                print("Docker Compose version test")
            sys.exit(0)
            """
        ),
        encoding="utf-8",
    )
    docker_mock.chmod(0o755)

    curl_mock = mock_bin / "curl"
    curl_mock.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            from pathlib import Path
            import sys

            with Path(os.environ["DEPLOY_TEST_COMMAND_LOG"]).open("a", encoding="utf-8") as log:
                log.write(json.dumps(["curl", *sys.argv[1:]]) + "\\n")
            """
        ),
        encoding="utf-8",
    )
    curl_mock.chmod(0o755)

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{mock_bin}{os.pathsep}{environment['PATH']}",
            "DEPLOY_TEST_COMMAND_LOG": str(command_log),
            "DEPLOY_SKIP_BACKUP": "true",
        }
    )
    return checkout, environment, command_log


def test_deploy_script_waits_for_health_and_prints_success_summary(tmp_path: Path) -> None:
    checkout, environment, command_log = _deployment_fixture(tmp_path)

    result = subprocess.run(
        ["./deploy/update.sh"],
        cwd=checkout,
        env=environment,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "DEPLOYMENT SUCCEEDED" in result.stdout
    assert "DEPLOY_STATUS=success" in result.stdout
    assert "https://deploy.example.test/admin" in result.stdout

    commands = [
        json.loads(line)
        for line in command_log.read_text(encoding="utf-8").splitlines()
    ]
    compose_up = next(command for command in commands if command[:3] == ["docker", "compose", "up"])
    assert "--wait" in compose_up
    assert "--wait-timeout" in compose_up
    assert any(
        command[0] == "curl" and "https://deploy.example.test/healthz" in command
        for command in commands
    )


def test_deploy_script_returns_diagnostics_when_rollout_fails(tmp_path: Path) -> None:
    checkout, environment, _command_log = _deployment_fixture(tmp_path)
    environment["DEPLOY_TEST_FAIL_UP"] = "1"

    result = subprocess.run(
        ["./deploy/update.sh"],
        cwd=checkout,
        env=environment,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 42
    assert "DEPLOYMENT FAILED" in result.stdout
    assert "stage:              Apply migrations and wait for healthy services" in result.stdout
    assert "DEPLOY_STATUS=failed stage=service-rollout" in result.stdout
    assert "--- docker compose ps --all ---" in result.stdout
    assert "--- recent deployment logs" in result.stdout
