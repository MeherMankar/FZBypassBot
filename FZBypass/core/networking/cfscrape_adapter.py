"""
Async browser-fingerprint HTTP client backed by wreq.

Replaces the old cfscrape/cloudscraper adapter.  wreq uses BoringSSL and
emits a genuine Chrome 136 TLS+HTTP/2 handshake (correct JA3/JA4, Akamai
H2 fingerprint) — things that cfscrape/cloudscraper never did, because
those libraries only spoofed headers while using Python's own TLS stack.

Key differences from the old adapter
-------------------------------------
- No `asyncio.to_thread()` / semaphore — wreq's client is natively async.
- `r.status_code` is not available; use the `HTTPResponse` wrapper below
  which normalises to the same interface the rest of the codebase expects.
- Proxy is passed as `wreq.Proxy.all(url)` at session-creation time, not
  as a per-request `proxies=` dict.

Usage (unchanged from before)
------------------------------
    from FZBypass.core.networking import cf

    resp = await cf.get("https://cloudflare-protected-site.com/path")
    resp.raise_for_status()
    print(resp.text)
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

import wreq
from wreq import Client, Emulation, Policy, Proxy

from FZBypass.core.networking.exceptions import (
    NetworkCloudflareBlock,
    NetworkConnectionError,
    NetworkHTTPError,
    NetworkRateLimited,
    NetworkTimeout,
)
from FZBypass.core.networking.models import HTTPResponse

LOGGER = logging.getLogger(__name__)

# Default redirect limit (matches old cfscrape allow_redirects=True behaviour).
_REDIRECT_FOLLOW = Policy.limited(10)
_REDIRECT_NONE   = Policy.none()

# Default emulation profile — Chrome 136 gives a real BoringSSL JA3/JA4.
_EMULATION = Emulation.Chrome136


# ── Internal helpers ──────────────────────────────────────────────────────────

def _status_int(r: Any) -> int:
    """Convert wreq StatusCode object to plain int."""
    return int(str(r.status).split()[0])


def _header_str(r: Any, name: str) -> str | None:
    """Get a response header value as a decoded string, or None."""
    mv = r.headers.get(name)
    if mv is None:
        return None
    try:
        return bytes(mv).decode()
    except Exception:
        return None


def _headers_dict(r: Any) -> dict[str, str]:
    """Convert wreq HeaderMap to a plain dict[str, str]."""
    out: dict[str, str] = {}
    for k_mv in r.headers.keys():
        try:
            k = bytes(k_mv).decode()
            v_mv = r.headers.get(k)
            if v_mv is not None:
                out[k] = bytes(v_mv).decode()
        except Exception:
            pass
    return out


async def _to_response(r: Any) -> HTTPResponse:
    """Consume a wreq response into an HTTPResponse."""
    text = await r.text()
    raw  = bytes(await r.bytes())
    return HTTPResponse(
        status_code=_status_int(r),
        url=str(r.url),
        headers=_headers_dict(r),
        content=raw,
        _text=text,
    )


def _check_cloudflare(resp: HTTPResponse) -> None:
    if resp.status_code in (403, 503) and "Just a moment" in resp.text:
        raise NetworkCloudflareBlock(f"Cloudflare challenge page at {resp.url}")


def _raise_from_wreq_exc(exc: Exception, url: str) -> None:
    """Map wreq exceptions to the NetworkError hierarchy."""
    name = type(exc).__name__
    if isinstance(exc, wreq.TimeoutError):
        raise NetworkTimeout(f"{name}: {exc}") from exc
    if isinstance(exc, (wreq.ConnectionError, wreq.TlsError, wreq.ProxyConnectionError)):
        raise NetworkConnectionError(f"{name}: {exc}") from exc
    if isinstance(exc, wreq.StatusError):
        # StatusError message: "is_status error: wreq::Error { kind: Status(NNN, …) }"
        try:
            code = int(str(exc).split("Status(")[1].split(",")[0])
        except Exception:
            code = 0
        if code == 429:
            raise NetworkRateLimited() from exc
        raise NetworkHTTPError(code, url) from exc
    if isinstance(exc, wreq.RedirectError):
        from FZBypass.core.networking.exceptions import NetworkRedirectLoop
        raise NetworkRedirectLoop(str(exc)) from exc
    raise NetworkConnectionError(f"{name}: {exc}") from exc


def _make_proxy(proxy_url: str | None) -> Proxy | None:
    if not proxy_url:
        return None
    return Proxy.all(proxy_url)


# ── Client class ──────────────────────────────────────────────────────────────

class CloudflareClient:
    """
    Async HTTP client with genuine Chrome TLS fingerprint via wreq.

    Exposes the same get() / post() / request() interface as the old
    CloudflareClient so all callsites are unchanged.

    A new wreq.Client is created per-request rather than reused as a
    long-lived session.  wreq clients are cheap to construct (no I/O),
    and keeping a shared stateful session across unrelated domains would
    bleed cookies.  Pass `fresh=True` (ignored — all requests are
    already isolated) or `cookies=` per-request for cookie injection.
    """

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        allow_redirects: bool = True,
        timeout: int = 30,
        fresh: bool = False,   # kept for API compatibility; always isolated
        proxy: str | None = None,
    ) -> HTTPResponse:
        redirect_policy = _REDIRECT_FOLLOW if allow_redirects else _REDIRECT_NONE
        client_kwargs: dict[str, Any] = {
            "emulation": _EMULATION,
            "redirect":  redirect_policy,
        }
        if proxy:
            client_kwargs["proxy"] = _make_proxy(proxy)

        req_headers = dict(headers) if headers else {}
        if cookies:
            # Inject as Cookie header (wreq cookie jar API is per-domain)
            cookie_hdr = "; ".join(f"{k}={v}" for k, v in cookies.items())
            existing = req_headers.get("Cookie", "")
            req_headers["Cookie"] = f"{existing}; {cookie_hdr}".lstrip("; ")

        try:
            async with Client(**client_kwargs) as c:
                async with c.get(url, headers=req_headers, timeout=float(timeout)) as r:
                    resp = await _to_response(r)
        except (NetworkCloudflareBlock, NetworkConnectionError,
                NetworkTimeout, NetworkHTTPError, NetworkRateLimited):
            raise
        except Exception as exc:
            _raise_from_wreq_exc(exc, url)

        _check_cloudflare(resp)
        return resp

    async def post(
        self,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: int = 30,
        fresh: bool = False,
        proxy: str | None = None,
    ) -> HTTPResponse:
        import json as _json_mod
        redirect_policy = _REDIRECT_FOLLOW
        client_kwargs: dict[str, Any] = {
            "emulation": _EMULATION,
            "redirect":  redirect_policy,
        }
        if proxy:
            client_kwargs["proxy"] = _make_proxy(proxy)

        req_headers = dict(headers) if headers else {}
        if cookies:
            cookie_hdr = "; ".join(f"{k}={v}" for k, v in cookies.items())
            existing = req_headers.get("Cookie", "")
            req_headers["Cookie"] = f"{existing}; {cookie_hdr}".lstrip("; ")

        # Prepare body
        body: bytes | None = None
        if json is not None:
            body = _json_mod.dumps(json).encode()
            req_headers.setdefault("Content-Type", "application/json")
        elif data is not None:
            if isinstance(data, bytes):
                body = data
            elif isinstance(data, str):
                body = data.encode()
            elif isinstance(data, dict):
                from urllib.parse import urlencode
                body = urlencode(data).encode()
                req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            else:
                body = str(data).encode()

        try:
            async with Client(**client_kwargs) as c:
                post_kwargs: dict[str, Any] = {
                    "headers": req_headers,
                    "timeout": float(timeout),
                }
                if body is not None:
                    post_kwargs["body"] = body
                async with c.post(url, **post_kwargs) as r:
                    resp = await _to_response(r)
        except (NetworkCloudflareBlock, NetworkConnectionError,
                NetworkTimeout, NetworkHTTPError, NetworkRateLimited):
            raise
        except Exception as exc:
            _raise_from_wreq_exc(exc, url)

        _check_cloudflare(resp)
        return resp

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        data: Any = None,
        allow_redirects: bool = True,
        timeout: int = 30,
        fresh: bool = False,
        proxy: str | None = None,
    ) -> HTTPResponse:
        """Generic method dispatcher — routes to get() or post()."""
        m = method.upper()
        if m == "GET":
            return await self.get(
                url, headers=headers, cookies=cookies,
                allow_redirects=allow_redirects, timeout=timeout,
                fresh=fresh, proxy=proxy,
            )
        if m == "POST":
            return await self.post(
                url, data=data, headers=headers, cookies=cookies,
                timeout=timeout, fresh=fresh, proxy=proxy,
            )
        # For other methods use wreq directly
        redirect_policy = _REDIRECT_FOLLOW if allow_redirects else _REDIRECT_NONE
        client_kwargs: dict[str, Any] = {"emulation": _EMULATION, "redirect": redirect_policy}
        if proxy:
            client_kwargs["proxy"] = _make_proxy(proxy)
        req_headers = dict(headers) if headers else {}
        if cookies:
            cookie_hdr = "; ".join(f"{k}={v}" for k, v in cookies.items())
            req_headers["Cookie"] = cookie_hdr
        try:
            async with Client(**client_kwargs) as c:
                req_fn = getattr(c, m.lower(), None)
                if req_fn is None:
                    raise NetworkConnectionError(f"wreq: unsupported method {m}")
                req_kwargs: dict[str, Any] = {"headers": req_headers, "timeout": float(timeout)}
                if data is not None:
                    req_kwargs["body"] = data if isinstance(data, bytes) else str(data).encode()
                async with req_fn(url, **req_kwargs) as r:
                    resp = await _to_response(r)
        except (NetworkCloudflareBlock, NetworkConnectionError,
                NetworkTimeout, NetworkHTTPError, NetworkRateLimited):
            raise
        except Exception as exc:
            _raise_from_wreq_exc(exc, url)

        _check_cloudflare(resp)
        return resp


# ── Module-level singleton ────────────────────────────────────────────────────
cf = CloudflareClient()
