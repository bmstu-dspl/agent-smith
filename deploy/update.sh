#!/bin/sh
set -eu

branch="${DEPLOY_BRANCH:-main}"
current_branch="$(git branch --show-current)"

if [ "$current_branch" != "$branch" ]; then
    echo "expected branch '$branch', current branch is '$current_branch'" >&2
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "working tree is not clean" >&2
    exit 1
fi

git pull --ff-only origin "$branch"
revision="$(git rev-parse --short=12 HEAD)"
VCS_REF="$(git rev-parse HEAD)"
export VCS_REF

docker compose config --quiet
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps

echo "deployed Git revision: $revision"
