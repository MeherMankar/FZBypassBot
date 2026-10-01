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
- Keep-alive ping every 10 min (prevents Render free tier sleep)
- Corrupt session auto-cleanup on startup

---

## ***Supported Sites***

> Last Updated: **30-09-2026**

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
| `mediafire.com` | ✅ | Untested |
| `ouo.io` · `ouo.press` | ✅ | Untested |
| `rslinks.net` | ✅ | Untested |
| `shareus.io` · `shrs.link` | ✅ | Untested |
| `shrdsk.me` | ✅ | Untested |
| `shrinkme.click` · `shrinkme.io` | ✅ | 30-09-2026 |
| `surl.li` | ✅ | Untested |
| `thinfi.com` | ✅ | Untested |
| `try2link.com` | ✅ | Untested |
| `vplink.in` · `vplinks.in` | ✅ | 30-09-2026 |

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
| `onedrive.live.com` · `1drv.ms` · `sharepoint.com` | ✅ | Untested |
| `pixeldrain.com` | ✅ | Untested |
| `pornhub.com` | ✅ | Untested |
| `streamtape.com` | ✅ | Untested |
| `terabox.*` (many domains) | ✅ | Untested |
| `we.tl` · `wetransfer.com` | ✅ | Untested |
| `disk.yandex.ru` | ✅ | Untested |

</details>

<details>
<summary><b>DL Index / Scraper Sites</b> — click to expand</summary>

| Site | Status | Last Tested |
|:-----|:------:|:------------|
| `4khdhub.one` | ✅ | Untested |
| `cinevood.*` | ✅ | Untested |
| `archive.toonworld4all.me` | ✅ | 30-09-2026 |
| `dotflix.store` | ✅ | 30-09-2026 |
| `hblinks.lol` | ✅ | Untested |
| `hdhub4u.*` | ✅ | Untested |
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
| `appdrive.*` · `filebee.*` | ✅ | Untested |
| `drivefire.co` | ✅ | Untested |
| `gdflix.*` | ✅ | Untested |
| `gdtot.cfd` | ✅ | Untested |
| `filepress.store` · `pressbee.xyz` | ✅ | Untested |
| `hubcloud.*` | ✅ | 30-09-2026 |
| `hubdrive.*` | ✅ | Untested |
| `katdrive.org` | ✅ | Untested |
| `sharer.pw` | ✅ | Untested |

</details>

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

## ***vplink Setup***

vplink.in now bypasses using pure HTTP — no external API needed. The `gt_uc_` cookie + `darkguruji.com` Referer trick makes the server serve the unlock form directly.

The old `BYPASS_API_URL` (link-bypass-api) still works as a fallback if the pure-HTTP method fails.

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
| `BYPASS_API_URL` | ➖ | link-bypass-api URL (vplink fallback) |
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
- `IndraYuda13/shortlink-bypass-bot` — shrinkme MrProBlogger chain discovery
- `KaramelliS/shortlink-bypass` — aylink/cpmlink token flow reference
