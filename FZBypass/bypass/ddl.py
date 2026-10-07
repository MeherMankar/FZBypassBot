"""
Bypass resolver functions — shortener / direct-link extraction.

HTTP architecture
-----------------
  http  (httpx)       — primary async client for all normal requests
  cf    (cfscrape)    — Cloudflare-compatible client; used only where
                        cloudscraper/JS-challenge behaviour is genuinely
                        needed, always called via asyncio.to_thread
  curl_cffi cSession  — retained for ouo.press (Chrome TLS fingerprint
                        required; neither httpx nor cfscrape replicates it)

Every network call has a bounded timeout.
No aiohttp ClientSession is created here any more.
"""
from __future__ import annotations

import json as _json
import re as _re
from asyncio import sleep as asleep
from asyncio import to_thread as _to_thread
from html import unescape as _html_unescape
from urllib.parse import parse_qs, quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from curl_cffi.requests import Session as cSession
from requests import Session  # synchronous — only used inside terabox WAP path

from FZBypass import Config
from FZBypass.bypass.recaptcha import recaptchaV3
from FZBypass.core.exceptions import DDLException, ResolverStepError
from FZBypass.core.networking import cf, http, ts
from FZBypass.core.networking.client import DEFAULT_TIMEOUT
from FZBypass.core.networking.exceptions import NetworkError

# ── Shared httpx timeout override for short-lived shortener pages ─────────────
_SHORT_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=15.0, pool=10.0)

# ── Mobile User-Agent used by most shortener bypass attempts ─────────────────
_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)

# ── Transient-error retry helper ─────────────────────────────────────────────
_TRANSIENT_PHRASES = (
    "TimeoutException", "ConnectError", "ReadError", "RemoteProtocol",
    "ConnectionError", "ReadTimeout", "ConnectTimeout", "NetworkError",
)

async def _retry(coro_fn, *args, attempts: int = 2, **kwargs):
    """
    Retry an async bypass call up to `attempts` times on transient network
    errors.  A DDLException whose message contains one of _TRANSIENT_PHRASES
    is considered transient and eligible for a retry.  Any other DDLException
    (logic error, page structure change, CAPTCHA, …) is re-raised immediately.
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await coro_fn(*args, **kwargs)
        except DDLException as e:
            msg = str(e)
            if any(p in msg for p in _TRANSIENT_PHRASES):
                last_exc = e
                if attempt < attempts - 1:
                    await asleep(1.5)
                continue
            raise  # non-transient — don't retry
    raise last_exc  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════════
# FILE HOSTER RESOLVERS
# ═══════════════════════════════════════════════════════════════════════════════
async def yandex_disk(url: str) -> str:
    """
    Uses cfscrape (via adapter) — Yandex Cloud API requires
    browser-like headers which cfscrape provides reliably.
    """
    api = f"https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key={url}"
    try:
        resp = await cf.get(api)
        resp.raise_for_status()
        data = _json.loads(resp.content)
        return data["href"]
    except KeyError:
        raise DDLException("Yandex: File not Found / Download Limit Exceeded")
    except NetworkError as e:
        raise DDLException(f"Yandex: {e}") from e


async def mediafire(url: str) -> str:
    """
    Uses cfscrape — Mediafire applies bot-detection headers checks.
    """
    # Fast path: direct download URL already in the input
    if m := _re.findall(r"https?://download\d+\.mediafire\.com/\S+/\S+/\S+", url):
        return m[0]
    try:
        r1 = await cf.get(url)
    except NetworkError as e:
        raise ResolverStepError("MediaFire", "landing-page", type(e).__name__) from e
    url = r1.url
    try:
        r2 = await cf.get(url)
        page = r2.text
    except NetworkError as e:
        raise ResolverStepError("MediaFire", "download-page", type(e).__name__) from e

    if m := _re.findall(r"'(https?://download\d+\.mediafire\.com/\S+/\S+/\S+)'", page):
        return m[0]
    # Newer Mediafire layout uses <a id="downloadButton" href="...">
    soup_mf = BeautifulSoup(page, "html.parser")
    dl_btn = soup_mf.find("a", {"id": "downloadButton"})
    if dl_btn and dl_btn.get("href", "").startswith("http"):
        return dl_btn["href"]
    if m := _re.findall(r"(https?://download\d+\.mediafire\.com/[^\s\"'<>]+)", page):
        return m[0]
    if m := _re.findall(r"//(www\.mediafire\.com/file/\S+/\S+/file\?\S+)", page):
        return await mediafire("https://" + m[0].strip('"'))
    raise ResolverStepError(
        "MediaFire", "extract-download-link", "no download links found in page"
    )


async def shrdsk(url: str) -> str:
    """
    Uses cfscrape for the initial redirect, then httpx for the API call.
    """
    try:
        r = await cf.get(url)
        short_id = r.url.split("/")[-1]
    except NetworkError as e:
        raise DDLException(f"Shrdsk: {type(e).__name__}") from e

    api = f"https://us-central1-affiliate2apk.cloudfunctions.net/get_data?shortid={short_id}"
    try:
        resp = await http.get(api, timeout=_SHORT_TIMEOUT)
        resp.raise_for_status()
    except NetworkError as e:
        raise DDLException(f"Shrdsk: {type(e).__name__}") from e

    data = _json.loads(resp.content)
    if data.get("type", "").lower() == "upload" and "video_url" in data:
        return quote(data["video_url"], safe=":/")
    raise DDLException("Shrdsk: No Direct Link Found")


async def pornhub(url: str) -> str:
    """
    Extract video download link from PornHub via grabx-api.
    Returns the best proxy download URL from the API.
    Requires GRABX_API_URL to be configured.
    """
    if not Config.GRABX_API_URL:
        raise DDLException(
            "PornHub: GRABX_API_URL not configured — "
            "deploy grabx-api and set the URL in config."
        )
    headers = {"Content-Type": "application/json"}
    if Config.GRABX_API_KEY:
        headers["X-API-Key"] = Config.GRABX_API_KEY
    try:
        resp = await http.post(
            f"{Config.GRABX_API_URL}/ph/download",
            json={"url": url},
            headers=headers,
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0),
        )
        data = _json.loads(resp.content)
    except NetworkError as e:
        raise DDLException(f"PornHub: API unreachable — {type(e).__name__}") from e

    if data.get("status") != "success":
        raise DDLException(f"PornHub: {data.get('message', 'unknown error')}")

    d = data.get("data", {})
    # Prefer proxy download URL (goes through API with auth headers)
    link = (
        d.get("best_proxy_url")
        or d.get("best_download_url")
        or d.get("best_url")
    )
    if not link:
        raise DDLException("PornHub: no download link in API response")
    return link


async def terabox(url: str) -> list:
    """
    Resolve a Terabox share URL to a list of direct download links.

    Path 1 — GRABX_API_URL (preferred, new grabx-api):
        POST /download with X-API-Key header.
        Returns proxy_url / dlink per file.
    Path 2 — TERABOX_API_URL (old terabox-downloader-api, fallback):
        POST /download with JSON body only.
    Path 3 — TERA_COOKIE WAP bypass (last resort):
        Synchronous requests.Session inside asyncio.to_thread().
    """
    # ── Path 1: grabx-api (new) ───────────────────────────────────────────────
    if Config.GRABX_API_URL:
        api_timeout = httpx.Timeout(connect=10.0, read=60.0, write=15.0, pool=10.0)
        headers = {"Content-Type": "application/json"}
        if Config.GRABX_API_KEY:
            headers["X-API-Key"] = Config.GRABX_API_KEY
        try:
            resp = await http.post(
                f"{Config.GRABX_API_URL}/download",
                json={"url": url},
                headers=headers,
                timeout=api_timeout,
            )
            resp.raise_for_status()
            data = _json.loads(resp.content)
        except NetworkError as e:
            if not Config.TERABOX_API_URL and not Config.TERA_COOKIE:
                raise DDLException(f"GrabX API unreachable: {type(e).__name__}") from e
        else:
            if data.get("status") == "success":
                files = data["data"].get("files", [])
                links = [
                    f.get("proxy_url") or f.get("dlink")
                    for f in files
                    if f.get("proxy_url") or f.get("dlink")
                ]
                if links:
                    return links
                raise DDLException("GrabX API: no download links in response")
            raise DDLException(
                f"GrabX API: {data.get('message', 'unknown error')}"
            )

    # ── Path 2: old terabox-downloader-api ────────────────────────────────────
    if Config.TERABOX_API_URL:
        api_timeout = httpx.Timeout(connect=10.0, read=60.0, write=15.0, pool=10.0)
        try:
            resp = await http.post(
                f"{Config.TERABOX_API_URL}/download",
                json={"url": url},
                headers={"Content-Type": "application/json"},
                timeout=api_timeout,
            )
            resp.raise_for_status()
            data = _json.loads(resp.content)
        except NetworkError as e:
            if not Config.TERA_COOKIE:
                raise DDLException(
                    f"Terabox API unreachable: {type(e).__name__}"
                ) from e
        else:
            if data.get("status") == "success":
                files = data["data"].get("files", [])
                links = [
                    f.get("proxy_url") or f.get("dlink")
                    for f in files
                    if f.get("proxy_url") or f.get("dlink")
                ]
                if links:
                    return links
                raise DDLException("Terabox API: no download links in response")
            raise DDLException(
                f"Terabox API: {data.get('message', 'unknown error')}"
            )

    # ── Path 3: WAP bypass using TERA_COOKIE ─────────────────────────────────
    if not Config.TERA_COOKIE:
        raise DDLException(
            "Terabox: set GRABX_API_URL (recommended), TERABOX_API_URL, or TERA_COOKIE"
        )

    import asyncio
    from urllib.parse import parse_qs, urlparse as _up

    TERABOX_DOMAINS = [
        ".terabox.com", ".1024terabox.com", ".teraboxapp.com",
        ".nephobox.com", ".4funbox.co", ".mirrobox.com",
        ".momerybox.com", ".terasharefile.com", ".freeterabox.com",
    ]
    TERABOX_HOSTNAMES = [
        "www.terabox.com", "www.1024terabox.com", "www.teraboxapp.com",
        "www.terasharefile.com", "www.nephobox.com", "www.4funbox.co",
        "www.mirrobox.com", "www.momerybox.com", "www.freeterabox.com",
    ]
    MOBILE_UA_WAP = _MOBILE_UA

    def _parse_surl(share_url: str) -> str:
        parsed = _up(share_url)
        if "/s/" in parsed.path:
            surl = parsed.path.split("/s/")[-1].strip("/")
        else:
            qs = parse_qs(parsed.query)
            surl = qs.get("surl", [""])[0]
        if not surl:
            raise DDLException(f"Cannot extract surl from URL: {share_url}")
        if len(surl) > 22 and surl.startswith("1"):
            surl = surl[1:]
        if len(surl) < 8:
            raise DDLException(f"Invalid surl: '{surl}'")
        return surl

    def _build_session(ndus: str) -> Session:
        sess = Session()
        for domain in TERABOX_DOMAINS:
            sess.cookies.set("ndus", ndus, domain=domain)
        return sess

    def _fetch_wap_sync(sess: Session, surl: str, share_url: str) -> str:
        host = _up(share_url).hostname or ""
        candidates: list[str] = []
        if host:
            candidates += [
                f"http://{host}/wap/share/filelist?surl={surl}",
                f"https://{host}/wap/share/filelist?surl={surl}",
            ]
        for h in TERABOX_HOSTNAMES:
            u = f"https://{h}/wap/share/filelist?surl={surl}"
            if u not in candidates:
                candidates.append(u)
        candidates.append(f"http://www.terabox.com/wap/share/filelist?surl={surl}")
        headers = {"User-Agent": MOBILE_UA_WAP, "Accept": "text/html,*/*"}
        for wap_url in candidates:
            try:
                r = sess.get(wap_url, headers=headers, allow_redirects=True, timeout=15)
                if r.status_code == 200 and "__INITIAL_STATE__" in r.text:
                    return r.text
            except Exception:
                continue
        raise DDLException(f"Could not load Terabox WAP page for surl={surl}")

    def _extract_dlinks(html: str) -> list[str]:
        m = _re.search(
            r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*(?:;|</script>)",
            html, _re.DOTALL,
        )
        if not m:
            raise DDLException("window.__INITIAL_STATE__ not found in WAP page")
        try:
            state = _json.loads(m.group(1))
        except _json.JSONDecodeError:
            fl_m = _re.search(r'"fileList"\s*:\s*(\[.+?\])\s*,\s*"', html, _re.DOTALL)
            if not fl_m:
                raise DDLException("Could not parse file list from WAP page")
            file_list = _json.loads(fl_m.group(1))
            state = {"share": {"fileList": file_list}}
        file_list = state.get("share", {}).get("fileList", [])
        if not file_list:
            raise DDLException("No files found in Terabox WAP page")
        dlinks = [
            f["dlink"] for f in file_list
            if str(f.get("isdir", "0")) != "1" and f.get("dlink")
        ]
        if not dlinks:
            raise DDLException("No direct links found (folder-only share?)")
        return dlinks

    def _wap_bypass(ndus: str, surl: str, share_url: str) -> list[str]:
        sess = _build_session(ndus)
        html = _fetch_wap_sync(sess, surl, share_url)
        return _extract_dlinks(html)

    try:
        surl = _parse_surl(url)
        return await asyncio.to_thread(_wap_bypass, Config.TERA_COOKIE, surl, url)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"Terabox WAP bypass error: {type(e).__name__}: {e}") from e


# ═══════════════════════════════════════════════════════════════════════════════
# SHORTENER RESOLVERS (httpx-based)
# ═══════════════════════════════════════════════════════════════════════════════
async def try2link(url: str) -> str:
    """
    try2link.com — now a pure-JS SPA (React), not bypassable via HTTP.
    Raises DDLException with a clear message.
    """
    raise DDLException(
        "try2link: domain is dead — try2link.com is now a parked 'for sale' page"
    )


async def gyanilinks(url: str) -> str:
    """Uses httpx — standard countdown shortener (bloggingaro backend)."""
    code = url.split("/")[-1]
    ua = _MOBILE_UA
    DOMAIN = "https://go.bloggingaro.com"
    hdrs1 = {"Referer": "https://tech.hipsonyc.com/", "User-Agent": ua}
    hdrs2 = {"Referer": "https://hipsonyc.com/", "User-Agent": ua}
    try:
        r1 = await http.get(f"{DOMAIN}/{code}", headers=hdrs1, timeout=_SHORT_TIMEOUT)
        cookies = dict(r1.headers.get("set-cookie", "").split("=", 1))  # minimal parse
        # Re-use the httpx client but pass cookies extracted from r1
        # We need the actual cookie jar — use httpx cookie parsing
        import httpx as _httpx
        jar: dict[str, str] = {}
        for ch in r1.headers.get_list("set-cookie") if hasattr(r1.headers, "get_list") else []:
            kv = ch.split(";")[0].strip()
            if "=" in kv:
                k, v = kv.split("=", 1)
                jar[k.strip()] = v.strip()

        r2 = await http.get(
            f"{DOMAIN}/{code}",
            headers=hdrs2,
            cookies=jar,
            timeout=_SHORT_TIMEOUT,
        )
        html = r2.text
    except NetworkError as e:
        raise DDLException(f"gyanilinks: {type(e).__name__}") from e

    soup = BeautifulSoup(html, "html.parser")
    data = {inp.get("name"): inp.get("value") for inp in soup.find_all("input")}
    await asleep(5)
    try:
        resp = await http.post(
            f"{DOMAIN}/links/go",
            data=data,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": ua,
                "Referer": f"{DOMAIN}/{code}",
            },
            cookies=jar,
            timeout=_SHORT_TIMEOUT,
        )
    except NetworkError as e:
        raise DDLException(f"gyanilinks: POST failed — {e}") from e

    ct = resp.headers.get("content-type", "")
    if "application/json" in ct:
        result = _json.loads(resp.content)
        if "url" in result:
            return result["url"]
    raise DDLException("gyanilinks: no URL in response")


async def ouo(url: str) -> str:
    """
    Uses curl_cffi — ouo.press requires Chrome TLS fingerprint; neither
    httpx nor cfscrape replicates it.  Uses chrome136 impersonation + proxy
    to bypass Cloudflare's datacenter IP block on Render/cloud hosts.
    """
    from re import compile as _compile
    tempurl = url.replace("ouo.io", "ouo.press")
    p = urlparse(tempurl)
    oid = tempurl.split("/")[-1]

    proxy = Config.next_proxy()
    proxies = {"https": proxy, "http": proxy} if proxy else None

    client = cSession(
        headers={
            "authority": "ouo.press",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "cache-control": "max-age=0",
            "referer": "http://www.google.com/ig/adde?moduleurl=",
            "upgrade-insecure-requests": "1",
        },
        proxies=proxies,
    )
    res = client.get(tempurl, impersonate="chrome136", timeout=30)
    next_url = f"{p.scheme}://{p.hostname}/go/{oid}"

    for _ in range(2):
        if res.headers.get("Location"):
            break
        bs4 = BeautifulSoup(res.content, "lxml")
        if not bs4.form:
            raise DDLException(
                f"ouo: page blocked (no form) — status {res.status_code}. "
                "ouo.press is Cloudflare-protected; ensure PROXY_URL is set."
            )
        inputs = bs4.form.findAll("input", {"name": _compile(r"token$")})
        data = {inp.get("name"): inp.get("value") for inp in inputs}
        data["x-token"] = await recaptchaV3()
        res = client.post(
            next_url,
            data=data,
            headers={"content-type": "application/x-www-form-urlencoded"},
            allow_redirects=False,
            impersonate="chrome136",
            timeout=30,
        )
        next_url = f"{p.scheme}://{p.hostname}/xreallcygo/{oid}"

    location = res.headers.get("Location")
    if not location:
        raise DDLException("ouo: no redirect Location header in response")
    return location


async def gplinks(url: str) -> str:
    """
    gplinks.co / gplinks.in — adLinkFly go-link form bypass.

    Uses curl_cffi Chrome impersonation to pass Cloudflare TLS checks.

    ── Flow (updated for GPlinks Flow / GPF plugin) ──────────────────────

    gplinks.co now routes through an intermediary WordPress article page
    (e.g. fakepe.com) using the GPlinks Flow (GPF) plugin, which gates
    the link behind a multi-step ad-viewing countdown.

    1. GET /alias               → subscription gate (gate-btn-skip link)
    2. GET /alias?skip_sub=1   → redirects to intermediary article page
       → Page embeds gpfConfig with rest endpoint + nonce + step count
    3. POST wp-json/gpf/v1/advance (repeat per step, each waits ~30s)
       → {status: "complete", url: "gplinks.co/alias?pid=...&vid=..."}
    4. GET gplinks.co/alias?pid=...&vid=...
       → page with hidden #go-link form (_method + _csrfToken)
    5. POST /links/go  → JSON {url: destination}

    Falls back to old direct go-link form approach for non-GPF pages.
    """
    import time as _time
    import json as _json
    from urllib.parse import urljoin as _urljoin

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )

    def _post_go_link(sess, page_url: str, html: str, proxy: str | None = None) -> str:
        """Submit the #go-link form from the final gplinks page and parse the response."""
        soup = BeautifulSoup(html, "html.parser")
        form = soup.select_one("form#go-link")
        if form is None:
            for candidate in soup.find_all("form"):
                if "/links/go" in (candidate.get("action") or ""):
                    form = candidate
                    break
        if form is None:
            raise DDLException("gplinks: go-link form not found on final page")

        form_data = {
            inp.get("name"): inp.get("value", "")
            for inp in form.find_all("input")
            if inp.get("name")
        }
        action = _urljoin(page_url, form.get("action") or "/links/go")
        if not action.startswith("http"):
            action = "https://gplinks.co" + action

        counter_m = _re.search(r'"counter_value"\s*:\s*(\d+)', html)
        counter = int(counter_m.group(1)) if counter_m else 0
        if counter > 0:
            _time.sleep(counter + 1)

        r2 = sess.post(
            action,
            data=form_data,
            headers={
                "Referer": page_url,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "/".join(page_url.split("/")[:3]),
            },
            allow_redirects=False,
            timeout=20,
        )
        loc = r2.headers.get("Location")
        if loc:
            return _urljoin(str(r2.url), loc)
        try:
            obj = _json.loads(r2.text)
        except Exception:
            raise DDLException(f"gplinks: unexpected go-link response — {r2.text[:200]}")

        dest = obj.get("url") or obj.get("destination") or obj.get("link")
        if isinstance(dest, str) and dest.startswith("http"):
            return dest

        message = str(obj.get("message", ""))
        captcha_markers = ("captcha", "recaptcha", "turnstile")
        if any(marker in message.lower() for marker in captcha_markers):
            raise DDLException("gplinks: CAPTCHA verification required")
        raise DDLException(f"gplinks: {message or 'link resolution failed'}")


    def _run_sync() -> str:
        proxy = Config.next_proxy()
        sess = cSession(
            impersonate="chrome136",
            proxies={"http": proxy, "https": proxy} if proxy else None,
        )
        sess.headers.update({
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
        })

        # Step 1: visit alias page to seed session cookies
        r0 = sess.get(url, allow_redirects=True, timeout=20)
        if r0.status_code >= 400:
            raise DDLException(f"gplinks: HTTP {r0.status_code}")

        html0 = r0.text
        soup0 = BeautifulSoup(html0, "html.parser")

        title = soup0.title.get_text(" ", strip=True).lower() if soup0.title else ""
        # Hard paywall: protected link with no skip available
        if any(m in title for m in ("protected link", "confirm subscription", "gplinks premium")):
            raise DDLException("gplinks: protected/subscription page — cannot bypass")

        # Check for gate-btn-skip link (subscription gate with GPF behind it)
        skip_link = soup0.select_one("a.gate-btn-skip")
        skip_href = skip_link.get("href") if skip_link else None

        # Only raise paywall error if there's no free skip available
        if not skip_href and ("subscription/initiate" in html0 or "PLAN_ID" in html0):
            raise DDLException("gplinks: link is behind a paid subscription — cannot bypass")

        if not skip_href:
            # No gate — try direct go-link form (non-GPF path)
            form = soup0.select_one("form#go-link")
            if form is None:
                for candidate in soup0.find_all("form"):
                    if "/links/go" in (candidate.get("action") or ""):
                        form = candidate
                        break
            if form:
                return _post_go_link(sess, str(r0.url), html0, proxy)
            loc = r0.headers.get("Location")
            if loc:
                return _urljoin(str(r0.url), loc)
            raise DDLException("gplinks: go-link form not found on page")

        # Step 2: GET skip_sub=1 → lands on GPF intermediary article page
        skip_url = skip_href if skip_href.startswith("http") else _urljoin(str(r0.url), skip_href)
        r1 = sess.get(
            skip_url,
            headers={"Referer": str(r0.url)},
            allow_redirects=True,
            timeout=20,
        )
        current_url = str(r1.url)
        html = r1.text

        m_cfg = _re.search(r"var gpfConfig = ({.*?});", html)
        if not m_cfg:
            # No GPF — try direct go-link
            soup1 = BeautifulSoup(html, "html.parser")
            form = soup1.select_one("form#go-link")
            if form:
                return _post_go_link(sess, current_url, html, proxy)
            raise DDLException("gplinks: gpfConfig not found and no go-link form")

        # Step 3: GPF advance loop
        for _step in range(8):
            m_cfg = _re.search(r"var gpfConfig = ({.*?});", html)
            if not m_cfg:
                soup_n = BeautifulSoup(html, "html.parser")
                form = soup_n.select_one("form#go-link")
                if form:
                    return _post_go_link(sess, current_url, html, proxy)
                raise DDLException("gplinks: GPF config disappeared without go-link form")

            try:
                cfg = _json.loads(m_cfg.group(1))
            except Exception:
                raise DDLException("gplinks: could not parse gpfConfig JSON")

            rest = cfg.get("rest")
            nonce = cfg.get("nonce")
            if not rest or not nonce:
                raise DDLException("gplinks: gpfConfig missing rest/nonce")

            origin = "/".join(current_url.split("/")[:3])
            adv_url = rest + "advance"
            adv_headers = {
                "User-Agent": _UA,
                "Referer": current_url,
                "Content-Type": "application/json",
                "X-WP-Nonce": nonce,
                "Origin": origin,
            }

            r_adv = sess.post(adv_url, headers=adv_headers, json={"imps": 1}, timeout=20)
            try:
                data = _json.loads(r_adv.text)
            except Exception:
                raise DDLException(f"gplinks: advance non-JSON — {r_adv.text[:100]}")

            if data.get("status") in ("wait", "retry"):
                wait_sec = int(
                    data.get("seconds")
                    or cfg.get("timing", {}).get("display_seconds")
                    or 30
                )
                _time.sleep(wait_sec + 1)
                r_adv = sess.post(adv_url, headers=adv_headers, json={"imps": 1}, timeout=20)
                try:
                    data = _json.loads(r_adv.text)
                except Exception:
                    raise DDLException(f"gplinks: advance retry non-JSON — {r_adv.text[:100]}")

            status = data.get("status")
            next_url = data.get("url")

            if status == "complete" and next_url:
                r_final = sess.get(
                    next_url,
                    headers={"User-Agent": _UA, "Referer": current_url},
                    allow_redirects=True,
                    timeout=20,
                )
                if "error_code=ip_changed" in str(r_final.url):
                    raise DDLException(
                        "gplinks: ip_changed error — proxy IP changed mid-session"
                    )
                return _post_go_link(sess, str(r_final.url), r_final.text, proxy)

            if status == "next" and next_url:
                r_next = sess.get(
                    next_url,
                    headers={"User-Agent": _UA, "Referer": current_url},
                    allow_redirects=True,
                    timeout=20,
                )
                current_url = str(r_next.url)
                html = r_next.text
                continue

            raise DDLException(
                f"gplinks: unexpected advance status '{status}' — {data.get('message', '')}"
            )

        raise DDLException("gplinks: exceeded maximum GPF step count")

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"gplinks: {type(e).__name__} — {e}") from e


async def cyberloom(url: str) -> str:
    """Follow CyberLoom's redirect and extract the signed MessyCloud link."""
    def _run_sync() -> str:
        session = Session()
        session.headers["User-Agent"] = _MOBILE_UA
        try:
            response = session.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            for _ in range(5):
                soup = BeautifulSoup(response.text, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    href = anchor["href"].strip()
                    host = (urlparse(href).hostname or "").lower()
                    if (
                        href.startswith(("http://", "https://"))
                        and host not in {
                            "messycloud.ink",
                            "www.messycloud.ink",
                            "cyberloom.best",
                            "www.cyberloom.best",
                        }
                        and not href.rstrip("/").endswith(("/out", "/go"))
                    ):
                        return href
                next_link = soup.select_one("a#cta[href], a[href*='/out?']")
                if not next_link:
                    break
                response = session.get(
                    next_link["href"], headers={"Referer": response.url},
                    timeout=30, allow_redirects=True,
                )
                response.raise_for_status()
            raise DDLException("CyberLoom: signed download link not found")
        except DDLException:
            raise
        except Exception as e:
            raise DDLException(f"CyberLoom: {type(e).__name__}") from e

    return await _to_thread(_run_sync)


async def transcript(url: str, DOMAIN: str, ref: str, sltime: float) -> str:
    """
    Generic countdown-shortener bypass using httpx.
    Used by ~40 different shortener patterns in checker.py.
    """
    code = url.rstrip("/").split("/")[-1]
    ua = _MOBILE_UA
    try:
        r = await http.get(
            f"{DOMAIN}/{code}",
            headers={"Referer": ref, "User-Agent": ua},
            timeout=_SHORT_TIMEOUT,
        )
    except NetworkError as e:
        raise DDLException(f"transcript: GET failed — {type(e).__name__}") from e

    soup = BeautifulSoup(r.text, "html.parser")
    title_tag = soup.find("title")
    if title_tag and title_tag.text == "Just a moment...":
        return "Unable To Bypass Due To Cloudflare Protected"

    data = {
        inp.get("name"): inp.get("value")
        for inp in soup.find_all("input")
        if inp.get("name") and inp.get("value")
    }
    # Preserve cookies from the GET for the POST
    jar: dict[str, str] = {}
    for ch in (r.headers.get("set-cookie") or "").split("\n"):
        kv = ch.split(";")[0].strip()
        if "=" in kv:
            k, v = kv.split("=", 1)
            jar[k.strip()] = v.strip()

    await asleep(sltime)
    try:
        resp = await http.post(
            f"{DOMAIN}/links/go",
            data=data,
            headers={
                "Referer": f"{DOMAIN}/{code}",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": ua,
            },
            cookies=jar or None,
            timeout=_SHORT_TIMEOUT,
        )
    except NetworkError as e:
        raise DDLException(f"transcript: POST failed — {type(e).__name__}") from e

    ct = resp.headers.get("content-type", "")
    if "application/json" in ct:
        result = _json.loads(resp.content)
        if "url" in result:
            return result["url"]
    raise DDLException("transcript: no URL in response")


async def gcloud(url: str) -> str:
    """
    GCloud / GDShare pure-HTTP bypass.

    Accepts both gdshare.top/download/<token> and gcloud.cyou/download/<token> URLs.

    Flow
    ----
    1. GET the download page → follows any redirect to gcloud.cyou/download/<signed_token>/
    2. GET /download/<signed_token>/generate-links/ with HX-Request: true
       → HTMX partial contains an ``href="https://gdshare.top/instant/<instant_token>"``
    3. GET <instant_url>?ajax=1&_t=<ms_timestamp> with X-Requested-With: XMLHttpRequest
       → {"success": true, "download_url": "https://video-downloads.googleusercontent.com/..."}
    4. If no instant URL found (some files omit it), fall back to
       POST /download/<signed_token>/filepress/ → {"success": true, "download_url": "..."}

    The vault-based links (xCloud, GoFile, Buzzheavier) require a Cloudflare Turnstile
    challenge at /download/resolve/ and cannot be resolved via plain HTTP.
    """
    import time as _time

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    _HEADERS = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # ── Step 1: fetch download page (follows redirect gdshare.top → gcloud.cyou) ──
    try:
        r1 = await http.get(url, headers=_HEADERS, timeout=_SHORT_TIMEOUT)
    except NetworkError as e:
        raise DDLException(f"gcloud: page fetch failed — {type(e).__name__}") from e

    if r1.status_code == 404:
        raise DDLException("gcloud: file not found (link may have expired)")
    if r1.status_code != 200:
        raise DDLException(f"gcloud: unexpected HTTP {r1.status_code} on download page")

    page_url = str(r1.url)
    # The signed token sits between /download/ and the trailing slash
    m_tok = _re.search(r"/download/([^/]+)/?$", page_url)
    if not m_tok:
        raise DDLException(f"gcloud: could not extract signed token from URL: {page_url}")
    signed_token = m_tok.group(1)

    # Grab CSRF token from the download page cookie
    csrf = r1.cookies.get("csrftoken", "")

    # ── Step 2: fetch generate-links HTMX partial ────────────────────────────
    gen_url = f"https://gcloud.cyou/download/{signed_token}/generate-links/"
    try:
        r2 = await http.get(
            gen_url,
            headers={
                **_HEADERS,
                "HX-Request": "true",
                "HX-Current-URL": page_url,
            },
            timeout=_SHORT_TIMEOUT,
        )
    except NetworkError as e:
        raise DDLException(f"gcloud: generate-links fetch failed — {type(e).__name__}") from e

    if r2.status_code == 404:
        raise DDLException("gcloud: generate-links returned 404 — file may have expired")
    if r2.status_code != 200:
        raise DDLException(f"gcloud: generate-links HTTP {r2.status_code}")

    gen_html = r2.text

    # Update CSRF from HTMX script block (more reliable than cookie alone)
    csrf_m = _re.search(r"CSRF\s*=\s*'([^']+)'", gen_html)
    if csrf_m:
        csrf = csrf_m.group(1)

    # ── Step 3: extract instant URL and resolve via AJAX ────────────────────
    instant_m = _re.search(
        r'href="(https://(?:gdshare\.top|gcloud\.cyou)/instant/[^"]+)"',
        gen_html,
    )
    if instant_m:
        instant_url = instant_m.group(1)
        ts_ms = int(_time.time() * 1000)
        ajax_url = f"{instant_url}?ajax=1&_t={ts_ms}"
        try:
            ra = await http.get(
                ajax_url,
                headers={
                    **_HEADERS,
                    "X-Requested-With": "XMLHttpRequest",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Referer": instant_url,
                },
                timeout=_SHORT_TIMEOUT,
            )
        except NetworkError as e:
            raise DDLException(f"gcloud: instant AJAX failed — {type(e).__name__}") from e

        if ra.status_code == 200:
            try:
                data = ra.json()
            except Exception:
                raise DDLException("gcloud: instant AJAX returned non-JSON response")
            if data.get("success") and data.get("download_url"):
                return data["download_url"]

    # ── Step 4: FilePress fallback ────────────────────────────────────────────
    fp_url = f"https://gcloud.cyou/download/{signed_token}/filepress/"
    try:
        rf = await http.post(
            fp_url,
            headers={
                **_HEADERS,
                "X-CSRFToken": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": page_url,
                "Origin": "https://gcloud.cyou",
            },
            content=b"",
            timeout=_SHORT_TIMEOUT,
        )
    except NetworkError as e:
        raise DDLException(f"gcloud: filepress fallback failed — {type(e).__name__}") from e

    if rf.status_code == 200:
        try:
            fp_data = rf.json()
        except Exception:
            raise DDLException("gcloud: filepress returned non-JSON response")
        if fp_data.get("success") and fp_data.get("download_url"):
            return fp_data["download_url"]
        msg = fp_data.get("message", "FilePress link unavailable")
        raise DDLException(f"gcloud: {msg}")

    raise DDLException(
        "gcloud: no downloadable link available — "
        "instant link missing and FilePress disabled by file owner"
    )


# Keep the old name as an alias so any external callers are not broken.
gdshare = gcloud


async def just2earn(url: str) -> str:
    """Resolve a Just2Earn AdLinkFly-style go-link form when accessible."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    try:
        page = await cf.get(url, timeout=30)
    except NetworkError as e:
        raise DDLException(f"Just2Earn: page request failed — {type(e).__name__}") from e

    soup = BeautifulSoup(page.text, "html.parser")
    form = soup.select_one("form#go-link")
    if form is None:
        form = next(
            (
                candidate
                for candidate in soup.find_all("form")
                if "/links/go" in (candidate.get("action") or "")
            ),
            None,
        )
    if form is None:
        if page.status_code in (403, 503) or "Just a moment" in page.text:
            raise DDLException("Just2Earn: Cloudflare challenge blocks the page")
        raise DDLException("Just2Earn: go-link form not found")

    fields = {
        item.get("name"): item.get("value", "")
        for item in form.select("input[name]")
    }
    if not fields:
        raise DDLException("Just2Earn: go-link form has no submission fields")

    action = urljoin(page.url, form.get("action") or "/links/go")
    counter_match = _re.search(
        r'"counter_value"\s*:\s*(\d+)|counter_value["\s:=]+(\d+)',
        page.text,
    )
    counter = int(next(value for value in counter_match.groups() if value)) if counter_match else 0
    if counter:
        await asleep(counter + 1)

    try:
        response = await cf.post(
            action,
            data=fields,
            headers={
                "Referer": page.url,
                "Origin": base,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
            timeout=30,
        )
    except NetworkError as e:
        raise DDLException(f"Just2Earn: go-link submission failed — {type(e).__name__}") from e

    try:
        data = _json.loads(response.content)
    except _json.JSONDecodeError as e:
        raise DDLException("Just2Earn: invalid go-link response") from e
    destination = data.get("url")
    if not destination or not isinstance(destination, str):
        raise DDLException(
            f"Just2Earn: {data.get('message', 'destination missing from response')}"
        )
    return destination


# ═══════════════════════════════════════════════════════════════════════════════
# REMAINING RESOLVERS (cfscrape or requests — documented reasons)
# ═══════════════════════════════════════════════════════════════════════════════
async def justpaste(url: str) -> str:
    """Uses curl_cffi — justpaste.it blocks cfscrape with NetworkConnectionError."""
    def _run_sync() -> str:
        sess = cSession(impersonate="chrome136")
        try:
            resp = sess.get(url, timeout=20)
        except Exception as e:
            raise DDLException(f"justpaste: {type(e).__name__}") from e
        soup = BeautifulSoup(resp.text, "html.parser")
        inps = soup.select('div[id="articleContent"] > p')
        parts = [p.get_text() for p in inps if p.get_text()]
        if not parts:
            raise DDLException("justpaste: no content paragraphs found")
        return ", ".join(parts)

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"justpaste: {type(e).__name__}") from e


async def linksxyz(url: str) -> str:
    """Uses httpx — plain redirect page."""
    try:
        resp = await http.get(url, timeout=_SHORT_TIMEOUT)
    except NetworkError as e:
        raise DDLException(f"linksxyz: {type(e).__name__}") from e
    soup = BeautifulSoup(resp.text, "html.parser")
    inps = soup.select('div[id="redirect-info"] > a')
    if not inps:
        raise DDLException("linksxyz: no redirect link found")
    return inps[0]["href"]


async def shareus(url: str) -> str:
    """Uses httpx — JSON API, no Cloudflare."""
    DOMAIN = "https://api.shrslink.xyz"
    code = url.split("/")[-1]
    ua = _MOBILE_UA
    try:
        r1 = await http.get(
            f"{DOMAIN}/v?shortid={code}&initial=true&referrer=",
            headers={"User-Agent": ua, "Origin": "https://shareus.io"},
            timeout=_SHORT_TIMEOUT,
        )
        r1.raise_for_status()
        sid = _json.loads(r1.content).get("sid")
    except (NetworkError, KeyError, _json.JSONDecodeError) as e:
        raise DDLException(f"shareus: {type(e).__name__}") from e
    if not sid:
        raise DDLException("shareus: ID Error")
    try:
        r2 = await http.get(
            f"{DOMAIN}/get_link?sid={sid}",
            headers={"User-Agent": ua, "Origin": "https://shareus.io"},
            timeout=_SHORT_TIMEOUT,
        )
        r2.raise_for_status()
        return _json.loads(r2.content)["link_info"]["destination"]
    except (NetworkError, KeyError, _json.JSONDecodeError) as e:
        raise DDLException(f"shareus: Link Extraction Failed — {e}") from e


async def dropbox(url: str) -> str:
    """Pure string transformation — no network call."""
    return (
        url.replace("www.", "")
        .replace("dropbox.com", "dl.dropboxusercontent.com")
        .replace("?dl=0", "")
    )


async def linkvertise(url: str) -> str:
    """
    Linkvertise bypass — pure HTTP via GraphQL API.

    Key insight: getContent, startTask, and completeTask must share the same
    client-generated action_id in task_args. Without it, startTask returns
    "TaskSet Not Found". The action_id is a UUID generated by the browser JS
    and passed consistently across all three mutations.

    Flow:
      1. Generate a random action_id
      2. getContent(identifier, task_args={action_id, ...})
         → ContentAccessTaskSet with tasks
      3. For each task: startTask + completeTask with same action_id
      4. Repeat until getContent returns DetailPageTargetData
      5. Return DetailPageTargetData.url
    """
    import uuid as _uuid

    _GRAPHQL = "https://publisher.linkvertise.com/graphql"
    _GQL_H = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://linkvertise.com",
        "Referer": "https://linkvertise.com/",
    }

    _GET_CONTENT = """query getContent($identifier: PublicLinkIdentificationInput!, $task_args: TaskArgument) {
        getContent(input: $identifier, task_args: $task_args) {
            __typename
            ... on ContentAccessTaskSet {
                tasks { __typename id status
                    ... on WaitTask { remainingWaitingTime adsTotal }
                    ... on AdTask { adIndex adsTotal }
                }
            }
            ... on DetailPageTargetData { type url paste }
        }
    }"""

    _START_TASK = """mutation startTask($identifier: PublicLinkIdentificationInput!, $task_id: String!, $task_args: TaskArgument) {
        startTask(input: $identifier, task_id: $task_id, task_args: $task_args) { __typename id status }
    }"""

    _COMPLETE_TASK = """mutation completeTask($identifier: PublicLinkIdentificationInput!, $task_id: String!, $task_args: TaskArgument) {
        completeTask(input: $identifier, task_id: $task_id, task_args: $task_args) { __typename id status }
    }"""

    # Extract user_id and slug from URL
    # Supports: linkvertise.com/USER_ID/SLUG, direct-link.net/USER_ID/SLUG, etc.
    id_m = _re.search(r"/(\d+)/([^/?&#]+)", url)
    if not id_m:
        raise DDLException("linkvertise: could not extract user_id/slug from URL")
    user_id, slug = id_m.group(1), id_m.group(2)

    # Generate action_id — must be consistent across all calls in this session
    action_id = str(_uuid.uuid4()) + str(_uuid.uuid4()).replace("-", "")[:20]
    request_id = str(_uuid.uuid4())  # helps complete WaitTask faster

    identifier = {"userIdAndUrl": {"url": slug, "user_id": user_id}}
    task_args = {
        "action_id": action_id,
        "request_id": request_id,
        "additional_data": {
            "taboola": {
                "user_id": "fallbackUserId",
                "consent_string": "",
                "external_referrer": "",
                "session_id": None,
                "url": f"https://linkvertise.com/access/{user_id}/{slug}",
            }
        },
    }

    async def _gql(c: httpx.AsyncClient, op: str, query: str, variables: dict) -> dict:
        r = await c.post(
            f"{_GRAPHQL}?name={op}",
            json={"operationName": op, "query": query, "variables": variables},
            headers=_GQL_H,
            timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=5.0),
        )
        return _json.loads(r.content)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=5.0),
        ) as c:
            # Initial page load to get Cloudflare cookies
            await c.get(url, headers={**_GQL_H, "Accept": "text/html,*/*"})

            completed: set[str] = set()

            for _attempt in range(15):
                # getContent — check if already unlocked
                d_gc = await _gql(c, "getContent", _GET_CONTENT,
                                  {"identifier": identifier, "task_args": task_args})
                result = d_gc.get("data", {}).get("getContent", {})

                if result.get("__typename") == "DetailPageTargetData":
                    dest = result.get("url") or result.get("paste")
                    if dest:
                        return dest
                    raise DDLException("linkvertise: destination page reached but no URL found")

                tasks = result.get("tasks", [])
                if not tasks:
                    raise DDLException("linkvertise: no tasks and no destination")

                any_action = False
                for task in tasks:
                    task_id = task["id"]
                    if task_id in completed or task.get("status") == "DONE":
                        completed.add(task_id)
                        continue
                    # PremiumTask requires a paid subscription — skip it
                    if task.get("__typename") == "PremiumTask":
                        completed.add(task_id)
                        continue

                    # startTask
                    d_st = await _gql(c, "startTask", _START_TASK,
                               {"identifier": identifier, "task_id": task_id,
                                "task_args": task_args})

                    # WaitTask: server enforces a timer — wait for it to expire
                    if task.get("__typename") == "WaitTask":
                        wait_secs = task.get("remainingWaitingTime") or 0
                        st_wait = (d_st.get("data", {})
                                      .get("startTask", {})
                                      .get("remainingWaitingTime") or 0)
                        wait_secs = max(wait_secs, st_wait)
                        if wait_secs and wait_secs > 0:
                            # Timer is server-enforced — cannot be bypassed
                            mins = round(wait_secs / 60)
                            raise DDLException(
                                f"linkvertise: this link has a wait timer of ~{mins} minute(s). "
                                f"Try again after the timer expires."
                            )

                    # completeTask
                    d_ct = await _gql(c, "completeTask", _COMPLETE_TASK,
                                      {"identifier": identifier, "task_id": task_id,
                                       "task_args": task_args})
                    new_status = (d_ct.get("data", {})
                                     .get("completeTask", {})
                                     .get("status"))
                    if new_status == "DONE":
                        completed.add(task_id)
                    any_action = True

                if not any_action:
                    raise DDLException("linkvertise: all tasks exhausted without destination")

            raise DDLException("linkvertise: destination not reached after 10 attempts")

    except DDLException:
        raise
    except (httpx.TimeoutException, httpx.RequestError) as e:
        raise DDLException(f"linkvertise: {type(e).__name__}") from e
    except Exception as e:
        raise DDLException(f"linkvertise: {type(e).__name__} — {e}") from e


async def rslinks(url: str) -> str:
    """Uses httpx with allow_redirects=False to read Location header."""
    try:
        resp = await http.get(
            url,
            follow_redirects=False,
            timeout=_SHORT_TIMEOUT,
        )
    except NetworkError as e:
        raise DDLException(f"rslinks: {type(e).__name__}") from e
    location = resp.headers.get("location", "")
    if not location:
        raise DDLException("rslinks: no Location header in response")
    code = location.split("ms9")[-1]
    return f"http://techyproio.blogspot.com/p/short.html?{code}=="


async def shorter(url: str) -> str:
    """
    Uses cfscrape — generic redirect follower; target sites vary wildly
    and often need browser-like headers that cfscrape provides.
    """
    try:
        resp = await cf.get(url, allow_redirects=False)
    except NetworkError as e:
        raise DDLException(f"shorter: {type(e).__name__}") from e
    location = resp.headers.get("Location") or resp.headers.get("location")
    if not location:
        raise DDLException("shorter: no Location header in response")
    return location


async def buzzheavier(url: str) -> str:
    """Resolve a Buzzheavier file page through its redirect endpoint."""
    download_url = url.rstrip("/") + "/download"
    try:
        resp = await http.get(
            download_url,
            follow_redirects=False,
            timeout=_SHORT_TIMEOUT,
        )
    except NetworkError as e:
        raise DDLException(f"Buzzheavier: {type(e).__name__}") from e

    destination = (
        resp.headers.get("Hx-Redirect")
        or resp.headers.get("hx-redirect")
        or resp.headers.get("Location")
        or resp.headers.get("location")
    )
    if not destination:
        raise DDLException("Buzzheavier: no download redirect found")
    return destination


async def vikingfile(url: str) -> str:
    """Solve VikingFile's Turnstile gate and extract its JSON download link."""
    if not Config.PEAK_API_KEY:
        raise DDLException(
            "VikingFile: PEAK_API_KEY is required for Turnstile solving"
        )
    proxy = Config.next_proxy()
    if not proxy:
        raise DDLException("VikingFile: a configured proxy is required")

    def _run_sync() -> str:
        session = Session()
        session.proxies.update({"http": proxy, "https": proxy})
        session.headers.update({"User-Agent": _MOBILE_UA})
        try:
            page = session.get(url, timeout=30)
            page.raise_for_status()
            sitekey_m = _re.search(
                r"sitekey\s*:\s*['\"]([^'\"]+)['\"]", page.text
            )
            if not sitekey_m:
                raise DDLException("VikingFile: Turnstile sitekey not found")

            solve_url = url if url.endswith("/") else url + "/"
            peak = session.post(
                "https://api.peak.fo/solve",
                headers={"X-API-Key": Config.PEAK_API_KEY},
                json={
                    "task_type": "turnstiletask",
                    "url": solve_url,
                    "sitekey": sitekey_m.group(1),
                    "proxy": proxy,
                },
                timeout=90,
            )
            peak.raise_for_status()
            peak_data = peak.json()
            token = (peak_data.get("data") or {}).get("token")
            if not peak_data.get("success") or not token:
                raise DDLException(
                    f"VikingFile: Peak solve failed — "
                    f"{peak_data.get('error', peak_data)}"
                )

            result = session.post(
                page.url,
                data={"cf-turnstile-response": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            result.raise_for_status()
            data = result.json()
            link = data.get("link")
            if not link:
                raise DDLException(
                    f"VikingFile: download link missing — "
                    f"{data.get('error', data)}"
                )
            return link
        except DDLException:
            raise
        except Exception as e:
            raise DDLException(f"VikingFile: {type(e).__name__} — {e}") from e

    return await _to_thread(_run_sync)


async def drivehub(url: str) -> str:
    """Solve DriveHub's Turnstile gate and resolve its secure mirror link."""
    if not Config.PEAK_API_KEY:
        raise DDLException("DriveHub: PEAK_API_KEY is required for Turnstile solving")
    proxy = Config.next_proxy()
    if not proxy:
        raise DDLException("DriveHub: a configured proxy is required")

    def _run_sync() -> str:
        session = Session()
        session.proxies.update({"http": proxy, "https": proxy})
        session.headers.update({"User-Agent": _MOBILE_UA})
        try:
            page = session.get(url, timeout=30)
            page.raise_for_status()
            sitekey_m = _re.search(r'data-sitekey="([^"]+)"', page.text)
            page_token_m = _re.search(r"const pageToken = '([^']+)'", page.text)
            if not sitekey_m or not page_token_m:
                raise DDLException("DriveHub: Turnstile parameters not found")

            peak = session.post(
                "https://api.peak.fo/solve",
                headers={"X-API-Key": Config.PEAK_API_KEY},
                json={
                    "task_type": "turnstiletask",
                    "url": page.url,
                    "sitekey": sitekey_m.group(1),
                    "proxy": proxy,
                },
                timeout=90,
            )
            peak.raise_for_status()
            peak_data = peak.json()
            token = (peak_data.get("data") or {}).get("token")
            if not peak_data.get("success") or not token:
                raise DDLException(
                    f"DriveHub: Peak solve failed — "
                    f"{peak_data.get('error', peak_data)}"
                )

            verify = session.post(
                f"{page.url.rstrip('/')}/ajax.php?ajax=verify-captcha",
                json={
                    "token": token,
                    "id": urlparse(page.url).path.rstrip("/").split("/")[-1],
                    "pt": page_token_m.group(1),
                },
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            verify.raise_for_status()
            verified = verify.json()
            if not verified.get("success") or not verified.get("secure_token"):
                raise DDLException(
                    f"DriveHub: captcha verification failed — "
                    f"{verified.get('message', verified)}"
                )

            secure_token = verified["secure_token"]
            targets = _re.findall(r'data-target="([^"]+)"', verified.get("html", ""))
            for target in ["instant", "r2", "gdrive", "hubcloud", *targets]:
                response = session.post(
                    page.url,
                    data={
                        "ajax_secure_action": "resolve_mirror",
                        "secure_token": secure_token,
                        "target": target,
                    },
                    headers={"X-Requested-With": "XMLHttpRequest"},
                    timeout=30,
                )
                if response.ok:
                    resolved = response.json()
                    if resolved.get("url"):
                        return resolved["url"]

            raise DDLException("DriveHub: no secure mirror URL returned")
        except DDLException:
            raise
        except Exception as e:
            raise DDLException(f"DriveHub: {type(e).__name__}") from e

    return await _to_thread(_run_sync)


async def extralink(url: str) -> str:
    """Resolve ExtraLink file pages through their session-bound /wk endpoint."""
    def _run_sync() -> str:
        import time

        session = Session()
        session.headers.update({"User-Agent": _MOBILE_UA})
        try:
            page = session.get(url, timeout=30, allow_redirects=True)
            page.raise_for_status()
            parsed = urlparse(str(page.url))
            server_id = parse_qs(parsed.query).get("id", [None])[0]
            if not server_id:
                raise DDLException("ExtraLink: download session ID not found")

            base = f"{parsed.scheme}://{parsed.netloc}"
            time.sleep(5)
            response = session.get(
                f"{base}/wk/{server_id}",
                timeout=30,
                allow_redirects=False,
                headers={"Referer": str(page.url)},
            )
            location = response.headers.get("Location") or response.headers.get(
                "location"
            )
            if not location:
                raise DDLException("ExtraLink: no direct download redirect found")
            if location.rstrip("/").endswith("/404"):
                raise DDLException("ExtraLink: file is unavailable")
            return urljoin(base, location)
        except DDLException:
            raise
        except Exception as e:
            raise DDLException(f"ExtraLink: {type(e).__name__} — {e}") from e

    return await _to_thread(_run_sync)


async def hubcdn(url: str) -> str:
    """Extract the encoded R2 object URL from a HubCDN redirect page."""
    import base64

    try:
        response = await cf.get(url)
    except NetworkError as e:
        raise DDLException(f"HubCDN: {type(e).__name__}") from e

    match_reurl = _re.search(r'var\s+reurl\s*=\s*["\']([^"\']+)', response.text)
    if not match_reurl:
        raise DDLException("HubCDN: redirect URL not found")

    encoded = parse_qs(urlparse(match_reurl.group(1)).query).get("r", [""])[0]
    if not encoded:
        raise DDLException("HubCDN: encoded destination not found")
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as e:
        raise DDLException("HubCDN: invalid encoded destination") from e

    destination = parse_qs(urlparse(decoded).query).get("link", [""])[0]
    if not destination.startswith(("http://", "https://")):
        raise DDLException("HubCDN: direct destination not found")
    return destination


async def vcloud(url: str) -> str:
    """Resolve VCloud's double-base64 token page to a direct mirror."""
    import base64

    try:
        first = await cf.get(url)
        token_match = _re.search(
            r"var\s+url\s*=\s*atob\s*\(\s*atob\s*\(\s*['\"]([^'\"]+)",
            first.text,
        )
        if not token_match:
            raise DDLException("VCloud: token URL not found")
        token_url = base64.b64decode(
            base64.b64decode(token_match.group(1))
        ).decode("utf-8")
        second = await cf.get(token_url)
    except NetworkError as e:
        raise DDLException(f"VCloud: {type(e).__name__}") from e
    except (ValueError, UnicodeDecodeError) as e:
        raise DDLException("VCloud: invalid encoded token URL") from e

    soup = BeautifulSoup(second.text, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        host = (urlparse(href).hostname or "").lower()
        if host.endswith(".r2.dev") or host.endswith(".r2.cloudflarestorage.com"):
            return href

    direct_match = _re.search(
        r"var\s+url\s*=\s*['\"](https?://[^'\"]+)",
        second.text,
    )
    if direct_match:
        return direct_match.group(1)
    raise DDLException("VCloud: no direct download mirror found")


async def xdmovies(url: str) -> str:
    """
    Follow XDMovie download wrappers to their downstream destination.

    XDMovie links currently redirect to ``latestnewsonline.sbs``. That
    downstream host may require a browser/Turnstile challenge, so the
    Peak-backed Turnstile client is used for the downstream request.
    """
    try:
        resp = await cf.get(url, allow_redirects=False)
    except NetworkError as e:
        raise DDLException(f"XDMovie: {type(e).__name__}") from e

    location = resp.headers.get("Location") or resp.headers.get("location")
    if not location:
        raise DDLException("XDMovie: no redirect location found")

    host = (urlparse(location).hostname or "").lower().removeprefix("www.")
    if host == "latestnewsonline.sbs":
        if not Config.PEAK_API_KEY:
            raise DDLException(
                "XDMovie: downstream latestnewsonline.sbs requires "
                "PEAK_API_KEY for Turnstile solving"
            )
        proxy = Config.next_proxy()
        if not proxy:
            raise DDLException(
                "XDMovie: Peak Turnstile solving requires a configured proxy"
            )
        try:
            solved = await ts.get(location, allow_redirects=True, proxy=proxy)
        except NetworkError as e:
            raise DDLException(
                f"XDMovie: Peak Turnstile solve failed "
                f"({type(e).__name__}: {e})"
            ) from e
        final_url = str(solved.url)
        if "latestnewsonline.sbs" in final_url and (
            solved.status_code in (403, 429, 503)
            or "just a moment" in solved.text.lower()
            or "turnstile" in solved.text.lower()
        ):
            raise DDLException(
                "XDMovie: downstream latestnewsonline.sbs remains "
                "Cloudflare-protected after Peak solving"
            )
        if final_url == location and not solved.text:
            raise DDLException(
                "XDMovie: Peak returned an empty downstream response"
            )
        return final_url
    return location


async def appurl(url: str) -> str:
    """Uses cfscrape — appurl sites have Cloudflare protection."""
    try:
        resp = await cf.get(url, allow_redirects=False)
    except NetworkError as e:
        raise DDLException(f"appurl: {type(e).__name__}") from e
    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select('meta[property="og:url"]')
    if not items:
        raise DDLException("appurl: og:url meta tag not found")
    return items[0]["content"]


async def surl(url: str) -> str:
    """Uses cfscrape — surl.li uses Cloudflare."""
    try:
        resp = await cf.get(f"{url}+")
    except NetworkError as e:
        raise DDLException(f"surl: {type(e).__name__}") from e
    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select('p[class="long-url"]')
    if not items or not items[0].string:
        raise DDLException("surl: long-url element not found")
    parts = items[0].string.split()
    if len(parts) < 2:
        raise DDLException("surl: could not parse long-url text")
    return parts[1]


async def thinfi(url: str) -> str:
    """Uses httpx — plain HTML redirect page."""
    try:
        resp = await http.get(url, timeout=_SHORT_TIMEOUT)
        resp.raise_for_status()
    except NetworkError as e:
        raise DDLException(f"thinfi: {type(e).__name__}") from e
    soup = BeautifulSoup(resp.content, "html.parser")
    try:
        return soup.p.a.get("href")
    except (AttributeError, TypeError):
        raise DDLException("thinfi: link element not found")




_PARTNER_CHAIN_SHORTENER_HOSTS = {"arolinks.com", "vplink.in", "vplinks.in"}


def _is_partner_chain_shortener_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return host in _PARTNER_CHAIN_SHORTENER_HOSTS


def _is_manual_partner_ad_gate(html_text: str) -> bool:
    page_text = " ".join(BeautifulSoup(html_text, "html.parser").stripped_strings)
    normalized = " ".join(page_text.casefold().split())
    has_step_counter = bool(_re.search(r"currently on step\s+\d+\s*/\s*\d+", normalized))
    requires_ad_click = "click any image" in normalized or "click image" in normalized
    requires_return = "come back" in normalized or "return to this page" in normalized
    return has_step_counter and requires_ad_click and requires_return


def _extract_vplink_partner_url(html_text: str, page_url: str) -> str | None:
    def _external_url(raw_url: str) -> str | None:
        raw_url = _html_unescape(raw_url.strip()).replace("\\/", "/")
        if raw_url.startswith("//"):
            raw_url = f"https:{raw_url}"

        candidate = urljoin(page_url, raw_url)
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not host:
            return None
        if host.removeprefix("www.") in _PARTNER_CHAIN_SHORTENER_HOSTS:
            return None
        return candidate

    soup = BeautifulSoup(html_text, "html.parser")
    anchors: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        candidate = _external_url(anchor["href"])
        if candidate:
            query = parse_qs(urlparse(candidate).query)
            label = anchor.get_text(" ", strip=True).casefold()
            priority = 0 if "insurancesstudy" in query else 1 if label == "click here" else 2
            anchors.append((priority, candidate))
    if anchors:
        return min(anchors, key=lambda item: item[0])[1]

    for raw_url in _re.findall(
        r"""(?:window|document)\.location(?:\.href)?\s*=\s*["']([^"']+)["']""",
        html_text,
    ):
        candidate = _external_url(raw_url)
        if candidate:
            return candidate
    return None


async def vplink(url: str) -> str:
    """
    vplink.in / vplinks.in — bypass via entiredust.in Referer + gt_uc_ cookie.

    The server returns the unlock page (gt-link anchor or go-link form) when
    the request carries a Chrome TLS fingerprint, the gt_uc_=<code> cookie,
    and one of the trusted entiredust.in article referers.
    """
    _shortcode = url.rstrip("/").split("/")[-1]

    _REFERERS = [
        "https://entiredust.in/studyscholorhiipss/top-5-fully-funded-global-enterprise-scholarships-2026/",
        "https://entiredust.in/studyscholorhiipss/best-fully-funded-us-corporate-universities-2026/",
        "https://entiredust.in/studyscholorhiipss/top-10-corporate-sponsored-global-universities-2026/",
        "https://entiredust.in/studyscholorhiipss/best-fully-funded-executive-enterprise-fellowships-canada-2026/",
        "https://entiredust.in/studyscholorhiipss/top-5-corporate-sponsored-us-universities-2026/",
        "https://entiredust.in/studyscholorhiipss/top-5-fully-funded-global-corporate-mba-destinations-2026/",
        "https://entiredust.in/studyscholorhiipss/top-5-sovereign-wealth-funded-global-corporate-scholarships-2026/",
        "https://darkguruji.com/",  # fallback
    ]

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    _DEST_PAT = _re.compile(
        r"(https?://(?:t\.me|telegram\.me|telegram\.dog|mega\.nz|"
        r"drive\.google\.com|devuploads\.com|gofile\.io|"
        r"pixeldrain\.[^'\"\s<>]+|fuckingfast\.[^'\"\s<>]+|"
        r"unlocktoearn\.[^'\"\s<>]+)[^\s'\"<>]*)"
    )

    _ANTIBYPASS_HOSTS = {"antibypass.koyeb.app", "avbypassbot.koyeb.app"}

    def _resolve_antibypass(sess_ab, ab_url: str, vplink_referer: str) -> str | None:
        """Hit antibypass URL with vplink session cookies + referer to extract finalUrl."""
        try:
            r_ab = sess_ab.get(
                ab_url,
                headers={"User-Agent": _UA, "Referer": vplink_referer},
                timeout=20,
            )
            if r_ab.status_code == 200:
                m = _re.search(
                    r'(?:var|let|const)\s+finalUrl\s*=\s*["\x27]([^"\']+)["\x27]',
                    r_ab.text,
                )
                if m:
                    return m.group(1)
        except Exception:
            pass
        return None

    def _run_sync() -> str:
        import time as _time
        for referer in _REFERERS:
            try:
                sess = cSession(impersonate="chrome120")
                sess.cookies.update({"gt_uc_": _shortcode})
                page = sess.get(
                    f"https://vplink.in/{_shortcode}",
                    headers={
                        "User-Agent": _UA,
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Referer": referer,
                    },
                    timeout=30,
                )
            except Exception:
                continue

            if page.status_code != 200:
                continue

            page_soup = BeautifulSoup(page.text, "html.parser")

            # Fast path — destination already in page as a direct link
            anchor = page_soup.find("a", id="gt-link")
            if anchor:
                href = anchor.get("href", "")
                if href.startswith("http") and "vplink.in" not in href:
                    # Resolve antibypass URLs inline using the current session
                    from urllib.parse import urlparse as _up_ab
                    ab_host = (_up_ab(href).hostname or "").lstrip("www.")
                    if ab_host in _ANTIBYPASS_HOSTS:
                        final = _resolve_antibypass(sess, href, f"https://vplink.in/{_shortcode}")
                        if final:
                            return final
                    return href

            # Standard go-link form
            unlock_form = page_soup.find("form", id="go-link")
            if not unlock_form:
                continue

            _time.sleep(7)

            form_action = unlock_form.get("action", "")
            if not form_action.startswith("http"):
                form_action = f"https://vplink.in{form_action}"

            form_fields = {
                field["name"]: field.get("value", "")
                for field in unlock_form.find_all("input")
                if field.get("name")
            }

            try:
                submit = sess.post(
                    form_action,
                    data=form_fields,
                    headers={
                        "Referer": str(page.url),
                        "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    timeout=30,
                )
                payload = _json.loads(submit.content)
                destination = (
                    payload.get("url") or payload.get("link") or payload.get("data")
                )
                if destination:
                    return destination
            except Exception:
                pass

            # Last resort: scan HTML for known destination URL patterns
            match = _DEST_PAT.search(page.text)
            if match:
                return match.group(1)

        raise DDLException("vplink: bypass failed — all referers exhausted")

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as exc:
        raise DDLException(f"vplink: {type(exc).__name__} — {exc}") from exc


async def antibypass(url: str) -> str:
    """
    antibypass.koyeb.app / avbypassbot.koyeb.app — MrSagarBots bypass proxy.

    These pages contain: let finalUrl = "https://t.me/..."
    Accessible with Referer: https://vplink.in/
    """
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def _run_sync() -> str:
        for referer in [
            "https://vplink.in/",
            "https://entiredust.in/studyscholorhiipss/top-5-fully-funded-global-enterprise-scholarships-2026/",
        ]:
            try:
                sess = cSession(impersonate="chrome120")
                r = sess.get(url, headers={"User-Agent": _UA, "Referer": referer}, timeout=20)
                if r.status_code == 200:
                    m = _re.search(
                        r'(?:var|let|const)\s+finalUrl\s*=\s*["\x27]([^"\']+)["\x27]',
                        r.text,
                    )
                    if m:
                        return m.group(1)
            except Exception:
                continue
        raise DDLException(
            "antibypass: could not extract finalUrl — must arrive from vplink.in"
        )

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as exc:
        raise DDLException(f"antibypass: {type(exc).__name__} — {exc}") from exc


async def arolinks(url: str) -> str:
    """
    arolinks.com — pure-HTTP bypass via techmint/onlinewish chain + referer trick.

    Confirmed flow (Oct 2026, discovered via CDP spy):
      1. GET arolinks.com/<code>  → set refXXX + gt_uc_ + AppSession cookies
      2. GET techmint.in/studyeducations/?universtityeducations=  → article 1
      3. GET article 1
      4. GET techmint.in/readmore/  → next landing URL
      5. GET techmint.in/studyeducations/?educationsscholorships=&pgtr=10&st=2  → article 2
      6. GET article 2
      7. GET onlinewish.in/studyblogs/educationsunivrsties/?univrsityinsurances=  → ow article
      8. GET ow article
      9. GET onlinewish.in/readmore/  â† establishes onlinewish.in session
      10. GET arolinks.com/<code> with Referer: https://onlinewish.in/
          → server returns go-link form or gt-link anchor (no timer!)
      11. Return gt-link href or POST /links/go
    """
    import re as _re2
    import time as _time

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    code = url.rstrip("/").split("/")[-1]

    def _run_sync() -> str:
        import requests as _req

        # Use plain requests for the chain (no CF challenges on techmint/onlinewish)
        s = _req.Session()
        s.headers.update({"User-Agent": _UA})

        def _js_redirect(text: str) -> str | None:
            match = _re2.search(
                r"""(?:window|document)\.location(?:\.href)?\s*=\s*
                ["']((?:https?:)?(?:\\?/\\?/|//)[^"']+)["']""",
                text,
                _re2.IGNORECASE | _re2.VERBOSE,
            )
            if not match:
                return None
            return match.group(1).replace("\\/", "/")

        # Step 1: GET arolinks → set refXXX + gt_uc_ cookies
        r1 = s.get(url, timeout=15)
        if r1.status_code != 200:
            raise DDLException(f"arolinks: HTTP {r1.status_code}")

        m = _re2.search(r'href=["\x27](https://techmint\.in[^"\']+)["\x27]', r1.text)
        partner = m.group(1).replace("&amp;", "&") if m else None
        if not partner:
            raise DDLException("arolinks: techmint URL not found in page")

        # Step 2: techmint landing 1 → article 1
        r2 = s.get(partner, headers={"Referer": url}, timeout=30)
        if r2.status_code >= 500:
            raise DDLException(f"arolinks: techmint down (HTTP {r2.status_code})")
        art1 = _js_redirect(r2.text)
        if not art1:
            raise DDLException("arolinks: techmint landing 1 JS redirect not found")
        s.get(art1, headers={"Referer": partner}, timeout=15)

        # Step 3: techmint readmore → second landing
        r_rm = s.get("https://techmint.in/readmore/", headers={"Referer": art1}, timeout=15)
        tl2 = _js_redirect(r_rm.text) or \
              f"https://techmint.in/studyeducations/?educationsscholorships={code}&pgtr=10&st=2"

        # Step 4: techmint landing 2 → article 2
        r3 = s.get(tl2, headers={"Referer": art1}, timeout=15)
        art2 = _js_redirect(r3.text) or art1
        s.get(art2, headers={"Referer": tl2}, timeout=15)

        # Step 5: onlinewish landing → article
        ow1 = f"https://onlinewish.in/studyblogs/educationsunivrsties/?univrsityinsurances={code}"
        r4 = s.get(ow1, headers={"Referer": art2}, timeout=15)
        ow_art = _js_redirect(r4.text)
        if ow_art:
            s.get(ow_art, headers={"Referer": ow1}, timeout=15)

        # Step 6: onlinewish readmore — establishes onlinewish.in domain session
        s.get("https://onlinewish.in/readmore/",
              headers={"Referer": ow_art or ow1}, timeout=15)

        # Step 7: hit arolinks with onlinewish.in referer via curl_cffi
        # (CF bot-score check requires a real Chrome TLS fingerprint)
        from curl_cffi.requests import Session as _CurlSess2
        sess = _CurlSess2(impersonate="chrome136")
        # Transfer arolinks cookies from the requests session
        for cookie in s.cookies:
            if "arolinks" in (cookie.domain or ""):
                sess.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
        # Also set by name for cookies without domain info
        for name in ("refNqtedK", f"ref{code}", "gt_uc_", "AppSession"):
            val = s.cookies.get(name)
            if val:
                sess.cookies.set(name, val, domain="arolinks.com")

        rf = sess.get(url, headers={"Referer": "https://onlinewish.in/",
                                    "User-Agent": _UA}, timeout=30)
        if rf.status_code != 200:
            raise DDLException(f"arolinks: final page HTTP {rf.status_code}")

        soup_f = BeautifulSoup(rf.text, "html.parser")

        # Fast path: gt-link anchor already has destination
        gt_link = soup_f.find("a", id="gt-link",
                              href=lambda h: h and h.startswith("http"))
        if gt_link:
            return gt_link["href"]

        # Standard go-link form
        golink = soup_f.select_one("form#go-link")
        if not golink:
            raise DDLException(
                f"arolinks: go-link form not found on final page — "
                "onlinewish.in session may not have been established"
            )
        hidden = {
            inp.get("name"): inp.get("value", "")
            for inp in golink.find_all("input")
            if inp.get("name")
        }
        action = golink.get("action") or "/links/go"
        if not action.startswith("http"):
            action = f"https://arolinks.com{action}"

        counter_m = _re2.search(r'"counter_value"\s*:\s*(\d+)', rf.text)
        counter = int(counter_m.group(1)) if counter_m else 0
        if counter > 0:
            _time.sleep(counter + 1)

        r_go = sess.post(
            action, data=hidden,
            headers={"Referer": str(rf.url), "X-Requested-With": "XMLHttpRequest"},
            timeout=20,
        )
        try:
            result = _json.loads(r_go.content)
        except Exception:
            raise DDLException(f"arolinks: non-JSON response — {r_go.text[:200]}")
        dest = result.get("url")
        if not dest:
            raise DDLException(f"arolinks: {result.get('message', 'no URL in response')}")
        return dest

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as exc:
        raise DDLException(f"arolinks: {type(exc).__name__} — {exc}") from exc
async def greenmotors(url: str) -> str:
    """
    greenmotors.club shortener bypass — pure HTTP, no browser.

    The token is stored in localStorage on the initial page as key 'o'.
    The /homelander/ page reads it and applies:
      token → base64_decode → base64_decode → ROT13 → base64_decode → JSON.parse
    The resulting JSON has an 'o' field which is a base64-encoded final URL.

    We replicate this entirely in Python:
      1. GET greenmotors.club/?id=... → extract localStorage token from JS
      2. Decode: b64d(b64d(rot13^-1(b64d(token)))) wait—
         actual order: b64d → b64d → rot13 → b64d → json → b64d(result['o'])
      3. Return the final URL
    """
    import base64 as _b64
    import codecs as _codecs
    import json as _json2

    def _b64d(s: str) -> str:
        s = s.strip()
        pad = 4 - len(s) % 4
        if pad != 4:
            s += "=" * pad
        return _b64.b64decode(s).decode("latin-1")

    def _decode_token(token: str) -> str:
        """Apply the full transformation chain to extract the final URL."""
        s = _b64d(token)          # step 1: base64 decode
        s = _b64d(s)              # step 2: base64 decode
        s = _codecs.encode(s, "rot_13")  # step 3: ROT13
        s = _b64d(s)              # step 4: base64 decode
        data = _json.loads(s)     # step 5: JSON parse → {w, l, o}
        encoded_url = data.get("o", "")
        if not encoded_url:
            raise DDLException("greenmotors: no destination URL in decoded token")
        return _b64d(encoded_url)  # step 6: base64 decode the final URL

    _H = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        async with httpx.AsyncClient(
            headers=_H, follow_redirects=True,
            timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=5.0),
        ) as c:
            r = await c.get(url)

        # Extract token from: s('o', 'TOKEN', ...)
        token_m = _re.search(r"s\('o','([^']+)'", r.text)
        if not token_m:
            raise DDLException("greenmotors: token not found on page")

        return _decode_token(token_m.group(1))

    except DDLException:
        raise
    except (httpx.TimeoutException, httpx.RequestError) as e:
        raise DDLException(f"greenmotors: {type(e).__name__}") from e
    except Exception as e:
        raise DDLException(f"greenmotors: {type(e).__name__} — {e}") from e


# ═══════════════════════════════════════════════════════════════════════════════
# FILE HOSTER RESOLVERS — batch 2
# ═══════════════════════════════════════════════════════════════════════════════
async def pixeldrain(url: str) -> str:
    """
    Pixeldrain direct link generator.

    Supports single files (/u/<id>) and lists (/l/<id>).
    Supports Pixeldrain domains with any valid DNS suffix, including
    multi-label suffixes such as .co.uk.
    Single file  → https://pixeldrain.<domain>/api/file/<id>?download
    List         → https://pixeldrain.<domain>/api/list/<id>/zip?download
    Verifies the file exists via the info endpoint before returning.
    """
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    domain = host.removeprefix("www.")
    if not _re.fullmatch(
        r"pixeldrain\."
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*",
        domain,
    ):
        raise DDLException("Pixeldrain: unsupported hostname")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0] not in {"u", "l"}:
        raise DDLException("Pixeldrain: unsupported URL format")
    kind, file_id = parts
    base_url = f"{parsed.scheme or 'https'}://{domain}"

    if kind == "l":
        info_link = f"{base_url}/api/list/{file_id}"
        dl_link = f"{base_url}/api/list/{file_id}/zip?download"
    else:
        info_link = f"{base_url}/api/file/{file_id}/info"
        dl_link = f"{base_url}/api/file/{file_id}?download"

    proxy = Config.next_proxy()

    def _fetch_info() -> dict:
        with cSession(
            impersonate="chrome136",
            proxies={"http": proxy, "https": proxy} if proxy else None,
        ) as session:
            response = session.get(info_link, timeout=30)
            response.raise_for_status()
            return response.json()

    try:
        data = await _to_thread(_fetch_info)
    except Exception as e:
        raise DDLException(f"Pixeldrain: {type(e).__name__}") from e

    if not data.get("success", True):
        raise DDLException(f"Pixeldrain: {data.get('message', 'File not accessible')}")

    return dl_link


async def gofile(url: str) -> str:
    """
    Gofile direct link generator.

    GoFile rotated their websiteToken (wt) away from a static constant.
    It is now a SHA-256 computed client-side:

        wt = sha256(f"{user_agent}::{language}::{account_token}::{window}::{salt}")
        window = floor(unix_time / 14400)   # 4-hour rotating bucket

    The salt ("12af056dacea0b") is embedded in wt.obf.js. It may change;
    override with the env var GOFILE_WT_SALT when that happens.

    The /contents request requires:
        Authorization: Bearer <token>
        X-Website-Token: <computed wt>
        X-BL: en-US
    """
    import hashlib as _hashlib
    import time as _time

    _API = "https://api.gofile.io"
    _GF_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    _GF_LANG = "en-US"
    _GF_SALT = "12af056dacea0b"  # from wt.obf.js; set GOFILE_WT_SALT env var to override

    import os as _os
    _GF_SALT = _os.environ.get("GOFILE_WT_SALT", _GF_SALT)

    content_id = url.rstrip("/").split("/")[-1]

    def _make_wt(account_token: str, window_offset: int = 0) -> str:
        window = int(_time.time() // 14400) + window_offset
        raw = f"{_GF_UA}::{_GF_LANG}::{account_token}::{window}::{_GF_SALT}"
        return _hashlib.sha256(raw.encode()).hexdigest()

    # Step 1: create guest account
    try:
        acc_resp = await http.post(
            f"{_API}/accounts",
            headers={"User-Agent": _GF_UA, "Origin": "https://gofile.io"},
            timeout=_SHORT_TIMEOUT,
        )
        acc_resp.raise_for_status()
        acc_data = _json.loads(acc_resp.content)
    except NetworkError as e:
        raise DDLException(f"Gofile: {type(e).__name__} creating account") from e

    if acc_data.get("status") != "ok":
        raise DDLException(f"Gofile: account creation failed — {acc_data.get('status', '')}")

    token = acc_data["data"]["token"]

    # Step 2: fetch content — retry once with previous time window on notPremium
    for window_offset in (0, -1):
        wt = _make_wt(token, window_offset)
        _content_headers = {
            "Authorization": f"Bearer {token}",
            "X-Website-Token": wt,
            "X-BL": _GF_LANG,
            "User-Agent": _GF_UA,
            "Origin": "https://gofile.io",
            "Referer": "https://gofile.io/",
        }
        try:
            content_resp = await http.get(
                f"{_API}/contents/{content_id}?contentFilter=&page=1&pageSize=1000"
                f"&sortField=createTime&sortDirection=-1",
                headers=_content_headers,
                timeout=_SHORT_TIMEOUT,
            )
            content_resp.raise_for_status()
            content_data = _json.loads(content_resp.content)
        except NetworkError as e:
            raise DDLException(f"Gofile: {type(e).__name__} fetching content") from e

        status = content_data.get("status", "")
        if status == "error-notPremium" and window_offset == 0:
            continue  # retry with previous 4-hour window
        if status != "ok":
            raise DDLException(f"Gofile: {status}")
        break

    children = content_data.get("data", {}).get("children", {})
    if not children:
        # Some responses use "contents" key instead
        children = content_data.get("data", {}).get("contents", {})
    if not children:
        raise DDLException("Gofile: no files found in content")

    for item in children.values():
        if item.get("type") == "file":
            link = item.get("link") or item.get("directLink")
            if link:
                return link

    raise DDLException("Gofile: no direct link found in content")



async def fichier(url: str) -> str:
    """
    1fichier.com direct link generator.

    Supports password-protected links via the :: separator:
      https://1fichier.com/?<id>::<password>

    Uses cfscrape — 1fichier checks TLS fingerprint / browser headers.
    """
    # Strip password if present
    pswd: str | None = None
    if "::" in url:
        url, pswd = url.rsplit("::", 1)

    # Strip affiliate/referral params (&af=, &aff=) — they redirect to homepage
    url = _re.sub(r'&af=[^&]+', '', url).rstrip('&')

    # Validate URL shape
    if not _re.match(r"^https?://.*1fichier\.com/\?.+", url):
        raise DDLException("1fichier: invalid URL format")

    post_data = {"pass": pswd} if pswd else {}

    try:
        resp = await cf.post(url, data=post_data)
    except NetworkError as e:
        raise DDLException(f"1fichier: {type(e).__name__}") from e

    if resp.status_code == 404:
        raise DDLException("1fichier: file not found")

    soup = BeautifulSoup(resp.content, "html.parser")

    # Success: orange download button
    btn = soup.find("a", {"class": "ok btn-general btn-orange"})
    if btn and btn.get("href"):
        return btn["href"]

    # Rate-limited or password-protected
    warnings = soup.find_all("div", {"class": "ct_warn"})
    for w in warnings:
        text = w.get_text(separator=" ").lower()
        if "you must wait" in text:
            nums = [int(x) for x in text.split() if x.isdigit()]
            wait = nums[0] if nums else "a few"
            raise DDLException(f"1fichier: rate limited — please wait {wait} minute(s)")
        if "protect access" in text:
            raise DDLException(
                "1fichier: password required — append ::<password> to the URL"
            )

    raise DDLException("1fichier: could not extract direct link from page")


async def streamtape(url: str) -> str:
    """
    Streamtape direct link extractor.

    The page embeds a JS expression of the form:
      document.getElementById('robotlink').innerHTML = '/get_video?...' + ('...')
    We regex-extract the two string fragments and assemble the URL.
    """
    # Fast path: already a direct CDN URL (/get_video?id=...)
    if "/get_video?" in url:
        if not url.startswith("http"):
            url = f"https://streamtape.com{url}"
        return url
    try:
        resp = await http.get(url, timeout=_SHORT_TIMEOUT)
        resp.raise_for_status()
    except NetworkError as e:
        raise DDLException(f"streamtape: {type(e).__name__}") from e

    text = resp.text

    # Pattern 1: modern inline JS  `document.xxx = "..."`
    m = _re.findall(r"robotlink['\"]?\)?[^>]*>([^<]+)<", text)
    if m:
        raw = m[-1].strip()
        if raw.startswith("/"):
            return f"https://streamtape.com{raw}"

    # Pattern 2: split JS concatenation  `= '/get_video?id=...' + '...'`
    parts = _re.findall(r"document[^=]+=\s*\"([^\"]+)\"", text)
    if len(parts) >= 2:
        fragment = (parts[-2] + parts[-1]).lstrip("/")
        return f"https://streamtape.com/{fragment}"

    # Pattern 3: single variable  `document.xxx = '/get_video?...'`
    m2 = _re.findall(r"document\.(?:getElementById\(['\"]robotlink['\"]\)|[^=]+)\s*=\s*['\"]([^'\"]+)['\"]", text)
    if m2:
        raw = m2[-1].strip()
        if raw.startswith("/"):
            return f"https://streamtape.com{raw}"

    raise DDLException("streamtape: could not extract video link from page")


async def wetransfer(url: str) -> str:
    """
    WeTransfer direct link extractor.

    Flow:
      1. GET the we.tl / wetransfer.com URL to resolve the final transfer URL
      2. POST /api/v4/transfers/<transfer_id>/download
         with {"security_hash": "<hash>", "intent": "entire_transfer"}
      3. Return direct_link from JSON response
    """
    try:
        # Follow redirects to get the canonical URL with transfer_id + hash
        resp = await cf.get(url)
        final_url = str(resp.url)
    except NetworkError as e:
        raise DDLException(f"wetransfer: {type(e).__name__}") from e

    # Extract transfer_id and security_hash from URL
    # Format: https://wetransfer.com/downloads/<transfer_id>/<security_hash>
    url_parts = final_url.rstrip("/").split("/")
    if len(url_parts) < 2:
        raise DDLException("wetransfer: could not parse transfer URL")

    transfer_id = url_parts[-2]
    security_hash = url_parts[-1]

    try:
        api_resp = await cf.post(
            f"https://wetransfer.com/api/v4/transfers/{transfer_id}/download",
            json={"security_hash": security_hash, "intent": "entire_transfer"},
            headers={"Content-Type": "application/json"},
        )
        data = _json.loads(api_resp.content)
    except NetworkError as e:
        raise DDLException(f"wetransfer: API call failed — {type(e).__name__}") from e

    if "direct_link" in data:
        return data["direct_link"]
    elif "message" in data:
        raise DDLException(f"wetransfer: {data['message']}")
    elif "error" in data:
        raise DDLException(f"wetransfer: {data['error']}")
    raise DDLException("wetransfer: no direct link in API response")


async def filecrypt(url: str) -> str:
    """
    Filecrypt.co DLC container extractor via dcrypt.it.

    Flow:
      1. GET filecrypt.co/... → find DownloadDLC('<id>') in button onclick
      2. GET filecrypt.co/DLC/<id>.html → DLC file content
      3. POST dcrypt.it/decrypt/paste → JSON list of real links
      4. Return the links as a newline-separated string
    """
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": url,
    }

    try:
        resp = await cf.get(url, headers={"Referer": url})
    except NetworkError as e:
        raise DDLException(f"filecrypt: {type(e).__name__}") from e

    soup = BeautifulSoup(resp.content, "html.parser")
    dlc_id: str | None = None
    for btn in soup.find_all("button"):
        onclick = btn.get("onclick", "")
        if "DownloadDLC(" in onclick:
            m = _re.search(r"DownloadDLC\('([^']+)'\)", onclick)
            if m:
                dlc_id = m.group(1)
                break

    if not dlc_id:
        raise DDLException("filecrypt: DLC button not found on page")

    dlc_url = f"https://filecrypt.co/DLC/{dlc_id}.html"
    try:
        dlc_resp = await cf.get(dlc_url, headers=_HEADERS)
    except NetworkError as e:
        raise DDLException(f"filecrypt: DLC fetch failed — {type(e).__name__}") from e

    dlc_content = dlc_resp.text

    # Decrypt via dcrypt.it
    try:
        decrypt_resp = await http.post(
            "http://dcrypt.it/decrypt/paste",
            data={"content": dlc_content},
            headers={
                "User-Agent": _HEADERS["User-Agent"],
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "http://dcrypt.it",
                "Referer": "http://dcrypt.it/",
            },
            timeout=_SHORT_TIMEOUT,
        )
        decrypt_resp.raise_for_status()
        result = _json.loads(decrypt_resp.content)
    except NetworkError as e:
        raise DDLException(f"filecrypt: dcrypt.it failed — {type(e).__name__}") from e

    links = result.get("success", {}).get("links", [])
    if not links:
        raise DDLException("filecrypt: dcrypt.it returned no links")

    return "\n\n".join(links)


async def krakenfiles(url: str) -> str:
    """
    KrakenFiles.com direct link extractor.

    Flow:
      1. GET krakenfiles.com/... → scrape form action URL + dl-token input
      2. POST <action_url> with {token: <dl-token>} → JSON {url: <direct_link>}
    """
    try:
        resp = await http.get(url, timeout=_SHORT_TIMEOUT)
        resp.raise_for_status()
    except NetworkError as e:
        raise DDLException(f"krakenfiles: {type(e).__name__}") from e

    soup = BeautifulSoup(resp.text, "html.parser")

    form = soup.find("form", {"id": "dl-form"})
    if not form:
        raise DDLException("krakenfiles: dl-form not found on page")

    action = form.get("action", "")
    if action.startswith("//"):
        action = "https:" + action
    elif action.startswith("/"):
        action = "https://krakenfiles.com" + action
    if not action:
        raise DDLException("krakenfiles: form action URL not found")

    token_inp = soup.find("input", {"id": "dl-token"})
    if not token_inp or not token_inp.get("value"):
        raise DDLException("krakenfiles: dl-token input not found")

    token = token_inp["value"]

    try:
        post_resp = await http.post(
            action,
            data={"token": token},
            timeout=_SHORT_TIMEOUT,
        )
        post_resp.raise_for_status()
        data = _json.loads(post_resp.content)
    except NetworkError as e:
        raise DDLException(f"krakenfiles: POST failed — {type(e).__name__}") from e

    dl_url = data.get("url")
    if not dl_url:
        raise DDLException("krakenfiles: no URL in POST response")

    return dl_url



async def onedrive(url: str) -> str:
    """
    OneDrive / 1drv.ms direct link generator.

    Flow:
      1. Base64-encode the share URL (without query string)
      2. HEAD https://api.onedrive.com/v1.0/shares/u!<encoded>/root/content
      3. Follow the 302 redirect → direct download URL

    Uses httpx follow_redirects=False to capture the Location header.
    """
    import base64 as _b64

    # Strip query string for the API call
    link_no_query = urlparse(url)._replace(query=None).geturl()
    encoded = _b64.b64encode(link_no_query.encode()).decode()
    api_url = f"https://api.onedrive.com/v1.0/shares/u!{encoded}/root/content"

    try:
        resp = await http.get(
            api_url,
            follow_redirects=False,
            timeout=_SHORT_TIMEOUT,
        )
    except NetworkError as e:
        raise DDLException(f"OneDrive: {type(e).__name__}") from e

    if resp.status_code == 302:
        location = resp.headers.get("location", "")
        if location:
            return location
        raise DDLException("OneDrive: 302 redirect but no Location header")

    if resp.status_code == 401:
        raise DDLException("OneDrive: link is private / requires sign-in")

    raise DDLException(f"OneDrive: unexpected status {resp.status_code}")




async def aylink(url: str) -> str:
    """
    aylink.co / ay.live shortener bypass.

    Token flow (from KaramelliS/shortlink-bypass):
      1. GET aylink.co/<slug>  → extract _a, _t, _d tokens + csrf + visitor_token
      2. POST /get/tk          → session key (th)
      3. POST /links/go2 with fake browser signal → destination URL
      4. Follow bildirim.online intermediate if present

    Uses curl_cffi for Chrome TLS fingerprint (aylink uses Cloudflare).
    """
    import time as _time

    _DOMAIN = "https://aylink.co"
    _UA = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # ay.live redirects to aylink.co — resolve slug first
    slug = url.rstrip("/").split("/")[-1]

    try:
        with cSession(impersonate="chrome120") as sess:
            # Step 1: landing page
            page = sess.get(
                f"{_DOMAIN}/{slug}",
                headers={"User-Agent": _UA},
                timeout=30,
            )
            html = page.text

        # Extract tokens
        _a = _re.search(r"_a\s*=\s*'([^']+)'", html)
        _t = _re.search(r"_t\s*=\s*'([^']+)'", html)
        _d = _re.search(r"_d\s*=\s*'([^']+)'", html)
        csrf = _re.search(r'csrf"\s*value="([^"]+)"', html)
        tok = _re.search(r"\['token'\]\s*=\s*'([^']+)'", html)

        if not all([_a, _t, _d, csrf, tok]):
            raise DDLException("aylink: tokens not found on page")

        _a_val = _a.group(1)
        _t_val = _t.group(1)
        _d_val = _d.group(1)
        csrf_val = csrf.group(1)
        tok_val = tok.group(1)
        ref = f"{_DOMAIN}/{slug}"

        # Step 2: get session key
        with cSession(impersonate="chrome120") as sess:
            tk_resp = sess.post(
                f"{_DOMAIN}/get/tk",
                data={"_a": _a_val, "_t": _t_val, "_d": _d_val},
                headers={
                    "User-Agent": _UA,
                    "Referer": ref,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Origin": _DOMAIN,
                },
                timeout=20,
            )
            tk_data = _json.loads(tk_resp.content)
            tk_val = tk_data.get("th")
            if not tk_val:
                raise DDLException("aylink: failed to get session key")

            # Step 3: go2 with fake browser signal
            signal = _json.dumps({
                "t": int(_time.time()), "d": 5,
                "m": {"move": 5, "click": 1, "scroll": 1, "key": 0, "touch": 0, "focus": 1},
                "f": {"webdriver": False, "headless": False, "noPlugins": False, "mobile": False},
            })
            go2_resp = sess.post(
                f"{_DOMAIN}/links/go2",
                data={
                    "alias": slug, "csrf": csrf_val,
                    "tkn": tk_val, "visitor_token": tok_val,
                    "signal": signal,
                },
                headers={
                    "User-Agent": _UA,
                    "Referer": ref,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Origin": _DOMAIN,
                },
                timeout=20,
            )
            go2_data = _json.loads(go2_resp.content)
            dest = go2_data.get("url", "")

        if not dest:
            raise DDLException("aylink: no destination URL in response")

        # Follow bildirim.online intermediate if present
        if "bildirim.online" in dest:
            try:
                r2 = await http.get(dest, headers={"User-Agent": _UA, "Referer": ref},
                                    timeout=_SHORT_TIMEOUT)
                m = _re.search(r"url\s*=\s*'([^']+)'", r2.text)
                if m:
                    dest = m.group(1)
            except NetworkError:
                pass

        return dest

    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"aylink: {type(e).__name__} — {e}") from e


async def cpmlink(url: str) -> str:
    """
    cpmlink.co / cpmlink.pro / cpm.link shortener bypass.

    Same token flow as aylink — /get/tk → /links/go2.
    Adapted from KaramelliS/shortlink-bypass.
    """
    import time as _time

    _DOMAIN = "https://cpmlink.pro"
    _UA = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # Resolve to cpmlink.pro if cpm.link or cpmlink.co
    slug = url.rstrip("/").split("/")[-1]

    try:
        with cSession(impersonate="chrome120") as sess:
            page = sess.get(
                f"{_DOMAIN}/{slug}",
                headers={"User-Agent": _UA},
                timeout=30,
            )
            html = page.text

        _a = _re.search(r"_a\s*=\s*'([^']+)'", html)
        _t = _re.search(r"_t\s*=\s*'([^']+)'", html)
        _d = _re.search(r"_d\s*=\s*'([^']+)'", html)
        csrf = _re.search(r'csrf"\s*value="([^"]+)"', html)
        vtoken = _re.search(r"app\['token'\]\s*=\s*'([^']+)'", html)
        alias = _re.search(r"app\['alias'\]\s*=\s*'([^']+)'", html)

        if not all([_a, _t, _d, csrf, vtoken]):
            raise DDLException("cpmlink: tokens not found on page")

        _a_val = _a.group(1)
        _t_val = _t.group(1)
        _d_val = _d.group(1)
        csrf_val = csrf.group(1)
        vtoken_val = vtoken.group(1)
        slug = alias.group(1) if alias else slug
        ref = f"{_DOMAIN}/{slug}"

        with cSession(impersonate="chrome120") as sess:
            tk_resp = sess.post(
                f"{_DOMAIN}/get/tk",
                data={"_a": _a_val, "_t": _t_val, "_d": _d_val},
                headers={
                    "User-Agent": _UA,
                    "Referer": ref,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Origin": _DOMAIN,
                },
                timeout=20,
            )
            tk_data = _json.loads(tk_resp.content)
            tk_val = tk_data.get("th")
            if not tk_val:
                raise DDLException("cpmlink: failed to get session key")

            signal = _json.dumps({
                "t": int(_time.time()), "d": 5,
                "m": {"move": 5, "click": 1, "scroll": 1, "key": 0, "touch": 0, "focus": 1},
                "f": {"webdriver": False, "headless": False, "noPlugins": False, "mobile": False},
            })
            go2_resp = sess.post(
                f"{_DOMAIN}/links/go2",
                data={
                    "alias": slug, "csrf": csrf_val,
                    "tkn": tk_val, "visitor_token": vtoken_val,
                    "signal": signal,
                },
                headers={
                    "User-Agent": _UA,
                    "Referer": ref,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Origin": _DOMAIN,
                },
                timeout=20,
            )
            dest = _json.loads(go2_resp.content).get("url", "")

        if not dest:
            raise DDLException("cpmlink: no destination URL in response")

        if "bildirim.online" in dest:
            try:
                r2 = await http.get(dest, headers={"User-Agent": _UA, "Referer": ref},
                                    timeout=_SHORT_TIMEOUT)
                m = _re.search(r"url\s*=\s*'([^']+)'", r2.text)
                if m:
                    dest = m.group(1)
            except NetworkError:
                pass

        return dest

    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"cpmlink: {type(e).__name__} — {e}") from e


async def boost(url: str) -> str:
    """
    boost.ink / mboost.me shortener bypass.

    The page embeds a base64-encoded destination in a JS variable `kekw`.
    Decode it to get the real URL.
    Adapted from KaramelliS/shortlink-bypass.
    """
    import base64 as _b64

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    try:
        resp = await http.get(url, headers={"User-Agent": _UA}, timeout=_SHORT_TIMEOUT)
        resp.raise_for_status()
    except NetworkError as e:
        raise DDLException(f"boost: {type(e).__name__}") from e

    m = _re.search(r'kekw\s*=\s*["\']([^"\']+)["\']', resp.text)
    if m:
        try:
            raw = m.group(1)
            padding = 4 - len(raw) % 4
            if padding != 4:
                raw += "=" * padding
            decoded = _b64.b64decode(raw).decode("utf-8", errors="replace")
            # Extract URL from decoded content
            url_m = _re.search(r'https?://[^\s"<>]+', decoded)
            if url_m:
                return url_m.group(0)
            if decoded.startswith("http"):
                return decoded.strip()
        except Exception as e:
            raise DDLException(f"boost: base64 decode failed — {e}") from e

    raise DDLException("boost: kekw variable not found on page")


async def shrinkme(url: str) -> str:
    """
    shrinkme.click / shrinkme.io shortener bypass — pure HTTP, no browser.

    The trick (analogous to vplink's gt_uc_ cookie):
      1. Visit shrinkme.click/<alias> first — this seeds a `ref<alias>` cookie
         that mrproblogger uses to verify the visitor came from a real shrinkme session
      2. GET https://en.mrproblogger.com/<alias> with the seeded cookies
         + Referer: https://themezon.net/ → form#go-link is served even from datacenter IPs
      3. Wait ~11s (server-side cryptographic timer in ad_form_data)
      4. POST /links/go → JSON {"status": "success", "url": "<destination>"}

    No Turnstile, no browser, no external API required.
    """
    _MRPRO = "https://en.mrproblogger.com"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )

    alias = url.rstrip("/").split("/")[-1]
    if not alias:
        raise DDLException("shrinkme: could not extract alias from URL")

    # Normalise to shrinkme.click domain
    shrinkme_url = f"https://shrinkme.click/{alias}"
    mrpro_url = f"{_MRPRO}/{alias}"

    def _run_sync() -> str:
        import time as _time
        from curl_cffi.requests import Session as _CurlSess

        proxy = Config.next_proxy()
        sess = _CurlSess(impersonate="chrome136",
                         proxies={"https": proxy, "http": proxy}
                         if proxy else None)

        # Step 1: seed ref<alias> cookie by visiting shrinkme.click.
        # If blocked (datacenter IP), set cookies directly on mrproblogger domain —
        # mrproblogger only checks for the presence of ref<alias>, not its value.
        seeded = False
        try:
            sess.get(shrinkme_url, headers={"User-Agent": _UA},
                     allow_redirects=True, timeout=15)
            seeded = any(c.name == f"ref{alias}" for c in sess.cookies.jar)
        except Exception:
            pass

        if not seeded:
            # Shrinkme.click blocked — inject cookies directly on mrproblogger
            # Use http.cookiejar for cross-version compatibility
            try:
                from http.cookiejar import Cookie as _Cookie
                _ck = _Cookie(
                    version=0, name=f"ref{alias}", value="bypass",
                    port=None, port_specified=False,
                    domain="en.mrproblogger.com", domain_specified=True,
                    domain_initial_dot=False,
                    path="/", path_specified=True, secure=False,
                    expires=None, discard=True,
                    comment=None, comment_url=None, rest={},
                )
                _ck2 = _Cookie(
                    version=0, name="app_visitor", value="Q2FrZQ==.bypass",
                    port=None, port_specified=False,
                    domain="en.mrproblogger.com", domain_specified=True,
                    domain_initial_dot=False,
                    path="/", path_specified=True, secure=False,
                    expires=None, discard=True,
                    comment=None, comment_url=None, rest={},
                )
                sess.cookies.jar.set_cookie(_ck)
                sess.cookies.jar.set_cookie(_ck2)
            except Exception:
                try:
                    sess.cookies.set(f"ref{alias}", "bypass",
                                     domain="en.mrproblogger.com")
                    sess.cookies.set("app_visitor", "Q2FrZQ==.bypass",
                                     domain="en.mrproblogger.com")
                except Exception:
                    pass

        # Step 2: hit mrproblogger with seeded session
        page = sess.get(
            mrpro_url,
            headers={"User-Agent": _UA, "Referer": "https://themezon.net/"},
            allow_redirects=False,  # capture raw response for diagnosis
            timeout=30,
        )

        # Log redirect chain for debugging
        status = page.status_code
        location = page.headers.get("location", "")
        sent_cookies = ""
        try:
            sent_cookies = page.request.headers.get("cookie", "") or page.request.headers.get("Cookie", "")
        except Exception:
            pass

        if status in (301, 302, 303, 307, 308):
            raise DDLException(
                f"shrinkme: mrproblogger redirected ({status}) -> {location[:60]} "
                f"[sent_cookies={'yes' if sent_cookies else 'no'}:{sent_cookies[:40]}]"
            )

        # Follow manually if needed
        if status != 200:
            raise DDLException(f"shrinkme: mrproblogger returned {status}")

        # Re-fetch with redirects for the actual page
        page = sess.get(
            mrpro_url,
            headers={"User-Agent": _UA, "Referer": "https://themezon.net/"},
            allow_redirects=True,
            timeout=30,
        )

        if page.status_code == 404:
            raise DDLException(f"shrinkme: alias '{alias}' not found")

        if "mrproblogger" not in str(page.url):
            raise DDLException(
                f"shrinkme: mrproblogger redirected to {str(page.url)[:60]}"
            )

        html = page.text
        soup = BeautifulSoup(html, "html.parser")

        # Check for Cloudflare challenge
        if "Just a moment" in html or "cf-browser-verification" in html:
            raise DDLException("shrinkme: mrproblogger blocked by Cloudflare")

        form = soup.select_one("form#go-link")
        if not form:
            # Log what the page actually contains to help debug
            title = soup.title.text.strip()[:50] if soup.title else "no title"
            raise DDLException(f"shrinkme: go-link form not found (title='{title}')")

        hidden = {
            inp.get("name"): inp.get("value", "")
            for inp in form.find_all("input")
            if inp.get("name")
        }
        action = form.get("action") or "/links/go"
        if not action.startswith("http"):
            action = f"{_MRPRO}{action}"

        # Step 3: wait for server-side timer (minimum 11s)
        counter_m = _re.search(r'counter_value["\s:=]+(\d+)', html)
        counter = int(counter_m.group(1)) if counter_m else 12
        _time.sleep(max(11, counter - 1))

        # Step 4: submit
        r2 = sess.post(
            action,
            data=hidden,
            headers={
                "User-Agent": _UA,
                "Referer": str(page.url),
                "Origin": _MRPRO,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
            timeout=30,
        )

        try:
            data = _json.loads(r2.content)
        except Exception:
            raise DDLException("shrinkme: invalid JSON response")

        dest = data.get("url")
        if not dest:
            raise DDLException(f"shrinkme: {data.get('message', 'no URL in response')}")

        return dest

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"shrinkme: {type(e).__name__} — {e}") from e


async def earnlinks(url: str) -> str:
    """
    earnlinks.in shortener bypass — pure HTTP, no browser.

    Referer: https://itiexamshala.com/ makes the server
    serve the go-link form directly, bypassing the ad/timer gate entirely.
    An 8s server-side timer is still enforced (Bad Request if submitted earlier).

    Flow:
      1. GET earnlinks.in/<code> with Referer: https://itiexamshala.com/
         → server returns go-link form directly (no redirect to ad site)
      2. Wait 8s (minimum server-side timer)
      3. POST /links/go → JSON {"status": "success", "url": "<destination>"}
    """
    _UA = (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    )
    _REFERER = "https://itiexamshala.com/"

    def _run_sync() -> str:
        import time as _time
        from curl_cffi.requests import Session as _CurlSess

        sess = _CurlSess(impersonate="chrome120")
        page = sess.get(
            url,
            headers={"User-Agent": _UA, "Referer": _REFERER},
            allow_redirects=True,
            timeout=20,
        )

        if page.status_code != 200:
            raise DDLException(f"earnlinks: unexpected response {page.status_code}")

        # If redirected away from earnlinks.in, the itiexamshala referer trick
        # didn't work for this code — it uses a partner chain we can't bypass
        if "earnlinks.in" not in str(page.url):
            raise DDLException(
                f"earnlinks: code redirects to partner site "
                f"({str(page.url).split('/')[2]}) — not bypassable via HTTP"
            )

        html = page.text
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find(id="go-link")
        if not form:
            raise DDLException("earnlinks: go-link form not found — Referer trick may have changed")

        hidden = {
            inp.get("name"): inp.get("value", "")
            for inp in form.find_all("input")
            if inp.get("name")
        }
        action = form.get("action") or "/links/go"
        if not action.startswith("http"):
            action = f"https://earnlinks.in{action}"

        # Respect server-side counter; skip wait if counter_value is 0
        counter_m = _re.search(r'counter_value["\s:=]+(\d+)', html)
        counter = int(counter_m.group(1)) if counter_m else 8
        if counter > 0:
            _time.sleep(counter + 1)

        r2 = sess.post(
            action,
            data=hidden,
            headers={
                "User-Agent": _UA,
                "Referer": str(page.url),
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, */*",
            },
            timeout=20,
        )

        try:
            data = _json.loads(r2.content)
        except Exception:
            raise DDLException("earnlinks: invalid JSON response")

        dest = data.get("url")
        if not dest:
            raise DDLException(f"earnlinks: {data.get('message', 'no URL in response')}")

        return dest

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"earnlinks: {type(e).__name__} — {e}") from e


async def itilink(url: str) -> str:
    """
    mvurl.site / liteurl.in — itiexamshala/earnlinks-backend shortener bypass.

    These domains redirect through a chain ending at
    itiexamshala.com/geio.php?grey=<code>. The grey code is the earnlinks.in
    alias, so the bypass is:

      1. Follow redirects manually until geio.php URL is seen, extract grey=
      2. GET earnlinks.in/<grey> with Referer: itiexamshala.com
         → go-link form served directly (same trick as earnlinks bypass)
      3. Wait server-side counter → POST /links/go → destination

    Redirect chain example:
      mvurl.site/<alias>
        → urls.tuktukgamer.in/<alias>
        → url.tuktukgamer.in/<alias>
        → redirect.tuktukgamer.in
        → itiexamshala.com/geio.php?grey=<code>
    """
    _UA_D = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    _UA_M = (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    )
    _REFERER = "https://itiexamshala.com/"

    def _run_sync() -> str:
        import time as _time
        from curl_cffi.requests import Session as _CurlSess

        # ── Step 1: Follow redirects to find grey code ────────────────────────
        sess = _CurlSess(impersonate="chrome136")
        grey_code = None
        current_url = url

        for _ in range(8):
            r = sess.get(
                current_url,
                headers={"User-Agent": _UA_D},
                allow_redirects=False,
                timeout=10,
            )
            loc = r.headers.get("location", "")
            if not loc:
                break

            # Check if this redirect or its target contains geio.php?grey=
            for candidate in (loc, current_url):
                m = _re.search(r'geio\.php\?grey=([^&\s#]+)', candidate)
                if m:
                    grey_code = m.group(1)
                    break

            if grey_code:
                break

            if not loc.startswith("http"):
                break
            current_url = loc

        if not grey_code:
            raise DDLException(
                f"itilink: could not extract grey code from redirect chain "
                f"(last URL: {current_url[:80]})"
            )

        # ── Step 2: Hit earnlinks.in/<grey> with itiexamshala referer ─────────
        sess2 = _CurlSess(impersonate="chrome120")
        earnlinks_url = f"https://earnlinks.in/{grey_code}"
        page = sess2.get(
            earnlinks_url,
            headers={"User-Agent": _UA_M, "Referer": _REFERER},
            allow_redirects=True,
            timeout=20,
        )

        if page.status_code != 200 or "earnlinks.in" not in str(page.url):
            raise DDLException(
                f"itilink: earnlinks returned {page.status_code} for grey={grey_code}"
            )

        html = page.text
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find(id="go-link")
        if not form:
            raise DDLException(
                f"itilink: go-link form not found for grey={grey_code}"
            )

        hidden = {
            inp.get("name"): inp.get("value", "")
            for inp in form.find_all("input")
            if inp.get("name")
        }
        action = form.get("action") or "/links/go"
        if not action.startswith("http"):
            action = f"https://earnlinks.in{action}"

        counter_m = _re.search(r'counter_value["\s:=]+(\d+)', html)
        counter = int(counter_m.group(1)) if counter_m else 8
        if counter > 0:
            _time.sleep(counter + 1)

        r2 = sess2.post(
            action,
            data=hidden,
            headers={
                "User-Agent": _UA_M,
                "Referer": str(page.url),
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, */*",
            },
            timeout=20,
        )

        try:
            data = _json.loads(r2.content)
        except Exception:
            raise DDLException("itilink: invalid JSON response from /links/go")

        dest = data.get("url")
        if not dest:
            raise DDLException(f"itilink: {data.get('message', 'no URL in response')}")

        return dest

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"itilink: {type(e).__name__} — {e}") from e


async def dotflix(url: str) -> str:
    """
    dotflix.store / dtflix.ink share-page bypass — pure HTTP, no browser.

    The page is a Next.js App Router app that embeds all file data in
    self.__next_f.push([1,"..."]) script calls in the initial HTML.
    The JSON string contains initialCloudflareData (Cloudflare R2 URL)
    and initialShareData (vikingfileLink, pixeldrainLink, filename, size).

    Flow:
      1. GET dotflix.store/share/<code>
      2. Extract all push([1,"..."]) payloads, unescape, concatenate
      3. Parse the JSON blob → extract every non-null download URL
      4. Return formatted message with file info + download links
    """
    def _run_sync() -> str:
        import httpx as _httpx

        r = _httpx.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            follow_redirects=True,
            timeout=20.0,
        )
        if r.status_code != 200:
            raise DDLException(f"dotflix: HTTP {r.status_code}")
        html = r.text

        # Collect all self.__next_f.push([1,"..."]) payloads
        rsc_payloads = _re.findall(
            r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', html, _re.S
        )
        if not rsc_payloads:
            raise DDLException("dotflix: RSC payload not found in page")

        # Unescape each payload (they are JSON string values) and join
        full_rsc = ""
        for raw in rsc_payloads:
            full_rsc += raw.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\/', '/') + "\n"

        # ── Extract initialShareData ──────────────────────────────────────────
        sd_m = _re.search(r'"initialShareData"\s*:\s*(\{[^{}]+\})', full_rsc)
        share_data: dict = {}
        if sd_m:
            try:
                share_data = _json.loads(sd_m.group(1))
            except Exception:
                pass

        # ── Extract initialCloudflareData ────────────────────────────────────
        cf_m = _re.search(r'"initialCloudflareData"\s*:\s*(\{[^{}]+\})', full_rsc)
        cf_data: dict = {}
        if cf_m:
            try:
                cf_data = _json.loads(cf_m.group(1))
            except Exception:
                pass

        if not share_data and not cf_data:
            raise DDLException("dotflix: could not parse file data from RSC payload")

        filename = share_data.get("filename") or "Unknown"
        size = share_data.get("formattedFileSize") or "Unknown"

        # ── Collect all available download links ─────────────────────────────
        links: list[tuple[str, str]] = []

        cf_url = cf_data.get("cloudflareFileUrl")
        cf_locked = cf_data.get("isCloudflareLocked", True)
        if cf_url and not cf_locked:
            links.append(("Cloudflare CDN", cf_url))

        pd_url = share_data.get("pixeldrainLink")
        if pd_url:
            links.append(("Pixeldrain", pd_url))

        vf_url = share_data.get("vikingfileLink")
        if vf_url:
            links.append(("VikingFile", vf_url))

        dp_url = share_data.get("dotplayLink")
        if dp_url:
            links.append(("DotPlay", dp_url))

        if not links:
            raise DDLException("dotflix: no download links found in share data")

        lines = [
            f"▸ <b>Title</b> (<a href=\"{url}\">{url}</a>) ➙ <code>{filename}</code>",
            "",
            f"▸ <b>Size</b> ➙ <code>{size}</code>",
            "",
            "▸ <b>Download Links</b> ➙",
            "",
        ]
        for label, link in links:
            lines.append(f"    • <a href=\"{link}\">{label}</a>")
        return "\n".join(lines)

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"dotflix: {type(e).__name__} — {e}") from e


async def srnky(url: str) -> str:
    """
    srnky.com / clksz.com / oii.la — pure-HTTP bypass (no browser required).

    Platform: shrinkearn.com / adLinkFly (cloud_theme 6.6.4).
    Requires: PEAK_API_KEY (Peak.fo, for Turnstile solving) + PROXY_URL.

    ── Confirmed flow (discovered via CDP spy on real Chrome session) ─────────

    1. GET srnky/<alias>
       → Sets refXXX session cookie; page has advertisingcamps form with
         token, c_d, c_t, alias. Turnstile sitekey: 0x4AAAAAABpMIvjgfpDTfgEj.

    2. Solve Turnstile via Peak API → cf-turnstile-response token.

    3. POST advertisingcamps.com/taboola1/landing/ with form fields + token
       → Returns JS redirect to loanbixby.com/<article>?get=<alias>&...

    4. POST loanbixby.com/<article>/ with token+c_d+c_t+alias+url
       → loanbixby's WordPress shortlink plugin registers the ad visit.

    5. POST srnky.com/<alias> with token+c_d+c_t+alias+url (no https in url)
       using Referer: loanbixby.com, Origin: loanbixby.com
       → Response is the alias page with a HIDDEN go-link form pre-populated:
             <form id="go-link" action="/links/go">
               <input name="_method" value="POST">
               <input name="ad_form_data" value="<server-signed-blob>">

    6. Wait counter_value seconds (server-side timer check).

    7. POST /links/go with _method=POST + ad_form_data
       → {"status":"success","url":"<destination>"}
    """
    import re as _re2
    import time as _time
    import requests as _requests

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    _SITEKEY_FALLBACK = "0x4AAAAAABpMIvjgfpDTfgEj"

    if not Config.PEAK_API_KEY:
        raise DDLException(
            "srnky/clksz/oii.la: PEAK_API_KEY is required (Peak.fo Turnstile solver). "
            "Set it in config.env."
        )

    def _find_input(html: str, name: str) -> str | None:
        for pat in [
            rf'name=["\x27]{_re2.escape(name)}["\x27]\s+[^>]*value=["\x27]([^"\x27]*)["\x27]',
            rf'value=["\x27]([^"\x27]*)["\x27][^>]*\s+name=["\x27]{_re2.escape(name)}["\x27]',
        ]:
            m = _re2.search(pat, html)
            if m:
                return m.group(1)
        return None

    def _run_sync() -> str:
        from urllib.parse import urlparse as _urlparse
        sess = _requests.Session()
        sess.headers.update({"User-Agent": _UA})

        # Derive host/origin from input URL (e.g. https://clksz.com or https://srnky.com)
        _parsed = _urlparse(url)
        _base_url = f"{_parsed.scheme}://{_parsed.netloc}"  # e.g. https://clksz.com
        _host = _parsed.netloc  # e.g. clksz.com

        # ── Step 1: GET alias page ────────────────────────────────────────────
        r1 = sess.get(url, timeout=20)
        html = r1.text

        alias_m = _re2.search(r'/([A-Za-z0-9]+)\s*$', url.rstrip('/'))
        alias = alias_m.group(1) if alias_m else url.split('/')[-1]

        token = _find_input(html, 'token')
        c_d   = _find_input(html, 'c_d')
        c_t   = _find_input(html, 'c_t')
        ad_type = _find_input(html, 'ad_type') or '2'
        mysite  = _find_input(html, 'mysite') or 'shrinkearn.com'

        counter_m = _re2.search(r'"counter_value"\s*:\s*(\d+)', html)
        counter = int(counter_m.group(1)) if counter_m else 15

        if not token:
            raise DDLException(f"srnky: could not extract token from {url}")

        # ── Step 2: Solve Turnstile via Peak API ──────────────────────────────
        # Extract sitekey dynamically — each domain uses a different key
        sitekey_m = _re2.search(r'(0x4[A-Za-z0-9]{20,})', html)
        sitekey = sitekey_m.group(1) if sitekey_m else _SITEKEY_FALLBACK

        proxy = Config.next_proxy()

        def _peak_solve(use_proxy: bool) -> dict:
            # Peak requires URL to end with a trailing slash
            _solve_url = url if url.endswith("/") else url + "/"
            if use_proxy:
                payload: dict = {
                    "task_type": "turnstiletask",
                    "url": _solve_url,
                    "sitekey": sitekey,
                    "proxy": proxy,
                }
            else:
                payload = {
                    "task_type": "TurnstileTaskProxyLess",
                    "url": _solve_url,
                    "sitekey": sitekey,
                }
            r = _requests.post(
                "https://api.peak.fo/solve",
                headers={"X-API-Key": Config.PEAK_API_KEY},
                json=payload,
                timeout=60,
            )
            return r.json()

        # Try proxyless first (Peak's own IPs are cleaner than shared datacenter IPs).
        # Note: proxyless tokens are accepted from any IP, so no session binding needed.
        # If that fails, retry with a Webshare proxy.
        peak_resp = _peak_solve(use_proxy=False)
        if not peak_resp.get("success"):
            _err1 = peak_resp.get("error", "")
            if proxy:
                peak_resp = _peak_solve(use_proxy=True)
                if not peak_resp.get("success"):
                    raise DDLException(
                        f"srnky: Turnstile solve failed — {peak_resp.get('error', peak_resp)} "
                        f"(proxyless error: {_err1})"
                    )
                proxy_used = proxy
            else:
                raise DDLException(
                    f"srnky: Turnstile solve failed (proxyless) — {_err1}"
                )
        else:
            proxy_used = None  # Proxyless solve; no IP binding required

        ts_token = peak_resp["data"]["token"]

        # Bind subsequent requests to the same proxy IP that was used for Turnstile
        # so the solved token is valid for the downstream requests.
        if proxy_used:
            # Convert compact host:port:user:pass or URL format to requests proxy dict
            if proxy_used.startswith("http"):
                proxy_dict = {"http": proxy_used, "https": proxy_used}
            else:
                parts = proxy_used.split(":")
                if len(parts) == 4:
                    h, p, u, pw = parts
                    proxy_url = f"http://{u}:{pw}@{h}:{p}"
                else:
                    proxy_url = f"http://{proxy_used}"
                proxy_dict = {"http": proxy_url, "https": proxy_url}
            sess.proxies.update(proxy_dict)

        # ── Step 3: POST to advertisingcamps ──────────────────────────────────
        ac_r = sess.post(
            "https://advertisingcamps.com/taboola1/landing/",
            data={
                "url": url,
                "token": token,
                "mysite": mysite,
                "c_d": c_d,
                "c_t": c_t,
                "ad_type": ad_type,
                "visit_token": "",
                "alias": alias,
                "submit": "",
                "cf-turnstile-response": ts_token,
            },
            headers={"Origin": _base_url, "Referer": url},
            timeout=20,
            allow_redirects=False,
        )
        lb_m = _re2.search(
            r'location\.href=["\x27](https://loanbixby\.com/[^""\x27]+)["\x27]',
            ac_r.text,
        )
        if not lb_m:
            raise DDLException(
                f"srnky: advertisingcamps did not return loanbixby URL "
                f"(Turnstile may have failed) — {ac_r.text[:200]}"
            )
        lb_url = lb_m.group(1)

        # Parse loanbixby URL params (get, date, time, token)
        lb_base = lb_url.split("?")[0]
        lb_qs = lb_url.split("?")[1] if "?" in lb_url else ""
        lb_params: dict[str, str] = {}
        for pair in lb_qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                from urllib.parse import unquote_plus
                lb_params[k] = unquote_plus(v)

        lb_token = lb_params.get("token", token)
        lb_date  = lb_params.get("date", c_d)
        lb_time  = lb_params.get("time", c_t)
        lb_alias = lb_params.get("get", alias)

        # ── Step 4: POST to loanbixby (register ad visit) ─────────────────────
        sess.post(
            lb_base,
            data={
                "token": lb_token,
                "c_d": lb_date,
                "c_t": lb_time,
                "alias": lb_alias,
                "next_page": lb_base,
                "url": f"{_host}/{lb_alias}",
            },
            headers={"Origin": "https://loanbixby.com", "Referer": lb_base},
            timeout=20,
            allow_redirects=False,
        )

        # ── Step 5: POST to srnky (get go-link form with ad_form_data) ────────
        srnky_cb = sess.post(
            url,
            data={
                "token": lb_token,
                "c_d": lb_date,
                "c_t": lb_time,
                "alias": lb_alias,
                "url": f"{_host}/{lb_alias}",
            },
            headers={
                "Origin": "https://loanbixby.com",
                "Referer": lb_base,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=20,
            allow_redirects=True,
        )

        afd_m = _re2.search(
            r'name=["\x27]ad_form_data["\x27]\s+value=["\x27]([^"\x27]+)["\x27]',
            srnky_cb.text,
        )
        if not afd_m:
            afd_m = _re2.search(
                r'value=["\x27]([^"\x27]+)["\x27][^>]*name=["\x27]ad_form_data["\x27]',
                srnky_cb.text,
            )
        if not afd_m:
            raise DDLException(
                "srnky: go-link form with ad_form_data not found in callback response — "
                "ad visit may not have registered correctly"
            )
        ad_form_data = afd_m.group(1)

        # ── Step 6: Wait counter ──────────────────────────────────────────────
        _time.sleep(counter + 1)

        # ── Step 7: POST /links/go ────────────────────────────────────────────
        base_url = url.split("/")[0] + "//" + url.split("/")[2]  # https://srnky.com
        go_r = sess.post(
            f"{base_url}/links/go",
            data={"_method": "POST", "ad_form_data": ad_form_data},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Origin": base_url,
                "Referer": url,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=20,
        )
        try:
            result = go_r.json()
        except Exception:
            raise DDLException(f"srnky: /links/go non-JSON response — {go_r.text[:200]}")

        if result.get("status") == "success" and result.get("url"):
            return result["url"]
        raise DDLException(
            f"srnky: /links/go failed — {result.get('message', result)}"
        )

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"srnky: {type(e).__name__} — {e}") from e


async def exeygo(url: str) -> str:
    """
    exeygo.com — CakePHP adLinkFly bypass via Turnstile + 2-step form.

    Flow:
      1. GET exeygo.com/<alias>
         → CakePHP before-captcha form with _csrfToken + f_n=sle + Turnstile
      2. Solve Turnstile via Peak API
      3. POST /alias with _csrfToken + f_n + cf-turnstile-response
         → Returns shortener page with go-link form + ad_form_data
      4. Wait counter_value seconds
      5. POST /links/go → JSON with destination URL

    Requires: PEAK_API_KEY
    """
    import re as _re2
    import time as _time
    import requests as _req

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )

    if not Config.PEAK_API_KEY:
        raise DDLException(
            "exeygo: PEAK_API_KEY is required. Set it in config.env."
        )

    def _run_sync() -> str:
        from urllib.parse import urlparse as _up

        sess = _req.Session()
        sess.headers.update({"User-Agent": _UA})

        # Step 1: GET page — get CSRF token and Turnstile sitekey
        r1 = sess.get(url, timeout=20)
        if r1.status_code != 200:
            raise DDLException(f"exeygo: HTTP {r1.status_code}")

        soup1 = BeautifulSoup(r1.text, "html.parser")
        form = soup1.find("form", {"id": "before-captcha"}) or \
               soup1.find("form")
        if not form:
            raise DDLException("exeygo: before-captcha form not found")

        inputs = {
            i.get("name"): i.get("value", "")
            for i in form.find_all("input")
            if i.get("name")
        }
        action = form.get("action", "")
        parsed = _up(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if not action.startswith("http"):
            action = f"{base}{action}"

        sitekey_m = _re2.search(r'(0x4[A-Za-z0-9]{20,})', r1.text)
        sitekey = sitekey_m.group(1) if sitekey_m else "0x4AAAAAACPCPhXQQr5wP1VW"

        # Step 2: Solve Turnstile via Peak
        proxy = Config.next_proxy()
        peak_payload = {
            "task_type": "turnstiletask",
            "url": url,
            "sitekey": sitekey,
        }
        if proxy:
            peak_payload["proxy"] = proxy

        peak_r = _req.post(
            "https://api.peak.fo/solve",
            headers={"X-API-Key": Config.PEAK_API_KEY},
            json=peak_payload,
            timeout=120,
        )
        peak_data = peak_r.json()
        if not peak_data.get("success"):
            raise DDLException(
                f"exeygo: Turnstile solve failed — {peak_data.get('error', peak_data)}"
            )
        ts_token = peak_data["data"]["token"]

        # Step 3: POST with Turnstile response → get go-link page
        inputs["cf-turnstile-response"] = ts_token
        r2 = sess.post(
            action,
            data=inputs,
            headers={"Referer": url, "Origin": base},
            timeout=30,
        )
        if r2.status_code != 200:
            raise DDLException(f"exeygo: captcha POST failed — {r2.status_code}")

        soup2 = BeautifulSoup(r2.text, "html.parser")
        golink = soup2.select_one("form#go-link")
        if not golink:
            # Check for direct gt-link anchor
            gt = soup2.find("a", id="gt-link", href=lambda h: h and h.startswith("http"))
            if gt:
                return gt["href"]
            raise DDLException("exeygo: go-link form not found after Turnstile solve")

        hidden = {
            i.get("name"): i.get("value", "")
            for i in golink.find_all("input")
            if i.get("name")
        }
        go_action = golink.get("action", "/links/go")
        if not go_action.startswith("http"):
            go_action = f"{base}{go_action}"

        # Step 4: Wait counter
        counter_m = _re2.search(r'"counter_value"\s*:\s*(\d+)', r2.text)
        counter = int(counter_m.group(1)) if counter_m else 5
        if counter > 0:
            _time.sleep(counter + 1)

        # Step 5: POST /links/go
        r3 = sess.post(
            go_action,
            data=hidden,
            headers={
                "Referer": str(r2.url),
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, */*",
            },
            timeout=20,
        )
        try:
            result = _json.loads(r3.content)
        except Exception:
            raise DDLException(f"exeygo: non-JSON response — {r3.text[:200]}")

        dest = result.get("url")
        if not dest:
            raise DDLException(f"exeygo: {result.get('message', 'no URL in response')}")
        return dest

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"exeygo: {type(e).__name__} — {e}") from e


async def shortxlinks(url: str) -> str:
    """
    shortxlinks.in / shortxlinks.com — wpSafeLink two-stage chain bypass.

    Confirmed flow (discovered via CDP spy + HTTP tracing):

    1. GET shortxlinks.in/<alias>
       → Redirects to shortxlinks.com → mtc1.thetechhint.in/?adlinkfly=...
       → Landing page: form with go=base64(shortxlinks URL + token)

    2. POST go to thetechhint.in
       → Returns newwpsafelink (base64 JSON with delay=25s and linkr URL)

    3. POST humanverification=1 + newwpsafelink to thetechhint.in
       → Returns another article page with next newwpsafelink

    4. Decode linkr, wait delay (25s), GET linkr
       → Redirects to mtc1.distancedata.in/?wpsafelink=...
       → Another landing with go=base64

    5. Repeat steps 2-4 for distancedata.in (another 25s delay)
       → linkr now points back to shortxlinks.com/<alias>?<token>

    6. GET shortxlinks.com/<alias>?<token>
       → Page has form#go-link with ad_form_data (adLinkFly platform)

    7. Wait counter_value seconds (15s)
       → POST /links/go → {"status":"success","url":"<destination>"}

    Total time: ~65s (two 25s delays + 15s counter).
    Pure HTTP, no browser, no CAPTCHA required.
    """
    import base64 as _b64
    import json as _json2
    import time as _time2
    from curl_cffi.requests import Session as _CurlSess

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )

    def _decode_nwsl(val: str) -> dict:
        try:
            return _json2.loads(_b64.b64decode(val + "==").decode("utf-8", errors="replace"))
        except Exception:
            return {}

    _MIN_DELAY = 15  # server enforces ~15s minimum per stage

    def _follow_chain(sess, r) -> tuple:
        """Follow newwpsafelink/go chain until form#go-link is found.
        Returns (final_response, go_link_form_soup_element)."""
        import time as _t
        # Known trusted intermediate domains for the wpSafeLink chain.
        # If linkr points somewhere else the chain has changed — bail out
        # with a clear error rather than silently following an unknown domain.
        _TRUSTED_DOMAINS = {
            "thetechhint.in", "mtc1.thetechhint.in",
            "distancedata.in", "mtc1.distancedata.in",
            "shortxlinks.in", "shortxlinks.com",
        }

        def _is_trusted(href: str) -> bool:
            if not href:
                return False
            from urllib.parse import urlparse as _up2
            host = (_up2(href).hostname or "").lstrip("www.")
            # Accept if the full hostname or its base domain is trusted
            return any(host == d or host.endswith("." + d) for d in _TRUSTED_DOMAINS)

        for _ in range(20):
            soup = BeautifulSoup(r.content, "lxml")

            golink = soup.select_one("form#go-link")
            if golink:
                return r, golink

            form = soup.find("form")
            if not form:
                return r, None

            action = form.get("action") or str(r.url)
            inputs = {
                i.get("name"): i.get("value", "")
                for i in form.find_all("input")
                if i.get("name")
            }

            if "newwpsafelink" in inputs:
                jd = _decode_nwsl(inputs["newwpsafelink"])
                linkr = jd.get("linkr", "")

                inputs["humanverification"] = "1"
                t_stage = _t.time()
                r2 = sess.post(
                    action, data=inputs,
                    headers={"User-Agent": _UA, "Referer": str(r.url)},
                    timeout=25,
                )
                if linkr:
                    # Validate linkr is from a known chain domain before following
                    if not _is_trusted(linkr):
                        raise DDLException(
                            f"shortxlinks: linkr points to unexpected domain "
                            f"({linkr[:60]}) — chain domain may have changed"
                        )
                    # Wait minimum time since stage start (server enforces ~15s)
                    elapsed = _t.time() - t_stage
                    remaining = max(0, _MIN_DELAY - elapsed)
                    if remaining > 0:
                        _time2.sleep(remaining)
                    r = sess.get(
                        linkr,
                        headers={"User-Agent": _UA, "Referer": str(r2.url)},
                        timeout=25, allow_redirects=True,
                    )
                else:
                    r = r2

            elif "go" in inputs:
                r = sess.post(
                    action, data=inputs,
                    headers={"User-Agent": _UA, "Referer": str(r.url)},
                    timeout=25, allow_redirects=True,
                )
            else:
                return r, None

        return r, None

    def _run_sync() -> str:
        proxy = Config.next_proxy()
        sess = _CurlSess(
            impersonate="chrome136",
            proxies={"https": proxy, "http": proxy} if proxy else None,
        )

        # Step 1: GET alias — follows shortxlinks.in → .com → thetechhint.in
        r = sess.get(
            url,
            headers={"User-Agent": _UA},
            timeout=20,
            allow_redirects=True,
        )

        # Step 2–7: Follow the full wpSafeLink chain
        r_final, golink = _follow_chain(sess, r)

        if not golink:
            raise DDLException(
                f"shortxlinks: go-link form not found after chain traversal "
                f"(final URL: {str(r_final.url)[:80]})"
            )

        # Extract hidden inputs
        hidden = {
            i.get("name"): i.get("value", "")
            for i in golink.find_all("input")
            if i.get("name")
        }

        # Read counter_value
        counter_m = _re.search(r'"counter_value"\s*:\s*(\d+)', r_final.text)
        counter = int(counter_m.group(1)) if counter_m else 15

        # Wait counter (track from when we got the go-link page)
        import time as _t2
        elapsed_since_golink = _t2.time() - _t2.time()  # already accounted above
        _time2.sleep(max(1, counter))

        # POST /links/go
        action_go = golink.get("action") or ""
        if not action_go.startswith("http"):
            base = "/".join(str(r_final.url).split("/")[:3])
            action_go = base + ("" if action_go.startswith("/") else "/") + action_go

        go_r = sess.post(
            action_go,
            data=hidden,
            headers={
                "User-Agent": _UA,
                "Referer": str(r_final.url),
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
            timeout=20,
        )

        try:
            result = go_r.json()
        except Exception:
            raise DDLException(
                f"shortxlinks: /links/go non-JSON response — {go_r.text[:200]}"
            )

        if result.get("status") == "success" and result.get("url"):
            return result["url"]
        raise DDLException(
            f"shortxlinks: /links/go failed — {result.get('message', result)}"
        )

    try:
        return await _to_thread(_run_sync)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"shortxlinks: {type(e).__name__} — {e}") from e


async def nexdrive(url: str) -> str:
    """
    nexdrive.fit — pure-HTTP bypass via fastdl.zip embed extraction.

    Flow (confirmed Oct 2026):
      1. GET nexdrive.fit/<path>/
         → Page contains a "Download" button linking to:
           https://fastdl.zip/embed?download=<ID>
      2. GET fastdl.zip/embed?download=<ID>
         → JS embeds the destination in:
           var reurl = "https://fastdl.zip/dl.php?link=<encoded-GDrive-URL>"
      3. Extract the `link=` query-param value → URL-decode → return direct URL

    The final URL is always a Google/Googleusercontent CDN link that can be
    downloaded directly (e.g. video-downloads.googleusercontent.com/…).
    """
    from urllib.parse import unquote as _unquote

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )

    try:
        # Step 1: GET nexdrive page
        r1 = await http.get(
            url,
            headers={"User-Agent": _UA},
            timeout=_SHORT_TIMEOUT,
        )
        r1.raise_for_status()

        # Find fastdl.zip embed URL
        m_embed = _re.search(
            r'https://fastdl\.zip/embed\?download=([A-Za-z0-9_-]+)',
            r1.text,
        )
        if not m_embed:
            raise DDLException("nexdrive: fastdl.zip embed link not found on page")

        embed_url = f"https://fastdl.zip/embed?download={m_embed.group(1)}"

        # Step 2: GET fastdl.zip embed page
        r2 = await http.get(
            embed_url,
            headers={"User-Agent": _UA, "Referer": url},
            timeout=_SHORT_TIMEOUT,
        )
        r2.raise_for_status()

        # Step 3: Extract var reurl
        m_reurl = _re.search(
            r"var\s+reurl\s*=\s*[\"']([^\"']+)[\"']",
            r2.text,
        )
        if not m_reurl:
            raise DDLException("nexdrive: reurl variable not found in fastdl.zip embed page")

        reurl = m_reurl.group(1)

        # reurl is "https://fastdl.zip/dl.php?link=<encoded-URL>"
        # Extract and decode the link= parameter
        m_link = _re.search(r'[?&]link=([^&\s"\'<>]+)', reurl)
        if m_link:
            return _unquote(m_link.group(1))

        # Fallback: reurl itself might be a direct URL
        if reurl.startswith("http"):
            return reurl

        raise DDLException(f"nexdrive: could not extract final URL from reurl: {reurl[:100]}")

    except DDLException:
        raise
    except NetworkError as e:
        raise DDLException(f"nexdrive: {type(e).__name__}") from e
    except Exception as e:
        raise DDLException(f"nexdrive: {type(e).__name__} — {e}") from e


async def eonmovies(url: str) -> str:
    """
    new4.eonmovies.click bypass — handles both /dl/ and /links/ pages.

    /dl/<id> endpoint flow (confirmed Oct 2026):
      • 302 → /links/<alias>       → own mirror-list page (scraped below)
      • 302 → azonahub.biz/file/…  → DDL hoster (checker recurses)
      • 302 → dtflix.ink/share/…   → dotflix-compatible (checker recurses)
      • 302 → other external URL   → checker recurses

    /links/<alias> page flow:
      • Custom mirror-list page showing multiple <a href="/dl/<id>"> buttons
      • Each button goes back through /dl/ to an external hoster
      • Scrape all /dl/ hrefs, follow each until a non-/links/ URL is found

    Both paths ultimately hand off to direct_link_checker via a returned URL.
    """
    _BASE = "https://new4.eonmovies.click"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )

    def _resolve(loc: str) -> str:
        """Make a relative Location header absolute."""
        if loc.startswith("/"):
            return f"{_BASE}{loc}"
        if not loc.startswith("http"):
            return f"{_BASE}/{loc}"
        return loc

    async def _follow_dl(dl_url: str) -> str | None:
        """
        Follow a single /dl/<id> redirect one hop.
        Returns the resolved Location URL, or None on error.
        """
        try:
            r = await http.get(
                dl_url,
                headers={"User-Agent": _UA},
                follow_redirects=False,
                timeout=_SHORT_TIMEOUT,
            )
        except NetworkError:
            return None
        if r.status_code not in (301, 302, 303, 307, 308):
            return None
        loc = r.headers.get("location", "")
        return _resolve(loc) if loc else None

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    # ── /links/<alias> page: scrape mirror buttons, try each dl ──────────────
    if "/links/" in path:
        try:
            r_page = await http.get(
                url,
                headers={"User-Agent": _UA},
                timeout=_SHORT_TIMEOUT,
            )
            r_page.raise_for_status()
        except NetworkError as e:
            raise DDLException(f"eonmovies: {type(e).__name__}") from e

        soup = BeautifulSoup(r_page.text, "html.parser")
        dl_hrefs = [
            _resolve(a["href"])
            for a in soup.find_all("a", href=_re.compile(r"^/dl/"))
            if a.get("href")
        ]
        if not dl_hrefs:
            raise DDLException("eonmovies: no /dl/ mirror links found on /links/ page")

        # Try each mirror in order; return first non-/links/ resolved URL
        errors: list[str] = []
        for dl_url in dl_hrefs:
            resolved = await _follow_dl(dl_url)
            if resolved and "/links/" not in resolved:
                return resolved
            elif resolved:
                errors.append(f"{dl_url} → loops back to /links/")
            else:
                errors.append(f"{dl_url} → no redirect")

        raise DDLException(
            f"eonmovies: all {len(dl_hrefs)} mirrors failed or looped — "
            + "; ".join(errors[:3])
        )

    # ── /dl/<id>: follow single redirect ─────────────────────────────────────
    resolved = await _follow_dl(url)
    if not resolved:
        try:
            # Re-fetch to get proper error message
            r2 = await http.get(url, headers={"User-Agent": _UA},
                                follow_redirects=False, timeout=_SHORT_TIMEOUT)
            raise DDLException(f"eonmovies: expected redirect, got {r2.status_code}")
        except NetworkError as e:
            raise DDLException(f"eonmovies: {type(e).__name__}") from e

    return resolved


async def toxcloud(url: str) -> str:
    """
    TOXcloud (cloud.azonahub.biz) — pure-HTTP scraper bypass.

    TOXcloud is the rebrand of azonahub.biz. Each file page has download
    links embedded directly in the HTML and a /mirror/<id> page with
    additional mirror links — no AJAX required.

    Flow:
      1. GET cloud.azonahub.biz/file/<id>
         → Extract filename, size, VikingFile and GCloud onclick URLs
      2. GET cloud.azonahub.biz/mirror/<id>
         → Extract all mirror links (VikingFile, Abyss, Filepress, etc.)
      3. Return formatted message with all available links
    """
    from urllib.parse import urlparse as _up2

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )

    # Normalise: accept cloud.azonahub.biz/file/<id> or short.azonahub.biz/<id>
    parsed = _up2(url)
    if "short.azonahub" in (parsed.hostname or ""):
        # short.azonahub.biz/<id> → 302 → cloud.azonahub.biz/file/<id>
        try:
            r0 = await http.get(url, headers={"User-Agent": _UA},
                                follow_redirects=False, timeout=_SHORT_TIMEOUT)
            loc = r0.headers.get("location", "")
            if loc:
                url = loc if loc.startswith("http") else f"https://cloud.azonahub.biz{loc}"
            else:
                raise DDLException("toxcloud: short redirect returned no Location")
        except NetworkError as e:
            raise DDLException(f"toxcloud: {type(e).__name__}") from e

    # Extract file ID from path: /file/<id>
    path_parts = _up2(url).path.strip("/").split("/")
    if len(path_parts) < 2 or path_parts[0] != "file":
        raise DDLException(f"toxcloud: unexpected URL format — {url}")
    file_id = path_parts[1]
    base = "https://cloud.azonahub.biz"

    _H = {"User-Agent": _UA, "Referer": url}

    try:
        import asyncio as _asyncio
        r1, r2 = await _asyncio.gather(
            http.get(url, headers=_H, timeout=_SHORT_TIMEOUT),
            http.get(f"{base}/mirror/{file_id}", headers=_H, timeout=_SHORT_TIMEOUT),
        )
    except NetworkError as e:
        raise DDLException(f"toxcloud: {type(e).__name__}") from e

    if r1.status_code == 404:
        raise DDLException("toxcloud: file not found (404)")
    if r1.status_code != 200:
        raise DDLException(f"toxcloud: HTTP {r1.status_code}")

    soup1 = BeautifulSoup(r1.text, "html.parser")
    soup2 = BeautifulSoup(r2.text, "html.parser") if r2.status_code == 200 else None

    # ── Metadata ──────────────────────────────────────────────────────────────
    title_tag = soup1.find("meta", property="og:title")
    filename = title_tag["content"].replace("Download ", "").strip() if title_tag else "Unknown"
    desc_tag = soup1.find("meta", property="og:description")
    size = "Unknown"
    if desc_tag:
        m_size = _re.search(r"File Size:\s*([^\|]+)", desc_tag.get("content", ""))
        if m_size:
            size = m_size.group(1).strip()

    # ── Collect links from main page (onclick) ────────────────────────────────
    seen: set[str] = set()
    links: list[tuple[str, str]] = []

    def _add(label: str, href: str) -> None:
        href = href.strip()
        if href and href not in seen and href.startswith("http"):
            seen.add(href)
            links.append((label, href))

    for btn in soup1.find_all("button", onclick=True):
        onclick = btn.get("onclick", "")
        m = _re.search(r"window\.open\(['\"]([^'\"]+)['\"]", onclick)
        if m:
            label = " ".join(btn.get_text().split())
            _add(label, m.group(1))

    # ── Collect links from /mirror/ page ─────────────────────────────────────
    if soup2:
        for btn in soup2.find_all("button", onclick=True):
            onclick = btn.get("onclick", "")
            m = _re.search(r"window\.open\(['\"]([^'\"]+)['\"]", onclick)
            if m:
                label = " ".join(btn.get_text().split())
                _add(label, m.group(1))
        for a in soup2.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "azonahub" not in href and "eonmovies" not in href:
                label = " ".join(a.get_text().split()) or "Mirror"
                _add(label, href)

    if not links:
        raise DDLException("toxcloud: no download links found on page")

    lines = [
        f"▸ <b>Title</b> (<a href=\"{url}\">{url}</a>) ➙ <code>{filename}</code>",
        "",
        f"▸ <b>Size</b> ➙ <code>{size}</code>",
        "",
        "▸ <b>Download Links</b> ➙",
        "",
    ]
    for label, link in links:
        lines.append(f"    • <a href=\"{link}\">{label}</a>")
    return "\n".join(lines)
