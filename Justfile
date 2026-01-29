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
    @echo "=== Initializing Airflow DAGs ==="
    just reserialize
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

# Stop all services and release ports (data persists in volumes)
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

# Show Airflow credentials (user and generated password)
airflow-pswd:
    #!/usr/bin/env bash
    json=$(docker compose exec airflow-webserver cat /opt/airflow/simple_auth_manager_passwords.json.generated 2>/dev/null)
    if [ -n "$json" ]; then
        user=$(echo "$json" | jq -r 'keys[0]')
        pswd=$(echo "$json" | jq -r '.[keys[0]]')
        echo "Airflow Credentials"
        echo "───────────────────"
        echo "  User:     $user"
        echo "  Password: $pswd"
    else
        echo "Could not retrieve credentials. Check logs with: just logs-airflow"
    fi

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

# Process all PENDING files via Airflow CLI
ingest-pending:
    docker compose exec airflow-scheduler airflow dags trigger ingestion_dag --conf '{"process_pending": true}'

# =============================================================================
# Bulk File Operations (via API)
# =============================================================================

# Register all files from TEST_FILES_PATH directory
register-all:
    @docker compose exec api ls /data/files/ | grep -E '\.(pdf|txt|docx|doc)$' | jq -R -s '{filenames: (split("\n") | map(select(length > 0)))}' | curl -s -X POST http://localhost:8000/ingest/register -H "Content-Type: application/json" -d @- | jq

# Register specific files (comma-separated)
register files:
    @echo '{"filenames": ["{{files}}"]}' | sed 's/,/","/g' | curl -s -X POST http://localhost:8000/ingest/register -H "Content-Type: application/json" -d @- | jq

# Trigger ingestion for all pending files via API
ingest-pending-api limit="50":
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
    #!/usr/bin/env bash
    curl -s -X POST http://localhost:8000/query -H "Content-Type: application/json" -d "{\"query\": \"{{question}}\"}" | jq

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
    docker compose exec api alembic upgrade head

# Show migration status
migrate-status:
    docker compose exec api alembic current

# =============================================================================
# ChromaDB Commands
# =============================================================================

# Check ChromaDB heartbeat
chroma-health:
    @curl -s http://localhost:8001/api/v2/heartbeat | jq

# Show ChromaDB statistics and random sample documents (usage: just chroma-docs-sample 5)
chroma-docs-sample n="10":
    #!/usr/bin/env bash
    # Colors
    CYAN='\033[0;36m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    DIM='\033[0;90m'
    BOLD='\033[1m'
    NC='\033[0m'

    # Get storage size
    size=$(docker compose exec chroma du -sb /data/ 2>/dev/null | cut -f1)
    if [ -n "$size" ]; then
        if [ "$size" -ge 1099511627776 ]; then
            human=$(echo "scale=2; $size / 1099511627776" | bc)TB
        elif [ "$size" -ge 1073741824 ]; then
            human=$(echo "scale=2; $size / 1073741824" | bc)GB
        elif [ "$size" -ge 1048576 ]; then
            human=$(echo "scale=2; $size / 1048576" | bc)MB
        elif [ "$size" -ge 1024 ]; then
            human=$(echo "scale=2; $size / 1024" | bc)KB
        else
            human="${size}B"
        fi
    else
        human="unknown"
    fi

    # Get stats
    stats=$(curl -s "http://localhost:8000/admin/chroma_stats")
    total=$(echo "$stats" | jq -r '.total_chunks')
    files=$(echo "$stats" | jq -r '.loaded_files')

    echo ""
    echo -e "${BOLD}ChromaDB Statistics${NC}"
    echo -e "─────────────────────────────────"
    echo -e "  ${CYAN}Total Chunks:${NC}  $total"
    echo -e "  ${CYAN}Loaded Files:${NC}  $files"
    echo -e "  ${CYAN}Storage:${NC}       $human"
    echo ""
    echo -e "${BOLD}Sample Chunks${NC} ${DIM}({{n}} random samples)${NC}"
    echo -e "─────────────────────────────────"

    # Get random samples from different files with chunk preview
    response=$(curl -s "http://localhost:8000/admin/chroma_list?limit=500&include_content=true")
    if echo "$response" | jq -e '.documents' >/dev/null 2>&1; then
        echo "$response" | \
            jq -r '.documents[] | select(.chunk != null) | "\(.filename)|\(.chunk_index)|\(.total_chunks)|\(.chunk[0:120] | gsub("\n"; " "))"' | \
            shuf | head -{{n}} | \
            while IFS='|' read -r fname idx total chunk; do
                echo -e "  ${GREEN}$fname${NC} ${DIM}[chunk $idx/$total]${NC}"
                echo -e "    ${YELLOW}\"${chunk}...\"${NC}"
                echo ""
            done
    else
        echo -e "  ${DIM}No documents found or API unavailable${NC}"
    fi

# =============================================================================
# Testing Commands
# =============================================================================

# Run all E2E tests
test:
    uv run pytest tests/e2e/ -v

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

# Full reset: DELETES ALL DATA (postgres, chroma), rebuilds from scratch
reset:
    docker compose down -v && docker compose build --no-cache && docker compose up -d && sleep 30 && just migrate
