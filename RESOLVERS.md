# Resolver Flow Reference

How each bypass resolver works internally. For live status and supported domains see [README.md](README.md).

---

## Shorteners

**Referer trick** — `earnlinks.in`, `shrinkme.click` and similar sites only serve the download form to visitors arriving from a specific referrer domain. Sending the correct `Referer` header bypasses the ad redirect entirely and loads the form directly.

**learn_more.php chain** (`vplink.in`, `arolinks.com`) — both sites run on the same platform. The full partner chain (CDP-spied on 08-10-2026) is: `vplink → techmint/studyinsurances/studyeducations → article1 → techmint/learn_more.php → techmint/studyeducations?educationsuniversities → article2 → bcsakhi.in/educatestudies/learn_more.php (×2) → vplink`. The bcsakhi `learn_more.php` redirects back to vplink which then serves the go-link form. However, Cloudflare Rocket Loader on the final vplink page gates the unlock JS — `cf_clearance` can only be obtained by executing the CF bot-score challenge in a real browser. The partner chain itself is fully replicated via HTTP but vplink serves "Please Wait" without `cf_clearance`. Both resolvers are broken as of 08-10-2026.

**AntiBypass redirect** (`antibypass.koyeb.app`) — the page serves a JavaScript `let finalUrl = "..."` variable after authenticating with a `vplink.in` referer. The resolver extracts this variable with a regex and returns it directly, avoiding any browser JS execution.

**wpSafeLink chain** (`shortxlinks.in`) — A two-stage WordPress plugin chain through `thetechhint.in` and `distancedata.in`. Each stage POSTs a signed `newwpsafelink` token, waits the server-enforced minimum timer (~15 s), then follows a `linkr` redirect to the next stage. Each redirect domain is validated against a known trusted-domain list to catch chain changes early.

**adLinkFly + Turnstile** (`srnky.com`, `clksz.com`, `oii.la`) — Cloudflare Turnstile gates the ad form. The bot solves it via [Peak.fo](https://peak.fo), posts to `advertisingcamps.com`, registers the ad visit on `loanbixby.com`, then posts back to the shortener to receive the signed `ad_form_data` blob for the final `/links/go` call. The same proxy is bound to both the Turnstile solve and all downstream requests to avoid token–IP mismatch.

**Token flow** (`aylink.co`, `cpmlink.pro`) — These expose a `/get/tk` endpoint that issues a session key from three time-based tokens in the landing page. The bot fetches the session key then posts a fake browser interaction signal to `/links/go2` to receive the destination URL.

---

## File Hosters & DDL Index Sites

**Buzzheavier redirect** (`buzzheavier.com`) — The resolver calls the file's `/download` endpoint and extracts the final CDN URL from the `Hx-Redirect` response header.

**VikingFile Turnstile** (`vikingfile.com/f/...`) — The resolver extracts the page sitekey, solves the Turnstile challenge through Peak using the configured proxy, posts the token back to the file page, and returns the JSON `link` value.

**ExtraLink session redirect** (`extralink.cc/file/...`) — The resolver follows the file page's session redirect, waits for the server timer, then calls `/wk/<id>` with the page referer and returns the final CDN location.

**HubCDN redirect** (`hubcdn.club/file/...`, `hubcdn.wiki/file/...`) — The resolver decodes the page's `reurl` payload and returns the embedded public R2 object URL.

**VCloud token flow** (`vcloud.fit/...`, `vcloud.beer/...`) — The resolver decodes the double-base64 token URL, follows the tokenized page, and returns its signed R2 mirror.

**fastdl.zip embed** (`nexdrive.fit`) — The page links to a `fastdl.zip/embed?download=<id>` page which contains a `var reurl` JavaScript variable holding the final Google CDN URL. Extracted with regex, no JS execution needed.

**Redirect follower** (`eonmovies.click/dl/`) — A simple 302 that the bot follows one hop, resolves relative paths to the full domain, and returns the result to the checker for recursion into the appropriate bypass.

**GCloud / GDShare instant download** (`gdshare.top/download/...`, `gcloud.cyou/download/...`) — The resolver fetches the download page (following any gdshare.top → gcloud.cyou redirect), then calls the HTMX `/generate-links/` partial to extract the signed instant-download URL. A second AJAX call to `<instant_url>?ajax=1` returns `{"success": true, "download_url": "..."}` — a direct Google CDN link. If the file owner has disabled the instant link, the resolver falls back to `POST /filepress/`. The vault-based mirrors (xCloud, GoFile, Buzzheavier) require a Cloudflare Turnstile solve at `/download/resolve/` and cannot be resolved via plain HTTP.

---

## Scraper Sites

**Linkshub mirrors** (`links.linkshub.fun/view/...`) — The scraper extracts DriveHub and HubDrive mirrors from a Linkshub view page.

**KatLinks mirrors** (`katlinks.in/archives/...`) — The scraper extracts Send, GDFlix, FilePress/Filebee, Gkyfilehost, and related download mirrors from KatLinks WordPress posts.

**XDMovie redirect** (`link.xdmovies.wtf`) — The wrapper redirect is followed, then the downstream `latestnewsonline.sbs` request is sent through the Peak-backed Turnstile client with the configured proxy. The current downstream response remains Cloudflare-protected after solving, so no false direct-link result is returned.
