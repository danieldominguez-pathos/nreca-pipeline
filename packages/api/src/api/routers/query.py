"""Query router - POST /query endpoint."""

from fastapi import APIRouter
from utils import get_logger

from api.schemas import QueryRequest, QueryResponse
from api.services import get_rag_service

router = APIRouter(prefix="/query", tags=["query"])
log = get_logger("api.routers.query")


@router.post("", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    """Query documents with RAG.

    Searches ChromaDB for relevant chunks and generates
    an answer using the LLM.

    Args:
        request: QueryRequest with query text and n_results

    Returns:
        QueryResponse with answer and source documents
    """
    log.info("query_request", query=request.query, n_results=request.n_results)

    rag_service = get_rag_service()
    response = await rag_service.query(
        query=request.query,
        n_results=request.n_results,
    )

    log.info("query_complete", sources_count=len(response.sources))

    return response
