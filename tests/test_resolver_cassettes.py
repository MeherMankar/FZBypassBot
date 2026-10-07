import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from resolver_cassette import ResolverCassette

from FZBypass.bypass.ddl import (
    _extract_vplink_partner_url,
    _is_manual_partner_ad_gate,
    _is_partner_chain_shortener_url,
    arolinks,
    buzzheavier,
    extralink,
    hubcdn,
    mediafire,
    vcloud,
    xdmovies,
    vikingfile,
)
from FZBypass.bypass.scrape import (
    bollyflix,
    extraflix,
    filmyfly,
    hdwebmovies,
    katlinks,
    linkshub,
)
from FZBypass.bypass.dlinks import gdflix
from FZBypass.core.exceptions import DDLException, ResolverStepError

FIXTURES = Path(__file__).parent / "fixtures"


class TestMediaFireCassette(unittest.IsolatedAsyncioTestCase):
    async def test_replays_recorded_flow_offline(self):
        cassette = ResolverCassette.load(FIXTURES / "mediafire" / "basic.json")
        with patch("FZBypass.bypass.ddl.cf.get", side_effect=cassette.get):
            result = await mediafire(cassette.fixture["input_url"])

        self.assertEqual(result, cassette.fixture["expected_result"])
        cassette.assert_complete()

    async def test_parse_failure_names_the_failed_step(self):
        cassette = ResolverCassette.load(FIXTURES / "mediafire" / "basic.json")
        cassette._exchanges[1]["response"]["body_text"] = "<html>changed form</html>"
        with (
            patch("FZBypass.bypass.ddl.cf.get", side_effect=cassette.get),
            self.assertRaises(ResolverStepError) as raised,
        ):
            await mediafire(cassette.fixture["input_url"])

        self.assertEqual(raised.exception.resolver, "MediaFire")
        self.assertEqual(raised.exception.step, "extract-download-link")


class TestPartnerChainUrl(unittest.TestCase):
    def test_detects_manual_partner_ad_gate(self):
        html = """
        <strong>You are currently on step <span>1/3</span>.</strong>
        <p>CLICK ANY IMAGE &amp; Wait 15 Seconds to GET LINK</p>
        <p>Click Image &amp; Wait &amp; Come back this page to Get Link</p>
        """

        self.assertTrue(_is_manual_partner_ad_gate(html))

    def test_does_not_flag_regular_partner_article(self):
        html = "<html><body><h1>Education Loan Guide</h1><p>Read more</p></body></html>"

        self.assertFalse(_is_manual_partner_ad_gate(html))

    def test_extracts_arolinks_partner_cta(self):
        html = (
            '<a href="https://techmint.in/studyeducations/'
            '?universtityeducations=IENOLw&amp;uiso=186442&amp;st=1">'
            "click here</a>"
        )

        result = _extract_vplink_partner_url(
            html,
            "https://arolinks.com/IENOLw",
        )

        self.assertEqual(
            result,
            "https://techmint.in/studyeducations/"
            "?universtityeducations=IENOLw&uiso=186442&st=1",
        )

    def test_extracts_escaped_javascript_partner_redirect(self):
        html = r'<script>window.location.href = "https:\/\/partner.example\/start?code=1";</script>'

        result = _extract_vplink_partner_url(html, "https://vplink.in/tu8au")

        self.assertEqual(result, "https://partner.example/start?code=1")

    def test_ignores_links_back_to_vplink(self):
        html = '<a href="https://vplink.in/other">click here</a>'

        self.assertIsNone(_extract_vplink_partner_url(html, "https://vplink.in/tu8au"))

    def test_ignores_links_back_to_arolinks(self):
        html = '<a href="https://arolinks.com/other">click here</a>'

        self.assertIsNone(
            _extract_vplink_partner_url(html, "https://arolinks.com/IENOLw")
        )

    def test_recognizes_arolinks_as_a_final_chain_destination(self):
        self.assertTrue(_is_partner_chain_shortener_url("https://arolinks.com/IENOLw"))
        self.assertTrue(_is_partner_chain_shortener_url("https://vplinks.in/tu8au"))
        self.assertFalse(_is_partner_chain_shortener_url("https://techmint.in/article"))


class TestGDFlixCassette(unittest.IsolatedAsyncioTestCase):
    async def test_replays_redirected_file_and_extracts_dynamic_links(self):
        cassette = ResolverCassette.load(FIXTURES / "gdflix" / "file.json")
        test_case = self

        class FakeResponse:
            def __init__(self, response: dict):
                self.status_code = response["status"]
                self.url = response["url"]
                self.text = response["body_text"]

        class FakeSession:
            def get(self, url, **kwargs):
                exchange = cassette.fixture["exchanges"][0]
                test_case.assertEqual(url, exchange["request"]["url"])
                test_case.assertEqual(kwargs["allow_redirects"], True)
                cassette._position += 1
                return FakeResponse(exchange["response"])

        with patch("FZBypass.bypass.dlinks.cSession", return_value=FakeSession()):
            result = await gdflix(cassette.fixture["input_url"])

        self.assertIn("Instant DL", result)
        self.assertIn("Cloud Download", result)
        self.assertIn("GoFile", result)
        self.assertIn("Telegram File", result)
        self.assertIn("Download", result)
        cassette.assert_complete()


class TestArolinksResolver(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_final_gt_link_after_partner_chain(self):
        def response(url, text=""):
            return SimpleNamespace(
                status_code=200,
                text=text,
                content=text.encode(),
                url=url,
            )

        short_url = "https://arolinks.com/NqtedK"
        session = MagicMock()
        session.cookies = MagicMock()
        session.cookies.__iter__.return_value = iter(())
        session.cookies.get.return_value = None
        session.get.side_effect = [
            response(short_url, '<a href="https://techmint.in/landing">go</a>'),
            response(
                "https://techmint.in/landing",
                '<script>window.location.href = "https://techmint.in/article-1";</script>',
            ),
            response("https://techmint.in/article-1"),
            response(
                "https://techmint.in/readmore/",
            ),
            response(
                "https://techmint.in/studyeducations/?educationsscholorships=NqtedK&pgtr=10&st=2",
            ),
            response("https://techmint.in/article-2"),
            response(
                "https://onlinewish.in/studyblogs/educationsunivrsties/?univrsityinsurances=NqtedK",
                '<script>window.location.href = "https://onlinewish.in/article-3";</script>',
            ),
            response("https://onlinewish.in/article-3"),
            response(
                "https://onlinewish.in/readmore/",
            ),
            response(
                short_url,
                '<a id="gt-link" href="https://t.me/example?start=token">Get</a>',
            ),
        ]

        with (
            patch("requests.Session", return_value=session),
            patch("cloudscraper.create_scraper", return_value=session),
        ):
            result = await arolinks(short_url)

        self.assertEqual(result, "https://t.me/example?start=token")
        self.assertEqual(session.get.call_count, 10)

    async def test_resolves_partner_chain_to_telegram_start_link(self):
        def response(url, text="", content=None):
            return SimpleNamespace(
                status_code=200,
                text=text,
                content=content if content is not None else text.encode(),
                url=url,
            )

        final_url = "https://t.me/Mr_ssobot?start=BQADAQAD1BoAAgX02URtHTiz-7lRSBYE"
        short_url = "https://arolinks.com/NqtedK"
        session = MagicMock()
        session.cookies = MagicMock()
        session.cookies.__iter__.return_value = iter(())
        session.cookies.get.return_value = None
        session.get.side_effect = [
            response(short_url, '<a href="https://techmint.in/landing">go</a>'),
            response(
                "https://techmint.in/landing",
                r'<script>window.location.href = "https:\/\/techmint.in\/article-1";</script>',
            ),
            response("https://techmint.in/article-1"),
            response(
                "https://techmint.in/studyeducations/?educationsuniversities=NqtedK",
                '<script>window.location.href = "https://techmint.in/article-2";</script>',
            ),
            response("https://techmint.in/article-2"),
            response(
                "https://onlinewish.in/studyblogs/educationsunivrsties/?univrsityinsurances=NqtedK",
                '<script>window.location.href = "https://onlinewish.in/article-3";</script>',
            ),
            response("https://onlinewish.in/article-3"),
            response(
                "https://onlinewish.in/studyblogs/learn_more.php",
                f'<script>window.location.href = "{short_url}";</script>',
            ),
            response(
                short_url,
                '<form id="go-link" action="/links/go">'
                '<input name="token" value="test-token"></form>',
            ),
        ]
        session.post.return_value = response(
            "https://arolinks.com/links/go",
            content=f'{{"url":"{final_url}"}}'.encode(),
        )

        with (
            patch("requests.Session", return_value=session),
            patch("cloudscraper.create_scraper", return_value=session),
            patch("time.sleep"),
        ):
            result = await arolinks(short_url)

        self.assertEqual(result, final_url)
        session.post.assert_called_once()


class TestExtraFlixResolver(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_linkshub_drivehub_mirrors(self):
        def response(html):
            return SimpleNamespace(text=html, status_code=200)

        movie_page = """
        <title>Ten Hours (2025) - Extraflix</title>
        <a href="https://links.linkshub.fun/view/480">Download Link</a>
        <a href="https://links.linkshub.fun/view/720">Download Link</a>
        """
        mirror_page_480 = """
        <title>Ten.Hours.480p.mkv - 353 MB</title>
        <a href="https://new1.drivehub.dad/file/3629460">1</a>
        <a href="https://hubdrive.pics/file/1906381367">2</a>
        """
        mirror_page_720 = """
        <title>Ten.Hours.720p.mkv - 724 MB</title>
        <a href="https://new1.drivehub.dad/file/2387617">1</a>
        """

        with patch(
            "FZBypass.bypass.scrape.cf.get",
            side_effect=[
                response(movie_page),
                response(mirror_page_480),
                response(mirror_page_720),
            ],
        ):
            result = await extraflix(
                "https://e8.extraflix.mobi/ten-hours-2025-hindi-tamil/"
            )

        self.assertIn("Ten.Hours.480p.mkv", result)
        self.assertIn("https://new1.drivehub.dad/file/3629460", result)
        self.assertIn("https://hubdrive.pics/file/1906381367", result)
        self.assertIn("https://new1.drivehub.dad/file/2387617", result)


class TestBollyflixResolver(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_grouped_ddl_links(self):
        page = """
        <title>Naruto Shippuden - Bollyflix</title>
        <article>
          <h3>480p Quality</h3>
          <a href="https://hubcloud.one/file/480">HubCloud</a>
          <h3>720p Quality</h3>
          <a href="https://new1.drivehub.dad/file/720">DriveHub</a>
          <h3>1080p Quality</h3>
          <a href="https://gdflix.dev/file/1080">GDFlix</a>
          <a href="https://ads.example/skip">Ad</a>
        </article>
        """
        with patch(
            "FZBypass.bypass.scrape.cf.get",
            return_value=SimpleNamespace(text=page, status_code=200),
        ):
            result = await bollyflix(
                "https://new.bollyflix.gd/naruto-shippuden-multi-audio-hindi-english-japanese-malayalam-tamil-web-series/"
            )

        self.assertIn("480p Quality", result)
        self.assertIn("https://hubcloud.one/file/480", result)
        self.assertIn("https://new1.drivehub.dad/file/720", result)
        self.assertIn("https://gdflix.dev/file/1080", result)
        self.assertNotIn("ads.example", result)


class TestHDWebMoviesResolver(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_quality_and_drive_pack_episode_links(self):
        page = """
        <title>Politricks Series - HDWebMovies</title>
        <article>
          <a href="https://tmbcloud.dev/download/FO6UBD">DOWNLOAD 480p</a>
          <a href="https://tmbcloud.dev/drivepacks.php?code=80628A">DOWNLOAD 480p</a>
        </article>
        """
        pack_page = """
        <a href="https://tmbcloud.lol/download/RFBECQ">Episode 1</a>
        <a href="https://tmbcloud.lol/download/O3NDY5">Episode 2</a>
        """
        with patch(
            "FZBypass.bypass.scrape.cf.get",
            side_effect=[
                SimpleNamespace(text=page, status_code=200),
                SimpleNamespace(text=pack_page, status_code=200),
            ],
        ):
            result = await hdwebmovies(
                "https://ww4.hdwebmovies.live/movies/politricks-series-all-episodes-download-watch-online-fridaay-web-dl/"
            )

        self.assertIn("https://tmbcloud.dev/download/FO6UBD", result)
        self.assertIn("https://tmbcloud.lol/download/RFBECQ", result)
        self.assertIn("https://tmbcloud.lol/download/O3NDY5", result)


class TestFilmyFlyResolver(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_linkmake_filesdl_links(self):
        filmy_page = """
        <title>Spider-Man - Brand New Day - FilmyFly</title>
        <a href="https://linkmake.in/view/DllvWnY0bA">Download</a>
        """
        linkmake_page = """
        <a href="https://new1.filesdl.in/cloud/YVp3eilODM">Download 510Mb {480p-HEVC}</a>
        <a href="https://new1.filesdl.in/drive/bpBOXHLg26">Download 1.1Gb {720p-HEVC 10bit}</a>
        <a href="https://ads.example/skip">Ad</a>
        """
        with patch(
            "FZBypass.bypass.scrape.cf.get",
            side_effect=[
                SimpleNamespace(text=filmy_page, status_code=200),
                SimpleNamespace(text=linkmake_page, status_code=200),
            ],
        ):
            result = await filmyfly(
                "https://filmyfly.army/movie/7449/SpiderMan-Brand-New-Day-2026-Hindi-English-Dual-Audio-MCU-Hollywood-Movie-HD-ESub.html"
            )

        self.assertIn("https://new1.filesdl.in/cloud/YVp3eilODM", result)
        self.assertIn("https://new1.filesdl.in/drive/bpBOXHLg26", result)
        self.assertNotIn("ads.example", result)

    async def test_filmyfiy_uses_same_linkmake_flow(self):
        def response(html):
            return SimpleNamespace(text=html, status_code=200)

        with patch(
            "FZBypass.bypass.scrape.cf.get",
            side_effect=[
                response(
                    '<title>Pechi 2024 - FilmyFiy</title>'
                    '<a href="https://linkmake.in/view/filmyfiy-test">Download</a>'
                ),
                response(
                    '<a href="https://new1.filesdl.in/cloud/pechi480">480p</a>'
                ),
            ],
        ):
            result = await filmyfly(
                "https://www.filmyfiy.mov/page-download/5620/"
                "Pechi-2024-Hindi-Tamil-Dual-Audio-UnCut-South-Movie-HD-ESub.html"
            )

        self.assertIn("https://new1.filesdl.in/cloud/pechi480", result)

    async def test_filmycab_uses_same_linkmake_flow(self):
        with patch(
            "FZBypass.bypass.scrape.cf.get",
            side_effect=[
                SimpleNamespace(
                    text=(
                        "<title>Dil Dhadak Dhadak - FilmyCab</title>"
                        '<a href="https://linkmake.in/view/filmycab-test">Download</a>'
                    ),
                    status_code=200,
                ),
                SimpleNamespace(
                    text=(
                        '<a href="https://new1.filesdl.in/cloud/dil-dhadak">'
                        "480p</a>"
                    ),
                    status_code=200,
                ),
            ],
        ):
            result = await filmyfly(
                "https://filmycab.fyi/page-download/4755/"
                "Dil-Dhadak-Dhadak-Padi-Padi-Leche-Manasu-2018-Dual-Audio-"
                "Hindi-Telugu-Full-Movie-HD-ESub.html"
            )

        self.assertIn("https://new1.filesdl.in/cloud/dil-dhadak", result)


class TestXDMovieResolver(unittest.IsolatedAsyncioTestCase):
    async def test_uses_peak_turnstile_client_for_downstream(self):
        response = SimpleNamespace(
            headers={"location": "https://latestnewsonline.sbs/r/yzQf2hDt"}
        )
        solved = SimpleNamespace(
            url="https://cdn.example/video.mp4",
            status_code=200,
            text="video response",
        )
        with (
            patch("FZBypass.bypass.ddl.cf.get", return_value=response),
            patch("FZBypass.bypass.ddl.Config.PEAK_API_KEY", "pk_test"),
            patch(
                "FZBypass.bypass.ddl.Config.next_proxy",
                return_value="http://proxy.example:8080",
            ),
            patch("FZBypass.bypass.ddl.ts.get", return_value=solved) as peak_get,
        ):
            result = await xdmovies(
                "https://link.xdmovies.wtf/download/ADPZ7A-ND73oxfKxV9oez6RuXq2K5PxdScbt1jCPS9I"
            )

        self.assertEqual(result, "https://cdn.example/video.mp4")
        peak_get.assert_awaited_once_with(
            "https://latestnewsonline.sbs/r/yzQf2hDt",
            allow_redirects=True,
            proxy="http://proxy.example:8080",
        )

    async def test_reports_downstream_cloudflare_block(self):
        response = SimpleNamespace(
            headers={"location": "https://latestnewsonline.sbs/r/yzQf2hDt"}
        )
        with (
            patch("FZBypass.bypass.ddl.cf.get", return_value=response),
            patch("FZBypass.bypass.ddl.Config.PEAK_API_KEY", ""),
            self.assertRaisesRegex(
                DDLException,
                "requires PEAK_API_KEY",
            ),
        ):
            await xdmovies(
                "https://link.xdmovies.wtf/download/ADPZ7A-ND73oxfKxV9oez6RuXq2K5PxdScbt1jCPS9I"
            )


class TestBuzzheavierResolver(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_hx_redirect(self):
        response = SimpleNamespace(
            headers={
                "Hx-Redirect": (
                    "https://cdn.buzzheavier.example/file.zip"
                )
            }
        )
        with patch(
            "FZBypass.bypass.ddl.http.get",
            return_value=response,
        ) as get:
            result = await buzzheavier("https://buzzheavier.com/9rn6r01g0vbf")

        self.assertEqual(result, "https://cdn.buzzheavier.example/file.zip")
        get.assert_awaited_once()


class TestVikingFileResolver(unittest.IsolatedAsyncioTestCase):
    async def test_solves_turnstile_and_extracts_link(self):
        class FakeResponse:
            url = "https://vik1ngfile.site/f/jYsngeyFfb"
            text = "sitekey: '0x4AAAAAAAgbsMNBuk2d3Qp6'"

            def raise_for_status(self):
                return None

            def json(self):
                return {"link": "https://cdn.example/file.zip"}

        class FakeSession:
            def __init__(self):
                self.proxies = {}
                self.headers = {}
                self.calls = 0

            def get(self, url, timeout):
                return FakeResponse()

            def post(self, url, **kwargs):
                self.calls += 1
                response = FakeResponse()
                if self.calls == 1:
                    response.json = lambda: {
                        "success": True,
                        "data": {"token": "turnstile-token"},
                    }
                return response

        with (
            patch("FZBypass.bypass.ddl.Config.PEAK_API_KEY", "pk_test"),
            patch(
                "FZBypass.bypass.ddl.Config.next_proxy",
                return_value="http://proxy.example:8080",
            ),
            patch("FZBypass.bypass.ddl.Session", FakeSession),
        ):
            result = await vikingfile("https://vikingfile.com/f/jYsngeyFfb")

        self.assertEqual(result, "https://cdn.example/file.zip")


class TestExtraLinkResolver(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_session_bound_wk_redirect(self):
        class FakeResponse:
            def __init__(self, page_url, headers=None):
                self.url = page_url
                self.headers = headers or {}

            def raise_for_status(self):
                return None

        class FakeSession:
            def __init__(self):
                self.headers = {}
                self.calls = []

            def get(self, request_url, **kwargs):
                self.calls.append((request_url, kwargs))
                if len(self.calls) == 1:
                    return FakeResponse(
                        "https://extralink.cc/download/?id=server-id"
                    )
                return FakeResponse(
                    "https://extralink.cc/wk/server-id",
                    {"Location": "https://cdn.example/file.zip"},
                )

        with patch("FZBypass.bypass.ddl.Session", FakeSession):
            result = await extralink(
                "https://extralink.cc/file/AbuODpxJSw0n37q"
            )

        self.assertEqual(result, "https://cdn.example/file.zip")


class TestLinkshubResolver(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_drivehub_mirrors(self):
        response = SimpleNamespace(
            text="""
            <title>Reacher.S04.zip - 11.82 GB</title>
            <a href="https://new1.drivehub.dad/file/2914761">DriveHub</a>
            <a href="https://hubdrive.pics/file/5389514508">HubDrive</a>
            """
        )
        with patch("FZBypass.bypass.scrape.cf.get", return_value=response):
            result = await linkshub(
                "https://links.linkshub.fun/view/1N6DOzQEHb"
            )

        self.assertIn("https://new1.drivehub.dad/file/2914761", result)
        self.assertIn("https://hubdrive.pics/file/5389514508", result)


class TestKatLinksResolver(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_download_mirrors(self):
        response = SimpleNamespace(
            text="""
            <article>
              <h1 class="entry-title">Blossom (Season 1) 480p Pack</h1>
              <a href="https://send.now/3ls5sfv49ao">Cloud [Send]</a>
              <a href="https://gdflix.dev/file/kr1LAa7Z2f4bjOr">G-Drive [Gdflix]</a>
              <a href="https://filebee.xyz/file/69e0c679426bf3dc7a3f2bfc">G-Drive [Filepress]</a>
              <a href="https://gkyfilehost.site/file/5856144411">G-Drive [Gkyfilehost]</a>
            </article>
            """
        )
        with patch("FZBypass.bypass.scrape.cf.get", return_value=response):
            result = await katlinks("https://katlinks.in/archives/80838")

        self.assertIn("https://send.now/3ls5sfv49ao", result)
        self.assertIn("https://gdflix.dev/file/kr1LAa7Z2f4bjOr", result)
        self.assertIn("https://filebee.xyz/file/69e0c679426bf3dc7a3f2bfc", result)
        self.assertIn("https://gkyfilehost.site/file/5856144411", result)


class TestHubCDNResolver(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_encoded_r2_destination(self):
        response = SimpleNamespace(
            text=(
                'var reurl = "https://inventoryidea.com/?r='
                'aHR0cHM6Ly9odWJjZG4uY2x1Yi9kbC8/bGluaz1odHRwczovL3B1Yi1jMGJjN2Q2OGJlMTY0NDA1ODk0NDY4YWFlOTVjZmY4Zi5yMi5kZXYvZjVmOWYxMGIwNjgzNzVhMDYwYTU5ZDkzOTM2ZjQyYmY=";'
            )
        )
        with patch("FZBypass.bypass.ddl.cf.get", return_value=response):
            result = await hubcdn(
                "https://hubcdn.club/file/8FkCRe2AAUFgEb8VJgntdxW7V"
            )

        self.assertEqual(
            result,
            "https://pub-c0bc7d68be164405894468aae95cff8f.r2.dev/"
            "f5f9f10b068375a060a59d93936f42bf",
        )


class TestVCloudResolver(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_double_encoded_token_to_r2(self):
        import base64

        token_url = "https://vcloud.beer/-cowx63waadr3xw?token=abc"
        encoded = base64.b64encode(
            base64.b64encode(token_url.encode())
        ).decode()
        first = SimpleNamespace(
            text=f"var url = atob(atob('{encoded}'));"
        )
        second = SimpleNamespace(
            text=(
                '<a href="https://pub.example.r2.dev/file?token=abc">'
                "Download</a>"
            )
        )
        with patch(
            "FZBypass.bypass.ddl.cf.get",
            side_effect=[first, second],
        ):
            result = await vcloud("https://vcloud.fit/-cowx63waadr3xw")

        self.assertEqual(
            result,
            "https://pub.example.r2.dev/file?token=abc",
        )


if __name__ == "__main__":
    unittest.main()
