"""
Async adapter for cloudscraper-turnstile (Peak.fo backend).

Used exclusively for Cloudflare Turnstile-protected shorteners such as
srnky.com, clksz.com, oii.la (shrinkearn.com / clk.sh ecosystem).

Architecture
------------
  cloudscraper-turnstile is a drop-in replacement for cloudscraper that
  intercepts Turnstile / 5-second "Just a moment" challenges and solves
  them via the Peak.fo API (https://peak.fo).  It is synchronous (like
  cloudscraper), so every call is wrapped in asyncio.to_thread().

  A separate semaphore (_TS_SEMAPHORE, default 3) caps concurrent solves
  because each solve is a paid API call and is slower (~1s) than a normal
  request.

Usage
-----
    from FZBypass.core.networking import ts

    resp = await ts.get("https://srnky.com/CjaPIdWKo")
    # resp is HTTPResponse, same interface as cf.get()

Configuration
-------------
  PEAK_API_KEY env var (or config.py key) — required.
  If unset, ts.get() / ts.post() raise NetworkConnectionError immediately
  with a clear message rather than crashing at import time.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping

from FZBypass.core.networking.exceptions import (
    NetworkCloudflareBlock,
    NetworkConnectionError,
    NetworkHTTPError,
    NetworkRateLimited,
    NetworkTimeout,
)
from FZBypass.core.networking.models import HTTPResponse

LOGGER = logging.getLogger(__name__)

# Turnstile solving is slower (~1s) and is a paid call — cap concurrency.
_TS_SEMAPHORE = asyncio.Semaphore(3)

# Generous timeout: Peak needs time to spin up a browser and solve.
TS_TIMEOUT = 60


def _to_response(r: Any) -> HTTPResponse:
    return HTTPResponse(
        status_code=r.status_code,
        url=str(r.url),
        headers=dict(r.headers),
        content=r.content,
        _text=r.text,
    )


def _make_ts_scraper(api_key: str, proxy: str | None = None) -> Any:
    """
    Build a cloudscraper-turnstile session with the Peak API key.

    cloudscraper-turnstile reads the key from:
      1. create_scraper(api_key="pk_...") — explicit kwarg
      2. create_scraper(captcha={"provider":"peak","api_key":"pk_..."})
      3. PEAK_API_KEY environment variable

    We pass it explicitly so the bot's PEAK_API_KEY config is always used
    regardless of whether the env var is set on the host.
    """
    import cloudscraper_turnstile as _cts  # type: ignore[import]
    kwargs: dict[str, Any] = {"api_key": api_key}
    if proxy:
        kwargs["proxy"] = proxy
    return _cts.create_scraper(**kwargs)


def _raise_from_requests_exc(exc: Exception, url: str) -> None:
    import requests.exceptions as req_exc
    name = type(exc).__name__
    if isinstance(exc, req_exc.Timeout):
        raise NetworkTimeout(f"{name}: {exc}") from exc
    if isinstance(exc, (req_exc.ConnectionError, req_exc.SSLError)):
        raise NetworkConnectionError(f"{name}: {exc}") from exc
    if isinstance(exc, req_exc.HTTPError):
        code = getattr(getattr(exc, "response", None), "status_code", 0)
        if code == 429:
            raise NetworkRateLimited() from exc
        raise NetworkHTTPError(code, url) from exc
    raise NetworkConnectionError(f"{name}: {exc}") from exc


class TurnstileClient:
    """
    Async wrapper around cloudscraper-turnstile.

    Mirrors the CloudflareClient interface (cf) so bypass functions can
    use ts.get() / ts.post() identically to cf.get() / cf.post().

    A single scraper session is created lazily on first use so that the
    PEAK_API_KEY is read after Config is fully initialised.
    """

    def __init__(self) -> None:
        self._scraper: Any = None
        self._api_key: str | None = None
        self._init_lock = asyncio.Lock()

    def _ensure_scraper(self, proxy: str | None = None) -> Any:
        """Return (cached) scraper or raise if key not configured."""
        if self._scraper is not None:
            return self._scraper
        # Import Config lazily to avoid circular import at module level
        from FZBypass import Config
        key = Config.PEAK_API_KEY
        if not key:
            raise NetworkConnectionError(
                "PEAK_API_KEY is not configured. "
                "Set it to your Peak.fo API key to use Turnstile bypass."
            )
        self._api_key = key
        self._scraper = _make_ts_scraper(key, proxy=proxy)
        return self._scraper

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        allow_redirects: bool = True,
        timeout: int = TS_TIMEOUT,
        proxy: str | None = None,
    ) -> HTTPResponse:
        scraper = self._ensure_scraper(proxy=proxy)
        if proxy and not getattr(scraper, "peak_proxy", None):
            scraper.peak_proxy = proxy
        kwargs: dict[str, Any] = {
            "allow_redirects": allow_redirects,
            "timeout": timeout,
        }
        if headers:
            kwargs["headers"] = headers
        if cookies:
            kwargs["cookies"] = cookies
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        try:
            async with _TS_SEMAPHORE:
                r = await asyncio.to_thread(scraper.get, url, **kwargs)
            return _to_response(r)
        except NetworkConnectionError:
            raise
        except Exception as exc:
            _raise_from_requests_exc(exc, url)

    async def post(
        self,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: int = TS_TIMEOUT,
        proxy: str | None = None,
    ) -> HTTPResponse:
        scraper = self._ensure_scraper(proxy=proxy)
        if proxy and not getattr(scraper, "peak_proxy", None):
            scraper.peak_proxy = proxy
        kwargs: dict[str, Any] = {"timeout": timeout}
        if data is not None:
            kwargs["data"] = data
        if json is not None:
            kwargs["json"] = json
        if headers:
            kwargs["headers"] = headers
        if cookies:
            kwargs["cookies"] = cookies
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        try:
            async with _TS_SEMAPHORE:
                r = await asyncio.to_thread(scraper.post, url, **kwargs)
            return _to_response(r)
        except NetworkConnectionError:
            raise
        except Exception as exc:
            _raise_from_requests_exc(exc, url)


# ── Module-level singleton ────────────────────────────────────────────────────
ts = TurnstileClient()
