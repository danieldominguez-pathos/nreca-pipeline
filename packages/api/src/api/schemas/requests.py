"""API request schemas."""

from pydantic import Field
from utils import StrictModel


class LoadFileRequest(StrictModel):
    """Request to load/ingest files."""

    filenames: list[str] = Field(
        ...,
        min_length=1,
        description="List of filenames to ingest",
    )


class QueryRequest(StrictModel):
    """Request to query documents with RAG."""

    query: str = Field(
        ...,
        min_length=1,
        description="Question or search query",
    )
    n_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of results to retrieve",
    )
