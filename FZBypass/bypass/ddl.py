from re import findall, compile
from asyncio import sleep as asleep
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup
from cloudscraper import create_scraper
from curl_cffi.requests import Session as cSession
from requests import Session, get as rget
from aiohttp import ClientSession

from FZBypass import Config
from FZBypass.core.exceptions import DDLException
from FZBypass.bypass.recaptcha import recaptchaV3

async def yandex_disk(url: str) -> str:
    cget = create_scraper().request
    try:
        return cget(
            "get",
            f"https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key={url}",
        ).json()["href"]
    except KeyError:
        raise DDLException("File not Found / Download Limit Exceeded")


async def mediafire(url: str):
    if final_link := findall(
        r"https?:\/\/download\d+\.mediafire\.com\/\S+\/\S+\/\S+", url
    ):
        return final_link[0]
    cget = create_scraper().request
    try:
        url = cget("get", url).url
        page = cget("get", url).text
    except Exception as e:
        raise DDLException(f"{e.__class__.__name__}")
    if final_link := findall(
        r"\'(https?:\/\/download\d+\.mediafire\.com\/\S+\/\S+\/\S+)\'", page
    ):
        return final_link[0]
    elif temp_link := findall(
        r'\/\/(www\.mediafire\.com\/file\/\S+\/\S+\/file\?\S+)', page
    ):
        return await mediafire("https://"+temp_link[0].strip('"'))
    else:
        raise DDLException("No links found in this page")


async def shrdsk(url: str) -> str:
    cget = create_scraper().request
    try:
        url = cget("GET", url).url
        res = cget(
            "GET",
            f'https://us-central1-affiliate2apk.cloudfunctions.net/get_data?shortid={url.split("/")[-1]}',
        )
    except Exception as e:
        raise DDLException(f"{e.__class__.__name__}")
    if res.status_code != 200:
        raise DDLException(f"Status Code {res.status_code}")
    res = res.json()
    if "type" in res and res["type"].lower() == "upload" and "video_url" in res:
        return quote(res["video_url"], safe=":/")
    raise DDLException("No Direct Link Found")


async def terabox(url: str) -> list:
    """
    Resolve a Terabox share URL to a list of direct download links.

    Strategy (in order):
      1. If TERABOX_API_URL is configured, POST to its /download endpoint.
         Returns proxy_url links (no cookie needed to download).
         On any failure, falls through to Path 2.
      2. Direct WAP bypass using TERA_COOKIE.
         Returns raw dlinks (needs ndus cookie to download).
      If neither is configured/working, raises DDLException.
    """
    import json as _json
    import re as _re

    # ------------------------------------------------------------------
    # Path 1: terabox-downloader-api (preferred)
    # ------------------------------------------------------------------
    if Config.TERABOX_API_URL:
        try:
            from aiohttp import ClientTimeout as _CT
            async with ClientSession() as session:
                async with session.post(
                    f"{Config.TERABOX_API_URL}/download",
                    json={"url": url},
                    headers={"Content-Type": "application/json"},
                    timeout=_CT(total=60),  # 60s to handle Render cold start
                ) as resp:
                    data = await resp.json()

            if data.get("status") == "success":
                files = data["data"].get("files", [])
                # Prefer proxy_url (no cookie needed) over raw dlink
                links = [
                    f.get("proxy_url") or f.get("dlink")
                    for f in files
                    if f.get("proxy_url") or f.get("dlink")
                ]
                if links:
                    return links
                raise DDLException("Terabox API: no download links in response")
            # Surface the actual API error message instead of silently falling through
            raise DDLException(
                f"Terabox API: {data.get('message', 'unknown error')}"
            )
        except DDLException:
            raise
        except Exception as e:
            # Network/timeout — only fall through to cookie path if TERA_COOKIE is set
            if not Config.TERA_COOKIE:
                raise DDLException(f"Terabox API unreachable: {e.__class__.__name__}: {e}")
            # else fall through

    # ------------------------------------------------------------------
    # Path 2: Direct WAP bypass using TERA_COOKIE (fallback)
    # ------------------------------------------------------------------
    if not Config.TERA_COOKIE:
        raise DDLException(
            "Terabox: set TERABOX_API_URL (recommended) or TERA_COOKIE to bypass"
        )

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
    MOBILE_UA = (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    )

    from urllib.parse import urlparse as _urlparse, parse_qs as _parse_qs

    def _parse_surl(share_url):
        parsed = _urlparse(share_url)
        if "/s/" in parsed.path:
            surl = parsed.path.split("/s/")[-1].strip("/")
        else:
            qs = _parse_qs(parsed.query)
            surl = qs.get("surl", [""])[0]
        if not surl:
            raise DDLException(f"Cannot extract surl from URL: {share_url}")
        if len(surl) > 22 and surl.startswith("1"):
            surl = surl[1:]
        if len(surl) < 8:
            raise DDLException(f"Invalid surl: '{surl}'")
        return surl

    def _build_session(ndus):
        sess = Session()
        for domain in TERABOX_DOMAINS:
            sess.cookies.set("ndus", ndus, domain=domain)
        return sess

    def _fetch_wap(sess, surl, share_url):
        host = _urlparse(share_url).hostname or ""
        candidates = []
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

        headers = {"User-Agent": MOBILE_UA, "Accept": "text/html,*/*"}
        for wap_url in candidates:
            try:
                r = sess.get(wap_url, headers=headers, allow_redirects=True, timeout=15)
                if r.status_code == 200 and "__INITIAL_STATE__" in r.text:
                    return r.text
            except Exception:
                continue
        raise DDLException(f"Could not load Terabox WAP page for surl={surl}")

    def _extract_dlinks(html):
        m = _re.search(
            r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*(?:;|</script>)',
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

    try:
        surl = _parse_surl(url)
        sess = _build_session(Config.TERA_COOKIE)
        html = _fetch_wap(sess, surl, url)
        return _extract_dlinks(html)
    except DDLException:
        raise
    except Exception as e:
        raise DDLException(f"Terabox WAP bypass error: {e.__class__.__name__}: {e}")


async def try2link(url: str) -> str:
    DOMAIN = 'https://try2link.com'
    code = url.split('/')[-1]

    async with ClientSession() as session:
        html = None
        referers = ['https://hightrip.net/', 'https://to-travel.net', 'https://world2our.com/']
        for referer in referers:
            async with session.get(f'{DOMAIN}/{code}', headers={"Referer": referer}) as res:
                if res.status == 200:
                    html = await res.text()
                    break
        if html is None:
            raise DDLException("try2link: could not load page (all referers failed)")
        soup = BeautifulSoup(html, "html.parser")
        go_link = soup.find(id="go-link")
        if not go_link:
            raise DDLException("try2link: go-link form not found")
        inputs = go_link.find_all(name="input")
        data = {input.get('name'): input.get('value') for input in inputs}
        await asleep(6)
        async with session.post(f"{DOMAIN}/links/go", data=data, headers={"X-Requested-With": "XMLHttpRequest"}) as resp:
            ct = resp.headers.get('Content-Type', '')
            if 'application/json' in ct:
                json_data = await resp.json()
                if 'url' in json_data:
                    return json_data['url']
            raise DDLException("try2link: no URL in response")


async def gyanilinks(url: str) -> str:
    '''
    Based on https://github.com/whitedemon938/Bypass-Scripts
    '''
    code = url.split('/')[-1]
    useragent = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    DOMAIN = "https://go.bloggingaro.com"

    async with ClientSession() as session:
        async with session.get(f"{DOMAIN}/{code}", headers={'Referer':'https://tech.hipsonyc.com/','User-Agent': useragent}) as res:
            cookies = res.cookies
            html = await res.text()
        async with session.get(f"{DOMAIN}/{code}", headers={'Referer':'https://hipsonyc.com/','User-Agent': useragent}, cookies=cookies) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, 'html.parser')
        data = {inp.get('name'): inp.get('value') for inp in soup.find_all('input')}
        await asleep(5)
        async with session.post(f"{DOMAIN}/links/go", data=data, headers={'X-Requested-With':'XMLHttpRequest','User-Agent': useragent, 'Referer': f"{DOMAIN}/{code}"}, cookies=cookies) as links:
            ct = links.headers.get('Content-Type', '')
            if 'application/json' in ct:
                result = await links.json()
                if 'url' in result:
                    return result['url']
            raise DDLException("gyanilinks: no URL in response")


async def ouo(url: str):
    tempurl = url.replace("ouo.io", "ouo.press")
    p = urlparse(tempurl)
    id = tempurl.split("/")[-1]
    client = cSession(
        headers={
            "authority": "ouo.press",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
            "cache-control": "max-age=0",
            "referer": "http://www.google.com/ig/adde?moduleurl=",
            "upgrade-insecure-requests": "1",
        }
    )
    res = client.get(tempurl, impersonate="chrome110")
    next_url = f"{p.scheme}://{p.hostname}/go/{id}"

    for _ in range(2):
        if res.headers.get("Location"):
            break
        bs4 = BeautifulSoup(res.content, "lxml")
        inputs = bs4.form.findAll("input", {"name": compile(r"token$")})
        data = {inp.get("name"): inp.get("value") for inp in inputs}
        data["x-token"] = await recaptchaV3()
        res = client.post(
            next_url,
            data=data,
            headers={"content-type": "application/x-www-form-urlencoded"},
            allow_redirects=False,
            impersonate="chrome110",
        )
        next_url = f"{p.scheme}://{p.hostname}/xreallcygo/{id}"

    location = res.headers.get("Location")
    if not location:
        raise DDLException("ouo: no redirect Location header in response")
    return location


async def transcript(url: str, DOMAIN: str, ref: str, sltime) -> str:
    code = url.rstrip("/").split("/")[-1]
    useragent = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'

    async with ClientSession() as session:
        async with session.get(f"{DOMAIN}/{code}", headers={'Referer': ref, 'User-Agent': useragent}) as res:
            html = await res.text()
            cookies = res.cookies
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find('title')
        if title_tag and title_tag.text == 'Just a moment...':
            return "Unable To Bypass Due To Cloudflare Protected"
        data = {inp.get('name'): inp.get('value') for inp in soup.find_all('input') if inp.get('name') and inp.get('value')}
        await asleep(sltime)
        async with session.post(
            f"{DOMAIN}/links/go", data=data,
            headers={'Referer': f"{DOMAIN}/{code}", 'X-Requested-With': 'XMLHttpRequest', 'User-Agent': useragent},
            cookies=cookies,
        ) as resp:
            ct = resp.headers.get('Content-Type', '')
            if 'application/json' in ct:
                result = await resp.json()
                if 'url' in result:
                    return result['url']
            raise DDLException("transcript: no URL in response")


async def justpaste(url: str):
    resp = rget(url, verify=False)
    soup = BeautifulSoup(resp.text, "html.parser")
    inps = soup.select('div[id="articleContent"] > p')
    return ", ".join(elem.string for elem in inps)
    

async def linksxyz(url: str):
    resp = rget(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    inps = soup.select('div[id="redirect-info"] > a')
    return inps[0]["href"]


async def shareus(url: str) -> str:
    DOMAIN = f"https://api.shrslink.xyz"
    code = url.split('/')[-1]
    headers = {
        'User-Agent':'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        'Origin':'https://shareus.io',
    }
    api = f"{DOMAIN}/v?shortid={code}&initial=true&referrer="
    id = rget(api, headers=headers).json()['sid']
    if id:
        api_2 = f"{DOMAIN}/get_link?sid={id}"
        res = rget(api_2, headers=headers)
        if res:
            return res.json()['link_info']['destination']
        else:
            raise DDLException("Link Extraction Failed")
    else:
        raise DDLException("ID Error")     


async def dropbox(url: str) -> str:
    return (
        url.replace("www.", "")
        .replace("dropbox.com", "dl.dropboxusercontent.com")
        .replace("?dl=0", "")
    )


async def linkvertise(url: str) -> str:
    resp = rget("https://bypass.pm/bypass2", params={"url": url}).json()
    if resp["success"]:
        return resp["destination"]
    else:
        raise DDLException(resp["msg"])


async def rslinks(url: str) -> str:
    resp = rget(url, stream=True, allow_redirects=False)
    code = resp.headers["location"].split("ms9")[-1]
    try:
        return f"http://techyproio.blogspot.com/p/short.html?{code}=="
    except:
        raise DDLException("Link Extraction Failed")


async def shorter(url: str) -> str:
    try:
        cget = create_scraper().request
        resp = cget("GET", url, allow_redirects=False)
        return resp.headers["Location"]
    except:
        raise DDLException("Link Extraction Failed")


async def appurl(url: str):
    cget = create_scraper().request
    resp = cget("GET", url, allow_redirects=False)
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.select('meta[property="og:url"]')[0]["content"]


async def surl(url: str):
    cget = create_scraper().request
    resp = cget("GET", f"{url}+")
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.select('p[class="long-url"]')[0].string.split()[1]


async def thinfi(url: str) -> str:
    try:
        return BeautifulSoup(rget(url).content, "html.parser").p.a.get("href")
    except:
        raise DDLException("Link Extraction Failed")
