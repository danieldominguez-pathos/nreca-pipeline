"""API response schemas."""

from datetime import datetime

from pydantic import Field
from utils import StrictModel


class LoadFileResponse(StrictModel):
    """Response from load_file endpoint."""

    status: str = Field(default="triggered")
    dag_run_id: str = Field(..., description="Airflow DAG run ID")
    filenames: list[str] = Field(..., description="Files being processed")
    file_count: int = Field(..., description="Number of files")


class QuerySource(StrictModel):
    """A source document from RAG query."""

    id: str = Field(..., description="Document chunk ID")
    path: str = Field(..., description="File path (S3 URI or localpath)")
    filename: str = Field(..., description="Original filename")
    chunk: str = Field(..., description="Retrieved text content")
    score: float = Field(..., description="Relevance score")


class QueryResponse(StrictModel):
    """Response from query endpoint."""

    answer: str = Field(..., description="LLM-generated answer")
    sources: list[QuerySource] = Field(
        default_factory=list,
        description="Source documents used",
    )


class DeadQueueItem(StrictModel):
    """A failed file in the dead queue."""

    filename: str
    path: str
    error: str
    failed_at: datetime
    dag_run_id: str


class DeadQueueResponse(StrictModel):
    """Response from dead_queue endpoint."""

    failed_files: list[DeadQueueItem] = Field(default_factory=list)
    count: int = Field(default=0)


class ChromaDocument(StrictModel):
    """A document in ChromaDB."""

    id: str
    path: str
    filename: str
    chunk_index: int
    total_chunks: int
    ingested_at: str
    chunk: str | None = None  # Optional text content


class ChromaListResponse(StrictModel):
    """Response from chroma_list endpoint."""

    documents: list[ChromaDocument] = Field(default_factory=list)
    total: int = Field(default=0)
    limit: int
    offset: int


class FileItem(StrictModel):
    """A file in the file registry."""

    id: str = Field(..., description="File UUID")
    path: str = Field(..., description="File path (S3 URI or localpath)")
    chroma_status: str = Field(..., description="PENDING, PROCESSING, LOADED, or FAILED")
    size: str = Field(..., description="Human-readable size (e.g., 1.5 MB)")
    chunk_count: int = Field(default=0, description="Number of chunks in ChromaDB")
    error_message: str | None = Field(default=None)


class ListFilesResponse(StrictModel):
    """Response from list_files endpoint."""

    files: list[FileItem] = Field(default_factory=list)
    total: int = Field(default=0)
    limit: int
    offset: int
