# NRECA Document Ingestion Pipeline

Document ingestion and RAG query pipeline for NRECA.

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
|------------|----------------------------|--------------------------------|
| API        | http://localhost:8000/docs | Registration, ingestion, query |
| Airflow    | http://localhost:8080      | DAG management                 |
| ChromaDB   | http://localhost:8001      | Vector database                |
| PostgreSQL | localhost:5434             | File tracking                  |

Airflow password: `just lookup-pswd`

## Commands

```bash
# Setup & lifecycle
just setup              # First-time setup (build, start, migrate)
just up                 # Start services
just down               # Stop services
just reset              # Full reset (removes data)

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
- Word (.docx)
- Plain text (.txt)

## Troubleshooting

See [docs/troubleshoot.md](docs/troubleshoot.md)
