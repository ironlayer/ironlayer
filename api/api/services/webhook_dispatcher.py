"""Webhook dispatcher for delivering IronLayer events to external subscribers.

Looks up active ``EventSubscription`` rows for the given event type and
tenant, then sends HTTP POST requests with HMAC-SHA256 signature headers
for verification.  Retries up to 3 times with exponential backoff.

SECURITY: Webhook secrets are hashed with bcrypt at rest.  The dispatcher
uses the *plaintext* secret (from ``EventPayload.data["_webhook_secret"]``
or looked up at init) to sign the request body.

INVARIANT: Webhook dispatch is fire-and-forget.  Failures are logged
but never propagate to the caller.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import logging
import socket
import urllib.parse
from typing import Any

import httpx

from api.services.event_bus import EventPayload

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0
_MAX_RETRIES = 3

# Private / reserved IP ranges that must be blocked for SSRF prevention.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_webhook_url(url: str, *, allow_http: bool = False) -> None:
    """Validate a webhook URL to prevent SSRF attacks.

    Raises ``ValueError`` if the URL targets a private/loopback address
    or uses a disallowed scheme.
    """
    parsed = urllib.parse.urlparse(url)

    # Require HTTPS in production; HTTP only if explicitly allowed (dev mode).
    if parsed.scheme == "http" and not allow_http:
        raise ValueError(f"Webhook URL must use HTTPS (got {parsed.scheme}): {url}")
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported webhook URL scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Webhook URL has no hostname: {url}")

    # Resolve hostname to IP addresses and check against blocked ranges.
    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve webhook hostname '{hostname}': {exc}") from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError(f"Webhook URL resolves to private/reserved IP {ip} " f"(network {network}): {url}")


_BACKOFF_BASE = 1.0  # seconds: 1, 2, 4


class WebhookDispatcher:
    """Dispatch events to registered webhook endpoints.

    Parameters
    ----------
    http_client:
        Optional ``httpx.AsyncClient`` for testing.  A default client
        is created if not provided.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
        self._owns_client = http_client is None

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client:
            await self._client.aclose()

    async def dispatch(
        self,
        payload: EventPayload,
        subscriptions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Deliver the event to all matching subscriptions.

        Parameters
        ----------
        payload:
            The event payload to deliver.
        subscriptions:
            List of subscription dicts with keys: ``url``, ``secret``,
            ``event_types`` (list[str]).

        Returns
        -------
        list[dict[str, Any]]
            Delivery results: ``{"url": ..., "status": ..., "attempts": ...}``.
        """
        body = payload.model_dump_json()
        results: list[dict[str, Any]] = []

        for sub in subscriptions:
            sub_url = sub["url"]
            sub_secret = sub.get("secret", "")
            sub_events = sub.get("event_types", [])

            # Filter: only deliver if the subscription covers this event.
            if sub_events and payload.event_type.value not in sub_events:
                continue

            # SSRF prevention: validate URL before delivery.
            try:
                _validate_webhook_url(sub_url, allow_http=False)
            except ValueError as exc:
                logger.warning("Skipping webhook delivery — %s", exc)
                results.append(
                    {
                        "url": sub_url,
                        "status": "blocked",
                        "error": str(exc),
                        "attempts": 0,
                    }
                )
                continue

            result = await self._deliver(sub_url, sub_secret, body, payload)
            results.append(result)

        return results

    async def _deliver(
        self,
        url: str,
        secret: str,
        body: str,
        payload: EventPayload,
    ) -> dict[str, Any]:
        """Attempt delivery with retries and exponential backoff."""
        signature = self._sign(body, secret)
        headers = {
            "Content-Type": "application/json",
            "X-IronLayer-Signature": signature,
            "X-IronLayer-Event": payload.event_type.value,
            "X-IronLayer-Delivery": payload.correlation_id,
        }

        last_error: str | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self._client.post(url, content=body, headers=headers)

                if 200 <= response.status_code < 300:
                    logger.info(
                        "Webhook delivered: url=%s status=%d attempt=%d event=%s",
                        url,
                        response.status_code,
                        attempt,
                        payload.event_type.value,
                    )
                    return {
                        "url": url,
                        "status": "delivered",
                        "status_code": response.status_code,
                        "attempts": attempt,
                    }

                last_error = f"HTTP {response.status_code}"
                logger.warning(
                    "Webhook delivery failed: url=%s status=%d attempt=%d/%d",
                    url,
                    response.status_code,
                    attempt,
                    _MAX_RETRIES,
                )

            except httpx.TimeoutException:
                last_error = "timeout"
                logger.warning(
                    "Webhook timeout: url=%s attempt=%d/%d",
                    url,
                    attempt,
                    _MAX_RETRIES,
                )
            except httpx.RequestError as exc:
                last_error = str(exc)
                logger.warning(
                    "Webhook error: url=%s error=%s attempt=%d/%d",
                    url,
                    exc,
                    attempt,
                    _MAX_RETRIES,
                )

            # Exponential backoff: 1s, 2s, 4s.
            if attempt < _MAX_RETRIES:
                backoff = _BACKOFF_BASE * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

        logger.error(
            "Webhook delivery exhausted retries: url=%s event=%s error=%s",
            url,
            payload.event_type.value,
            last_error,
        )
        return {
            "url": url,
            "status": "failed",
            "error": last_error,
            "attempts": _MAX_RETRIES,
        }

    @staticmethod
    def _sign(body: str, secret: str) -> str:
        """Compute HMAC-SHA256 signature of the request body."""
        if not secret:
            return ""
        return hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def verify_signature(body: str, secret: str, signature: str) -> bool:
        """Verify a webhook signature (for use by receivers)."""
        expected = WebhookDispatcher._sign(body, secret)
        return hmac.compare_digest(expected, signature)
