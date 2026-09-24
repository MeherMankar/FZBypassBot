"""
HTML scraper resolvers — sites that return structured page content
rather than plain redirect URLs.

HTTP architecture
-----------------
  cf   (cfscrape)  — primary client; all target sites here have Cloudflare
                     or similar bot protection.  All calls are async via the
                     cf adapter (asyncio.to_thread with semaphore).
  http (httpx)     — used for toonworld4all's known-clean intermediate hops
                     where no Cloudflare is expected.

Fixes applied vs previous version
----------------------------------
  sharespark   — returns DDLException instead of None when no links found
  toonworld4all — bounded redirect loop (MAX_REDIRECT_DEPTH=10) with
                  visited-URL set; raises DDLException on loop/depth exceeded
  All resolvers  — explicit error paths instead of silent fall-through
"""
from __future__ import annotations

import asyncio
from asyncio import gather, create_task
from re import search, match, sub
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from FZBypass.bypass.ddl import transcript
from FZBypass.core.exceptions import DDLException
from FZBypass.core.networking import cf, http
from FZBypass.core.networking.client import DEFAULT_TIMEOUT as _SHORT_TIMEOUT
from FZBypass.core.networking.exceptions import NetworkError

# Maximum hops when following redirect chains in toonworld4all
_MAX_REDIRECT_DEPTH = 10


# ═══════════════════════════════════════════════════════════════════════════════
# ShareSpark
# ═══════════════════════════════════════════════════════════════════════════════

async def sharespark(url: str) -> str:
    """
    Scrapes ShareSpark article pages for GDToT download links.
    Uses cfscrape — ShareSpark uses Cloudflare.
    Raises DDLException instead of returning None when no links are found.
    """
    try:
        res = await cf.get("?action=printpage;".join(url.split("?")))
    except NetworkError as e:
        raise DDLException(f"ShareSpark: {type(e).__name__}") from e

    soup = BeautifulSoup(res.text, "html.parser")
    gd_txt = ""

    for br in soup.findAll("br"):
        next_s = br.nextSibling
        if not (next_s and isinstance(next_s, NavigableString)):
            continue
        next2_s = next_s.nextSibling
        if not (next2_s and isinstance(next2_s, Tag) and next2_s.name == "br"):
            continue
        if not str(next_s).strip():
            continue
        if match(r"^(480p|720p|1080p)(.+)? Links:\Z", next_s):
            gd_txt += f'<b>{next_s.replace("Links:", "GDToT Links :")}</b>\n\n'
        for s in next_s.split():
            ns = sub(r"\(|\)", "", s)
            if match(r"https?://.+\.gdtot\.\S+", ns):
                try:
                    page_r = await cf.get(ns)
                    page_soup = BeautifulSoup(page_r.text, "html.parser")
                    items = page_soup.select('meta[property^="og:description"]')
                    if items:
                        parse_data = (
                            items[0]["content"]
                            .replace("Download ", "")
                            .rsplit("-", maxsplit=1)
                        )
                        gd_txt += (
                            f"┎ <b>Name :</b> {parse_data[0]}\n"
                            f"┠ <b>Size :</b> {parse_data[-1]}\n"
                            f"┃\n"
                            f"┖ <b>GDTot :</b> {ns}\n\n"
                        )
                except (NetworkError, Exception):
                    gd_txt += f"┖ <b>GDTot :</b> {ns}\n\n"
            elif match(r"https?://pastetot\.\S+", ns):
                nxt = sub(r"\(|\)|(https?://pastetot\.\S+)", "", next_s)
                gd_txt += f"\n<b>{nxt}</b>\n┖ {ns}\n"

        # Hard limit to prevent Telegram message overflow
        if len(gd_txt) > 4000:
            break

    if not gd_txt:
        raise DDLException("ShareSpark: no GDToT links found on page")
    return gd_txt


# ═══════════════════════════════════════════════════════════════════════════════
# SkyMoviesHD
# ═══════════════════════════════════════════════════════════════════════════════

async def skymovieshd(url: str) -> str:
    """Uses cfscrape — skymovieshd has Cloudflare protection."""
    try:
        r = await cf.get(url, allow_redirects=False)
    except NetworkError as e:
        raise DDLException(f"SkyMoviesHD: {type(e).__name__}") from e

    soup = BeautifulSoup(r.text, "html.parser")
    t = soup.select('div[class^="Robiul"]')
    if not t:
        raise DDLException("SkyMoviesHD: title element not found")
    gd_txt = f"<i>{t[-1].text.replace('Download ', '')}</i>"
    _cache: list[str] = []

    for link in soup.select('a[href*="howblogs.xyz"]'):
        if link["href"] in _cache:
            continue
        _cache.append(link["href"])
        gd_txt += f"\n\n<b>{link.text} :</b> \n"
        try:
            nsoup_r = await cf.get(link["href"], allow_redirects=False)
            nsoup = BeautifulSoup(nsoup_r.text, "html.parser")
            atag = nsoup.select('div[class="cotent-box"] > a[href]')
            for no, a in enumerate(atag, start=1):
                gd_txt += f"{no}. {a['href']}\n"
        except NetworkError:
            gd_txt += "<i>Error fetching links</i>\n"

    return gd_txt


# ═══════════════════════════════════════════════════════════════════════════════
# Cinevood
# ═══════════════════════════════════════════════════════════════════════════════

async def cinevood(url: str) -> str:
    """Uses cfscrape — cinevood has Cloudflare protection."""
    try:
        resp = await cf.get(url)
    except NetworkError as e:
        raise DDLException(f"Cinevood: {type(e).__name__}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    titles = soup.select("h6")
    post_title = soup.title.string.strip() if soup.title else "Unknown"

    links_by_title: dict[str, list[str]] = {}
    for title_el in titles:
        title_text = title_el.text.strip()
        _map = {
            "gdtot":    ("GDToT",    "gdtot"),
            "multiup":  ("MultiUp",  "multiup"),
            "filepress":("FilePress","filepress"),
            "gdflix":   ("GDFlix",   "gdflix"),
            "kolop":    ("Kolop",    "kolop"),
            "zipylink": ("ZipyLink", "zipylink"),
        }
        found: list[str] = []
        for key, (label, substr) in _map.items():
            a = title_el.find_next("a", href=lambda h, s=substr: h and s in h.lower())
            if a:
                found.append(
                    f'<a href="{a["href"]}" style="text-decoration:none;"><b>{label}</b></a>'
                )
        if found:
            links_by_title[title_text] = found

    prsd = f"<b>🔖 Title:</b> {post_title}\n"
    for title_text, links in links_by_title.items():
        prsd += f"\n┏<b>🏷️ Name:</b> <code>{title_text}</code>\n"
        prsd += "┗<b>🔗 Links:</b> " + " | ".join(links) + "\n"
    return prsd


# ═══════════════════════════════════════════════════════════════════════════════
# Kayoanime
# ═══════════════════════════════════════════════════════════════════════════════

async def kayoanime(url: str) -> str:
    """Uses cfscrape — kayoanime has Cloudflare protection."""
    try:
        resp = await cf.get(url)
    except NetworkError as e:
        raise DDLException(f"Kayoanime: {type(e).__name__}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    gdlinks = soup.select('a[href*="drive.google.com"], a[href*="tinyurl"]')
    prsd = f"<b>{soup.title.string if soup.title else 'Unknown'}</b>"
    gd_txt = "GDrive"

    for n, gd in enumerate(gdlinks, start=1):
        link = gd["href"]
        if "tinyurl" in link:
            try:
                r = await http.get(link, follow_redirects=True, timeout=_SHORT_TIMEOUT)
                link = r.url
                domain = urlparse(link).hostname or ""
                gd_txt = (
                    "Mega" if "mega" in domain
                    else "G Group" if "groups" in domain
                    else "Direct Link"
                )
            except NetworkError:
                pass
        prsd += f"\n\n{n}. <i><b>{gd.string}</b></i>\n┗ <b>Links :</b> <a href='{link}'><b>{gd_txt}</b></a>"

    return prsd


# ═══════════════════════════════════════════════════════════════════════════════
# Toonworld4all — bounded redirect loop (was unbounded)
# ═══════════════════════════════════════════════════════════════════════════════

async def toonworld4all(url: str) -> str:
    """
    Uses a mix of httpx (for clean hops) and cf (for CF-protected pages).

    FIXED: The previous implementation had an unbounded
    `while all(...): nsl = rget(...).headers["location"]` loop that could
    hang indefinitely.  This version enforces MAX_REDIRECT_DEPTH=10 and
    a visited-URL set to detect cycles.
    """
    if "/redirect/main.php?url=" in url:
        try:
            r = await http.get(url, follow_redirects=True, timeout=_SHORT_TIMEOUT)
            return f"┎ <b>Source Link:</b> {url}\n┃\n┖ <b>Bypass Link:</b> {r.url}"
        except NetworkError as e:
            raise DDLException(f"toonworld4all redirect: {type(e).__name__}") from e

    try:
        resp = await cf.get(url)
    except NetworkError as e:
        raise DDLException(f"toonworld4all: {type(e).__name__}") from e

    xml = resp.text
    soup = BeautifulSoup(xml, "html.parser")

    # ── Series/episode list page ──────────────────────────────────────────────
    if "/episode/" not in url:
        epl = soup.select('a[href*="/episode/"]')
        tls = soup.select('div[class*="mks_accordion_heading"]')
        m = search(r'"name":"(.+)"', xml)
        stitle = m.group(1).split('"')[0] if m else "Unknown"
        prsd = f"<b><i>{stitle}</i></b>"
        for n, (t, lnk) in enumerate(zip(tls, epl), start=1):
            prsd += f"\n\n{n}. <i><b>{t.strong.string}</b></i>\n┖ <b>Link :</b> {lnk['href']}"
        return prsd

    # ── Single episode page ───────────────────────────────────────────────────
    links = soup.select('a[href*="/redirect/main.php?url="]')
    titles_els = soup.select("h5")
    if not titles_els:
        raise DDLException("toonworld4all: no h5 title elements found")
    prsd = f"<b><i>{titles_els[0].string}</i></b>"
    titles_els.pop(0)

    if not links:
        raise DDLException("toonworld4all: no redirect links found on episode page")

    slicer, _ = divmod(len(links), max(len(titles_els), 1))
    slicer = max(slicer, 1)

    async def _resolve_link(sl_href: str) -> str:
        """Follow the redirect chain with depth + cycle protection."""
        current = sl_href
        visited: set[str] = set()
        for depth in range(_MAX_REDIRECT_DEPTH):
            if current in visited:
                raise DDLException(f"toonworld4all: redirect loop detected at {current}")
            visited.add(current)
            # Check if we've landed on a known shortener
            if "rocklinks" in current:
                return await transcript(
                    current,
                    "https://insurance.techymedies.com/",
                    "https://highkeyfinance.com/",
                    5,
                )
            if "link1s" in current:
                return await transcript(
                    current, "https://link1s.com", "https://anhdep24.com/", 9
                )
            # Follow one hop
            try:
                r = await http.get(
                    current,
                    follow_redirects=False,
                    timeout=_SHORT_TIMEOUT,
                )
            except NetworkError as e:
                raise DDLException(
                    f"toonworld4all: hop failed at depth {depth} — {type(e).__name__}"
                ) from e
            location = r.headers.get("location") or r.headers.get("Location")
            if not location:
                raise DDLException(
                    f"toonworld4all: no Location header at depth {depth} for {current}"
                )
            current = location

        raise DDLException(
            f"toonworld4all: max redirect depth ({_MAX_REDIRECT_DEPTH}) exceeded"
        )

    atasks = [create_task(_resolve_link(sl["href"])) for sl in links]
    com_tasks = await gather(*atasks, return_exceptions=True)
    lstd = [com_tasks[i: i + slicer] for i in range(0, len(com_tasks), slicer)]

    for no, tl in enumerate(titles_els):
        prsd += f"\n\n<b>{tl.string}</b>\n┃\n┖ <b>Links :</b> "
        chunk = lstd[no] if no < len(lstd) else []
        parts: list[str] = []
        for sl, resolved in zip(links, chunk):
            if isinstance(resolved, Exception):
                parts.append(str(resolved))
            else:
                parts.append(f"<a href='{resolved}'>{sl.string}</a>")
        prsd += ", ".join(parts)

    return prsd


# ═══════════════════════════════════════════════════════════════════════════════
# TamilMV
# ═══════════════════════════════════════════════════════════════════════════════

async def tamilmv(url: str) -> str:
    """Uses cfscrape — tamilmv has Cloudflare protection."""
    try:
        resp = await cf.get(url)
    except NetworkError as e:
        raise DDLException(f"TamilMV: {type(e).__name__}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    mag = soup.select('a[href^="magnet:?xt=urn:btih:"]')
    tor = soup.select('a[data-fileext="torrent"]')
    title_str = soup.title.string if soup.title else "Unknown"
    parse_data = f"<b><u>{title_str}</u></b>"

    for no, (t, m) in enumerate(zip(tor, mag), start=1):
        filename = sub(r"www\S+|\- |\.torrent", "", t.string or "")
        parse_data += (
            f"\n\n{no}. <code>{filename}</code>\n"
            f"┖ <b>Links :</b> "
            f"<a href=\"https://t.me/share/url?url={m['href'].split('&')[0]}\"><b>Magnet </b>🧲</a>"
            f"  | <a href=\"{t['href']}\"><b>Torrent 🌐</b></a>"
        )
    return parse_data


# ═══════════════════════════════════════════════════════════════════════════════
# HDHub4u
# ═══════════════════════════════════════════════════════════════════════════════

async def hdhub4u(url: str) -> str:
    """
    Scrape download links from hdhub4u.* movie pages.

    hdhub4u is a WordPress-based site.  Each movie/series post contains a
    download section with buttons linking to GDFlix, HubDrive, HubCloud,
    or direct shorteners.  The buttons are typically inside <article> or
    <div class="entry-content"> as plain <a> tags.
    """
    try:
        resp = await cf.get(url)
    except NetworkError as e:
        raise DDLException(f"HDHub4u: {type(e).__name__}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    post_title = soup.title.string.strip() if soup.title else "Unknown"

    # Known download link domains on hdhub4u posts
    _DL_DOMAINS = (
        "gdflix", "hubdrive", "hubcloud", "drivescript",
        "gdtot", "filepress", "appdrive", "katdrive",
        "drivefire", "filebee", "pressbee",
    )

    # Collect all external download links, grouped by quality label
    # hdhub4u wraps each quality block in a <h3> or <strong> heading
    # followed by <a> download buttons
    sections: dict[str, list[str]] = {}
    current_heading = "Download Links"

    content = soup.select_one("article") or soup.select_one("div.entry-content") or soup

    for el in content.find_all(["h3", "h4", "strong", "a"]):
        tag = el.name
        if tag in ("h3", "h4"):
            current_heading = el.get_text(strip=True) or current_heading
        elif tag == "strong" and el.get_text(strip=True):
            text = el.get_text(strip=True)
            # Only use as heading if it looks like a quality label
            if any(q in text.upper() for q in ("480P", "720P", "1080P", "4K", "DOWNLOAD", "QUALITY")):
                current_heading = text
        elif tag == "a":
            href = el.get("href", "")
            if not href.startswith("http"):
                continue
            # Skip internal links and ads
            if "hdhub4u" in href or "bit.ly" in href.lower():
                continue
            if any(d in href.lower() for d in _DL_DOMAINS):
                label = el.get_text(strip=True) or href.split("/")[2]
                sections.setdefault(current_heading, []).append(
                    f'<a href="{href}">{label}</a>'
                )

    if not sections:
        raise DDLException("HDHub4u: no download links found on page")

    out = f"<b>🎬 {post_title}</b>\n"
    for heading, links in sections.items():
        out += f"\n<b>{heading}</b>\n"
        out += " | ".join(links) + "\n"

    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 4KHDHub
# ═══════════════════════════════════════════════════════════════════════════════

async def fourkhdhub(url: str) -> str:
    """
    Scrape download links from 4khdhub.one movie/series pages.

    Page structure:
      div.download-groups
        section.download-group  (one per quality group, e.g. "2160p / 4K BluRay")
          div.download-group-title  → group heading
          div.download-item         (one per file variant)
            span.download-title-text  → variant title
            div.file-title            → filename
            a.btn href=greenmotors.club → HubCloud / HubDrive link

    Uses curl_cffi Chrome impersonation — 4khdhub has Cloudflare protection
    that cfscrape cannot solve.
    """
    from asyncio import to_thread as _to_thread
    from curl_cffi.requests import Session as _CS

    def _fetch():
        with _CS(impersonate="chrome120") as s:
            r = s.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
                "Accept-Language": "en-US,en;q=0.5",
            }, timeout=20)
            return r.text, r.status_code

    try:
        text, status = await _to_thread(_fetch)
    except Exception as e:
        raise DDLException(f"4KHDHub: {type(e).__name__}") from e

    if status != 200:
        raise DDLException(f"4KHDHub: HTTP {status}")

    soup = BeautifulSoup(text, "html.parser")
    post_title = soup.title.string.strip() if soup.title else "Unknown"
    post_title = post_title.replace(" - 4K-HDHub", "").replace(" - 4KHDHub", "").strip()

    out = f"<b>🎬 {post_title}</b>\n"

    def _extract_item(item) -> str | None:
        """Extract formatted text from a div.download-item."""
        # Title — try span.download-title-text first, fall back to flex-1 div text
        # The download-header div contains both the title and badge spans —
        # grab only the title span text, not the badge text
        title_el = item.select_one("span.download-title-text")
        if title_el:
            variant = title_el.get_text(strip=True)
        else:
            # Fallback: get text from flex-1 div but strip badge text
            flex_el = item.select_one("div.flex-1")
            if flex_el:
                # Remove badge spans before getting text
                for badge in flex_el.find_all("span", class_="badge"):
                    badge.decompose()
                for code in flex_el.find_all("code"):
                    code.decompose()
                variant = flex_el.get_text(strip=True)
            else:
                variant = ""

        fname_el = item.select_one("div.file-title")
        fname = fname_el.get_text(strip=True) if fname_el else ""

        size_el = item.select_one("span.badge[style*='ea580c']")
        size = size_el.get_text(strip=True) if size_el else ""

        links = []
        for a in item.select("a.btn[href], a[href*='greenmotors'], a[href*='hubcloud'], a[href*='hubdrive']"):
            href = a.get("href", "")
            if not href.startswith("http"):
                continue
            label = a.get_text(strip=True).replace("Download ", "").strip() or href.split("/")[2]
            links.append(f'<a href="{href}">{label}</a>')

        if not links:
            return None

        line = f"  ┠ <code>{variant}</code>" if variant else "  ┠"
        if size:
            line += f" <b>[{size}]</b>"
        if fname:
            line += f"\n  ┠ <i>{fname}</i>"
        line += "\n  ┗ " + " | ".join(links)
        return line

    # Structure A: section.download-group wrappers (JS-rendered)
    groups = soup.select("section.download-group")
    if groups:
        for group in groups:
            title_el = group.select_one("div.download-group-title")
            group_label = sub(r"\s*\d+\s*options?", "",
                              title_el.get_text(" ", strip=True) if title_el else "").strip()
            if group_label:
                out += f"\n<b>📦 {group_label}</b>\n"
            for item in group.select("div.download-item"):
                line = _extract_item(item)
                if line:
                    out += line + "\n"
    else:
        # Structure B: flat div.download-item list (no JS grouping)
        items = soup.select("div.download-item")
        if not items:
            raise DDLException("4KHDHub: no download items found on page")
        out += "\n<b>📦 Download Links</b>\n"
        for item in items:
            line = _extract_item(item)
            if line:
                out += line + "\n"

    if out.strip() == f"<b>🎬 {post_title}</b>":
        raise DDLException("4KHDHub: no download links found on page")

    return out
