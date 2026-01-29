# NRECA Pipeline Development Commands
# Requires: just (https://github.com/casey/just)
set dotenv-load

# Default recipe - show available commands
default:
    @just --list

# =============================================================================
# First-Time Setup
# =============================================================================

# Complete first-time setup: fix permissions, build, start, and migrate
setup:
    @echo "=== Setting up directories ==="
    mkdir -p logs venv_cache test_files
    docker run --rm -v "$(pwd)/logs:/logs" alpine chown -R 50000:0 /logs
    docker run --rm -v "$(pwd)/venv_cache:/venv_cache" alpine chown -R 50000:0 /venv_cache
    @echo ""
    @echo "=== Building containers ==="
    docker compose build
    @echo ""
    @echo "=== Starting services ==="
    docker compose up -d
    @echo ""
    @echo "=== Waiting for services to be ready (60s) ==="
    sleep 60
    @echo ""
    @echo "=== Running database migrations ==="
    just migrate
    @echo ""
    @echo "=== Setup complete! ==="
    @echo "Run 'just health' to verify services are running"
    @echo "Run 'just pipeline-all' to ingest documents"

# Fix directory permissions for Airflow (uid 50000)
fix-perms:
    mkdir -p logs venv_cache test_files
    docker run --rm -v "$(pwd)/logs:/logs" alpine chown -R 50000:0 /logs
    docker run --rm -v "$(pwd)/venv_cache:/venv_cache" alpine chown -R 50000:0 /venv_cache

# =============================================================================
# Docker Compose Commands
# =============================================================================

# Build all containers
build:
    docker compose build

# Build without cache
build-fresh:
    docker compose build --no-cache

# Start all services
up:
    docker compose up -d

# Stop all services
down:
    docker compose down

# Restart all services
restart:
    docker compose restart

# Show container status
status:
    docker compose ps

# =============================================================================
# Airflow Commands
# =============================================================================

# Lookup the auto-generated SAM password (Airflow 3.x generates one on startup)
lookup-pswd:
    @docker compose exec airflow-webserver cat /opt/airflow/simple_auth_manager_passwords.json.generated 2>/dev/null || docker compose logs airflow-webserver 2>&1 | grep "Password for user" | tail -1

# Show Airflow webserver logs
logs-airflow:
    docker compose logs --tail=100 airflow-webserver

# Show Airflow scheduler logs
logs-scheduler:
    docker compose logs --tail=100 airflow-scheduler

# List all DAGs
dags:
    docker compose exec airflow-scheduler airflow dags list

# Force DAG reserialization
reserialize:
    docker compose exec airflow-scheduler airflow dags reserialize

# Trigger a DAG manually (usage: just trigger ingestion_dag)
trigger dag_id:
    docker compose exec airflow-scheduler airflow dags trigger {{dag_id}}

# Trigger ingestion for specific file IDs (usage: just ingest-files "uuid1,uuid2")
ingest-files file_ids:
    docker compose exec airflow-scheduler airflow dags trigger ingestion_dag --conf '{"file_ids": ["{{file_ids}}"]}'

# Process all PENDING files (no arguments needed)
ingest-pending:
    docker compose exec airflow-scheduler airflow dags trigger ingestion_dag --conf '{"process_pending": true}'

# Process all PENDING files with custom limit
ingest-pending-limit limit:
    docker compose exec airflow-scheduler airflow dags trigger ingestion_dag --conf '{"process_pending": true, "pending_limit": {{limit}}}'

# =============================================================================
# Bulk File Operations (via API)
# =============================================================================

# Register all files from TEST_FILES_PATH directory
register-all:
    @docker compose exec api ls /data/files/ | grep -E '\.(pdf|txt|docx|doc)$' | jq -R -s 'split("\n") | map(select(length > 0))' | curl -s -X POST http://localhost:8000/ingest/register -H "Content-Type: application/json" -d @- | jq

# Register specific files (comma-separated)
register files:
    @echo '{"filenames": ["{{files}}"]}' | sed 's/,/","/g' | curl -s -X POST http://localhost:8000/ingest/register -H "Content-Type: application/json" -d @- | jq

# Trigger ingestion for all pending files via API
ingest-pending-api:
    @curl -s -X POST "http://localhost:8000/ingest/pending?limit=50" | jq

# Trigger ingestion with limit via API
ingest-pending-api-limit limit:
    @curl -s -X POST "http://localhost:8000/ingest/pending?limit={{limit}}" | jq

# Full pipeline: register all files then ingest
pipeline-all:
    @echo "=== Registering all files ===" && just register-all
    @echo ""
    @echo "=== Triggering ingestion ===" && just ingest-pending-api

# =============================================================================
# API Commands
# =============================================================================

# Show API logs
logs-api:
    docker compose logs --tail=100 api

# Check API health
health:
    @curl -s http://localhost:8000/health | jq

# Query documents (usage: just query "your question here")
query question:
    @curl -s -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"query": "{{question}}"}' | jq

# Rebuild and restart API only
rebuild-api:
    docker compose build api && docker compose up -d api

# =============================================================================
# Database Commands
# =============================================================================

# Connect to PostgreSQL
psql:
    psql "postgresql://app:app@localhost:5434/app"

# Run alembic migrations
migrate:
    DATABASE_URL="postgresql+psycopg://app:app@localhost:5434/app" uv run alembic upgrade head

# Show migration status
migrate-status:
    DATABASE_URL="postgresql+psycopg://app:app@localhost:5434/app" uv run alembic current

# =============================================================================
# ChromaDB Commands
# =============================================================================

# Check ChromaDB heartbeat
chroma-health:
    @curl -s http://localhost:8001/api/v2/heartbeat | jq

# List ChromaDB collections
chroma-collections:
    @curl -s "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database/collections" | jq '.[].name'

# =============================================================================
# Testing Commands
# =============================================================================

# Run all E2E tests
test:
    uv run pytest tests/e2e/ -v

# Run tests with short traceback
test-short:
    uv run pytest tests/e2e/ -v --tb=short

# Run specific test file
test-file file:
    uv run pytest {{file}} -v

# =============================================================================
# Development Commands
# =============================================================================

# Run linter
lint:
    uv run ruff check packages/ dags/

# Run linter with auto-fix
lint-fix:
    uv run ruff check packages/ dags/ --fix

# Format code
fmt:
    uv run ruff format packages/ dags/

# All logs (follow mode)
logs:
    docker compose logs -f

# Clean up test data from database
clean-test-data:
    psql "postgresql://app:app@localhost:5434/app" -c "DELETE FROM file_records WHERE filename LIKE 'test_%'; DELETE FROM dead_queue WHERE filename LIKE 'test_%';"

# Full reset: stop, remove volumes, rebuild, start
reset:
    docker compose down -v && docker compose build --no-cache && docker compose up -d && sleep 30 && just migrate
