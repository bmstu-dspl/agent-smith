#!/bin/sh
set -eu

# Production deployment entrypoint for both manual SSH sessions and CI/CD.
#
# Optional environment:
#   DEPLOY_BRANCH=main                 Git branch to deploy.
#   DEPLOY_EXPECTED_SHA=<full SHA>     Refuse to deploy another revision.
#   DEPLOY_WAIT_TIMEOUT=240            Compose health deadline in seconds.
#   DEPLOY_LOG_TAIL=200                Lines per service in failure report.
#   DEPLOY_SKIP_BACKUP=false           Skip the pre-deploy PostgreSQL backup.
#   DEPLOY_BACKUP_DIR=backups          Host directory for pg_dump files.
#   DEPLOY_LOCK_DIR=.git/deploy.lock   Prevent concurrent deployments.

branch="${DEPLOY_BRANCH:-main}"
expected_sha="${DEPLOY_EXPECTED_SHA:-}"
wait_timeout="${DEPLOY_WAIT_TIMEOUT:-240}"
log_tail="${DEPLOY_LOG_TAIL:-200}"
skip_backup="${DEPLOY_SKIP_BACKUP:-false}"
backup_dir="${DEPLOY_BACKUP_DIR:-backups}"
lock_dir="${DEPLOY_LOCK_DIR:-.git/deploy.lock}"

started_at="$(date +%s)"
stage="initialization"
stage_id="initialization"
compose_ready="false"
lock_acquired="false"
backup_path=""
previous_revision=""
deployed_revision=""
app_domain=""
admin_port="8001"

say() {
    printf '%s\n' "$*"
}

step() {
    stage_id="$1"
    stage="$2"
    say ""
    say "==> $stage"
}

is_true() {
    case "$1" in
        1|true|TRUE|yes|YES|on|ON) return 0 ;;
        *) return 1 ;;
    esac
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        say "required command is unavailable: $1" >&2
        return 1
    fi
}

release_lock() {
    if [ "$lock_acquired" = "true" ]; then
        rm -f "$lock_dir/pid"
        rmdir "$lock_dir" 2>/dev/null || true
    fi
}

failure_report() {
    exit_code="$1"
    current_revision="$(git rev-parse --short=12 HEAD 2>/dev/null || printf 'unknown')"

    say ""
    say "DEPLOYMENT FAILED"
    say "  stage:              $stage"
    say "  exit code:          $exit_code"
    say "  branch:             $branch"
    say "  previous revision:  ${previous_revision:-unknown}"
    say "  checkout revision:  $current_revision"
    say "  backup:             ${backup_path:-not created}"
    say ""
    say "The source checkout may have advanced while the previously running"
    say "containers remain active. Do not downgrade the database automatically."

    if [ "$compose_ready" = "true" ]; then
        say ""
        say "--- docker compose ps --all ---"
        docker compose ps --all 2>&1 || true
        say ""
        say "--- recent deployment logs (tail=$log_tail) ---"
        docker compose logs \
            --no-color \
            --tail="$log_tail" \
            migrate postgres redis ai-agent admin bot caddy 2>&1 || true
    fi

    say ""
    say "Suggested next checks:"
    say "  docker compose ps --all"
    say "  docker compose logs --tail=$log_tail migrate admin ai-agent bot caddy"
    if [ -n "$previous_revision" ]; then
        say "  previous code revision: $previous_revision"
    fi
    say "DEPLOY_STATUS=failed stage=$stage_id revision=$current_revision"
}

success_report() {
    finished_at="$(date +%s)"
    elapsed="$((finished_at - started_at))"

    say ""
    say "DEPLOYMENT SUCCEEDED"
    say "  branch:             $branch"
    say "  revision:           $deployed_revision"
    say "  previous revision:  $previous_revision"
    say "  elapsed:            ${elapsed}s"
    say "  backup:             ${backup_path:-not created}"
    say "  public health:       https://$app_domain/healthz"
    say "  admin:               https://$app_domain/admin"
    say ""
    docker compose ps
    say ""
    say "DEPLOY_STATUS=success revision=$deployed_revision elapsed_seconds=$elapsed"
}

finish() {
    exit_code="$?"
    trap - EXIT INT TERM
    set +e
    release_lock
    if [ "$exit_code" -eq 0 ]; then
        success_report
    else
        failure_report "$exit_code"
    fi
    exit "$exit_code"
}

trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

step "preflight" "Preflight checks"
require_command git
require_command docker
require_command curl

case "$wait_timeout" in
    ''|*[!0-9]*) say "DEPLOY_WAIT_TIMEOUT must be a positive integer" >&2; exit 2 ;;
esac
if [ "$wait_timeout" -eq 0 ]; then
    say "DEPLOY_WAIT_TIMEOUT must be a positive integer" >&2
    exit 2
fi
case "$log_tail" in
    ''|*[!0-9]*) say "DEPLOY_LOG_TAIL must be a positive integer" >&2; exit 2 ;;
esac
if [ "$log_tail" -eq 0 ]; then
    say "DEPLOY_LOG_TAIL must be a positive integer" >&2
    exit 2
fi

if ! mkdir "$lock_dir" 2>/dev/null; then
    say "another deployment may be running; lock exists: $lock_dir" >&2
    if [ -f "$lock_dir/pid" ]; then
        say "recorded process: $(cat "$lock_dir/pid")" >&2
    fi
    exit 1
fi
lock_acquired="true"
printf '%s\n' "$$" > "$lock_dir/pid"

current_branch="$(git branch --show-current)"
if [ "$current_branch" != "$branch" ]; then
    say "expected branch '$branch', current branch is '$current_branch'" >&2
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    say "working tree is not clean" >&2
    git status --short >&2
    exit 1
fi

previous_revision="$(git rev-parse HEAD)"

step "source-update" "Fetch and fast-forward $branch"
git fetch --prune origin "$branch"
target_revision="$(git rev-parse FETCH_HEAD)"

if [ -n "$expected_sha" ]; then
    case "$expected_sha" in
        *[!0-9a-fA-F]*) say "DEPLOY_EXPECTED_SHA must be a Git commit SHA" >&2; exit 2 ;;
    esac
    expected_revision="$(git rev-parse "$expected_sha^{commit}")"
    if [ "$target_revision" != "$expected_revision" ]; then
        say "origin/$branch is $target_revision, expected $expected_revision" >&2
        exit 1
    fi
fi

git merge --ff-only "$target_revision"
deployed_revision="$(git rev-parse HEAD)"
export VCS_REF="$deployed_revision"

step "configuration" "Validate configuration"
docker compose version
docker compose config --quiet
compose_ready="true"

compose_environment="$(docker compose config --environment)"
app_domain="$(
    printf '%s\n' "$compose_environment" |
        awk -F= '$1 == "APP_DOMAIN" { sub(/^[^=]*=/, ""); print; exit }'
)"
configured_admin_port="$(
    printf '%s\n' "$compose_environment" |
        awk -F= '$1 == "ADMIN_PORT" { sub(/^[^=]*=/, ""); print; exit }'
)"
if [ -n "$configured_admin_port" ]; then
    admin_port="$configured_admin_port"
fi
if [ -z "$app_domain" ]; then
    say "APP_DOMAIN is not resolved by Docker Compose" >&2
    exit 1
fi

step "networks" "Ensure deployment networks"
if ! docker network inspect mcp-network >/dev/null 2>&1; then
    docker network create mcp-network >/dev/null
    say "created external Docker network: mcp-network"
else
    say "external Docker network already exists: mcp-network"
fi

step "database-backup" "Create pre-deploy PostgreSQL backup"
postgres_container="$(docker compose ps -q postgres 2>/dev/null || true)"
postgres_running="false"
if [ -n "$postgres_container" ]; then
    postgres_running="$(
        docker inspect --format '{{.State.Running}}' "$postgres_container" 2>/dev/null ||
            printf 'false'
    )"
fi

if is_true "$skip_backup"; then
    say "backup explicitly skipped by DEPLOY_SKIP_BACKUP"
elif [ "$postgres_running" = "true" ]; then
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    short_previous="$(printf '%.12s' "$previous_revision")"
    umask 077
    mkdir -p "$backup_dir"
    chmod 700 "$backup_dir"
    backup_path="$backup_dir/agent-smith-$timestamp-$short_previous.dump"
    docker compose exec -T postgres sh -c \
        'pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom' \
        > "$backup_path"
    if [ ! -s "$backup_path" ]; then
        say "PostgreSQL backup is empty: $backup_path" >&2
        exit 1
    fi
    say "backup created: $backup_path"
else
    say "PostgreSQL is not currently running; no pre-deploy backup was created"
fi

step "image-build" "Build application images"
docker compose build --pull

step "service-rollout" "Apply migrations and wait for healthy services"
docker compose up \
    --detach \
    --remove-orphans \
    --wait \
    --wait-timeout "$wait_timeout"

step "admin-health" "Verify local admin health"
curl \
    --fail \
    --silent \
    --show-error \
    --retry 5 \
    --retry-all-errors \
    --connect-timeout 5 \
    --max-time 20 \
    "http://127.0.0.1:$admin_port/health" >/dev/null

step "public-health" "Verify public HTTPS endpoint"
curl \
    --fail \
    --silent \
    --show-error \
    --retry 5 \
    --retry-all-errors \
    --connect-timeout 10 \
    --max-time 30 \
    "https://$app_domain/healthz" >/dev/null

step "verified" "Deployment verified"
