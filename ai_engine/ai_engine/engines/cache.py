"""In-process advisory response cache with SHA-256 keys and per-type TTL.

Caches deterministic AI engine responses (semantic classification, cost
prediction, risk scoring, SQL optimisation) to avoid redundant computation
and LLM calls for identical inputs.

Cache keys are SHA-256 hashes of the request payload (JSON-serialised with
sorted keys) plus the prompt version, so prompt updates automatically
invalidate stale entries.

Design notes:
    * In-process dict — no external dependency (Redis comes later with
      horizontal scaling).
    * Thread-safe via a threading lock (FastAPI runs handlers in an async
      event loop but may dispatch sync work to thread pool executors).
    * Each entry stores an expiry timestamp; a background sweep is not
      needed because expired entries are lazily evicted on access.
    * ``invalidate_all()`` supports immediate full-cache flush, e.g.
      after a cost model retrain or prompt version change.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default TTLs per request type (seconds)
# ---------------------------------------------------------------------------

DEFAULT_TTL: dict[str, int] = {
    "semantic_classify": 3600,  # 1 hour — SQL diff classifications are stable
    "predict_cost": 900,  # 15 min — cost predictions depend on mutable stats
    "risk_score": 3600,  # 1 hour — risk is deterministic on inputs
    "optimize_sql": 1800,  # 30 min — optimisation suggestions are stable
}

_FALLBACK_TTL = 900  # 15 min for unknown request types


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _CacheEntry:
    """A cached response with an expiry wall-clock timestamp."""

    value: Any
    expires_at: float
    request_type: str
    created_at: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# ResponseCache
# ---------------------------------------------------------------------------


class ResponseCache:
    """SHA-256 keyed in-process cache for AI advisory responses.

    Parameters
    ----------
    ttl_overrides:
        Optional mapping of ``{request_type: ttl_seconds}`` to override
        the built-in defaults.
    max_entries:
        Maximum number of entries to store.  When exceeded, the oldest
        entries are evicted (LRU-style, not LFU).
    enabled:
        If ``False``, all operations are no-ops.  Allows disabling via
        config without changing call sites.
    """

    def __init__(
        self,
        *,
        ttl_overrides: dict[str, int] | None = None,
        max_entries: int = 10_000,
        enabled: bool = True,
    ) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self._enabled = enabled
        self._max_entries = max_entries

        self._ttls = dict(DEFAULT_TTL)
        if ttl_overrides:
            self._ttls.update(ttl_overrides)

        # Stats
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(request_type: str, payload: dict[str, Any], prompt_version: str = "v1") -> str:
        """Build a deterministic SHA-256 cache key.

        Parameters
        ----------
        request_type:
            One of ``semantic_classify``, ``predict_cost``, ``risk_score``,
            ``optimize_sql``.
        payload:
            The request body as a dict (must be JSON-serialisable).
        prompt_version:
            Current prompt template version.  Including this ensures
            cache invalidation when prompts change.
        """
        canonical = json.dumps(
            {"type": request_type, "prompt_version": prompt_version, "payload": payload},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Look up a cached response.  Returns ``None`` on miss or expiry."""
        if not self._enabled:
            return None

        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            if time.monotonic() > entry.expires_at:
                # Lazy eviction
                del self._store[key]
                self._misses += 1
                logger.debug("Cache expired: key=%s type=%s", key[:12], entry.request_type)
                return None

            self._hits += 1
            logger.debug("Cache hit: key=%s type=%s", key[:12], entry.request_type)
            return entry.value

    def put(self, key: str, value: Any, request_type: str) -> None:
        """Store a response in the cache.

        Parameters
        ----------
        key:
            The SHA-256 key from ``make_key()``.
        value:
            The response object to cache (Pydantic model or dict).
        request_type:
            Used to look up the TTL.
        """
        if not self._enabled:
            return

        ttl = self._ttls.get(request_type, _FALLBACK_TTL)
        now = time.monotonic()

        with self._lock:
            # Evict if at capacity — remove oldest entries first
            if len(self._store) >= self._max_entries and key not in self._store:
                self._evict_oldest()

            self._store[key] = _CacheEntry(
                value=value,
                expires_at=now + ttl,
                request_type=request_type,
                created_at=now,
            )

        logger.debug(
            "Cache put: key=%s type=%s ttl=%ds entries=%d",
            key[:12],
            request_type,
            ttl,
            len(self._store),
        )

    def invalidate(self, key: str) -> bool:
        """Remove a single entry.  Returns ``True`` if found."""
        with self._lock:
            removed = self._store.pop(key, None)
        return removed is not None

    def invalidate_by_type(self, request_type: str) -> int:
        """Remove all entries of a given request type.  Returns count removed."""
        with self._lock:
            keys = [k for k, v in self._store.items() if v.request_type == request_type]
            for k in keys:
                del self._store[k]
        logger.info("Invalidated %d cache entries for type=%s", len(keys), request_type)
        return len(keys)

    def invalidate_all(self) -> int:
        """Flush the entire cache.  Returns count removed."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            self._hits = 0
            self._misses = 0
        logger.info("Full cache invalidation: removed %d entries", count)
        return count

    @property
    def stats(self) -> dict[str, Any]:
        """Return cache hit/miss statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
                "max_entries": self._max_entries,
                "enabled": self._enabled,
            }

    @property
    def size(self) -> int:
        """Number of entries currently in the cache (including expired)."""
        return len(self._store)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evict_oldest(self) -> None:
        """Remove the 10% oldest entries when at capacity.

        Must be called while holding ``self._lock``.
        """
        now = time.monotonic()

        # First try to remove expired entries
        expired_keys = [k for k, v in self._store.items() if now > v.expires_at]
        for k in expired_keys:
            del self._store[k]

        if len(self._store) < self._max_entries:
            return

        # Still full — evict oldest 10%
        evict_count = max(1, self._max_entries // 10)
        sorted_keys = sorted(
            self._store.keys(),
            key=lambda k: self._store[k].created_at,
        )
        for k in sorted_keys[:evict_count]:
            del self._store[k]

        logger.debug(
            "Evicted %d expired + %d oldest entries",
            len(expired_keys),
            min(evict_count, len(sorted_keys)),
        )
