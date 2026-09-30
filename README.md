<div align="center">
    <a href="https://github.com/MeherMankar">
        <kbd>
            <img width="250" src="https://graph.org/file/80f677693ae80cbd8707e.jpg" alt="FZ Bypass Logo">
        </kbd>
    </a>

## ***FZBypassBot***

<i>A **Fast, Async, Multi-Threaded Bypass Telegram Bot** for mass-bypassing shorteners and extracting direct download links.</i>

[**Demo Bot**](https://t.me/FZBypassBot) | [**Supported Sites**](#supported-sites) | [**Support Group**](https://t.me/FXTorrentz)

</div>

---

## ***Features***
- Fully async — built with `httpx`, `curl_cffi`, and `cfscrape` (no aiohttp)
- LoopBypass — auto-resolves nested shortener chains (e.g. shrinkme → gdflix → direct links)
- Simultaneous multi-link bypass
- Authorized Chats & Topics support
- Inline Bypass (use anywhere — enable via BotFather → Inline Mode)
- **Channel Auto-Bypass** — bot edits channel posts in-place, replacing links silently
- **greenmotors.club** — pure HTTP token decode bypass (no browser)
- **linkvertise / direct-link.net** — pure HTTP GraphQL bypass
- **vplink.in** — pure HTTP Chrome TLS fingerprint + `darkguruji.com` Referer shortcut
- **shrinkme.click / shrinkme.io** — pure HTTP MrProBlogger cookie seeding trick (11s timer)
- **Terabox** — via grabx-api (primary) or cookie fallback
- **4khdhub.one / hdhub4u** — full page scraper with greenmotors resolution
- **hblinks.lol** — article scraper (HUBLinks DDL index)
- **hubcloud** — full download button extraction (FSL, 10Gbps, Pixeldrain, Buzz)
- **PornHub** — via grabx-api
- **PROXY_URL** — residential proxy rotation for sites that block datacenter IPs
- Keep-alive ping every 10 min (prevents Render free tier sleep)
- Corrupt session auto-cleanup on startup

---

## ***Supported Sites***

> Last Updated: **30-09-2026**

<details>
<summary><b>Shortener Sites</b> — click to expand</summary>

> All shorteners below use dedicated bypass functions. The old generic `transcript()` method (POST /links/go) is broken across the board as of 2026 due to CSRF/Cloudflare protection being added to all sites.

| Shortener | Status | Method |
|:----------|:------:|:-------|
| `aylink.co` · `ay.live` | ✅ | `/get/tk` token flow + `/links/go2` |
| `bit.ly` · `tinyurl.com` · `shorturl.at` · `t.ly` | ✅ | redirect follow |
| `boost.ink` · `mboost.me` · `bst.gg` | ✅ | base64 `kekw` attribute decode |
| `cpmlink.co` · `cpmlink.pro` · `cpm.link` | ✅ | `/get/tk` token flow + `/links/go2` |
| `direct-link.net` · `linkvertise.com` · `lootlinks.co` · `lootlabs.io` · `lv-linkvertise.com` | ✅ | pure HTTP GraphQL |
| `disk.yandex.ru` · `yandex.com` | ✅ | Yandex Cloud API |
| `dropbox.com` | ✅ | URL transform |
| `greenmotors.club` | ✅ | pure HTTP token decode chain |
| `gyanilinks.com` · `gtlinks.me` | ✅ | bloggingaro backend |
| `justpaste.it` | ✅ | cfscrape content extract |
| `linksxyz.in` | ✅ | redirect extract |
| `mediafire.com` | ✅ | cfscrape + regex |
| `ouo.io` · `ouo.press` | ✅ | curl_cffi Chrome TLS + reCAPTCHA |
| `rslinks.net` | ✅ | redirect chain |
| `shareus.io` · `shrs.link` | ✅ | JSON API |
| `shrdsk.me` | ✅ | CF API |
| `shrinkme.click` · `shrinkme.io` | ✅ | MrProBlogger cookie seeding — [Setup ↗](#proxy-setup) |
| `surl.li` | ✅ | cfscrape |
| `thinfi.com` | ✅ | httpx HTML extract |
| `try2link.com` | ✅ | countdown form |
| `vplink.in` · `vplinks.in` | ✅ | pure HTTP — Chrome TLS + `darkguruji.com` Referer |
| `appurl.io` | ✅ | cfscrape redirect |

</details>

<details>
<summary><b>File Hosters</b> — click to expand</summary>

| Hoster | Status | Notes |
|:-------|:------:|:------|
| `1fichier.com` | ✅ | POST + page scrape; supports `::password` |
| `drive.google.com` | ✅ | direct index |
| `filecrypt.co` | ✅ | DLC → dcrypt.it |
| `gofile.io` | ✅ | API — SHA-256 websiteToken (salt `12af056dacea0b`) |
| `krakenfiles.com` | ✅ | form scrape + token POST |
| `mediafire.com` | ✅ | cfscrape |
| `onedrive.live.com` · `1drv.ms` · `sharepoint.com` | ✅ | OneDrive API |
| `pixeldrain.com` | ✅ | API info check + direct URL |
| `pornhub.com` | ✅ | grabx-api |
| `streamtape.com` | ✅ | JS robotlink extraction |
| `terabox.*` (many domains) | ✅ | grabx-api / TERA_COOKIE — [Setup ↗](#terabox-setup) |
| `we.tl` · `wetransfer.com` | ✅ | redirect → API v4 |
| `disk.yandex.ru` | ✅ | Yandex Cloud API |

</details>

<details>
<summary><b>DL Index / Scraper Sites</b> — click to expand</summary>

| Site | Status | Notes |
|:-----|:------:|:------|
| `4khdhub.one` | ✅ | full page scraper + greenmotors resolution |
| `cinevood.*` | ✅ | page scraper |
| `hblinks.lol` | ✅ | HUBLinks article scraper |
| `hdhub4u.*` | ✅ | page scraper |
| `kayoanime.com` | ✅ | page scraper |
| `skymovieshd.*` | ✅ | page scraper |
| `toonworld4all.*` | ✅ | page + episode scraper |
| `sharespark.cfd` | ✅ | printpage scraper |
| `1tamilmv.*` | ✅ | page scraper |

</details>

<details>
<summary><b>GDrive / DDL Index Sites</b> — click to expand</summary>

| Site | Status | Notes |
|:-----|:------:|:------|
| `appdrive.*` · `filebee.*` | ✅ | AppFlix API |
| `drivefire.co` | ✅ | DriveFire crypt |
| `gdflix.*` | ✅ | pack + single file, all servers |
| `gdtot.cfd` | ✅ | API |
| `filepress.store` · `pressbee.xyz` | ✅ | API |
| `hubcloud.*` | ✅ | FSL / 10Gbps / Pixeldrain / Buzz servers |
| `hubdrive.*` | ✅ | via HubCloud |
| `katdrive.org` | ✅ | KatDrive crypt |
| `sharer.pw` | ✅ | requires `LARAVEL_SESSION` + `XSRF_TOKEN` |

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
- `SilentDemonSD` — original developer
- `MeherMankar` — maintainer & contributor
- `bipinkrish/Link-Bypasser-Bot` — many scripts adapted and modified
- `IndraYuda13/shortlink-bypass-bot` — shrinkme MrProBlogger chain discovery
- `KaramelliS/shortlink-bypass` — aylink/cpmlink token flow reference

---

## ***Features***
- Fully async — built with `httpx`, `curl_cffi`, and `cfscrape` (no aiohttp)
- LoopBypass — auto-resolves nested shortener chains
- Simultaneous multi-link bypass
- Authorized Chats & Topics support
- Inline Bypass (use anywhere — enable via BotFather → Inline Mode)
- **Channel Auto-Bypass** — bot edits channel posts in-place, replacing links silently
- **greenmotors.club** — pure HTTP token decode bypass (no browser)
- **linkvertise / direct-link.net** — pure HTTP GraphQL bypass
- **vplink.in** — via configurable [link-bypass-api](#vplink-setup) microservice
- **Terabox** — via grabx-api (primary) or cookie fallback
- **4khdhub.one / hdhub4u** — full page scraper with greenmotors resolution
- **hblinks.lol** — article scraper (HUBLinks DDL index)
- **PornHub** — via grabx-api
- Keep-alive ping every 10 min (prevents Render free tier sleep)
- Corrupt session auto-cleanup on startup

---

## ***Supported Sites***

> Last Updated: **29-09-2026**

<details>
<summary><b>Shortener Sites</b> — click to expand</summary>

> Note: All shorteners below use their own dedicated bypass functions (not the generic `transcript()` method which is broken across the board as of late 2026 due to `/links/go` endpoint changes).

| Shortener | Status | Method |
|:----------|:------:|:-------|
| `bit.ly` · `tinyurl.com` · `shorturl.at` · `t.ly` | ✅ | redirect follow |
| `direct-link.net` · `linkvertise.com` · `lootlinks.co` · `lootlabs.io` · `lv-linkvertise.com` | ✅ | pure HTTP GraphQL |
| `disk.yandex.ru` · `yandex.com` | ✅ | Yandex Cloud API |
| `dropbox.com` | ✅ | URL transform |
| `greenmotors.club` | ✅ | pure HTTP token decode chain |
| `gyanilinks.com` · `gtlinks.me` | ✅ | bloggingaro backend |
| `justpaste.it` | ✅ | cfscrape content extract |
| `linksxyz.in` | ✅ | redirect extract |
| `mediafire.com` | ✅ | cfscrape + regex |
| `ouo.io` · `ouo.press` | ✅ | curl_cffi Chrome TLS + reCAPTCHA |
| `rslinks.net` | ✅ | redirect chain |
| `shareus.io` · `shrs.link` | ✅ | JSON API |
| `shrdsk.me` | ✅ | CF API |
| `surl.li` | ✅ | cfscrape |
| `thinfi.com` | ✅ | httpx HTML extract |
| `try2link.com` | ✅ | countdown form |
| `vplink.in` · `vplinks.in` | ✅ | [link-bypass-api](#vplink-setup) |
| `appurl.io` | ✅ | cfscrape redirect |

</details>

<details>
<summary><b>File Hosters</b> — click to expand</summary>

| Hoster | Status | Notes |
|:-------|:------:|:------|
| `1fichier.com` | ✅ | POST + page scrape; supports `::password` |
| `drive.google.com` | ✅ | direct index |
| `filecrypt.co` | ✅ | DLC → dcrypt.it |
| `gofile.io` | ✅ | API — SHA-256 websiteToken |
| `gofile.io` (password) | ✅ | SHA-256 hashed password |
| `krakenfiles.com` | ✅ | form scrape + token POST |
| `mediafire.com` | ✅ | cfscrape |
| `onedrive.live.com` · `1drv.ms` · `sharepoint.com` | ✅ | OneDrive API |
| `pixeldrain.com` | ✅ | API info check + direct URL |
| `pornhub.com` | ✅ | grabx-api |
| `streamtape.com` | ✅ | JS robotlink extraction |
| `terabox.*` (many domains) | ✅ | grabx-api / TERA_COOKIE — [Setup ↗](#terabox-setup) |
| `we.tl` · `wetransfer.com` | ✅ | redirect → API v4 |
| `disk.yandex.ru` | ✅ | Yandex Cloud API |

</details>

<details>
<summary><b>DL Index / Scraper Sites</b> — click to expand</summary>

| Site | Status | Notes |
|:-----|:------:|:------|
| `4khdhub.one` | ✅ | full page scraper + greenmotors resolution |
| `cinevood.*` | ✅ | page scraper |
| `hblinks.lol` | ✅ | HUBLinks article scraper |
| `hdhub4u.*` | ✅ | page scraper |
| `kayoanime.com` | ✅ | page scraper |
| `skymovieshd.*` | ✅ | page scraper |
| `toonworld4all.*` | ✅ | page + episode scraper |
| `sharespark.cfd` | ✅ | printpage scraper |
| `1tamilmv.*` | ✅ | page scraper |

</details>

<details>
<summary><b>GDrive / DDL Index Sites</b> — click to expand</summary>

| Site | Status | Notes |
|:-----|:------:|:------|
| `appdrive.*` · `filebee.*` | ✅ | AppFlix API |
| `drivefire.co` | ✅ | DriveFire crypt |
| `gdflix.*` | ✅ | pack + single file, all servers |
| `gdtot.cfd` | ✅ | API |
| `filepress.store` · `pressbee.xyz` | ✅ | API |
| `hubcloud.*` | ✅ | all download servers |
| `hubdrive.*` | ✅ | via HubCloud |
| `katdrive.org` | ✅ | KatDrive crypt |
| `sharer.pw` | ✅ | requires `LARAVEL_SESSION` + `XSRF_TOKEN` |

</details>

---

## ***Terabox Setup***

Terabox links are resolved in order: **grabx-api → terabox-downloader-api → TERA_COOKIE**

### 1. Via grabx-api *(Recommended)*

Deploy [grabx-api](https://github.com/MeherMankar/grabx-api) and set `GRABX_API_URL`. This also handles PornHub.

### 2. Via terabox-downloader-api *(Fallback)*

Deploy [terabox-downloader-api](https://github.com/MeherMankar/terabox-downloader-api) and set `TERABOX_API_URL`.

### 3. Direct cookie bypass *(Last resort)*

Set `TERA_COOKIE` to your Terabox `ndus` cookie value.

**Getting your `ndus` cookie:** Log in to terabox.com → DevTools → Application → Cookies → copy `ndus`.

---

## ***vplink Setup***

vplink.in links require a running instance of [link-bypass-api](https://github.com/MeherMankar/link-bypass-api) — a Puppeteer/Chromium microservice.

1. Fork [link-bypass-api](https://github.com/MeherMankar/link-bypass-api)
2. Deploy as a Web Service on [Render](https://render.com)
3. Set `BYPASS_API_URL` in this bot's config to the deployed URL

API: `POST /bypass` with `{"url": "https://vplink.in/CODE"}` → `{"status": "ok", "result": "<destination>"}`

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
| `BYPASS_API_URL` | ➖ | link-bypass-api URL for vplink.in |
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
- `SilentDemonSD` — original developer
- `MeherMankar` — maintainer & contributor
- `bipinkrish/Link-Bypasser-Bot` — many scripts adapted and modified
- all contributors who helped internally
