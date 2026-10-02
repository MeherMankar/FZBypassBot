<div align="center">
    <a href="https://github.com/MeherMankar">
        <kbd>
            <img width="250" src="https://graph.org/file/80f677693ae80cbd8707e.jpg" alt="FZ Bypass Logo">
        </kbd>
    </a>

## ***FZBypassBot***

<i>A **Fast, Async, Multi-Threaded Bypass Telegram Bot** for mass-bypassing shorteners and extracting direct download links.</i>

[**Demo Bot**](https://t.me/teradownr0bot) | [**Supported Sites**](#supported-sites) | [**Support**](https://t.me/meherpatil)

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
- **PEAK_API_KEY** — pure-HTTP Turnstile solving via Peak.fo for srnky.com / clksz.com / oii.la (proxy optional)
- Keep-alive ping every 10 min (prevents Render free tier sleep)
- Corrupt session auto-cleanup on startup

---

## ***Supported Sites***

> Last Updated: **02-10-2026**

<details>
<summary><b>Shortener Sites</b> — click to expand</summary>

> All shorteners below use dedicated bypass functions. The old generic `transcript()` method (POST /links/go) is broken across the board as of 2026 due to CSRF/Cloudflare protection being added to all sites.

| Shortener | Status | Last Tested |
|:----------|:------:|:------------|
| `aylink.co` · `ay.live` | ✅ | 30-09-2026 |
| `appurl.io` | ✅ | Untested |
| `bit.ly` · `tinyurl.com` · `shorturl.at` · `t.ly` | ✅ | 30-09-2026 |
| `boost.ink` · `mboost.me` · `bst.gg` | ✅ | 30-09-2026 |
| `cpmlink.co` · `cpmlink.pro` · `cpm.link` | ✅ | 30-09-2026 |
| `direct-link.net` · `linkvertise.com` · `lootlinks.co` · `lootlabs.io` · `lv-linkvertise.com` | ✅ | 26-09-2026 |
| `disk.yandex.ru` · `yandex.com` | ✅ | Untested |
| `dropbox.com` | ✅ | Untested |
| `earnlinks.in` | ✅ | 30-09-2026 |
| `greenmotors.club` | ✅ | 26-09-2026 |
| `gyanilinks.com` · `gtlinks.me` | ✅ | Untested |
| `justpaste.it` | ✅ | Untested |
| `linksxyz.in` | ✅ | Untested |
| `liteurl.in` · `mvurl.site` | ✅ | 30-09-2026 |
| `mediafire.com` | ✅ | Untested |
| `ouo.io` · `ouo.press` | ✅ | Untested |
| `rslinks.net` | ✅ | Untested |
| `shareus.io` · `shrs.link` | ✅ | Untested |
| `shrdsk.me` | ✅ | Untested |
| `shortxlinks.in` · `shortxlinks.com` | ✅ | 01-10-2026 |
| `shrinkme.click` · `shrinkme.io` | ✅ | 30-09-2026 |
| `srnky.com` · `clksz.com` · `oii.la` | ✅ | 01-10-2026 |
| `surl.li` | ✅ | Untested |
| `thinfi.com` | ✅ | Untested |
| `try2link.com` | ✅ | Untested |
| `vplink.in` · `vplinks.in` | ✅ | 02-10-2026 |

</details>

<details>
<summary><b>File Hosters</b> — click to expand</summary>

| Hoster | Status | Last Tested |
|:-------|:------:|:------------|
| `1fichier.com` | ✅ | Untested |
| `drive.google.com` | ✅ | Untested |
| `filecrypt.co` | ✅ | Untested |
| `gofile.io` | ✅ | Untested |
| `krakenfiles.com` | ✅ | Untested |
| `mediafire.com` | ✅ | Untested |
| `nexdrive.fit` | ✅ | 02-10-2026 |
| `onedrive.live.com` · `1drv.ms` · `sharepoint.com` | ✅ | Untested |
| `pixeldrain.com` | ✅ | Untested |
| `pornhub.com` | ✅ | 27-09-2026 |
| `streamtape.com` | ✅ | Untested |
| `terabox.*` (many domains) | ✅ | 27-09-2026 |
| `we.tl` · `wetransfer.com` | ✅ | Untested |
| `disk.yandex.ru` | ✅ | Untested |

</details>

<details>
<summary><b>DL Index / Scraper Sites</b> — click to expand</summary>

| Site | Status | Last Tested |
|:-----|:------:|:------------|
| `4khdhub.one` | ✅ | 27-09-2026 |
| `cinevood.*` | ✅ | Untested |
| `archive.toonworld4all.me` | ✅ | 30-09-2026 |
| `dotflix.store` · `dtflix.ink` | ✅ | 02-10-2026 |
| `eonmovies.click` (`/dl/` · `/links/`) | ✅ | 02-10-2026 |
| `hblinks.lol` | ✅ | 27-09-2026 |
| `hdhub4u.*` | ✅ | 27-09-2026 |
| `kayoanime.com` | ✅ | Untested |
| `skymovieshd.*` | ✅ | Untested |
| `toonworld4all.*` | ✅ | Untested |
| `sharespark.cfd` | ✅ | Untested |
| `1tamilmv.*` | ✅ | Untested |

</details>


<details>
<summary><b>GDrive / DDL Index Sites</b> — click to expand</summary>

| Site | Status | Last Tested |
|:-----|:------:|:------------|
| `appdrive.*` · `filebee.*` | ✅ | 27-09-2026 |
| `drivefire.co` | ✅ | 27-09-2026 |
| `gdflix.*` | ✅ | 27-09-2026 |
| `gdtot.cfd` | ✅ | Untested |
| `filepress.store` · `pressbee.xyz` | ✅ | Untested |
| `hubcloud.*` | ✅ | 30-09-2026 |
| `hubdrive.*` | ✅ | 27-09-2026 |
| `katdrive.org` | ✅ | Untested |
| `sharer.pw` | ✅ | Untested |

</details>

---

## ***How It Works***

Most shorteners gate the destination URL behind one of a few patterns. Each has a dedicated bypass:

**Referer trick** — `earnlinks.in`, `shrinkme.click` and similar sites only serve the download form to visitors arriving from a specific referrer domain. Sending the correct `Referer` header bypasses the ad redirect entirely and loads the form directly.

**learn_more.php chain** (`vplink.in`) — vplink routes visitors through a multi-hop chain across partner ad sites (`techmint.in` → `onlinewish.in`) via successive `learn_more.php` calls. The bot follows each hop in sequence, collecting session cookies along the way, until the final vplink page with the `go-link` form appears.

**wpSafeLink chain** (`shortxlinks.in`) — A two-stage WordPress plugin chain through `thetechhint.in` and `distancedata.in`. Each stage POSTs a signed `newwpsafelink` token, waits the server-enforced minimum timer (~15s), then follows a `linkr` redirect to the next stage. Each redirect domain is validated against a known trusted-domain list to catch chain changes early.

**adLinkFly + Turnstile** (`srnky.com`, `clksz.com`, `oii.la`) — Cloudflare Turnstile gates the ad form. The bot solves it via [Peak.fo](https://peak.fo), posts to `advertisingcamps.com`, registers the ad visit on `loanbixby.com`, then posts back to the shortener to receive the signed `ad_form_data` blob for the final `/links/go` call. The same proxy is bound to both the Turnstile solve and all downstream requests to avoid token–IP mismatch.

**Token flow** (`aylink.co`, `cpmlink.pro`) — These expose a `/get/tk` endpoint that issues a session key from three time-based tokens in the landing page. The bot fetches the session key then posts a fake browser interaction signal to `/links/go2` to receive the destination URL.

**fastdl.zip embed** (`nexdrive.fit`) — The page links to a `fastdl.zip/embed?download=<id>` page which contains a `var reurl` JavaScript variable holding the final Google CDN URL. Extracted with regex, no JS execution needed.

**Redirect follower** (`eonmovies.click/dl/`) — A simple 302 that the bot follows one hop, resolves relative paths to the full domain, and returns the result to the checker for recursion into the appropriate bypass.

---

## ***Proxy Setup***

Some sites (e.g. `shrinkme.click`) block datacenter IPs via Cloudflare. Set `PROXY_URL` on Render to use residential proxies:

```
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
