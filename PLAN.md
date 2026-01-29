# NRECA Pipeline - Ingestion & RAG Implementation Plan

## Overview

Single EC2 deployment with two main components:
- **Airflow**: Ingestion logic - file fetching, parsing, chunking, embedding, dead queue management
- **FastAPI**: HTTP interface + query logic - triggers ingestion DAGs, handles RAG queries directly

**Key Principle**:
- **Ingestion** (`/load_file`) → Airflow DAG (async, complex pipeline)
- **Query** (`/query`) → FastAPI direct (sync, Chroma + LLM)
- **Admin** (`/dead_queue`, `/chroma_list`) → FastAPI reads shared datastores

**Environment Abstraction**: `APP_ENV=local` vs `APP_ENV=prod` controls file sources and ChromaDB targets.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            EC2 Instance                                 │
│                                                                         │
│  ┌───────────────────────────────┐    ┌────────────────────────────────┐│
│  │  FastAPI (Port 8000)          │    │  Airflow (Port 8080)           ││
│  │                               │    │                                ││
│  │  POST /load_file ─────────────┼───▶│  ingestion_dag                 ││
│  │    └─ validate, trigger DAG   │    │    └─ fetch file (S3/local)    ││
│  │                               │    │    └─ parse document           ││
│  │  POST /query                  │    │    └─ chunk content            ││
│  │    └─ search ChromaDB ────────┼───▶│    └─ generate embeddings      ││
│  │    └─ call LLM                │    │    └─ store in ChromaDB        ││
│  │    └─ return with sources     │    │    └─ on fail: write dead_queue││
│  │                               │    │                                ││
│  │  GET /dead_queue              │    └────────────────────────────────┘│
│  │    └─ read PostgreSQL ────────┼───▶ [reads dead_queue table]        │
│  │                               │                                      │
│  │  GET /chroma_list             │                                      │
│  │    └─ read ChromaDB ──────────┼───▶ [reads collection metadata]     │
│  └───────────────────────────────┘                                      │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                     Shared Data Stores                              ││
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ ││
│  │  │   PostgreSQL    │  │    ChromaDB     │  │  File Storage       │ ││
│  │  │   - dead_queue  │  │   - documents   │  │  (S3 or local)      │ ││
│  │  │                 │  │   - embeddings  │  │                     │ ││
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘ ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  APP_ENV=local                │         APP_ENV=prod                ││
│  │  ─────────────────────────────────────────────────────────────────  ││
│  │  Files: /test_files           │  Files: s3://nreca-bucket/          ││
│  │  Chroma: localhost:8001       │  Chroma: 18.205.154.91:8000         ││
│  │  Path: localpath/<file>       │  Path: s3://bucket/key              ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### Responsibility Split

| Component | Responsibility |
|-----------|----------------|
| **FastAPI** | HTTP interface + query logic: triggers ingestion DAGs, queries Chroma+LLM directly, reads dead_queue |
| **Airflow** | Ingestion logic: file fetching, parsing, chunking, embedding, ChromaDB storage, dead queue writes |
| **PostgreSQL** | Shared state: dead_queue table (written by Airflow, read by FastAPI) |
| **ChromaDB** | Vector storage: document chunks with embeddings and metadata (written by Airflow, read by FastAPI) |

### Logic Distribution

| Endpoint | Where Logic Lives | Why |
|----------|-------------------|-----|
| `POST /load_file` | **Airflow** | Async ingestion pipeline with retries, complex parsing, chunking |
| `POST /query` | **FastAPI** | Synchronous request-response, direct Chroma + LLM call |
| `GET /dead_queue` | **FastAPI** | Simple DB read (Airflow writes failures) |
| `GET /chroma_list` | **FastAPI** | Simple Chroma read |

### Design Decision: Why Query is Direct (Not a DAG)

| Aspect | `/load_file` (DAG) | `/query` (Direct) |
|--------|--------------------|--------------------|
| **Nature** | Write operation (ingestion) | Read operation (retrieval) |
| **Duration** | Minutes (large docs) | Seconds (LLM call) |
| **Failure handling** | Needs retries, dead queue | Idempotent, retry client-side |
| **User expectation** | Async (check status later) | Sync (immediate response) |
| **Complexity** | Multi-step pipeline | Single Chroma + LLM call |

If audit/caching needed for queries: FastAPI logs to PostgreSQL async (background task).

---

## 1. New Package: `packages/storage`

Unified file abstraction layer that handles S3 and local filesystem transparently.

### Files to Create

```
packages/storage/
├── pyproject.toml
└── src/storage/
    ├── __init__.py
    ├── config.py        # Storage settings (extends utils.Settings)
    ├── base.py          # Abstract StorageBackend protocol
    ├── local.py         # LocalStorageBackend implementation
    ├── s3.py            # S3StorageBackend implementation
    └── factory.py       # get_storage() factory based on APP_ENV
```

### Key Features

- **StorageBackend Protocol**:
  ```python
  class StorageBackend(Protocol):
      def exists(self, filename: str) -> bool
      def read(self, filename: str) -> bytes
      def get_path(self, filename: str) -> str  # Returns localpath/<file> or s3://uri
      def list_files(self, prefix: str = "") -> list[str]
  ```

- **Configuration** (`storage/config.py`):
  ```python
  class StorageSettings(Settings):
      app_env: Literal["local", "prod"] = "local"
      local_path: str = "/home/danyiel/Working/NovaDynamics/test_files"
      s3_bucket: str = "nreca-ingest-bucket"
      s3_prefix: str = "documents/"
  ```

- **Factory Pattern**:
  ```python
  def get_storage() -> StorageBackend:
      settings = get_storage_settings()
      if settings.app_env == "local":
          return LocalStorageBackend(settings.local_path)
      return S3StorageBackend(settings.s3_bucket, settings.s3_prefix)
  ```

---

## 2. New Package: `packages/vectordb`

ChromaDB abstraction with environment-aware client configuration.

### Files to Create

```
packages/vectordb/
├── pyproject.toml
└── src/vectordb/
    ├── __init__.py
    ├── config.py        # ChromaDB settings
    ├── client.py        # ChromaDB client factory
    ├── collections.py   # Collection management
    └── models.py        # Document metadata models
```

### Key Features

- **Configuration** (`vectordb/config.py`):
  ```python
  class ChromaSettings(Settings):
      app_env: Literal["local", "prod"] = "local"
      chroma_local_host: str = "localhost"
      chroma_local_port: int = 8001
      chroma_prod_host: str = "18.205.154.91"
      chroma_prod_port: int = 8000
      collection_name: str = "nreca_documents"
  ```

- **Client Factory**:
  ```python
  def get_chroma_client() -> chromadb.HttpClient:
      settings = get_chroma_settings()
      if settings.app_env == "local":
          return chromadb.HttpClient(host=settings.chroma_local_host, port=settings.chroma_local_port)
      return chromadb.HttpClient(host=settings.chroma_prod_host, port=settings.chroma_prod_port)
  ```

- **Document Metadata Model**:
  ```python
  class DocumentMetadata(StrictModel):
      id: UUID = Field(default_factory=uuid4)
      path: str           # s3://bucket/key OR localpath/<filename>
      filename: str
      chunk_index: int
      total_chunks: int
      ingested_at: datetime
  ```

---

## 3. New Package: `packages/api`

FastAPI application with endpoints that trigger Airflow DAGs.

### Files to Create

```
packages/api/
├── pyproject.toml
└── src/api/
    ├── __init__.py
    ├── main.py          # FastAPI app factory
    ├── config.py        # API settings (Airflow URL, LLM config)
    ├── routers/
    │   ├── __init__.py
    │   ├── ingest.py    # POST /load_file - triggers Airflow DAG
    │   ├── query.py     # POST /query - direct Chroma + LLM
    │   └── admin.py     # GET /dead_queue, GET /chroma_list
    ├── services/
    │   ├── __init__.py
    │   ├── airflow.py   # Airflow REST API client (trigger DAGs)
    │   ├── rag.py       # RAG query logic (Chroma search + LLM call)
    │   └── llm.py       # LLM client abstraction (OpenAI/Anthropic)
    └── schemas/
        ├── __init__.py
        ├── requests.py  # Pydantic request models
        └── responses.py # Pydantic response models
```

### Endpoints Specification

#### POST `/load_file`
Triggers file ingestion pipeline (thin layer - just triggers Airflow).

**Request** (supports single or bulk):
```json
{
  "filenames": ["document.pdf"]
}
// OR for bulk:
{
  "filenames": ["doc1.pdf", "doc2.pdf", "doc3.docx"]
}
```

**FastAPI does**:
1. Validate request
2. Check files exist (S3 or local based on APP_ENV)
3. Trigger Airflow `ingestion_dag` via REST API with `conf={"filenames": [...]}`
4. Return DAG run ID immediately (async)

**Airflow `ingestion_dag` does** (all the logic):
1. Receive list of filenames
2. For each file (dynamic task mapping):
   - Fetch file content
   - Parse document (PDF, DOCX, TXT)
   - Chunk content with overlap
   - Generate embeddings
   - Store in ChromaDB with metadata
3. On individual file failure: write to dead_queue table
4. Continue processing remaining files

**Response**:
```json
{
  "status": "triggered",
  "dag_run_id": "manual__2026-01-28T12:00:00",
  "filenames": ["document.pdf"],
  "file_count": 1
}
```

#### POST `/query`
Query documents with RAG hydration (direct FastAPI - no Airflow).

**Request**:
```json
{
  "query": "What are the membership requirements?",
  "n_results": 5
}
```

**FastAPI does** (synchronous, all logic here):
1. Validate request
2. Query ChromaDB for relevant chunks (using vectordb package)
3. Retrieve document metadata (path, id, filename) from results
4. Build prompt with context chunks
5. Call LLM API (OpenAI/Anthropic)
6. Return answer with source references

**Response**:
```json
{
  "answer": "Based on the documents...",
  "sources": [
    {
      "id": "uuid-here",
      "path": "s3://bucket/doc.pdf",
      "filename": "doc.pdf",
      "chunk": "relevant text excerpt...",
      "score": 0.92
    }
  ]
}
```

#### GET `/dead_queue`
List files that failed ingestion.

**Response**:
```json
{
  "failed_files": [
    {
      "filename": "corrupted.pdf",
      "path": "s3://bucket/corrupted.pdf",
      "error": "PDF parsing failed: invalid header",
      "failed_at": "2026-01-28T10:30:00Z",
      "dag_run_id": "manual__2026-01-28T10:00:00"
    }
  ],
  "count": 1
}
```

#### GET `/chroma_list`
List contents in ChromaDB collection.

**Request** (query params):
```
?limit=100&offset=0
```

**Response**:
```json
{
  "documents": [
    {
      "id": "uuid-here",
      "path": "s3://bucket/doc.pdf",
      "filename": "doc.pdf",
      "chunk_index": 0,
      "total_chunks": 5,
      "ingested_at": "2026-01-28T10:00:00Z"
    }
  ],
  "total": 150,
  "limit": 100,
  "offset": 0
}
```

---

## 4. New DAG: `dags/ingestion_dag/`

File ingestion pipeline from source to ChromaDB. This is where ALL ingestion logic lives.

### Files to Create

```
dags/ingestion_dag/
├── __init__.py
├── ingestion_dag.py     # Main DAG definition
├── task_fetch.py        # File retrieval from storage (uses storage package)
├── task_parse.py        # Document parsing (PDF, DOCX, TXT)
├── task_chunk.py        # Text chunking with overlap
└── task_embed.py        # Embedding generation and ChromaDB insertion
```

### DAG Flow

```
                    ┌─────────────────────────────────────────────────┐
                    │              ingestion_dag                       │
                    │                                                  │
[trigger from API]──▶ [fetch_file] ─▶ [parse_document] ─▶ [chunk_content]
                    │                                            │     │
                    │                                            ▼     │
                    │                                   [embed_and_store]
                    │                                            │     │
                    │                      ┌─────────────────────┘     │
                    │                      ▼                           │
                    │               [update_status]                    │
                    │                 /        \                       │
                    │           success       failure                  │
                    │              │             │                     │
                    │              ▼             ▼                     │
                    │            done      [write_dead_queue]          │
                    └─────────────────────────────────────────────────┘
```

### Task Details

1. **fetch_file** (Regular @task)
   - Receives filename from DAG params
   - Uses `storage.get_storage().read(filename)`
   - Returns file bytes + metadata

2. **parse_document** (@task.virtualenv)
   - Requirements: pypdf, python-docx, unstructured
   - Extracts text from PDF/DOCX/TXT
   - Returns extracted text + page count

3. **chunk_content** (Regular @task)
   - Splits text into overlapping chunks (512 tokens, 50 overlap)
   - Assigns chunk indices
   - Returns list of chunk dicts

4. **embed_and_store** (@task.virtualenv)
   - Requirements: chromadb, sentence-transformers
   - Generates embeddings (all-MiniLM-L6-v2 or similar)
   - Stores in ChromaDB with metadata:
     - `id`: UUID
     - `path`: S3 URI or localpath/<filename>
     - `filename`: original filename
     - `chunk_index`: position in document
     - `total_chunks`: total chunks
     - `ingested_at`: timestamp

5. **update_status** (Regular @task)
   - On success: logs completion
   - On failure: writes to dead_queue table in PostgreSQL

---

## 5. Database Model: Dead Queue

Add to `packages/db/src/db/models.py`:

```python
class DeadQueueItem(SQLModel, table=True):
    __tablename__ = "dead_queue"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    filename: str = Field(max_length=512)
    path: str = Field(max_length=1024)
    error_message: str
    dag_run_id: str = Field(max_length=255)
    failed_at: datetime = Field(default_factory=datetime.utcnow)
    retry_count: int = Field(default=0)
```

### Migration

Create `alembic/versions/002_create_dead_queue.py`:
- Creates `dead_queue` table
- Indexes on `filename` and `failed_at`

---

## 6. Docker Services Update

### docker-compose.yaml additions

```yaml
services:
  # ... existing airflow services ...

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      - APP_ENV=${APP_ENV:-local}
      - DATABASE_URL=postgresql://app:app@postgres:5432/app
      - AIRFLOW_API_URL=http://airflow-webserver:8080/api/v1
    depends_on:
      - postgres
      - airflow-webserver
    volumes:
      - ./packages:/opt/app/packages:ro
      - ${LOCAL_FILE_PATH:-./test_files}:/data/files:ro

  chroma:
    image: chromadb/chroma:latest
    ports:
      - "8001:8000"
    volumes:
      - chroma_data:/chroma/chroma
    profiles:
      - local  # Only starts with --profile local

volumes:
  chroma_data:
```

### Dockerfile.api (new)

```dockerfile
FROM python:3.12-slim

WORKDIR /opt/app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy and install dependencies
COPY packages/api/pyproject.toml packages/api/
COPY packages/utils/pyproject.toml packages/utils/
COPY packages/storage/pyproject.toml packages/storage/
COPY packages/vectordb/pyproject.toml packages/vectordb/
COPY packages/db/pyproject.toml packages/db/

RUN uv pip install --system -e packages/api -e packages/utils -e packages/storage -e packages/vectordb -e packages/db

COPY packages/ packages/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 7. Configuration Updates

### .env.example additions

```bash
# Environment
APP_ENV=local  # local | prod

# Storage
LOCAL_FILE_PATH=/home/danyiel/Working/NovaDynamics/test_files
S3_BUCKET=nreca-ingest-bucket
S3_PREFIX=documents/

# ChromaDB
CHROMA_LOCAL_HOST=localhost
CHROMA_LOCAL_PORT=8001
CHROMA_PROD_HOST=18.205.154.91
CHROMA_PROD_PORT=8000
CHROMA_COLLECTION=nreca_documents

# LLM (for query endpoint)
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# Airflow API (for FastAPI to trigger DAGs)
AIRFLOW_API_URL=http://localhost:8080/api/v1
AIRFLOW_USERNAME=airflow
AIRFLOW_PASSWORD=airflow
```

---

## 8. Implementation Order

### Phase 1: Core Infrastructure
1. [ ] Create `packages/storage` package with local/S3 abstraction
2. [ ] Create `packages/vectordb` package with ChromaDB client
3. [ ] Add `DeadQueueItem` model and migration
4. [ ] Update `pyproject.toml` workspace members

### Phase 2: Ingestion Pipeline
5. [ ] Create `dags/ingestion_dag/` with all tasks
6. [ ] Add document parsing logic (PDF, DOCX, TXT)
7. [ ] Implement chunking with configurable params
8. [ ] Implement embedding and ChromaDB storage

### Phase 3: API Layer
9. [ ] Create `packages/api` package structure
10. [ ] Implement `/load_file` endpoint
11. [ ] Implement `/query` endpoint with RAG
12. [ ] Implement `/dead_queue` endpoint
13. [ ] Implement `/chroma_list` endpoint

### Phase 4: Docker Integration
14. [ ] Create `Dockerfile.api`
15. [ ] Update `docker-compose.yaml` with new services
16. [ ] Add ChromaDB local service (profile: local)
17. [ ] Test full stack locally

### Phase 5: Testing & Documentation
18. [ ] Add unit tests for storage backends
19. [ ] Add integration tests for API endpoints
20. [ ] Update README with deployment instructions

---

## 9. Dependencies to Add

### packages/storage/pyproject.toml
```toml
dependencies = [
    "utils",
    "boto3>=1.35.0",
    "botocore>=1.35.0",
]
```

### packages/vectordb/pyproject.toml
```toml
dependencies = [
    "utils",
    "chromadb>=0.5.0",
    "sentence-transformers>=3.0.0",
]
```

### packages/api/pyproject.toml
```toml
dependencies = [
    "utils",
    "storage",
    "vectordb",
    "db",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "httpx>=0.27.0",
    "openai>=1.50.0",
]
```

---

## 10. File Metadata Contract

All files stored in ChromaDB must have this metadata:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | UUID | Unique document chunk ID | `550e8400-e29b-41d4-a716-446655440000` |
| `path` | str | Full path to source | `s3://bucket/doc.pdf` or `localpath/doc.pdf` |
| `filename` | str | Original filename | `doc.pdf` |
| `chunk_index` | int | Position in document | `0` |
| `total_chunks` | int | Total chunks | `5` |
| `ingested_at` | str | ISO timestamp | `2026-01-28T10:00:00Z` |

**Path format rules**:
- `APP_ENV=local`: `localpath/<filename>` (e.g., `localpath/report.pdf`)
- `APP_ENV=prod`: `s3://<bucket>/<key>` (e.g., `s3://nreca-bucket/documents/report.pdf`)
