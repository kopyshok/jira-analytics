#!/usr/bin/env bash
# Run the backend test suite against a local Postgres container.
# Usage: ./scripts/run_tests_postgres.sh [pytest-args...]
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose_file="$script_dir/../docker-compose.test.yml"

docker compose -f "$compose_file" up -d

cleanup() {
    docker compose -f "$compose_file" down
}
trap cleanup EXIT

# Wait for healthcheck (up to 60s)
status=""
for _ in $(seq 1 60); do
    status=$(docker inspect -f '{{.State.Health.Status}}' jira-analytics-test-pg 2>/dev/null || echo "starting")
    if [ "$status" = "healthy" ]; then break; fi
    sleep 1
done
if [ "$status" != "healthy" ]; then
    echo "Postgres test container did not become healthy within 60s" >&2
    exit 1
fi

export TEST_DATABASE_URL="postgresql://test:test@localhost:55432/jira_analytics_test"
python -m pytest tests/ "$@"
