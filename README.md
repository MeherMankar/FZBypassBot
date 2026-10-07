<div align="center">
    <a href="https://github.com/MeherMankar">
        <kbd>
            <img width="250" src="https://graph.org/file/80f677693ae80cbd8707e.jpg" alt="FZ Bypass Logo">
        </kbd>
    </a>

## ***FZBypassBot***

<i>A **Fast, Async, Multi-Threaded Bypass Telegram Bot** for mass-bypassing shorteners and extracting direct download links.</i>

[**Demo Bot**](https://t.me/teradownr0bot) | [**Supported Sites**](#supported-sites) | [**Support**](https://t.me/meherpatil)

[**Contributor guide**](CONTRIBUTING.md) | [**Resolver flows**](RESOLVERS.md)

</div>

---

## ***Features***
- Fully async — built with `httpx`, `curl_cffi`, and `cfscrape` (no aiohttp)
- LoopBypass — auto-resolves nested shortener chains (e.g. shrinkme → gdflix → direct links)
- Simultaneous multi-link bypass
- Authorized Chats & Topics support
- Inline Bypass (use anywhere — enable via BotFather → Inline Mode)
- **Channel Auto-Bypass** — bot edits channel posts in-place, replacing links silently
- **PROXY_URL** — residential proxy rotation for sites that block datacenter IPs
- HubCloud aliases are detected automatically from the exact `hubcloud` hostname label and routed through the canonical endpoint when needed
- **PEAK_API_KEY** — pure-HTTP Turnstile solving via Peak.fo for srnky.com / clksz.com / oii.la (proxy optional)
- Keep-alive ping every 10 min (prevents Render free tier sleep)
- SQLite session files are left intact for SQLite's own WAL recovery

---

## ***Supported Sites***

> Status snapshot updated: **07-10-2026**. Dates below reflect the repository's existing reports; they are not a guarantee of current live availability.

> **Working** means a live check was reported successful on the date shown. **Broken** means a reproducible live failure is known. **Untested** means no recent live check is recorded. Offline fixture tests do not update live status.

Provider matching is suffix-agnostic for supported branded hostnames: changing a provider's TLD (including multi-label suffixes) does not require a new route, and resolvers use the input hostname when the provider flow supports it. Integrations with canonical API or alias hosts continue to use those provider-specific endpoints; recognizing a hostname variant does not guarantee that the remote service has deployed that variant.

<details>
<summary><b>Shortener Sites</b> — click to expand</summary>

> All shorteners below use dedicated bypass functions. The old generic `transcript()` method (POST /links/go) is broken across the board as of 2026 due to CSRF/Cloudflare protection being added to all sites.

| Shortener | Status | Last Verified |
|:----------|:------:|:-------------:|
| `aylink.co` · `ay.live` | Working | 30-09-2026 |
| `appurl.io` | Untested | — |
| `bit.ly` · `tinyurl.com` · `shorturl.at` · `t.ly` | Working | 30-09-2026 |
| `boost.ink` · `mboost.me` · `bst.gg` | Working | 30-09-2026 |
| `cpmlink.co` · `cpmlink.pro` · `cpm.link` | Working | 30-09-2026 |
| `direct-link.net` · `linkvertise.com` · `lootlinks.co` · `lootlabs.io` · `lv-linkvertise.com` | Working | 26-09-2026 |
| `disk.yandex.ru` · `yandex.com` | Untested | — |
| `dropbox.com` | Untested | — |
| `earnlinks.in` | Working | 30-09-2026 |
| `greenmotors.club` | Working | 26-09-2026 |
| `gplinks.co` · `gplinks.in` | Working | 02-10-2026 |
| `gyanilinks.com` · `gtlinks.me` | Untested | — |
| `justpaste.it` | Untested | — |
| `just2earn.com` | Resolver added; live request blocked by Cloudflare, flow unverified | 07-10-2026 |
| `linksxyz.in` | Untested | — |
| `liteurl.in` · `mvurl.site` | Working | 30-09-2026 |
| `mediafire.com` | Untested | — |
| `ouo.io` · `ouo.press` | Working (resolves supplied OuO URL to Get-To) | 07-10-2026 |
| `rslinks.net` | Untested | — |
| `shareus.io` · `shrs.link` | Untested | — |
| `shrdsk.me` | Untested | — |
| `shortxlinks.in` · `shortxlinks.com` | Working | 01-10-2026 |
| `shrinkme.click` · `shrinkme.io` | Working | 30-09-2026 |
| `srnky.com` · `clksz.com` · `oii.la` | Working | 01-10-2026 |
| `surl.li` | Untested | — |
| `thinfi.com` | Untested | — |
| `try2link.com` | Untested | — |
| `vplink.in` · `vplinks.in` | Working | 02-10-2026 |
| `arolinks.com` | Working (partner-chain resolver; Telegram deep links) | 07-10-2026 |
| `antibypass.koyeb.app` | Working (JS `finalUrl` extraction via vplink.in referer) | 07-10-2026 |
| `exeygo.com` | Partial (CakePHP adLinkFly; Turnstile POST returns 500 — not fully bypassable) | 07-10-2026 |
| `get-to.link` | Working (Peak-backed Cloudflare continuation + download mirrors) | 07-10-2026 |

</details>

<details>
<summary><b>File Hosters</b> — click to expand</summary>

| Hoster | Status | Last Verified |
|:-------|:------:|:-------------:|
| `1fichier.com` | Untested | — |
| `drive.google.com` | Untested | — |
| `filecrypt.co` | Untested | — |
| `gofile.io` | Untested | — |
| `krakenfiles.com` | Untested | — |
| `mediafire.com` | Untested | — |
| `nexdrive.fit` | Working | 02-10-2026 |
| `onedrive.live.com` · `1drv.ms` · `sharepoint.com` | Untested | — |
| `pixeldrain.*` (any valid DNS suffix) | Working (API metadata validation + direct download URL) | 07-10-2026 |
| `pornhub.com` | Working | 27-09-2026 |
| `streamtape.com` | Untested | — |
| `terabox.*` (many domains) | Working | 27-09-2026 |
| `we.tl` · `wetransfer.com` | Untested | — |
| `disk.yandex.ru` | Untested | — |

</details>

<details>
<summary><b>DL Index / Scraper Sites</b> — click to expand</summary>

| Site | Status | Last Verified |
|:-----|:------:|:-------------:|
| `4khdhub.one` | Working | 27-09-2026 |
| `cinevood.*` | Untested | — |
| `archive.toonworld4all.me` | Working | 30-09-2026 |
| `dotflix.store` · `dtflix.ink` | Working | 02-10-2026 |
| `eonmovies.click` (`/dl/` · `/links/`) | Working | 02-10-2026 |
| `extraflix.mobi` | Working (Linkshub/DriveHub mirrors) | 07-10-2026 |
| `bollyflix.gd` · `bollyflix.in` · `bollyflix.com` | In progress (DDL mirror scraper; unverified) | 07-10-2026 |
| `hdwebmovies.live` | Working (TMBCloud quality/episode scraper) | 07-10-2026 |
| `filmyfly.army` · `filmyfly.io` · `filmyfly.in` · `filmyfly.com` | Working (Linkmake/filesdl scraper) | 07-10-2026 |
| `filmyfiy.mov` | In progress (FilmyFly-compatible Linkmake/filesdl scraper; live host reset) | 07-10-2026 |
| `filmycab.fyi` | In progress (FilmyFly-compatible Linkmake/filesdl scraper; live host reset) | 07-10-2026 |
| `*.drivehub.dad` | Peak Turnstile secure-mirror resolver (live flow unverified) | 07-10-2026 |
| `*.vifix.site/file/...` | Working (delegates to matching `new4.gdflix.io` file) | 07-10-2026 |
| `cyberloom.best/l/...` | Working (redirect chain + signed CDN link) | 07-10-2026 |
| `link.xdmovies.wtf` | Peak Turnstile attempted; downstream still Cloudflare-protected | 07-10-2026 |
| `buzzheavier.com` | Working (`/download` + `Hx-Redirect`) | 07-10-2026 |
| `vikingfile.com` | Peak Turnstile resolver | 07-10-2026 |
| `extralink.cc` | Working (`/download` session + `/wk` redirect) | 07-10-2026 |
| `links.linkshub.fun` | Working (DriveHub/HubDrive mirror scraper) | 07-10-2026 |
| `katlinks.in` | Working (WordPress mirror scraper) | 07-10-2026 |
| `hubcdn.club` · `hubcdn.wiki` | Working (encoded R2 redirect) | 07-10-2026 |
| `vcloud.fit` · `vcloud.beer` | Working (double-encoded token/R2 mirror) | 07-10-2026 |
| `azonahub.biz` (TOXcloud — `cloud.azonahub.biz` · `short.azonahub.biz`) | Working | 02-10-2026 |
| `hblinks.lol` | Working | 27-09-2026 |
| `hdhub4u.*` | Working (new1 timeout fallback to new2) | 07-10-2026 |
| `hindianimeszone.com` (`/download1.php`) | Working (Peak Turnstile verification + mirror extraction) | 07-10-2026 |
| `kayoanime.com` | Untested | — |
| `skymovieshd.*` | Untested | — |
| `toonworld4all.*` | Untested | — |
| `sharespark.cfd` | Untested | — |
| `1tamilmv.*` | Untested | — |

</details>


<details>
<summary><b>GDrive / DDL Index Sites</b> — click to expand</summary>

| Site | Status | Last Verified |
|:-----|:------:|:-------------:|
| `appdrive.*` · `filebee.*` | Working | 27-09-2026 |
| `filebee.*` · `drivecloud.*` (`/file/...`) | Pass-through (returns the supplied URL unchanged) | 07-10-2026 |
| `drivefire.co` | Working | 27-09-2026 |
| `gdflix.*` | Working | 27-09-2026 |
| `gdtot.cfd` | Untested | — |
| `gdshare.top/download/...` · `gcloud.cyou/download/...` | Working (instant AJAX → Google CDN direct URL; FilePress fallback) | 07-10-2026 |
| `filepress.store` · `pressbee.xyz` | Untested | — |
| `hubcloud.*` | Working | 30-09-2026 |
| `hubdrive.*` | Working | 27-09-2026 |
| `katdrive.org` | Untested | — |
| `sharer.pw` | Untested | — |

</details>

---

## ***Resolver Testing***

Offline resolver regressions use recorded/sanitized HTTP fixtures and are safe
for CI; they do not contact shortener sites. Run the unittest suite with:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

To check a resolver against a live link, run its separate manual smoke check.
For example, see [the MediaFire live check](tests/live_mediafire.py). Live
checks are intentionally excluded from CI because site behavior, rate limits,
and network access change independently of the code. Fixture replay and the
live status table answer different questions: passing replay means the code
still handles the recorded flow, not that the live site still matches it.
Contributor instructions for adding fixtures and running manual checks are in
[CONTRIBUTING.md](CONTRIBUTING.md).

### Session database recovery

If startup reports `sqlite3.OperationalError: no such table: version`, stop the
bot and preserve the existing session files by renaming `FZ.session`,
`FZ.session-shm`, and `FZ.session-wal` together (only files that exist). Start
the bot again to create a fresh bot session. Do not remove WAL/SHM files while
the bot is running; SQLite uses them to recover pending database changes.

---

## ***How It Works***

For a detailed breakdown of each resolver's HTTP flow, see [**RESOLVERS.md**](RESOLVERS.md).

---

## ***Proxy Setup***

Some sites (e.g. `shrinkme.click`, `ouo.press`) block datacenter IPs via Cloudflare. You can configure proxies either directly via **Webshare Proxy API** (recommended) or via a manual **`PROXY_URL`** list.

### 1. Webshare Proxy API (Auto-fetch & Multi-API Rotation)
Supports one or multiple Webshare API tokens (`api1, api2, api3, ...`).
The bot automatically and randomly chooses an API key, fetches its proxies, and randomly selects a proxy from that API's pool. Proxies are cached in memory and refreshed automatically in the background.

```env
# Comma-separated list of Webshare API keys:
WEBSHARE_API_KEY=key1,key2,key3,key4
# OR
WEBSHARE_API_KEYS=key1,key2,key3,key4

# Or individual numbered variables:
WEBSHARE_API_KEY_1=key1
WEBSHARE_API_KEY_2=key2
WEBSHARE_API_KEY_3=key3

# Optional: mode ("direct" [default] or "backbone")
WEBSHARE_MODE=direct

# Optional: cache refresh interval in seconds (default: 1800, i.e. 30 minutes)
WEBSHARE_REFRESH_INTERVAL=1800
```

### 2. Manual Proxy List (`PROXY_URL`)
If not using Webshare, or as a fallback:

```env
PROXY_URL=host:port:user:pass,host:port:user:pass,...
```

Both formats are supported:
- `host:port:user:pass` — compact (from proxy providers)
- `http://user:pass@host:port` — standard URL format

Proxies are rotated randomly per request.

---

## ***Peak Setup (Turnstile Shorteners)***

`srnky.com`, `clksz.com`, and `oii.la` (shrinkearn.com / adLinkFly platform) gate every link behind a Cloudflare Turnstile widget. Bypassing is done entirely via pure HTTP — no browser required. You need:

1. A **Peak.fo API key** — set `PEAK_API_KEY`. Get one free (1,000 solves) at [peak.fo](https://peak.fo).
2. (Optional) A **residential proxy** — set `PROXY_URL`. Helps if your server IP is flagged by Turnstile or advertisingcamps.com. The proxy is passed to Peak so the solved token is tied to the same IP as subsequent requests.

```
PEAK_API_KEY=pk_your_key_here
PROXY_URL=host:port:user:pass   # optional but recommended on shared hosting
```

Without `PEAK_API_KEY` set, the bot raises a clear error rather than silently failing.

---

## ***Terabox Setup***

Terabox links are resolved in order: **grabx-api → terabox-downloader-api → TERA_COOKIE**

### 1. Via grabx-api *(Recommended)*

Deploy [grabx-api](https://github.com/MeherMankar/grabx-api) and set `GRABX_API_URL`. Also handles PornHub.

### 2. Via terabox-downloader-api *(Fallback)*

Deploy [terabox-downloader-api](https://github.com/MeherMankar/terabox-downloader-api) and set `TERABOX_API_URL`.

### 3. Direct cookie bypass *(Last resort)*

Set `TERA_COOKIE` to your Terabox `ndus` cookie value.

**Getting your `ndus` cookie:** Log in to terabox.com → DevTools → Application → Cookies → copy `ndus`.

---

## ***Deploy***

### Render / Koyeb / Heroku
Use [pyTele-Loader](https://github.com/SilentDemonSD/pyTele-Loader):
- `REPO_URL`: `https://github.com/MeherMankar/FZBypassBot`
- `REPO_BRANCH`: `main`
- `START_CMD`: `bash start.sh`

On Render/Koyeb deploy as a **Web Service** — the bot serves a health page on `$PORT`.

### VPS / Docker
```bash
git clone https://github.com/MeherMankar/FZBypassBot && cd FZBypassBot
docker build . -t fzbypass
docker run fzbypass
```

---

## ***Config***

Copy `sample_config.env` → `config.env` and fill in:

| Variable | Required | Description |
|:---------|:--------:|:------------|
| `BOT_TOKEN` | ✅ | Telegram bot token from BotFather |
| `API_ID` | ✅ | From https://my.telegram.org |
| `API_HASH` | ✅ | From https://my.telegram.org |
| `OWNER_ID` | ✅ | Your Telegram user ID |
| `AUTH_CHATS` | ➖ | `chat_id:topic_id` pairs, space-separated |
| `AUTH_CHANNELS` | ➖ | Channel IDs for auto-bypass, space-separated |
| `AUTO_BYPASS` | ➖ | `True` for auto-bypass mode, default `False` |
| `CMD_SUFFIX` | ➖ | Suffix for commands (e.g. `1` → `/bypass1`) |
| `GRABX_API_URL` | ➖ | grabx-api URL for Terabox + PornHub |
| `GRABX_API_KEY` | ➖ | grabx-api key |
| `TERABOX_API_URL` | ➖ | terabox-downloader-api URL (fallback) |
| `TERA_COOKIE` | ➖ | Terabox `ndus` cookie (last resort) |
| `PEAK_API_KEY` | ➖ | Peak.fo key for Turnstile shorteners — [Setup ↗](#peak-setup-turnstile-shorteners) |
| `WEBSHARE_API_KEY` / `WEBSHARE_API_KEYS` | ➖ | Webshare proxy API token(s) (supports multiple APIs) — [Setup ↗](#1-webshare-proxy-api-auto-fetch--multi-api-rotation) |
| `PROXY_URL` | ➖ | Comma-separated residential proxies — [Setup ↗](#proxy-setup) |
| `GDTOT_CRYPT` | ➖ | GdToT cookie |
| `KATDRIVE_CRYPT` | ➖ | KatDrive cookie |
| `DRIVEFIRE_CRYPT` | ➖ | DriveFire cookie |
| `LARAVEL_SESSION` | ➖ | sharer.pw cookie |
| `XSRF_TOKEN` | ➖ | sharer.pw cookie |
| `DIRECT_INDEX` | ➖ | GDrive fast index URL |
| `PORT` | ➖ | Health server port, default `8080` |
| `UPSTREAM_REPO` | ➖ | Fork URL for auto-update |
| `UPSTREAM_BRANCH` | ➖ | Branch for auto-update, default `main` |
| `GOFILE_WT_SALT` | ➖ | Override gofile.io websiteToken salt if rotated |

---

## ***Credits***
- `MeherMankar` — maintainer & contributor
- `SilentDemonSD` — original developer (Base repo)
- `bipinkrish/Link-Bypasser-Bot` — many scripts adapted and modified
- `IndraYuda13/shortlink-bypass-bot` — shrinkme MrProBlogger chain discovery + lnbz.la article-chain flow reference (loanbixby callback mechanism)
- `KaramelliS/shortlink-bypass` — aylink/cpmlink token flow reference
