"""
HTTP client and Token Bucket Rate Limiting for BioNexus MCP Services.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from bionexus.egress_guard import guarded_urlopen

logger = logging.getLogger("bionexus.mcp.client")

class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter to prevent API 429 rate limit saturation."""

    def __init__(self, rate: float = 3.0, capacity: float = 5.0):
        self.rate = rate  # tokens added per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


# Domain-specific rate limiters
RATE_LIMITERS: Dict[str, TokenBucketRateLimiter] = {
    "ncbi": TokenBucketRateLimiter(rate=3.0, capacity=5.0),
    "ebi": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
    "opentargets": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
    "gnomad": TokenBucketRateLimiter(rate=4.0, capacity=8.0),
    "pdb": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
    "alphafold": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
    "string": TokenBucketRateLimiter(rate=3.0, capacity=5.0),
    "default": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
}


def _get_limiter_for_url(url: str) -> TokenBucketRateLimiter:
    if "ncbi.nlm.nih.gov" in url:
        return RATE_LIMITERS["ncbi"]
    elif "ebi.ac.uk" in url or "uniprot.org" in url or "ensembl.org" in url or "reactome.org" in url:
        return RATE_LIMITERS["ebi"]
    elif "opentargets.org" in url:
        return RATE_LIMITERS["opentargets"]
    elif "gnomad" in url:
        return RATE_LIMITERS["gnomad"]
    elif "rcsb.org" in url:
        return RATE_LIMITERS["pdb"]
    elif "ebi.ac.uk/pdbe" in url or "alphafold" in url:
        return RATE_LIMITERS["alphafold"]
    elif "string-db.org" in url:
        return RATE_LIMITERS["string"]
    return RATE_LIMITERS["default"]


# --- Configuration & Auth Loading ---
def get_api_key(key_name: str) -> Optional[str]:
    """Retrieve API key from environment variable or local .env file."""
    val = os.environ.get(key_name)
    if val:
        return val.strip()

    search_dirs = [
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ]
    for search_dir in search_dirs:
        env_path = os.path.join(search_dir, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"{key_name}="):
                            return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception as e:
                logger.debug(f"Error reading .env from {env_path}: {e}")
    return None


# --- Async HTTP Engine with Exponential Backoff Retries ---


async def async_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
    max_retries: int = 3,
    backoff_factor: float = 1.5,
) -> Any:
    """
    Execute asynchronous HTTP request with non-blocking I/O and exponential backoff retry.
    Uses asyncio.to_thread for thread-pool I/O without blocking the JSON-RPC event loop.
    """
    limiter = _get_limiter_for_url(url)
    await limiter.acquire()

    req_headers = {
        "User-Agent": "BioNexus-LocalMCP/2.0.0 (OpenScience; Contact: https://agent-plugins.org/)",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)

    body_bytes = None
    if json_data is not None:
        req_headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(json_data).encode("utf-8")

    def _sync_request() -> Any:
        req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
        with guarded_urlopen(
            req,
            timeout=timeout,
            purpose="Local MCP public scientific API request",
            payload=json_data,
        ) as resp:
            content = resp.read().decode("utf-8")
            if not content.strip():
                return {}
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"raw_text": content}

    endpoint = urlparse(url).hostname or "unknown-host"
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return await asyncio.to_thread(_sync_request)
        except urllib.error.HTTPError as e:
            last_exc = e
            logger.warning("HTTP %s from %s (attempt %s/%s)", e.code, endpoint, attempt, max_retries)
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                delay = backoff_factor**attempt
                await asyncio.sleep(delay)
            else:
                raise
        except Exception as e:
            last_exc = e
            logger.warning("Network %s from %s (attempt %s/%s)", type(e).__name__, endpoint, attempt, max_retries)
            if attempt < max_retries:
                delay = backoff_factor**attempt
                await asyncio.sleep(delay)
            else:
                raise

    raise last_exc or RuntimeError(f"Failed request to {endpoint}")


