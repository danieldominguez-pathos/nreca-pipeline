# NRECA Document Ingestion Pipeline

Document ingestion and RAG query pipeline for NRECA.

## Architecture

```
                         Docker Compose

┌─────────────┐         ┌───────────────────────────────────────┐
│   FastAPI   │         │             Airflow 3.x               │
│    :8000    │         │                                       │
│             │ trigger │  ┌──────────┐    ┌─────────────────┐  │
│  /register ─┼────────▶│  │Scheduler │───▶│  ingestion_dag  │  │
│  /pending   │         │  └──────────┘    │                 │  │
│  /query     │         │                  │  get_file_ids   │  │
│  /admin/*   │         │  ┌──────────┐    │       │         │  │
└──────┬──────┘         │  │Webserver │    │       ▼         │  │
       │                │  │  :8080   │    │  fetch_parse ───┼──┼───┐
       │                │  └──────────┘    │       │         │  │   │
       │                │                  │       ▼         │  │   │
       │                │                  │  chunk_text     │  │   │
       │                │                  │       │         │  │   │
       │                │                  │       ▼         │  │   │
       │                │                  │  embed_store ───┼──┼───┼──┐
       │                │                  │       │         │  │   │  │
       │                │                  │       ▼         │  │   │  │
       │                │          ┌───────── update_meta    │  │   │  │
       │                │          │       │       │         │  │   │  │
       │                │          │       │       ▼         │  │   │  │
       │                │          │       │  summarize      │  │   │  │
       │                │          │       └─────────────────┘  │   │  │
       │                └──────────│────────────────────────────┘   │  │
       ▼                           │                                │  │
┌─────────────────────────┐        │  ┌────────────────────────┐    │  │
│      PostgreSQL         │        │  │       ChromaDB         │    │  │
│        :5434            │        │  │        :8001           │◀───┼──┘
│                         │        │  │                        │    │
│  ┌───────────────────┐  │ status │  │   nreca_documents      │    │
│  │   file_records  ◀─┼──┼─update─┘  │                        │    │
│  │   dead_queue      │  │           │  (vector embeddings)   │    │
│  └───────────────────┘  │           └────────────────────────┘    │
│                         │                                         │
│  ┌───────────────────┐  │           ┌────────────────────────┐    │
│  │airflow (metadata) │  │           │        AWS S3          │    │
│  └───────────────────┘  │           │  *.pdf, *.docx, *.txt  │◀───┘
└─────────────────────────┘           │  (or local test_files/ │
                                      └────────────────────────┘


Data Flow:
  1. POST /ingest/register  →  Creates file_records (status: PENDING)
  2. POST /ingest/pending   →  Triggers ingestion_dag via Airflow API
  3. ingestion_dag          →  fetch → parse → chunk → embed → store
  4. POST /query            →  Retrieves from ChromaDB → LLM generates answer
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- [just](https://github.com/casey/just) command runner
- Groq API key (free at https://console.groq.com)

### Setup

```bash
# Clone and configure
git clone <repo-url>
cd nreca-pipeline
cp .env.example .env
# Edit .env and set GROQ_API_KEY

# One-command setup
just setup
```

### Verify

```bash
just health   # API health
just dags     # List DAGs
just status   # Container status
```

### Usage

```bash
# Register and ingest all documents
just pipeline-all

# Query documents
just query "What is the cooperative policy on renewable energy?"
```

## Services

| Service    | URL                        | Description                    |
| ---------- | -------------------------- | ------------------------------ |
| API        | http://localhost:8000/docs | Registration, ingestion, query |
| Airflow    | http://localhost:8080      | DAG management                 |
| ChromaDB   | http://localhost:8001      | Vector database                |
| PostgreSQL | localhost:5434             | File tracking                  |

Airflow credentials: `just airflow-pswd`

## Commands

```bash
# Setup & lifecycle
just setup              # First-time setup (build, start, migrate)
just up                 # Start services
just down               # Stop services
just reset              # Full reset (removes data)
just airflow-pswd       # Show Airflow user and password

# Pipeline
just register-all       # Register files in test_files/
just ingest-pending     # Ingest pending files
just pipeline-all       # Register + ingest
just query "question"   # Query documents

# Development
just migrate            # Run database migrations
just logs               # View all logs
just test               # Run E2E tests
```

Full command list: `just --list`

## Environment Variables

Required:

```bash
GROQ_API_KEY=your-key      # Get at https://console.groq.com
```

Optional:

```bash
APP_ENV=local              # Environment
GROQ_MODEL=llama-3.3-70b-versatile
CHROMA_COLLECTION=nreca_documents
```

Production:

```bash
OPENAI_API_KEY=...         # Use OpenAI instead of Groq
LLM_MODEL=gpt-4o-mini
CHROMA_PROD_HOST=...       # Remote ChromaDB
S3_BUCKET=...              # S3 storage
```

## Project Structure

```
.
├── dags/                 # Airflow DAGs
│   ├── ingestion_dag/    # Document ingestion
│   └── registration_dag/ # File registration
├── packages/
│   ├── api/              # FastAPI application
│   ├── db/               # Database models
│   ├── storage/          # S3/local storage
│   ├── utils/            # Shared utilities
│   └── vectordb/         # ChromaDB client
├── tests/e2e/            # End-to-end tests
├── docs/                 # Documentation
├── test_files/           # Place documents here
├── Dockerfile            # Airflow image
├── Dockerfile.api        # API image
└── Justfile              # Task runner
```

## Supported File Types

- PDF (.pdf)
- Word (.docx, .doc)
- Plain text (.txt)

## Troubleshooting

See [docs/troubleshoot.md](docs/troubleshoot.md)
