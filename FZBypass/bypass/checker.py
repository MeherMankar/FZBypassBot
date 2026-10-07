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
    host = urlparse(url).hostname
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
    host = urlparse(url).hostname
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
        )
    )


def _has_host_label(host: str | None, label: str) -> bool:
    """Match a provider label without assuming its subdomain or TLD."""
    return label in (host or "").lower().split(".")


async def direct_link_checker(link, onlylink=False):
    domain = urlparse(link).hostname

    # R2 public buckets expose the file directly and must not be sent through
    # another resolver after a shortener returns them.
    if domain and (
        domain.endswith(".r2.dev")
        or domain.endswith(".r2.cloudflarestorage.com")
    ):
        return link

    # Provider sites use rotating subdomains and TLDs. Match their exact
    # hostname labels before legacy domain-specific regular expressions.
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
    if _has_host_label(domain, "1tamilmv"):
        return await tamilmv(link)
    if _has_host_label(domain, "greenmotors"):
        return await greenmotors(link)

    # File Hoster Links
    if bool(match(r"https?:\/\/(yadi|disk.yandex)\.\S+", link)):
        return await yandex_disk(link)
    elif bool(match(r"https?:\/\/.+\.mediafire\.\S+", link)):
        return await mediafire(link)
    elif bool(match(r"https?:\/\/shrdsk\.\S+", link)):
        return await shrdsk(link)
    elif any(
        x in (domain or "")
        for x in [
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
        ]
    ):
        dlinks = await terabox(link)
        # Single file → return plain string; multi-file → return list for numbered display
        return dlinks[0] if len(dlinks) == 1 else dlinks

    elif bool(match(r"https?:\/\/(www\.)?(pornhub\.com|pornhub\.org|pornhub\.net)\S+", link)):
        return await pornhub(link)
    elif bool(match(r"https?:\/\/(www\.)?pixeldrain\.com\/(u|l)\/\S+", link)):
        return await pixeldrain(link)
    elif bool(match(r"https?:\/\/cdn\.pixeldrain\.\S+\/[a-zA-Z0-9]+", link)):
        # cdn.pixeldrain.eu.cc/<id> — already a direct CDN URL, extract ID and return direct link
        _pd_id = link.rstrip("/").split("/")[-1].split("?")[0]
        return f"https://pixeldrain.com/api/file/{_pd_id}?download"
    elif bool(match(r"https?:\/\/clk\.sh\S+", link)):
        # clk.sh redirects to clksz.com — follow it first
        blink = await shorter(link)
    elif bool(match(r"https?:\/\/(www\.)?gofile\.io\/(d|download)\/\S+", link)):
        return await gofile(link)
    elif bool(match(r"https?:\/\/(1drv\.ms|onedrive\.live\.com|sharepoint\.com)\S+", link)):
        return await onedrive(link)
    elif "drive.google.com" in link:
        return await to_thread(get_dl, link, True)

    # DDL Links
    elif bool(match(r"https?:\/\/try2link\.\S+", link)):
        blink = await try2link(link)
    elif bool(match(r"https?:\/\/(gyanilinks|gtlinks)\.\S+", link)):
        blink = await gyanilinks(link)
    elif bool(match(r"https?:\/\/earnlinks\.\S+", link)):
        blink = await earnlinks(link)
    elif bool(match(r"https?:\/\/(mvurl\.site|liteurl\.in)\S+", link)):
        blink = await itilink(link)
    elif bool(match(r"https?:\/\/(aylink\.co|ay\.live)\S+", link)):
        blink = await aylink(link)
    elif bool(match(r"https?:\/\/(cpmlink\.(co|pro)|cpm\.link)\S+", link)):
        blink = await cpmlink(link)
    elif bool(match(r"https?:\/\/(boost\.ink|mboost\.me|bst\.gg|booo\.st)\S+", link)):
        blink = await boost(link)
    elif bool(match(r"https?:\/\/(shrinkme\.click|shrinkme\.io)\S+", link)):
        blink = await shrinkme(link)
    elif bool(match(r"https?:\/\/(shortxlinks\.(in|com))\S+", link)):
        blink = await shortxlinks(link)
    elif bool(match(r"https?:\/\/(srnky\.com|clksz\.com|oii\.la)\S+", link)):
        blink = await srnky(link)
    elif bool(
        match(r"https?:\/\/(?:vplink|vplinks)\.in\S*", link)
    ):
        blink = await vplink(link)
    elif bool(match(r"https?:\/\/(?:www\.)?arolinks\.com\S*", link)):
        blink = await arolinks(link)
    elif bool(match(r"https?:\/\/(?:antibypass|avbypassbot)\.koyeb\.app\S*", link)):
        blink = await antibypass(link)
    elif bool(match(r"https?:\/\/(www\.)?gplinks\.(co|in)\S*", link)):
        blink = await gplinks(link)
    elif bool(match(r"https?:\/\/ouo\.\S+", link)):
        blink = await ouo(link)
    elif bool(match(r"https?:\/\/(shareus|shrs)\.\S+", link)):
        blink = await shareus(link)
    elif bool(match(r"https?:\/\/(.+\.)?dropbox\.\S+", link)):
        blink = await dropbox(link)
    elif bool(match(r"https?:\/\/(linkvertise|link-to|lootlinks|lootlabs|linkvertised|lv-linkvertise|direct-link)\.\S+", link)):
        blink = await linkvertise(link)
    elif bool(match(r"https?:\/\/rslinks\.\S+", link)):
        blink = await rslinks(link)
    elif bool(match(r"https?:\/\/(?:www\.)?buzzheavier\.com\/\S+", link)):
        blink = await buzzheavier(link)
    elif bool(match(r"https?:\/\/(?:www\.)?vikingfile\.com\/f\/\S+", link)):
        blink = await vikingfile(link)
    elif bool(match(r"https?:\/\/(?:www\.)?extralink\.cc\/file\/\S+", link)):
        blink = await extralink(link)
    elif bool(match(r"https?:\/\/links\.linkshub\.fun\/view\/\S+", link)):
        return await linkshub(link)
    elif bool(match(r"https?:\/\/(?:www\.)?katlinks\.in\/archives\/\S+", link)):
        return await katlinks(link)
    elif bool(match(r"https?:\/\/(?:www\.)?hubcdn\.(?:club|wiki)\/file\/\S+", link)):
        blink = await hubcdn(link)
    elif bool(match(r"https?:\/\/(?:www\.)?vcloud\.(?:fit|beer)\/\S+", link)):
        blink = await vcloud(link)
    elif bool(match(r"https?:\/\/(bit\.ly|tinyurl\.com|(.+\.)short\.\S+|shorturl\.at|t\.ly)\S*", link)):
        blink = await shorter(link)
    elif bool(match(r"https?:\/\/(?:link\.)?xdmovies\.wtf\/download\/\S+", link, flags=2)):
        blink = await xdmovies(link)
    elif bool(match(r"https?:\/\/appurl\.\S+", link)):
        blink = await appurl(link)
    elif bool(match(r"https?:\/\/surl\.\S+", link)):
        blink = await surl(link)
    elif bool(match(r"https?:\/\/thinfi\.\S+", link)):
        blink = await thinfi(link)
    elif bool(match(r"https?:\/\/justpaste\.\S+", link)):
        blink = await justpaste(link)
    elif bool(match(r"https?:\/\/linksxyz\.\S+", link)):
        blink = await linksxyz(link)

    # ── File hosters that return direct links ─────────────────────────────────
    elif bool(match(r"https?:\/\/(www\.)?streamtape\.\S+", link)):
        return await streamtape(link)
    elif bool(match(r"https?:\/\/(wetransfer\.com|we\.tl)\S+", link)):
        return await wetransfer(link)
    elif bool(match(r"https?:\/\/(www\.)?filecrypt\.(co|cc)\S+", link)):
        return await filecrypt(link)
    elif bool(match(r"https?:\/\/(www\.)?krakenfiles\.com\S+", link)):
        return await krakenfiles(link)
    elif bool(match(r"https?:\/\/.*1fichier\.com\S*", link)):
        return await fichier(link)

    # DL Sites
    elif bool(match(r"https?:\/\/(www\.)?dotflix\.store\/share\S+", link)):
        return await dotflix(link)
    elif bool(match(r"https?:\/\/(www\.)?dtflix\.ink\/share\S+", link)):
        return await dotflix(link)
    elif bool(match(r"https?:\/\/(cloud|short)\.azonahub\.biz\S+", link)):
        return await toxcloud(link)
    elif bool(match(r"https?:\/\/(new\d+\.)?eonmovies\.\S+\/dl\/\S+", link)):
        blink = await eonmovies(link)
    elif bool(match(r"https?:\/\/(new\d+\.)?eonmovies\.\S+\/links\/\S+", link)):
        blink = await eonmovies(link)
    elif bool(match(r"https?:\/\/nexdrive\.fit\S+", link)):
        return await nexdrive(link)
    elif bool(match(r"https?:\/\/(www\.)?hblinks\.lol\S+", link)):
        return await hblinks(link)
    elif bool(match(r"https?:\/\/(.+\.)?cinevood\.\S+", link)):
        return await cinevood(link)
    elif bool(match(r"https?:\/\/(?:.+\.)?hdstream4u\.\S+", link)):
        return await hdstream4u(link)
    elif bool(match(r"https?:\/\/.+\.hdhub4u\.\S+|https?:\/\/hdhub4u\.\S+", link)):
        return await hdhub4u(link)

    elif bool(match(r"https?:\/\/(?:[a-z0-9-]+\.)?extraflix\.mobi\S+", link, flags=2)):
        return await extraflix(link)

    elif bool(match(r"https?:\/\/(?:[a-z0-9-]+\.)?bollyflix\.(?:gd|in|com)\S+", link, flags=2)):
        return await bollyflix(link)

    elif bool(match(r"https?:\/\/(?:[a-z0-9-]+\.)?hdwebmovies\.live\S+", link, flags=2)):
        return await hdwebmovies(link)

    elif bool(match(r"https?:\/\/(?:[a-z0-9-]+\.)?filmyfly\.(?:army|io|in|com)\S+", link, flags=2)):
        return await filmyfly(link)
    elif bool(match(r"https?:\/\/(?:www\.)?filmyfiy\.mov\/\S+", link, flags=2)):
        return await filmyfly(link)
    elif bool(match(r"https?:\/\/(?:www\.)?filmycab\.fyi\/\S+", link, flags=2)):
        return await filmyfly(link)

    elif bool(match(r"https?:\/\/4khdhub\.\S+", link)):
        return await fourkhdhub(link)

    elif bool(match(r"https?:\/\/greenmotors\.club\S*", link)):
        return await greenmotors(link)
    elif bool(match(r"https?:\/\/kayoanime\.\S+", link)):
        return await kayoanime(link)
    elif bool(match(r"https?:\/\/toonworld4all\.\S+", link)):
        return await toonworld4all(link)
    elif bool(match(r"https?:\/\/archive\.toonworld4all\.\S+\/(redirect|verify)\/\S+", link)):
        return await tw4all_redirect(link)
    elif bool(match(r"https?:\/\/skymovieshd\.\S+", link)):
        return await skymovieshd(link)
    elif bool(match(r"https?:\/\/.+\.sharespark\.\S+", link)):
        return await sharespark(link)
    elif bool(match(r"https?:\/\/.+\.1tamilmv\.\S+", link)):
        return await tamilmv(link)

    # DL Links
    elif bool(match(r"https?:\/\/hubcloud\.\S+", link)):
        return await hubcloud(link)
    elif bool(match(r"https?:\/\/hubdrive\.\S+", link)):
        return await drivescript(link, Config.HUBDRIVE_CRYPT, "HubDrive")
    elif bool(match(r"https?:\/\/katdrive\.\S+", link)):
        return await drivescript(link, Config.KATDRIVE_CRYPT, "KatDrive")
    elif bool(match(r"https?:\/\/drivefire\.\S+", link)):
        return await drivescript(link, Config.DRIVEFIRE_CRYPT, "DriveFire")
    elif bool(match(r"https?:\/\/sharer\.\S+", link)):
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
    elif bool(match(r"https?:\/\/.+\.technicalatg\.\S+", link)):
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
