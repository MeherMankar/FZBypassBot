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
    httpx nor cfscrape replicates it.  Kept as-is on purpose.
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
    res = client.get(tempurl, impersonate="chrome110", timeout=30)
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
            impersonate="chrome110",
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
