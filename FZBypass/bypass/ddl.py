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
from asyncio import sleep as asleep, to_thread as _to_thread
from urllib.parse import quote, urlparse

import httpx
from bs4 import BeautifulSoup
from curl_cffi.requests import Session as cSession
from requests import Session  # synchronous — only used inside terabox WAP path

from FZBypass import Config
from FZBypass.core.exceptions import DDLException
from FZBypass.core.networking import cf, http
from FZBypass.core.networking.client import DEFAULT_TIMEOUT
from FZBypass.core.networking.exceptions import NetworkError
from FZBypass.bypass.recaptcha import recaptchaV3

# ── Shared httpx timeout override for short-lived shortener pages ─────────────
_SHORT_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=15.0, pool=10.0)

# ── Mobile User-Agent used by most shortener bypass attempts ─────────────────
_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)


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
        url = r1.url
        r2 = await cf.get(url)
        page = r2.text
    except NetworkError as e:
        raise DDLException(f"Mediafire: {type(e).__name__}") from e

    if m := _re.findall(r"'(https?://download\d+\.mediafire\.com/\S+/\S+/\S+)'", page):
        return m[0]
    if m := _re.findall(r"//(www\.mediafire\.com/file/\S+/\S+/file\?\S+)", page):
        return await mediafire("https://" + m[0].strip('"'))
    raise DDLException("Mediafire: no download links found in page")


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
    """Uses httpx — normal HTTP shortener with countdown form."""
    DOMAIN = "https://try2link.com"
    code = url.split("/")[-1]
    referers = [
        "https://hightrip.net/",
        "https://to-travel.net",
        "https://world2our.com/",
    ]
    html: str | None = None
    for referer in referers:
        try:
            resp = await http.get(
                f"{DOMAIN}/{code}",
                headers={"Referer": referer, "User-Agent": _MOBILE_UA},
                timeout=_SHORT_TIMEOUT,
            )
            if resp.status_code == 200:
                html = resp.text
                break
        except NetworkError:
            continue

    if html is None:
        raise DDLException("try2link: could not load page (all referers failed)")

    soup = BeautifulSoup(html, "html.parser")
    go_link = soup.find(id="go-link")
    if not go_link:
        raise DDLException("try2link: go-link form not found")
    inputs = go_link.find_all(name="input")
    data = {inp.get("name"): inp.get("value") for inp in inputs}
    await asleep(6)
    try:
        resp2 = await http.post(
            f"{DOMAIN}/links/go",
            data=data,
            headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": _MOBILE_UA},
            timeout=_SHORT_TIMEOUT,
        )
    except NetworkError as e:
        raise DDLException(f"try2link: POST failed — {e}") from e

    ct = resp2.headers.get("content-type", "")
    if "application/json" in ct:
        result = _json.loads(resp2.content)
        if "url" in result:
            return result["url"]
    raise DDLException("try2link: no URL in response")


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
    httpx nor cfscrape replicates it.  Uses chrome136 impersonation.
    """
    from re import compile as _compile
    tempurl = url.replace("ouo.io", "ouo.press")
    p = urlparse(tempurl)
    oid = tempurl.split("/")[-1]
    client = cSession(
        headers={
            "authority": "ouo.press",
            "accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "cache-control": "max-age=0",
            "referer": "http://www.google.com/ig/adde?moduleurl=",
            "upgrade-insecure-requests": "1",
        }
    )
    res = client.get(tempurl, impersonate="chrome136", timeout=30)
    next_url = f"{p.scheme}://{p.hostname}/go/{oid}"

    for _ in range(2):
        if res.headers.get("Location"):
            break
        bs4 = BeautifulSoup(res.content, "lxml")
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


# ═══════════════════════════════════════════════════════════════════════════════
# REMAINING RESOLVERS (cfscrape or requests — documented reasons)
# ═══════════════════════════════════════════════════════════════════════════════

async def justpaste(url: str) -> str:
    """Uses cfscrape — justpaste.it actively blocks curl/httpx user-agents."""
    try:
        resp = await cf.get(url)
    except NetworkError as e:
        raise DDLException(f"justpaste: {type(e).__name__}") from e
    soup = BeautifulSoup(resp.text, "html.parser")
    inps = soup.select('div[id="articleContent"] > p')
    parts = [p.get_text() for p in inps if p.get_text()]
    if not parts:
        raise DDLException("justpaste: no content paragraphs found")
    return ", ".join(parts)


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




async def vplink(url: str) -> str:
    """
    vplink.in bypass via link-bypass-api (Puppeteer/Chromium microservice).

    Requires BYPASS_API_URL to be configured.
    Deploy your own instance: https://github.com/MeherMankar/link-bypass-api

    POST {BYPASS_API_URL}/bypass  {"url": "<vplink_url>"}
    → {"status": "ok", "result": "<destination_url>"}
    """
    api_base = Config.BYPASS_API_URL
    if not api_base:
        raise DDLException(
            "vplink: BYPASS_API_URL not configured — "
            "deploy link-bypass-api and set the URL in config."
        )
    try:
        resp = await http.post(
            f"{api_base}/bypass",
            json={"url": url},
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0),
        )
    except NetworkError as e:
        raise DDLException(f"vplink: API unreachable — {type(e).__name__}") from e

    if resp.status_code != 200:
        raise DDLException(f"vplink: API returned {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:
        raise DDLException("vplink: API returned invalid JSON") from e

    if data.get("status") != "ok":
        msg = data.get("message") or data.get("error") or "unknown error"
        raise DDLException(f"vplink: {msg}")

    result = data.get("result") or data.get("url") or data.get("data")
    if not result:
        raise DDLException("vplink: API response missing destination URL")

    return result


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
    Single file  → https://pixeldrain.com/api/file/<id>?download
    List         → https://pixeldrain.com/api/list/<id>/zip?download
    Verifies the file exists via the info endpoint before returning.
    """
    url = url.strip("/ ")
    parts = url.rstrip("/").split("/")
    file_id = parts[-1]

    if len(parts) >= 2 and parts[-2] == "l":
        info_link = f"https://pixeldrain.com/api/list/{file_id}"
        dl_link = f"https://pixeldrain.com/api/list/{file_id}/zip?download"
    else:
        info_link = f"https://pixeldrain.com/api/file/{file_id}/info"
        dl_link = f"https://pixeldrain.com/api/file/{file_id}?download"

    try:
        resp = await http.get(info_link, timeout=_SHORT_TIMEOUT)
        resp.raise_for_status()
        data = _json.loads(resp.content)
    except NetworkError as e:
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

        if page.status_code != 200 or "earnlinks.in" not in str(page.url):
            raise DDLException(f"earnlinks: unexpected response {page.status_code}")

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


async def dotflix(url: str) -> str:
    """
    dotflix.store share-page bypass — pure HTTP, no browser.

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
    _SITEKEY = "0x4AAAAAABpMIvjgfpDTfgEj"

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
        sess = _requests.Session()
        sess.headers.update({"User-Agent": _UA})

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
        proxy = Config.next_proxy()
        peak_payload: dict = {
            "task_type": "turnstiletask",
            "url": url,
            "sitekey": _SITEKEY,
        }
        if proxy:
            peak_payload["proxy"] = proxy

        peak_r = _requests.post(
            "https://api.peak.fo/solve",
            headers={"X-API-Key": Config.PEAK_API_KEY},
            json=peak_payload,
            timeout=60,
        )
        peak_resp = peak_r.json()
        if not peak_resp.get("success"):
            raise DDLException(
                f"srnky: Turnstile solve failed — {peak_resp.get('error', peak_resp)}"
            )
        ts_token = peak_resp["data"]["token"]

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
            headers={"Origin": "https://srnky.com", "Referer": url},
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
                "url": f"srnky.com/{lb_alias}",
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
                "url": f"srnky.com/{lb_alias}",
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
