"""Data models for document storage and retrieval."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field
from utils import StrictModel


class DocumentMetadata(StrictModel):
    """Metadata for a document chunk stored in ChromaDB.

    This follows the metadata contract specified in the plan:
    - id: UUID for the chunk
    - path: S3 URI or localpath/<filename>
    - filename: original filename
    - chunk_index: position in document
    - total_chunks: total number of chunks
    - ingested_at: timestamp
    """

    id: UUID = Field(default_factory=uuid4, description="Unique chunk identifier")
    path: str = Field(..., description="S3 URI (s3://bucket/key) or localpath/<filename>")
    filename: str = Field(..., description="Original filename")
    chunk_index: int = Field(..., ge=0, description="Position of chunk in document")
    total_chunks: int = Field(..., ge=1, description="Total number of chunks in document")
    ingested_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when chunk was ingested",
    )

    def to_chroma_metadata(self) -> dict[str, str | int]:
        """Convert to ChromaDB-compatible metadata dict.

        ChromaDB requires flat metadata with string/int/float/bool values.
        """
        return {
            "id": str(self.id),
            "path": self.path,
            "filename": self.filename,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "ingested_at": self.ingested_at.isoformat(),
        }

    @classmethod
    def from_chroma_metadata(cls, metadata: dict) -> "DocumentMetadata":
        """Create from ChromaDB metadata dict."""
        return cls(
            id=UUID(metadata["id"]),
            path=metadata["path"],
            filename=metadata["filename"],
            chunk_index=metadata["chunk_index"],
            total_chunks=metadata["total_chunks"],
            ingested_at=datetime.fromisoformat(metadata["ingested_at"]),
        )


class DocumentChunk(StrictModel):
    """A chunk of a document ready for embedding and storage."""

    content: str = Field(..., description="Text content of the chunk")
    metadata: DocumentMetadata = Field(..., description="Chunk metadata")

    @property
    def chunk_id(self) -> str:
        """Get the chunk ID as string for ChromaDB."""
        return str(self.metadata.id)


class QueryResult(StrictModel):
    """Result from a ChromaDB query."""

    id: str = Field(..., description="Chunk ID")
    path: str = Field(..., description="File path (S3 URI or localpath)")
    filename: str = Field(..., description="Original filename")
    chunk: str = Field(..., description="Retrieved text content")
    score: float = Field(..., description="Similarity score (higher is better)")
    chunk_index: int = Field(..., description="Position in document")
    total_chunks: int = Field(..., description="Total chunks in document")

    @classmethod
    def from_chroma_result(
        cls,
        document: str,
        metadata: dict,
        distance: float,
    ) -> "QueryResult":
        """Create from ChromaDB query result.

        Args:
            document: The text content
            metadata: ChromaDB metadata dict
            distance: Distance score (lower is more similar)
        """
        # Convert distance to similarity score (1 - distance for cosine)
        similarity = 1.0 - distance if distance <= 1.0 else 0.0

        return cls(
            id=metadata["id"],
            path=metadata["path"],
            filename=metadata["filename"],
            chunk=document,
            score=round(similarity, 4),
            chunk_index=metadata["chunk_index"],
            total_chunks=metadata["total_chunks"],
        )
