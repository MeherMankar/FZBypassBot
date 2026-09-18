from base64 import b64decode
from asyncio import create_task, gather
from re import findall, DOTALL
from urllib.parse import urlparse
from uuid import uuid4

from bs4 import BeautifulSoup
from cloudscraper import create_scraper
from curl_cffi.requests import Session as cSession
from lxml import etree
from requests import Session
from aiohttp import ClientSession

from FZBypass import LOGGER, Config
from FZBypass.core.bot_utils import get_dl
from FZBypass.core.exceptions import DDLException


async def gdflix(url: str) -> str:
    """
    GDFlix bypass — uses curl_cffi Chrome impersonation to bypass Cloudflare.
    Extracts all download buttons directly from the /file/ page.
    Labels are derived from button text.
    """
    from urllib.parse import urlparse as _up

    EXCLUDED_HOSTS = {
        "new4.gdflix.io", "gdflix.dev", "gdflix.sbs", "goflix.sbs",
        "t.me", "telegram.me", "telegram.dog",
        "cdn2.iconfinder.com", "challenges.cloudflare.com",
    }

    c = cSession()
    r = c.get(url, impersonate="chrome110", timeout=30)
    if r.status_code != 200:
        raise DDLException(f"GDFlix: HTTP {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")

    # Token expired / Cloudflare block check
    if "Just a moment" in r.text:
        raise DDLException("GDFlix: Cloudflare challenge not bypassed")

    title_tag = soup.find("title")
    filename = title_tag.text.replace("GDFlix | ", "").strip() if title_tag else "Unknown"

    # Extract size from og:description  e.g. "Download filename - 1.78GB"
    desc = soup.find("meta", property="og:description")
    size = "Unknown"
    if desc and " - " in (desc.get("content") or ""):
        size = desc["content"].rsplit(" - ", 1)[-1]

    seen, links = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        host = _up(href).hostname or ""
        if not host or host in EXCLUDED_HOSTS:
            continue
        cls = " ".join(a.get("class", []))
        if "btn" not in cls:
            continue
        if href in seen:
            continue
        seen.add(href)
        label = a.text.strip()
        # Clean up label
        label = " ".join(label.split())
        if not label:
            label = host.split(".")[0].capitalize() + " Server"
        links.append((label, href))

    if not links:
        raise DDLException("GDFlix: no download links found")

    lines = [
        f"┏<b>Name:</b> <code>{filename}</code>",
        f"┠<b>Size:</b> <code>{size}</code>",
        f"┠<b>GDFlix:</b> <a href=\"{url}\">Source</a>",
    ]
    for i, (label, link) in enumerate(links):
        prefix = "┗" if i == len(links) - 1 else "┠"
        lines.append(f"{prefix}<b>{label}:</b> <a href=\"{link}\">Click Here</a>")

    return "\n".join(lines)


async def filepress(url: str):
    cget = create_scraper().request
    try:
        url = cget("GET", url).url
        raw = urlparse(url)
        file_id = raw.path.split("/")[-1]
        base = f"{raw.scheme}://{raw.hostname}"
        async with ClientSession() as sess:
            async with sess.post(
                f"{base}/api/file/telegram/downlaod/",
                headers={"Referer": base},
                json={"id": file_id},
            ) as resp:
                tg_id = await resp.json(content_type=None)
    except Exception as e:
        raise DDLException(f"{e.__class__.__name__}")

    tg_url = tg_id.get("data", "") if tg_id.get("data") else ""
    if not tg_url:
        raise DDLException(
            tg_id.get("statusText", "FilePress: no download link returned")
        )

    # Convert tgfiles URL → t.me/filepress_XXXX_bot?start=TOKEN
    # by scraping the bot name from the filepress JS bundle
    tg_link = tg_url  # fallback: direct tgfiles URL
    try:
        token = tg_url.split("start=")[-1] if "start=" in tg_url else ""
        if token:
            import re as _re
            async with ClientSession() as sess:
                # Get index page to find JS bundle filename
                async with sess.get(base, headers={"Referer": base}) as r_idx:
                    idx_html = await r_idx.text()
                js_m = _re.search(r'src="(/assets/index-[^"]+\.js)"', idx_html)
                if js_m:
                    async with sess.get(
                        f"{base}{js_m.group(1)}", headers={"Referer": base}
                    ) as r_js:
                        js = await r_js.text()
                    bot_m = _re.search(r'filepress_[a-zA-Z0-9]+_bot', js)
                    if bot_m:
                        tg_link = f"https://t.me/{bot_m.group()}/?start={token}"
    except Exception:
        pass  # fallback to tgfiles URL

    parse_txt = (
        f"┏<b>FilePress:</b> <a href=\"{url}\">Source</a>\n"
        f"┗<b>Telegram:</b> <a href=\"{tg_link}\">Click Here</a>"
    )
    return parse_txt


async def gdtot(url):
    cget = create_scraper().request
    try:
        url = cget("GET", url).url
        p_url = urlparse(url)
        res = cget(
            "POST",
            f"{p_url.scheme}://{p_url.hostname}/ddl",
            data={"dl": str(url.split("/")[-1])},
        )
    except Exception as e:
        raise DDLException(f"{e.__class__.__name__}")
    if (
        drive_link := findall(r"myDl\('(.*?)'\)", res.text)
    ) and "drive.google.com" in drive_link[0]:
        d_link = drive_link[0]
    elif Config.GDTOT_CRYPT:
        cget("GET", url, cookies={"crypt": Config.GDTOT_CRYPT})
        p_url = urlparse(url)
        js_script = cget(
            "POST",
            f"{p_url.scheme}://{p_url.hostname}/dld",
            data={"dwnld": url.split("/")[-1]},
        )
        g_id = findall("gd=(.*?)&", js_script.text)
        try:
            decoded_id = b64decode(str(g_id[0])).decode("utf-8")
        except:
            raise DDLException(
                "Try in your browser, mostly file not found or user limit exceeded!"
            )
        d_link = f"https://drive.google.com/open?id={decoded_id}"
    else:
        raise DDLException(
            "Drive Link not found, Try in your broswer! GDTOT_CRYPT not Provided!"
        )
    soup = BeautifulSoup(cget("GET", url).content, "html.parser")
    parse_data = (
        (soup.select('meta[property^="og:description"]')[0]["content"])
        .replace("Download ", "")
        .rsplit("-", maxsplit=1)
    )
    parse_txt = f"""┏<b>Name:</b> <code>{parse_data[0]}</code>
┠<b>Size:</b> <code>{parse_data[-1]}</code>
┠<b>GDToT:</b> <a href="{url}">Click Here</a>
"""
    if Config.DIRECT_INDEX:
        parse_txt += f"┠<b>Temp Index:</b> <a href='{get_dl(d_link)}'>Click Here</a>\n"
    parse_txt += f"┗<b>GDrive:</b> <a href='{d_link}'>Click Here</a>"
    return parse_txt


async def drivescript(url, crypt, dtype):
    rs = Session()
    resp = rs.get(url)
    p_url = urlparse(url)

    # HubDrive redesigned — extract HubCloud link and resolve it directly
    if dtype == "HubDrive":
        soup = BeautifulSoup(resp.text, "html.parser")
        h6 = soup.find("h6", class_="font-weight-bold")
        title = h6.text.strip() if h6 else (
            soup.title.string.replace("HubDrive | ", "").strip() if soup.title else "Unknown"
        )
        tds = soup.select("td")
        size = tds[1].text.strip() if len(tds) > 1 else "Unknown"
        hc_tag = soup.find("a", href=lambda h: h and "hubcloud" in h)
        if hc_tag:
            try:
                return await hubcloud(hc_tag["href"])
            except Exception:
                pass
        parse_txt = (
            f"┏<b>Name:</b> <code>{title}</code>\n"
            f"┠<b>Size:</b> <code>{size}</code>\n"
            f"┠<b>HubDrive:</b> <a href=\"{url}\">Click Here</a>"
        )
        if hc_tag:
            parse_txt += f"\n┗<b>HubCloud:</b> <a href=\"{hc_tag['href']}\">Click Here</a>"
        else:
            parse_txt += "\n┗<b>Note:</b> Login required for GDrive link"
        return parse_txt

    # KatDrive / DriveFire — original logic
    titles = findall(r">(.*?)<\/h4>", resp.text)
    sizes = findall(r">(.*?)<\/td>", resp.text)
    title = titles[0] if titles else "Unknown"
    size = sizes[1] if len(sizes) > 1 else (sizes[0] if sizes else "Unknown")

    dlink = ""
    if dtype != "DriveFire":
        try:
            js_query = rs.post(
                f"{p_url.scheme}://{p_url.hostname}/ajax.php?ajax=direct-download",
                data={"id": str(url.split("/")[-1])},
                headers={"x-requested-with": "XMLHttpRequest"},
            ).json()
            if str(js_query["code"]) == "200":
                dlink = f"{p_url.scheme}://{p_url.hostname}{js_query['file']}"
        except Exception as e:
            LOGGER.error(e)

    if not dlink and crypt:
        rs.get(url, cookies={"crypt": crypt})
        try:
            js_query = rs.post(
                f"{p_url.scheme}://{p_url.hostname}/ajax.php?ajax=download",
                data={"id": str(url.split("/")[-1])},
                headers={"x-requested-with": "XMLHttpRequest"},
            ).json()
        except Exception as e:
            raise DDLException(f"{e.__class__.__name__}")
        if str(js_query["code"]) == "200":
            dlink = f"{p_url.scheme}://{p_url.hostname}{js_query['file']}"

    if dlink:
        res = rs.get(dlink)
        soup = BeautifulSoup(res.text, "html.parser")
        gd_data = soup.select('a[class="btn btn-primary btn-user"]')
        parse_txt = f"""┏<b>Name:</b> <code>{title}</code>
┠<b>Size:</b> <code>{size}</code>
┠<b>{dtype}:</b> <a href="{url}">Click Here</a>"""
        if (d_link := gd_data[0]["href"] if gd_data else None) and Config.DIRECT_INDEX:
            parse_txt += f"\n┠<b>Temp Index:</b> <a href='{get_dl(d_link)}'>Click Here</a>"
        parse_txt += f"\n┗<b>GDrive:</b> <a href='{d_link}'>Click Here</a>"
        return parse_txt
    elif not dlink and not crypt:
        raise DDLException(f"{dtype} Crypt Not Provided and Direct Link Generate Failed")
    else:
        raise DDLException(f'{js_query["file"]}')


async def hubcloud(url: str) -> str:
    """
    Two-step bypass for hubcloud.ist share links.
    Step 1: GET hubcloud.ist/drive/<id>  → extract gamerxyt.com URL from page JS
    Step 2: GET gamerxyt.com/hubcloud.php?...  → parse all download buttons generically
    Returns formatted text with all available server links.
    """
    from re import search as _search
    from urllib.parse import urlparse as _up
    from aiohttp import ClientTimeout

    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    headers = {"User-Agent": ua}
    timeout = ClientTimeout(total=30)

    async with ClientSession(timeout=timeout) as sess:
        async with sess.get(url, headers=headers, allow_redirects=True) as r1:
            html1 = await r1.text()

        m = _search(r"var url = '(https://gamerxyt\.com/hubcloud\.php[^']+)'", html1)
        if m:
            ajax_url = m.group(1)
        else:
            soup1 = BeautifulSoup(html1, "html.parser")
            dl = soup1.find("a", id="download")
            if not dl or not dl.get("href"):
                raise DDLException("HubCloud: could not find download URL in page")
            ajax_url = dl["href"]

        async with sess.get(
            ajax_url,
            headers={**headers, "Referer": "https://hubcloud.ist/"},
            allow_redirects=True,
        ) as r2:
            html2 = await r2.text()

    soup2 = BeautifulSoup(html2, "html.parser")

    size_el = soup2.find(id="size")
    if size_el and size_el.text.strip() in ("NAN", "NAN "):
        raise DDLException("HubCloud: token expired — retry")

    title = soup2.find("title")
    filename = title.text.strip() if title else "Unknown"
    size_text = size_el.text.strip() if size_el else "Unknown"

    EXCLUDED_HOSTS = {
        "hubcloud.ist", "hubcloud.cx", "hubcloud.club", "hubcloud.fans",
        "hubcloud.lat", "gamerxyt.com", "tinyurl.com", "t.me",
        "snvhost.com", "one.one.one.one", "hdhub4u.ms", "www.google.com",
    }

    def _label(href: str) -> str:
        host = _up(href).hostname or ""
        if "pongala" in host or "lenin.buzz" in host:
            return "FSLv2 Server"
        if "r2.cloudflarestorage.com" in host:
            return "FSL Server"
        if "storage.googleapis.com" in host:
            return "ZipDisk Server"
        if "pixeldrain" in host:
            return "Pixeldrain"
        if "fuckingfast.net" in host:
            return "Buzz Server"
        return host.replace("www.", "").split(".")[0].capitalize() + " Server"

    seen, links = set(), []
    for a in soup2.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("https://"):
            continue
        host = _up(href).hostname or ""
        if not host or host in EXCLUDED_HOSTS:
            continue
        cls = " ".join(a.get("class", []))
        if "btn" not in cls:
            continue
        if href in seen:
            continue
        seen.add(href)
        links.append((_label(href), href))

    if not links:
        raise DDLException("HubCloud: no download links found")

    lines = [
        f"┏<b>Name:</b> <code>{filename}</code>",
        f"┠<b>Size:</b> <code>{size_text}</code>",
        f"┠<b>HubCloud:</b> <a href=\"{url}\">Source</a>",
    ]
    for i, (label, link) in enumerate(links):
        prefix = "┗" if i == len(links) - 1 else "┠"
        lines.append(f"{prefix}<b>{label}:</b> <a href=\"{link}\">Click Here</a>")

    return "\n".join(lines)


async def appflix(url):
    async def appflix_single(url):
        cget = create_scraper().request
        url = cget("GET", url).url
        soup = BeautifulSoup(
            cget("GET", url, allow_redirects=False).text, "html.parser"
        )
        ss = soup.select("li[class^='list-group-item']")
        dbotv2 = (
            dbot[0]["href"]
            if "gdflix" in url and (dbot := soup.select("a[href*='drivebot.lol']"))
            else None
        )
        try:
            d_link = await sharer_scraper(url)
        except Exception as e:
            if not dbotv2:
                raise DDLException(e)
            else:
                d_link = str(e)
        parse_txt = f"""┏<b>Name:</b> <code>{ss[0].string.split(":")[1]}</code>
┠<b>Size:</b> <code>{ss[2].string.split(":")[1]}</code>
┠<b>Source:</b> <code>{url}</code>"""
        if dbotv2:
            parse_txt += f"\n┠<b>DriveBot V2:</b> <a href='{dbotv2}'>Click Here</a>"
        if d_link and Config.DIRECT_INDEX:
            parse_txt += (
                f"\n┠<b>Temp Index:</b> <a href='{get_dl(d_link)}'>Click Here</a>"
            )
        parse_txt += f"\n┗<b>GDrive:</b> <a href='{d_link}'>Click Here</a>"
        return parse_txt

    if "/pack/" in url:
        cget = create_scraper().request
        url = cget("GET", url).url
        soup = BeautifulSoup(cget("GET", url).content, "html.parser")
        p_url = urlparse(url)
        body = ""
        atasks = [
            create_task(
                appflix_single(f"{p_url.scheme}://{p_url.hostname}" + ss["href"])
            )
            for ss in soup.select("a[href^='/file/']")
        ]
        completed_tasks = await gather(*atasks, return_exceptions=True)
        for bp_link in completed_tasks:
            if isinstance(bp_link, Exception):
                body += "\n\n" + f"<b>Error:</b> {bp_link}"
            else:
                body += "\n\n" + bp_link
        return f"""┏<b>Name:</b> <code>{soup.title.string}</code>
┗<b>Source:</b> <code>{url}</code>{body}"""
    return await appflix_single(url)


async def sharerpw(url: str, force=False):
    if not Config.XSRF_TOKEN and not Config.LARAVEL_SESSION:
        raise DDLException("XSRF_TOKEN or LARAVEL_SESSION not Provided!")
    cget = create_scraper(allow_brotli=False).request
    resp = cget(
        "GET",
        url,
        cookies={
            "XSRF-TOKEN": Config.XSRF_TOKEN,
            "laravel_session": Config.LARAVEL_SESSION,
        },
    )
    parse_txt = findall(r">(.*?)<\/td>", resp.text)
    ddl_btn = etree.HTML(resp.content).xpath("//button[@id='btndirect']")
    token = findall(r"_token\s=\s'(.*?)'", resp.text, DOTALL)[0]
    data = {"_token": token}
    if not force:
        data["nl"] = 1
    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
    }
    try:
        res = cget("POST", url + "/dl", headers=headers, data=data).json()
    except Exception as e:
        raise DDLException(str(e))
    parse_data = f"""┏<b>Name:</b> <code>{parse_txt[2]}</code>
┠<b>Size:</b> <code>{parse_txt[8]}</code>
┠<b>Added On:</b> <code>{parse_txt[11]}</code>
"""
    if res["status"] == 0:
        if Config.DIRECT_INDEX:
            parse_data += (
                f"\n┠<b>Temp Index:</b> <a href='{get_dl(res['url'])}'>Click Here</a>"
            )
        return parse_data + f"\n┗<b>GDrive:</b> <a href='{res['url']}'>Click Here</a>"
    elif res["status"] == 2:
        msg = res["message"].replace("<br/>", "\n")
        return parse_data + f"\n┗<b>Error:</b> {msg}"
    if len(ddl_btn) and not force:
        return await sharerpw(url, force=True)


async def sharer_scraper(url):
    cget = create_scraper().request
    try:
        url = cget("GET", url).url
        raw = urlparse(url)
        header = {
            "useragent": "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/534.10 (KHTML, like Gecko) Chrome/7.0.548.0 Safari/534.10"
        }
        res = cget("GET", url, headers=header)
    except Exception as e:
        raise DDLException(f"{e.__class__.__name__}")
    key = findall(r'"key",\s+"(.*?)"', res.text)
    if not key:
        raise DDLException("Download Link Key not found!")
    key = key[0]
    if not etree.HTML(res.content).xpath("//button[@id='drc']"):
        raise DDLException("Link don't have direct download button")
    boundary = uuid4()
    headers = {
        "Content-Type": f"multipart/form-data; boundary=----WebKitFormBoundary{boundary}",
        "x-token": raw.hostname,
        "useragent": "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/534.10 (KHTML, like Gecko) Chrome/7.0.548.0 Safari/534.10",
    }

    data = (
        f'------WebKitFormBoundary{boundary}\r\nContent-Disposition: form-data; name="action"\r\n\r\ndirect\r\n'
        f'------WebKitFormBoundary{boundary}\r\nContent-Disposition: form-data; name="key"\r\n\r\n{key}\r\n'
        f'------WebKitFormBoundary{boundary}\r\nContent-Disposition: form-data; name="action_token"\r\n\r\n\r\n'
        f"------WebKitFormBoundary{boundary}--\r\n"
    )
    try:
        res = cget("POST", url, cookies=res.cookies, headers=headers, data=data).json()
    except Exception as e:
        raise DDLException(f"{e.__class__.__name__}")
    if "url" not in res:
        raise DDLException("Drive Link not found, Try in your browser")
    if "drive.google.com" in res["url"]:
        return res["url"]
    try:
        res = cget("GET", res["url"])
    except Exception as e:
        raise DDLException(f"ERROR: {e.__class__.__name__}")
    if (
        drive_link := etree.HTML(res.content).xpath("//a[contains(@class,'btn')]/@href")
    ) and "drive.google.com" in drive_link[0]:
        return drive_link[0]
    else:
        raise DDLException("Drive Link not found, Try in your browser")
