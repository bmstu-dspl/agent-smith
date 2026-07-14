# Deployment strategy

## Target topology

Production deployment is a single Linux host with Docker Compose:

```text
Internet -> Caddy (TLS, 80/443) -> Telegram bot -> AI agent
                                      |
                                      +-> PostgreSQL + pgvector
```

- Only Caddy publishes host ports.
- PostgreSQL, bot, and AI agent communicate through an internal Docker network.
- Caddy obtains and renews TLS certificates through ACME.
- `migrate` is a one-shot service and must finish before application services start.
- PostgreSQL and Caddy state is stored in named volumes.
- Application containers run as a non-root user with a read-only root filesystem.

This topology is suitable for one production node. It is not highly available. For multi-node or zero-downtime operation, use an orchestrator and managed PostgreSQL; do not scale the stateful Compose services across hosts.

## Host prerequisites

- Linux host with Docker Engine and Docker Compose v2.
- DNS `A`/`AAAA` record for `APP_DOMAIN` pointing to the host.
- Inbound TCP `80`, TCP `443`, and UDP `443` allowed.
- Outbound HTTPS allowed for Telegram and ACME.
- Enough disk for PostgreSQL data, WAL, backups, and Docker image layers.

## Initial deployment

Clone the application source from GitHub with a read-only deploy key:

```bash
git clone git@github.com:bmstu-dspl/agent-smith.git
cd agent-smith
git switch main
```

Create configuration and secret files:

```bash
cp .env.example .env
mkdir -p secrets
chmod 700 secrets
printf '%s' 'replace-with-a-random-password' > secrets/postgres_password
printf '%s' 'replace-with-telegram-token' > secrets/bot_token
chmod 600 secrets/*
```

Set `APP_DOMAIN` in `.env`, then validate and start:

```bash
docker compose config --quiet
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs migrate
```

Deployment is successful when `postgres`, `ai-agent`, `bot`, and `caddy` are healthy/running and `migrate` exited with code `0`.

## Release process

1. Merge a tested PR into the protected `main` branch.
2. Create a PostgreSQL backup before schema changes.
3. On the production host, run `DEPLOY_BRANCH=main ./deploy/update.sh`.
4. Record the deployed Git SHA printed by the script.
5. Verify migration exit code, healthchecks, webhook delivery, and error rate.

`update.sh` refuses a dirty worktree or wrong branch, performs only `git pull --ff-only`, builds the application image locally from the checked-out source, labels it with the full Git SHA, and then recreates services. No application image is pulled from a Docker registry. PostgreSQL, Caddy, Python, and uv remain pinned third-party base images and are still obtained from their image registries.

Migrations must follow expand/contract rules: first add backward-compatible schema, then deploy code, then remove obsolete schema in a later release. A failed migration blocks bot and agent startup.

## Backup and restore

Create a logical backup outside the Docker volume:

```bash
mkdir -p backups
docker compose exec -T postgres pg_dump \
  -U "${POSTGRES_USER:-agent_smith}" \
  -d "${POSTGRES_DB:-agent_smith}" \
  --format=custom > "backups/agent-smith-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

Backups must be encrypted, copied off-host, retention-controlled, and periodically restored into a disposable database. A backup without a tested restore is not a recovery plan.

Restore is a maintenance operation:

```bash
docker compose stop bot ai-agent
docker compose exec -T postgres dropdb -U "${POSTGRES_USER:-agent_smith}" --force "${POSTGRES_DB:-agent_smith}"
docker compose exec -T postgres createdb -U "${POSTGRES_USER:-agent_smith}" "${POSTGRES_DB:-agent_smith}"
docker compose exec -T postgres pg_restore \
  -U "${POSTGRES_USER:-agent_smith}" \
  -d "${POSTGRES_DB:-agent_smith}" --clean --if-exists < backups/selected.dump
docker compose up -d
```

## Rollback

- Code-only failure: check out the previously recorded Git SHA, run `docker compose build` and `docker compose up -d --remove-orphans`.
- Backward-compatible migration: keep the new schema and roll back only the code.
- Destructive migration: stop services and restore the pre-deployment backup.
- Caddy or certificate failure: inspect Caddy logs, DNS, firewall, and ACME rate limits before retrying.

## Operations

```bash
docker compose ps
docker compose logs --since=15m bot ai-agent postgres caddy
docker compose exec postgres pg_isready -U "${POSTGRES_USER:-agent_smith}" -d "${POSTGRES_DB:-agent_smith}"
curl --fail "https://${APP_DOMAIN}/healthz"
```

Docker log rotation prevents unbounded local logs, but production should ship logs and metrics off-host. Alert at minimum on container restarts, healthcheck failures, disk pressure, PostgreSQL connection saturation, backup failure, and webhook error rate.

## Upgrade policy

- Application source is pulled from the protected GitHub `main` branch and built on the production host.
- Every deployment records the exact Git SHA for rollback and audit.
- PostgreSQL major upgrades require a separate tested migration plan.
- pgvector and Caddy use pinned version tags and are upgraded through a normal tested release.
- Dependency and container vulnerability scanning runs in CI.
