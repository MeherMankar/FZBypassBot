"""
spy.py — Full CDP network spy for vplink.in / arolinks.com

Launches a real Chromium browser via Playwright, navigates to the target URL,
follows the full partner chain automatically (clicks nothing — just observes),
and captures every:
  - Network request (URL, method, headers, POST body)
  - Network response (URL, status, headers, Set-Cookie)
  - Console messages
  - JS redirects / navigation events
  - Cookies at end of session
  - Final page HTML

Usage:
    python spy.py <url>
    python spy.py https://vplink.in/J8pR7O1y
    python spy.py https://arolinks.com/jumx

Output: spy_log_<code>.json  (all events)
        spy_log_<code>.txt   (human-readable summary)

Requires: pip install playwright && playwright install chromium
"""
import asyncio
import json
import sys
import re
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright, Request, Response
except ImportError:
    print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
TARGET_URL = sys.argv[1] if len(sys.argv) > 1 else "https://vplink.in/J8pR7O1y"
CODE = TARGET_URL.rstrip("/").split("/")[-1]
DOMAIN = urlparse(TARGET_URL).netloc

# Hard cap — kill the browser after this many seconds regardless
HARD_TIMEOUT_S = 120

# Domains we care about most (show in summary)
KEY_DOMAINS = {
    "vplink.in", "arolinks.com", "techmint.in", "onlinewish.in",
    "entiredust.in", "darkguruji.com", "aiweave.site",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts() -> str:
    return f"{time.time():.3f}"

def _is_key(url: str) -> bool:
    h = urlparse(url).hostname or ""
    return any(k in h for k in KEY_DOMAINS)

def _short(s: str, n: int = 120) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"

# ── Main spy ──────────────────────────────────────────────────────────────────

async def spy(target_url: str):
    log: list[dict] = []
    txt_lines: list[str] = []

    def record(event: dict):
        log.append(event)

    def say(line: str):
        safe = line.encode("cp1252", errors="replace").decode("cp1252")
        print(safe)
        txt_lines.append(line)

    say(f"{'='*70}")
    say(f"SPY: {target_url}")
    say(f"{'='*70}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
            ],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
            ignore_https_errors=True,
        )

        page = await ctx.new_page()

        # ── Network request listener ──────────────────────────────────────
        async def on_request(req: Request):
            url = req.url
            method = req.method
            body = ""
            try:
                body = req.post_data or ""
            except Exception:
                pass
            hdrs = {}
            try:
                hdrs = dict(req.headers)
            except Exception:
                pass

            event = {
                "ts": _ts(), "type": "REQ", "method": method,
                "url": url, "body": body[:500], "headers": hdrs,
            }
            record(event)

            marker = "★" if _is_key(url) else "·"
            say(f"\n{marker} REQ  [{method}] {_short(url)}")
            if body:
                say(f"       BODY: {_short(body)}")
            # Highlight interesting headers
            for h in ("referer", "cookie", "x-requested-with", "content-type"):
                if h in hdrs:
                    say(f"       {h}: {_short(hdrs[h])}")

        # ── Network response listener ─────────────────────────────────────
        async def on_response(resp: Response):
            url = resp.url
            status = resp.status
            hdrs = {}
            body_text = ""
            try:
                hdrs = dict(resp.headers)
            except Exception:
                pass
            ct = hdrs.get("content-type", "")

            # Capture body for key domains or redirects
            if _is_key(url) or status in (301, 302, 303, 307, 308):
                try:
                    if "html" in ct or "json" in ct or "javascript" in ct:
                        body_text = await resp.text()
                except Exception:
                    pass

            event = {
                "ts": _ts(), "type": "RES", "status": status,
                "url": url, "headers": hdrs, "body": body_text[:2000],
            }
            record(event)

            loc = hdrs.get("location", "")
            set_cookie = hdrs.get("set-cookie", "")
            marker = "★" if _is_key(url) else "·"
            say(f"{marker} RES  [{status}] {_short(url)}")
            if loc:
                say(f"       LOCATION → {_short(loc)}")
            if set_cookie:
                say(f"       SET-COOKIE: {_short(set_cookie)}")
            if _is_key(url) and body_text:
                # Show interesting bits of body
                for pat in [
                    r'window\.location(?:\.href)?\s*=\s*["\x27](.*?)["\x27]',
                    r'document\.location(?:\.href)?\s*=\s*["\x27](.*?)["\x27]',
                    r'"url"\s*:\s*"(https?://[^"]+)"',
                    r'(?:var|let|const)\s+finalUrl\s*=\s*["\x27]([^"\']+)["\x27]',
                    r'href=["\x27](https?://t\.me/[^"\']+)["\x27]',
                    r'id=["\x27]gt-link["\x27][^>]*href=["\x27]([^"\']+)["\x27]',
                ]:
                    for m in re.finditer(pat, body_text, re.IGNORECASE):
                        say(f"       ↳ {_short(m.group(1), 150)}")

        # ── Navigation / framenavigation ──────────────────────────────────
        async def on_navigation(frame):
            url = frame.url
            record({"ts": _ts(), "type": "NAV", "url": url})
            say(f"\n→ NAV  {_short(url)}")

        # ── Console messages ──────────────────────────────────────────────
        async def on_console(msg):
            txt = msg.text
            record({"ts": _ts(), "type": "CON", "level": msg.type, "text": txt[:300]})
            if any(k in txt for k in ["COOKIE_SET", "error", "blocked", "arolinks", "vplink", "finalUrl"]):
                say(f"  CON [{msg.type}] {_short(txt)}")

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("framenavigated", on_navigation)
        page.on("console", on_console)

        # ── Navigate ──────────────────────────────────────────────────────
        say(f"\n→ Opening {target_url} ...")
        # Expose a helper to log document.cookie assignments
        await page.add_init_script("""
            const origDescriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
            Object.defineProperty(document, 'cookie', {
                get: origDescriptor.get,
                set: function(val) {
                    console.log('[COOKIE_SET] ' + val.split(';')[0]);
                    return origDescriptor.set.call(this, val);
                },
                configurable: true
            });
        """)
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            say(f"  goto error: {e}")

        # ── Wait for full chain to complete ───────────────────────────────
        # Strategy: actively follow the vplink/arolinks partner chain steps:
        # 1. Wait for vplink → techmint navigation (JS redirect fires)
        # 2. Wait for article load
        # 3. Navigate to techmint/readmore/ manually (user would do this)
        # 4. Follow readmore redirect back to start domain
        # 5. Wait for go-link form or gt-link on final page

        say(f"\n⏳ Following partner chain (up to {HARD_TIMEOUT_S}s)...")
        start = time.time()

        # Step A: Wait for vplink → techmint navigation
        try:
            await page.wait_for_url(re.compile(r"techmint\.in"), timeout=20000)
            say(f"  [+{time.time()-start:.1f}s] On techmint: {_short(page.url)}")
        except Exception:
            say(f"  [+{time.time()-start:.1f}s] Still on: {_short(page.url)}")

        # Step B: Wait for article page to fully load
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        say(f"  [+{time.time()-start:.1f}s] Article loaded: {_short(page.url)}")

        # Step C: Navigate to techmint readmore
        # The partner chain lives under a subdirectory (e.g. /studyinsurances/).
        # Derive readmore URL from the current article URL's first path segment.
        cur_url = page.url
        parsed_cur = urlparse(cur_url)
        path_parts = [p for p in parsed_cur.path.split("/") if p]
        tm_origin = f"{parsed_cur.scheme}://{parsed_cur.netloc}"
        # First path segment is the subdirectory (e.g. "studyinsurances", "studyeducations")
        # If the URL has no subdir (e.g. techmint.in/article/), subdir is empty
        subdir = path_parts[0] if len(path_parts) >= 2 else ""
        # Only use subdir if it looks like a category, not an article slug
        # Article slugs contain hyphens and are long; subdirs are short keywords
        if subdir and len(subdir) > 30:
            subdir = ""
        if subdir:
            readmore_url = f"{tm_origin}/{subdir}/readmore/"
        else:
            readmore_url = f"{tm_origin}/readmore/"
        say(f"  [+{time.time()-start:.1f}s] Navigating to readmore: {readmore_url}")
        try:
            await page.goto(readmore_url, wait_until="domcontentloaded", timeout=20000)
            say(f"  [+{time.time()-start:.1f}s] Readmore loaded: {_short(page.url)}")
        except Exception as e:
            say(f"  readmore goto error: {e}")

        # Step D: Wait for readmore to redirect (5s delay then JS fires)
        say(f"  Waiting 8s for readmore JS redirect...")
        await asyncio.sleep(8)
        say(f"  [+{time.time()-start:.1f}s] After readmore wait: {_short(page.url)}")

        # Step E: If we landed back on the start domain, wait for form
        # If we landed on arolinks (from vplink chain), navigate back to vplink
        cur = page.url
        if "arolinks.com" in cur and DOMAIN not in cur:
            say(f"  Readmore went to arolinks: {_short(cur)}")
            # This is the broken cross-chain — arolinks 404
            # Just record and continue
        elif DOMAIN in cur or "vplink.in" in cur or "arolinks.com" in cur:
            say(f"  Back on platform domain: {_short(cur)}")

        # Step F: If still on partner, navigate back to target manually
        # First: explicitly ensure all vplink cookies are set in the context
        vplink_cookies = [
            c for c in await ctx.cookies()
            if "vplink" in c.get("domain", "")
        ]
        say(f"  vplink cookies in jar before final visit: {[c['name'] for c in vplink_cookies]}")
        if vplink_cookies:
            # Re-inject to ensure they're sent
            await ctx.add_cookies(vplink_cookies)

        if DOMAIN not in (urlparse(page.url).netloc or ""):
            say(f"  Navigating back to {TARGET_URL} via JS click simulation")
            try:
                # Use JS location assign — simulates a real browser navigation
                # which correctly sends SameSite=Lax cookies
                await page.evaluate(f"window.location.href = '{TARGET_URL}'")
                await page.wait_for_url(re.compile(re.escape(DOMAIN)), timeout=20000)
                await asyncio.sleep(5)
            except Exception as e:
                say(f"  JS navigate error: {e}")
                try:
                    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(5)
                except Exception as e2:
                    say(f"  goto fallback error: {e2}")

        # Step G: Final wait
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(2)

        # ── Capture final state ───────────────────────────────────────────
        final_url = page.url
        say(f"\n{'='*70}")
        say(f"FINAL URL: {final_url}")

        # Cookies
        cookies = await ctx.cookies()
        say(f"\n{'='*70}")
        say(f"COOKIES ({len(cookies)} total):")
        for ck in cookies:
            say(f"  {ck['name']}={ck['value'][:40]}  domain={ck['domain']}")

        # Final page HTML
        try:
            html = await page.content()
        except Exception:
            html = ""

        say(f"\n{'='*70}")
        say(f"FINAL PAGE HTML (first 3000 chars):")
        say(html[:3000])

        # Key findings summary
        say(f"\n{'='*70}")
        say("KEY FINDINGS:")
        say(f"  Start URL:  {target_url}")
        say(f"  Final URL:  {final_url}")

        # Collect all navigations
        navs = [e["url"] for e in log if e["type"] == "NAV"]
        say(f"\n  Navigation chain ({len(navs)} hops):")
        for n in navs:
            say(f"    → {n}")

        # POST requests to key domains
        posts = [e for e in log if e["type"] == "REQ" and e["method"] == "POST"]
        if posts:
            say(f"\n  POST requests ({len(posts)}):")
            for p in posts:
                say(f"    POST {_short(p['url'])}")
                if p["body"]:
                    say(f"         {_short(p['body'])}")

        # XHR/fetch JSON responses
        json_ress = [
            e for e in log
            if e["type"] == "RES"
            and "json" in e.get("headers", {}).get("content-type", "")
            and e.get("body")
        ]
        if json_ress:
            say(f"\n  JSON responses ({len(json_ress)}):")
            for r in json_ress:
                say(f"    [{r['status']}] {_short(r['url'])}")
                say(f"         {_short(r['body'])}")

        # All Set-Cookie headers
        set_cookies = [
            (e["url"], e["headers"].get("set-cookie", ""))
            for e in log
            if e["type"] == "RES" and e["headers"].get("set-cookie")
        ]
        if set_cookies:
            say(f"\n  Set-Cookie headers ({len(set_cookies)}):")
            for url, ck in set_cookies:
                say(f"    {_short(url, 60)}: {_short(ck, 80)}")

        record({
            "ts": _ts(), "type": "FINAL",
            "url": final_url, "cookies": cookies, "html": html[:5000],
        })

        await browser.close()

    # ── Write output files ────────────────────────────────────────────────
    out_json = Path(f"spy_log_{CODE}.json")
    out_txt  = Path(f"spy_log_{CODE}.txt")
    out_json.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    out_txt.write_text("\n".join(txt_lines), encoding="utf-8", errors="replace")
    say(f"\n[OK] Log written: {out_json}  ({len(log)} events)")
    say(f"[OK] Summary:     {out_txt}")
    return log


if __name__ == "__main__":
    asyncio.run(spy(TARGET_URL))
