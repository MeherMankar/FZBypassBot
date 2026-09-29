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

| Shortener | Status | Notes |
|:----------|:------:|:------|
| `adrinolinks.com` | ✅ | transcript |
| `adsfly.in` | ✅ | transcript |
| `anlinks.in` | ✅ | transcript |
| `appurl.io` | ✅ | cfscrape redirect |
| `bindaaslinks.com` | ✅ | transcript |
| `bit.ly` · `tinyurl.com` · `shorturl.at` · `t.ly` | ✅ | redirect follow |
| `bringlifes.com` | ✅ | transcript |
| `dalink.in` | ✅ | transcript |
| `direct-link.net` | ✅ | linkvertise GraphQL |
| `disk.yandex.ru` · `yandex.com` | ✅ | Yandex Cloud API |
| `download.mdiskshortner.link` | ✅ | transcript |
| `dropbox.com` | ✅ | URL transform |
| `droplink.co` | ✅ | transcript |
| `dtglinks.in` | ✅ | transcript |
| `du-link.in` · `dulink.in` | ✅ | transcript |
| `earn.moneykamalo.com` | ✅ | transcript |
| `earn2me.com` | ✅ | transcript |
| `earn2short.in` | ✅ | transcript |
| `earn4link.in` | ✅ | transcript |
| `evolinks.in` | ✅ | transcript |
| `ez4short.com` | ✅ | transcript |
| `go.lolshort.tech` | ✅ | transcript |
| `greenmotors.club` | ✅ | pure HTTP token decode |
| `gtlinks.me` · `gyanilinks.com` | ✅ | bloggingaro backend |
| `indianshortner.in` | ✅ | transcript |
| `indyshare.net` | ✅ | transcript |
| `instantearn.in` | ✅ | transcript |
| `justpaste.it` | ✅ | cfscrape content extract |
| `kpslink.in` · `v2.kpslink.in` | ✅ | transcript |
| `krownlinks.me` | ✅ | transcript |
| `link.shorito.com` | ✅ | transcript |
| `link.tnlink.in` | ✅ | transcript |
| `link.tnshort.net` | ✅ | transcript |
| `link.vipurl.in` · `vipurl.in` | ✅ | transcript |
| `link1s.com` | ✅ | transcript |
| `link4earn.com` | ✅ | transcript |
| `linkfly.me` | ✅ | transcript |
| `linkjust.com` | ✅ | transcript |
| `linkpays.in` | ✅ | transcript |
| `linkshortx.in` | ✅ | transcript |
| `linksly.co` | ✅ | transcript |
| `linkvertise.com` · `lootlinks.co` · `lootlabs.io` · `lv-linkvertise.com` | ✅ | pure HTTP GraphQL |
| `linksxyz.in` | ✅ | redirect extract |
| `linkyearn.com` | ✅ | transcript |
| `m.easysky.in` | ✅ | transcript |
| `m.narzolinks.click` | ✅ | transcript |
| `mdisk.pro` | ✅ | transcript |
| `mdiskshortner.link` | ✅ | transcript |
| `mediafire.com` | ✅ | cfscrape + regex |
| `modijiurl.com` | ✅ | transcript |
| `moneycase.link` | ✅ | transcript |
| `mplaylink.com` | ✅ | transcript |
| `omnifly.in.net` | ✅ | transcript |
| `onepagelink.in` | ✅ | transcript |
| `ouo.io` · `ouo.press` | ✅ | curl_cffi Chrome TLS |
| `pandaznetwork.com` | ✅ | transcript |
| `pdisk.site` | ✅ | transcript |
| `pdiskshortener.com` | ✅ | transcript |
| `pkin.me` · `go.paisakamalo.in` | ✅ | transcript |
| `publicearn.com` | ✅ | transcript |
| `rocklinks.net` | ✅ | transcript |
| `ronylink.com` | ✅ | transcript |
| `rslinks.net` | ✅ | redirect + redirect |
| `shareus.io` · `shrs.link` | ✅ | JSON API |
| `sheralinks.com` | ✅ | transcript |
| `short.tnvalue.in` | ✅ | transcript |
| `short2url.in` | ✅ | transcript |
| `shortingly.com` | ✅ | transcript |
| `shrdsk.me` | ✅ | CF API |
| `shrinke.me` | ✅ | transcript |
| `shrinkforearn.xyz` | ✅ | transcript |
| `sklinks.in` | ✅ | transcript |
| `surl.li` | ✅ | cfscrape |
| `sxslink.com` | ✅ | transcript |
| `tamizhmasters.com` | ✅ | transcript |
| `terabox.*` · `1024tera.*` · `nephobox.*` · `4funbox.*` · `mirrobox.*` · `momerybox.*` · `freeterabox.*` | ✅ | grabx-api / cookie — [Setup ↗](#terabox-setup) |
| `tglink.in` | ✅ | transcript |
| `thinfi.com` | ✅ | httpx HTML extract |
| `tinyfy.in` | ✅ | transcript |
| `try2link.com` | ✅ | countdown form |
| `tulinks.one` · `go.tulinks.online` | ✅ | transcript |
| `url4earn.in` | ✅ | transcript |
| `urllinkshort.in` | ✅ | transcript |
| `urlsopen.com` | ✅ | transcript |
| `urlspay.in` | ✅ | transcript |
| `v2links.com` | ✅ | transcript |
| `viplinks.io` | ✅ | transcript |
| `vplink.in` · `vplinks.in` | ✅ | [link-bypass-api](#vplink-setup) |
| `xpshort.com` · `push.bdnewsx.com` · `techymozo.com` | ✅ | transcript |
| `ziplinker.net` | ✅ | transcript |

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
