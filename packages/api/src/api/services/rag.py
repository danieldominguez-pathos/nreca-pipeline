"""RAG (Retrieval Augmented Generation) service."""

from functools import lru_cache

from utils import get_logger
from vectordb import query_documents

from api.schemas import QueryResponse, QuerySource
from api.services.llm import LLMClient, get_llm_client

log = get_logger("api.services.rag")

# Maximum length for chunk preview in responses
CHUNK_PREVIEW_LENGTH = 500


class RAGService:
    """Service for RAG queries combining ChromaDB and LLM."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def query(self, query: str, n_results: int = 5) -> QueryResponse:
        """Execute a RAG query.

        1. Search ChromaDB for relevant chunks
        2. Build context from results
        3. Generate answer with LLM
        4. Return answer with sources

        Args:
            query: User's question
            n_results: Number of chunks to retrieve

        Returns:
            QueryResponse with answer and sources
        """
        log.info("rag_query", query=query, n_results=n_results)

        # Step 1: Search ChromaDB
        results = query_documents(query=query, n_results=n_results)

        log.info("chroma_results", count=len(results))

        if not results:
            return QueryResponse(
                answer="No relevant documents found for your query.",
                sources=[],
            )

        # Step 2: Build context and sources
        context_chunks = [r.chunk for r in results]
        sources = [
            QuerySource(
                id=r.id,
                path=r.path,
                filename=r.filename,
                chunk=r.chunk[:CHUNK_PREVIEW_LENGTH] + "..."
                if len(r.chunk) > CHUNK_PREVIEW_LENGTH
                else r.chunk,
                score=r.score,
            )
            for r in results
        ]

        # Step 3: Generate answer
        answer = await self._llm.generate_answer(query, context_chunks)

        log.info("rag_complete", sources_count=len(sources))

        return QueryResponse(answer=answer, sources=sources)


@lru_cache(maxsize=1)
def get_rag_service() -> RAGService:
    """Get cached RAG service singleton."""
    return RAGService(get_llm_client())
