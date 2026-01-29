# Troubleshooting Guide

## Services Not Starting

### Check container logs

```bash
docker compose logs airflow-webserver
docker compose logs airflow-scheduler
docker compose logs api
```

### Rebuild from scratch

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

## Port Conflicts

### Find what's using a port

```bash
lsof -i :8000   # API
lsof -i :8080   # Airflow
lsof -i :8001   # ChromaDB
lsof -i :5434   # PostgreSQL
```

### Kill blocking container

```bash
docker ps -a | grep <port>
docker rm -f <container-name>
```

## Database Issues

### Airflow database migration errors

```bash
# Manually run Airflow migrations
docker compose exec airflow-scheduler airflow db migrate
```

### App database migration errors

```bash
# Run Alembic migrations locally
just migrate

# Or manually
DATABASE_URL="postgresql+psycopg://app:app@localhost:5434/app" uv run alembic upgrade head
```

### Check migration status

```bash
just migrate-status
```

### Connect to PostgreSQL directly

```bash
just psql
# Or: psql "postgresql://app:app@localhost:5434/app"
```

## Permission Errors

### Airflow can't write to logs/venv_cache

The Airflow user runs as uid 50000. Fix permissions:

```bash
# Using Docker (no sudo required)
docker run --rm -v "$(pwd)/logs:/logs" alpine chown -R 50000:0 /logs
docker run --rm -v "$(pwd)/venv_cache:/venv_cache" alpine chown -R 50000:0 /venv_cache

# Or using sudo
sudo chown -R 50000:0 logs venv_cache

# Or use the just command
just fix-perms
```

## DAG Issues

### DAGs not appearing

```bash
# Force DAG reserialization
just reserialize

# Check for import errors
docker compose logs airflow-scheduler | grep -i error
```

### DAG import errors

```bash
# Test DAG imports manually
docker compose exec airflow-scheduler python -c "from ingestion_dag import ingestion_dag"
```

## Ingestion Failures

### Check dead queue for failed files

```bash
curl -s http://localhost:8000/admin/dead_queue | jq
```

### Check file status

```bash
curl -s http://localhost:8000/admin/list_files | jq
```

### Verify files are mounted

```bash
docker compose exec api ls -la /data/files/
```

## RAG Query Issues

### No results returned

1. Verify documents were ingested:
   ```bash
   just chroma-collections
   curl -s "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database/collections" | jq
   ```

2. Check if ChromaDB has embeddings:
   ```bash
   curl -s http://localhost:8000/admin/chroma_list | jq
   ```

### LLM errors

1. Verify API key is set in `.env`:
   ```bash
   grep GROQ_API_KEY .env
   ```

2. Check API logs:
   ```bash
   just logs-api
   ```

## Network Issues

### Docker can't pull images

If you see DNS or timeout errors:

```bash
# Check DNS resolution
nslookup registry-1.docker.io

# If VPN is active, try disconnecting temporarily
# Or add Google DNS to Docker daemon.json:
# /etc/docker/daemon.json: {"dns": ["8.8.8.8", "8.8.4.4"]}
# Then: sudo systemctl restart docker
```

### Services can't communicate

```bash
# Verify network exists
docker network ls | grep nreca

# Check if containers are on the same network
docker network inspect nreca-pipeline_default
```

## Full Reset

When all else fails:

```bash
# Stop everything, remove volumes, rebuild, restart
just reset

# Or manually:
docker compose down -v
rm -rf logs/* venv_cache/*
just fix-perms
docker compose build --no-cache
docker compose up -d
sleep 60
just migrate
```

## Getting Help

1. Check container status: `just status`
2. View all logs: `just logs`
3. Check service health: `just health`
4. List DAGs: `just dags`
