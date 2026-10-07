from re import match
from asyncio import to_thread
from urllib.parse import urlparse

from FZBypass.bypass.dlinks import *
from FZBypass.bypass.ddl import *
from FZBypass.bypass.scrape import *
from FZBypass.core.bot_utils import get_dl
from FZBypass.core.exceptions import DDLException

fmed_list = [
    "fembed.net",
    "fembed.com",
    "femax20.com",
    "fcdn.stream",
    "feurl.com",
    "layarkacaxxi.icu",
    "naniplay.nanime.in",
    "naniplay.nanime.biz",
    "naniplay.com",
    "mm9842.com",
]


def is_share_link(url):
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    return any(
        _has_host_label(host, label)
        for label in (
            "gdtot",
            "filepress",
            "pressbee",
            "gdflix",
            "onlystream",
            "filebee",
            "appdrive",
        )
    )


def is_excep_link(url):
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if _has_host_label(host, "gdshare") or _has_host_label(host, "gcloud"):
        return parsed.path.startswith("/download/")
    if _has_host_label(host, "filebee") or _has_host_label(host, "drivecloud"):
        return parsed.path.startswith("/file/")
    if _has_host_label(host, "hindianimeszone"):
        return parsed.path.endswith("/download1.php")
    return any(
        _has_host_label(host, label)
        for label in (
            "1tamilmv",
            "gdtot",
            "filepress",
            "pressbee",
            "gdflix",
            "sharespark",
            "sharer",
            "onlystream",
            "hubdrive",
            "hubcloud",
            "katdrive",
            "drivefire",
            "skymovieshd",
            "toonworld4all",
            "kayoanime",
            "cinevood",
            "filebee",
            "appdrive",
            "hdhub4u",
            "hdstream4u",
            "4khdhub",
            "get-to",
            "just2earn",
        )
    )


def _has_host_label(host: str | None, label: str) -> bool:
    """Match a provider label without assuming its subdomain or TLD."""
    return label in (host or "").lower().split(".")


def _is_provider_url(url: str, *labels: str) -> bool:
    """Match provider hostname labels across subdomains and DNS suffixes."""
    parsed = urlparse(url)
    return (
        parsed.scheme.lower() in {"http", "https"}
        and any(_has_host_label(parsed.hostname, label) for label in labels)
    )


async def direct_link_checker(link, onlylink=False):
    domain = urlparse(link).hostname

    # R2 public buckets expose the file directly and must not be sent through
    # another resolver after a shortener returns them.
    if domain and (
        domain.endswith(".r2.dev")
        or domain.endswith(".r2.cloudflarestorage.com")
    ):
        return link

    if (
        _is_provider_url(link, "gdshare", "gcloud")
        and urlparse(link).path.startswith("/download/")
    ):
        return await gcloud(link)

    if (
        _is_provider_url(link, "filebee", "drivecloud")
        and urlparse(link).path.startswith("/file/")
    ):
        return link

    # Provider sites use rotating subdomains and TLDs. Match their exact
    # hostname labels before legacy domain-specific regular expressions.
    if _has_host_label(domain, "hindianimeszone") and urlparse(link).path.endswith(
        "/download1.php"
    ):
        return await hindianimeszone(link)
    if _has_host_label(domain, "hdstream4u"):
        return await hdstream4u(link)
    if _has_host_label(domain, "hdhub4u"):
        return await hdhub4u(link)
    if _has_host_label(domain, "4khdhub"):
        return await fourkhdhub(link)
    if _has_host_label(domain, "hubcloud"):
        return await hubcloud(link)
    if _has_host_label(domain, "hubdrive"):
        return await drivescript(link, Config.HUBDRIVE_CRYPT, "HubDrive")
    if _has_host_label(domain, "drivehub"):
        return await drivehub(link)
    if _has_host_label(domain, "katdrive"):
        return await drivescript(link, Config.KATDRIVE_CRYPT, "KatDrive")
    if _has_host_label(domain, "drivefire"):
        return await drivescript(link, Config.DRIVEFIRE_CRYPT, "DriveFire")
    if _has_host_label(domain, "gdflix"):
        return await gdflix(link)
    if _has_host_label(domain, "vifix"):
        vifix_path = urlparse(link).path
        if vifix_path.startswith("/file/"):
            gdflix_url = f"https://new4.gdflix.io{vifix_path}"
            return await gdflix(gdflix_url)
        raise DDLException("Vifix: unsupported URL format")
    if _has_host_label(domain, "filepress"):
        return await filepress(link)
    if _has_host_label(domain, "pressbee"):
        return await filepress(link)
    if _has_host_label(domain, "appdrive"):
        return await appflix(link)
    if _has_host_label(domain, "cinevood"):
        return await cinevood(link)
    if _has_host_label(domain, "hblinks"):
        return await hblinks(link)
    if _has_host_label(domain, "nexdrive"):
        return await nexdrive(link)
    if _has_host_label(domain, "kayoanime"):
        return await kayoanime(link)
    if _has_host_label(domain, "toonworld4all"):
        return await toonworld4all(link)
    if _has_host_label(domain, "skymovieshd"):
        return await skymovieshd(link)
    if _has_host_label(domain, "sharespark"):
        return await sharespark(link)
    if _has_host_label(domain, "get-to"):
        return await gettolink(link)
    if _has_host_label(domain, "1tamilmv"):
        return await tamilmv(link)
    if _has_host_label(domain, "greenmotors"):
        return await greenmotors(link)

    # File Hoster Links
    if _is_provider_url(link, "yadi", "yandex"):
        return await yandex_disk(link)
    elif _is_provider_url(link, "mediafire"):
        return await mediafire(link)
    elif _is_provider_url(link, "shrdsk"):
        return await shrdsk(link)
    elif any(
        _has_host_label(domain, label)
        for label in (
            "1024tera",
            "terabox",
            "nephobox",
            "4funbox",
            "mirrobox",
            "momerybox",
            "teraboxapp",
            "terasharefile",
            "freeterabox",
            "teraboxlink",
            "terafileshare",
            "teraboxshare",
        )
    ):
        dlinks = await terabox(link)
        # Single file → return plain string; multi-file → return list for numbered display
        return dlinks[0] if len(dlinks) == 1 else dlinks

    elif _is_provider_url(link, "pornhub"):
        return await pornhub(link)
    elif bool(
        match(
            r"https?:\/\/(?:www\.)?pixeldrain\."
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
            r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
            r"\/(u|l)\/\S+",
            link,
            flags=2,
        )
    ):
        return await pixeldrain(link)
    elif bool(match(r"https?:\/\/cdn\.pixeldrain\.\S+\/[a-zA-Z0-9]+", link)):
        # cdn.pixeldrain.eu.cc/<id> — already a direct CDN URL, extract ID and return direct link
        _pd_id = link.rstrip("/").split("/")[-1].split("?")[0]
        return f"https://pixeldrain.com/api/file/{_pd_id}?download"
    elif _is_provider_url(link, "vipshort"):
        # vipshort.in → link.vipshort.in uses gangstarnewyorkapk wpSafeLink
        # which we can't bypass via HTTP — return the link.vipshort.in URL as-is
        from urllib.parse import urlparse as _upvip
        _host = _upvip(link).hostname or ""
        if "link." in _host:
            return link  # already link.vipshort.in, can't go further
        blink = await shorter(link)  # follow vipshort.in → link.vipshort.in redirect
    elif _is_provider_url(link, "gofile") and urlparse(link).path.split("/")[1:2] in (
        ["d"],
        ["download"],
    ):
        return await gofile(link)
    elif domain == "1drv.ms" or _is_provider_url(link, "onedrive", "sharepoint"):
        return await onedrive(link)
    elif "drive.google.com" in link:
        return await to_thread(get_dl, link, True)

    # DDL Links
    elif _is_provider_url(link, "try2link"):
        blink = await try2link(link)
    elif _is_provider_url(link, "gyanilinks", "gtlinks"):
        blink = await gyanilinks(link)
    elif _is_provider_url(link, "earnlinks"):
        blink = await earnlinks(link)
    elif _is_provider_url(link, "mvurl", "liteurl"):
        blink = await itilink(link)
    elif _is_provider_url(link, "aylink", "ay"):
        blink = await aylink(link)
    elif _is_provider_url(link, "cpmlink", "cpm"):
        blink = await cpmlink(link)
    elif _is_provider_url(link, "boost", "mboost", "bst", "booo"):
        blink = await boost(link)
    elif _is_provider_url(link, "shrinkme"):
        blink = await shrinkme(link)
    elif _is_provider_url(link, "shortxlinks"):
        blink = await shortxlinks(link)
    elif _is_provider_url(link, "srnky", "clksz", "oii"):
        blink = await srnky(link)
    elif _is_provider_url(link, "exeygo"):
        blink = await exeygo(link)
    elif _is_provider_url(link, "vplink", "vplinks"):
        blink = await vplink(link)
    elif _is_provider_url(link, "arolinks"):
        blink = await arolinks(link)
    elif _is_provider_url(link, "antibypass", "avbypassbot") and domain and domain.endswith(
        ".koyeb.app"
    ):
        blink = await antibypass(link)
    elif _is_provider_url(link, "gplinks"):
        blink = await gplinks(link)
    elif _is_provider_url(link, "cyberloom") and urlparse(link).path.startswith("/l/"):
        blink = await cyberloom(link)
    elif _is_provider_url(link, "ouo"):
        blink = await ouo(link)
    elif _is_provider_url(link, "shareus", "shrs"):
        blink = await shareus(link)
    elif _is_provider_url(link, "dropbox"):
        blink = await dropbox(link)
    elif _is_provider_url(
        link,
        "linkvertise",
        "link-to",
        "lootlinks",
        "lootlabs",
        "linkvertised",
        "lv-linkvertise",
        "direct-link",
    ):
        blink = await linkvertise(link)
    elif _is_provider_url(link, "rslinks"):
        blink = await rslinks(link)
    elif _is_provider_url(link, "buzzheavier"):
        blink = await buzzheavier(link)
    elif _is_provider_url(link, "vikingfile") and urlparse(link).path.startswith("/f/"):
        blink = await vikingfile(link)
    elif _is_provider_url(link, "extralink") and urlparse(link).path.startswith("/file/"):
        blink = await extralink(link)
    elif _is_provider_url(link, "linkshub") and urlparse(link).path.startswith("/view/"):
        return await linkshub(link)
    elif _is_provider_url(link, "katlinks") and urlparse(link).path.startswith("/archives/"):
        return await katlinks(link)
    elif _is_provider_url(link, "hubcdn") and urlparse(link).path.startswith("/file/"):
        blink = await hubcdn(link)
    elif _is_provider_url(link, "vcloud"):
        blink = await vcloud(link)
    elif _is_provider_url(link, "bit", "tinyurl", "shorturl", "t") or (
        domain and ".short." in domain
    ):
        blink = await shorter(link)
    elif _is_provider_url(link, "xdmovies") and urlparse(link).path.startswith("/download/"):
        blink = await xdmovies(link)
    elif _is_provider_url(link, "appurl"):
        blink = await appurl(link)
    elif _is_provider_url(link, "surl"):
        blink = await surl(link)
    elif _is_provider_url(link, "thinfi"):
        blink = await thinfi(link)
    elif _is_provider_url(link, "justpaste"):
        blink = await justpaste(link)
    elif _is_provider_url(link, "just2earn"):
        blink = await just2earn(link)
    elif _is_provider_url(link, "linksxyz"):
        blink = await linksxyz(link)

    # ── File hosters that return direct links ─────────────────────────────────
    elif _is_provider_url(link, "streamtape"):
        return await streamtape(link)
    elif _is_provider_url(link, "wetransfer") or domain == "we.tl":
        return await wetransfer(link)
    elif _is_provider_url(link, "filecrypt"):
        return await filecrypt(link)
    elif _is_provider_url(link, "krakenfiles"):
        return await krakenfiles(link)
    elif _is_provider_url(link, "1fichier"):
        return await fichier(link)

    # DL Sites
    elif _is_provider_url(link, "dotflix") and urlparse(link).path.startswith("/share"):
        return await dotflix(link)
    elif _is_provider_url(link, "dtflix") and urlparse(link).path.startswith("/share"):
        return await dotflix(link)
    elif (
        _is_provider_url(link, "azonahub")
        and domain
        and domain.split(".")[0] in {"cloud", "short"}
    ):
        return await toxcloud(link)
    elif _is_provider_url(link, "eonmovies") and urlparse(link).path.startswith("/dl/"):
        blink = await eonmovies(link)
    elif _is_provider_url(link, "eonmovies") and urlparse(link).path.startswith("/links/"):
        blink = await eonmovies(link)
    elif _is_provider_url(link, "nexdrive"):
        return await nexdrive(link)
    elif _is_provider_url(link, "hblinks"):
        return await hblinks(link)
    elif _is_provider_url(link, "cinevood"):
        return await cinevood(link)
    elif _is_provider_url(link, "hdstream4u"):
        return await hdstream4u(link)
    elif _is_provider_url(link, "hdhub4u"):
        return await hdhub4u(link)

    elif _is_provider_url(link, "extraflix"):
        return await extraflix(link)

    elif _is_provider_url(link, "bollyflix"):
        return await bollyflix(link)

    elif _is_provider_url(link, "hdwebmovies"):
        return await hdwebmovies(link)

    elif _is_provider_url(link, "filmyfly"):
        return await filmyfly(link)
    elif _is_provider_url(link, "filmyfiy"):
        return await filmyfly(link)
    elif _is_provider_url(link, "filmycab"):
        return await filmyfly(link)

    elif _is_provider_url(link, "4khdhub"):
        return await fourkhdhub(link)

    elif _is_provider_url(link, "greenmotors"):
        return await greenmotors(link)
    elif _is_provider_url(link, "kayoanime"):
        return await kayoanime(link)
    elif _is_provider_url(link, "toonworld4all") and urlparse(link).path.startswith(
        ("/redirect/", "/verify/")
    ):
        return await tw4all_redirect(link)
    elif _is_provider_url(link, "toonworld4all"):
        return await toonworld4all(link)
    elif _is_provider_url(link, "skymovieshd"):
        return await skymovieshd(link)
    elif _is_provider_url(link, "sharespark"):
        return await sharespark(link)
    elif _is_provider_url(link, "1tamilmv"):
        return await tamilmv(link)

    # DL Links
    elif _is_provider_url(link, "hubcloud"):
        return await hubcloud(link)
    elif _is_provider_url(link, "hubdrive"):
        return await drivescript(link, Config.HUBDRIVE_CRYPT, "HubDrive")
    elif _is_provider_url(link, "katdrive"):
        return await drivescript(link, Config.KATDRIVE_CRYPT, "KatDrive")
    elif _is_provider_url(link, "drivefire"):
        return await drivescript(link, Config.DRIVEFIRE_CRYPT, "DriveFire")
    elif _is_provider_url(link, "sharer"):
        return await sharerpw(link)
    elif is_share_link(link):
        if "gdtot" in domain:
            return await gdtot(link)
        elif "filepress" in domain or "pressbee" in domain:
            return await filepress(link)
        elif "gdflix" in domain:
            return await gdflix(link)
        elif "appdrive" in domain:
            return await appflix(link)
        else:
            return await sharer_scraper(link)

    # Exceptions
    elif (
        _is_provider_url(link, "technicalatg")
        and domain
        and domain.count(".") >= 2
    ):
        raise DDLException("Bypass Not Allowed !")
    else:
        raise DDLException(
            f"<i>No Bypass Function Found for your Link :</i> <code>{link}</code>"
        )

    if onlylink:
        return blink

    links = []
    depth = 0
    MAX_DEPTH = 10
    seen_links = set()
    while depth < MAX_DEPTH:
        if blink in seen_links:
            break  # redirect loop detected
        seen_links.add(blink)
        try:
            links.append(blink)
            blink = await direct_link_checker(blink, onlylink=True)
            if is_excep_link(links[-1]):
                links.append("\n\n" + blink)
                break
        except Exception:
            break
        depth += 1
    return links
