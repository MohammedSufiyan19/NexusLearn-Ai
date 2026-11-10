"""
NexusLearn AI — LLM Providers with Circuit Breaker
Groq primary with exponential backoff + jitter.
Circuit breaker routes to Mistral after N consecutive failures.
"""
import logging
import random
import time
from enum import Enum
from threading import Lock

# pyrefly: ignore[missing-import]
from app.core.config import settings
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI

logger = logging.getLogger(__name__)


# ── Circuit Breaker ──────────────────────────────────────────────────────────

class CBState(Enum):
    CLOSED = "closed"       # normal: requests go to primary
    OPEN = "open"           # fault: requests go to fallback
    HALF_OPEN = "half_open" # probing: one request goes to primary


class CircuitBreaker:
    """
    Thread-safe circuit breaker.
    CLOSED → OPEN after `failure_threshold` consecutive failures.
    OPEN → HALF_OPEN after `recovery_timeout` seconds.
    HALF_OPEN → CLOSED on success, OPEN on failure.
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self._state = CBState.CLOSED
        self._failures = 0
        self._last_failure_time: float | None = None
        self._threshold = failure_threshold
        self._recovery = recovery_timeout
        self._lock = Lock()

    @property
    def state(self) -> CBState:
        with self._lock:
            if self._state == CBState.OPEN:
                if time.time() - self._last_failure_time > self._recovery:
                    self._state = CBState.HALF_OPEN
                    logger.info("Circuit breaker → HALF_OPEN: probing primary LLM")
            return self._state

    def record_success(self):
        with self._lock:
            self._failures = 0
            if self._state != CBState.CLOSED:
                logger.info("Circuit breaker → CLOSED: primary LLM recovered")
            self._state = CBState.CLOSED

    def record_failure(self):
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._failures >= self._threshold:
                if self._state != CBState.OPEN:
                    logger.warning(
                        "Circuit breaker → OPEN after %d failures. Routing to fallback.",
                        self._failures
                    )
                self._state = CBState.OPEN


_cb = CircuitBreaker(
    failure_threshold=settings.circuit_breaker_failure_threshold,
    recovery_timeout=settings.circuit_breaker_recovery_timeout,
)


# ── Retry with Exponential Backoff + Jitter ──────────────────────────────────

def _invoke_with_retry(llm, prompt, max_retries: int = 3):
    """Invoke an LLM with exponential backoff + jitter. Honours retry-after."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            result = llm.invoke(prompt)
            return result
        except Exception as exc:
            last_exc = exc
            err_str = str(exc).lower()

            # Parse retry-after if present
            retry_after = None
            if "retry-after" in err_str:
                try:
                    retry_after = int([s for s in err_str.split() if s.isdigit()][0])
                except Exception:
                    pass

            if retry_after:
                wait = retry_after + random.uniform(0, 1)
            else:
                wait = (2 ** attempt) + random.uniform(0, 1)  # jitter

            logger.warning("LLM call attempt %d failed (%s). Retrying in %.1fs", attempt + 1, exc, wait)
            time.sleep(wait)

    raise last_exc


# ── Provider Factory ─────────────────────────────────────────────────────────

def _make_groq() -> ChatGroq:
    return ChatGroq(
        api_key=settings.groq_api_key,
        model="openai/gpt-oss-120b",
        temperature=0.3,
        request_timeout=30,
    )


def _make_mistral() -> ChatMistralAI:
    return ChatMistralAI(
        api_key=settings.mistral_api_key,
        model="mistral-small-latest",
        temperature=0.3,
        request_timeout=30,
    )


# ── Public Interface ─────────────────────────────────────────────────────────

def invoke_llm(prompt, provider_log: list | None = None) -> str:
    """
    Invoke the best available LLM with circuit breaker + retry.
    Returns the answer string.
    Appends the provider name to provider_log if supplied.
    """
    cb_state = _cb.state

    # Try primary (Groq) if circuit is CLOSED or HALF_OPEN
    if cb_state in (CBState.CLOSED, CBState.HALF_OPEN) and settings.groq_api_key:
        try:
            llm = _make_groq()
            result = _invoke_with_retry(llm, prompt)
            _cb.record_success()
            if provider_log is not None:
                provider_log.append("groq")
            logger.debug("LLM answered by groq")
            return result.content
        except Exception as exc:
            logger.warning("Groq failed: %s — routing to Mistral fallback", exc)
            _cb.record_failure()

    # Fallback: Mistral
    if settings.mistral_api_key:
        try:
            llm = _make_mistral()
            result = _invoke_with_retry(llm, prompt)
            if provider_log is not None:
                provider_log.append("mistral")
            logger.info("LLM answered by mistral (fallback)")
            return result.content
        except Exception as exc:
            logger.error("Mistral fallback also failed: %s", exc)
            raise

    raise RuntimeError("No LLM provider available — check GROQ_API_KEY / MISTRAL_API_KEY in .env")


def get_embeddings():
    """Returns the Mistral embedding model instance."""
    from langchain_mistralai import MistralAIEmbeddings
    return MistralAIEmbeddings(
        api_key=settings.mistral_api_key,
        model="mistral-embed",
    )
