"""LLM client for RAG queries.

Supports multiple providers:
- GROQ: For local testing (fast, free tier available)
- Gemma: For production (previously called immediatum)
- OpenAI: Fallback if configured
"""

from functools import lru_cache

from openai import AsyncOpenAI
from utils import get_logger

from api.config import APISettings, get_api_settings

log = get_logger("api.services.llm")


class LLMClient:
    """Client for LLM API calls with multi-provider support."""

    def __init__(self, settings: APISettings) -> None:
        self._settings = settings
        self._client: AsyncOpenAI | None = None
        self._model: str = ""
        self._provider: str = "none"

        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the appropriate LLM client based on environment and config."""
        settings = self._settings

        # Local environment: prefer GROQ
        if settings.is_local and settings.groq_api_key:
            self._client = AsyncOpenAI(
                api_key=settings.groq_api_key.get_secret_value(),
                base_url="https://api.groq.com/openai/v1",
            )
            self._model = settings.groq_model
            self._provider = "groq"
            log.info("llm_initialized", provider="groq", model=self._model)
            return

        # Production environment: prefer Gemma
        if not settings.is_local and settings.gemma_api_key:
            self._client = AsyncOpenAI(
                api_key=settings.gemma_api_key.get_secret_value(),
                base_url=settings.gemma_base_url,
            )
            self._model = settings.gemma_model
            self._provider = "gemma"
            log.info("llm_initialized", provider="gemma", model=self._model)
            return

        # Custom base URL (works with any OpenAI-compatible API)
        if settings.llm_base_url and settings.openai_api_key:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                base_url=settings.llm_base_url,
            )
            self._model = settings.llm_model
            self._provider = "custom"
            log.info("llm_initialized", provider="custom", model=self._model)
            return

        # Fallback to standard OpenAI
        if settings.openai_api_key:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value()
            )
            self._model = settings.llm_model
            self._provider = "openai"
            log.info("llm_initialized", provider="openai", model=self._model)
            return

        log.warning("llm_not_configured", hint="Set GROQ_API_KEY or OPENAI_API_KEY")

    @property
    def provider(self) -> str:
        """Get the current LLM provider name."""
        return self._provider

    @property
    def model(self) -> str:
        """Get the current model name."""
        return self._model

    async def generate_answer(
        self,
        query: str,
        context_chunks: list[str],
    ) -> str:
        """Generate an answer using RAG context.

        Args:
            query: User's question
            context_chunks: Retrieved document chunks for context

        Returns:
            Generated answer string
        """
        if not self._client:
            log.warning("llm_not_configured")
            return self._fallback_answer(query, context_chunks)

        # Build prompt with context
        context = "\n\n---\n\n".join(context_chunks)
        prompt = f"""You are a helpful assistant answering questions about NRECA documents.
Use the following context to answer the question. If you cannot find the answer in the context,
say so clearly.

Context:
{context}

Question: {query}

Answer:"""

        log.info(
            "generating_answer",
            provider=self._provider,
            model=self._model,
            query_length=len(query),
            context_chunks=len(context_chunks),
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1024,
                temperature=0.7,
            )

            answer = response.choices[0].message.content or ""
            log.info("answer_generated", answer_length=len(answer))

            return answer

        except Exception as e:
            log.error("llm_error", provider=self._provider, error=str(e))
            return self._fallback_answer(query, context_chunks)

    def _fallback_answer(self, query: str, context_chunks: list[str]) -> str:
        """Generate a fallback answer when LLM is not available."""
        if not context_chunks:
            return "No relevant documents found for your query."

        count = len(context_chunks)
        return f"Found {count} relevant document(s). LLM not configured for answer generation."


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """Get cached LLM client singleton."""
    return LLMClient(get_api_settings())
