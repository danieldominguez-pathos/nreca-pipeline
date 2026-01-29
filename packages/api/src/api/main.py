"""FastAPI application factory and main app instance."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from utils import get_logger

from api.config import get_api_settings
from api.routers import admin_router, ingest_router, query_router

log = get_logger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - pre-warm models on startup."""
    log.info("startup_begin", message="Pre-warming sentence-transformer model...")

    # Pre-warm the embedding model to avoid cold start on first query
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        embedding_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        # Warm up with a test embedding
        _ = embedding_fn(["warmup test"])
        log.info("startup_complete", message="Sentence-transformer model loaded")
    except Exception as e:
        log.warning("startup_warmup_failed", error=str(e))

    yield  # Application runs here

    log.info("shutdown", message="API shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    settings = get_api_settings()

    app = FastAPI(
        title="NRECA Pipeline API",
        description="Document ingestion and RAG query endpoints",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_local else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(ingest_router)
    app.include_router(query_router)
    app.include_router(admin_router)

    @app.get("/health")
    async def health_check() -> dict:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "env": settings.app_env,
        }

    return app


# Create the default app instance
app = create_app()
