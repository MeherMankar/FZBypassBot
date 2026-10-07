import os
import unittest
from asyncio import FIRST_COMPLETED, create_task, sleep, wait
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("OWNER_ID", "1")

from wzgram.enums import MessageEntityType

from FZBypass import Config
from FZBypass.bypass.checker import direct_link_checker, is_excep_link, is_share_link
from FZBypass.bypass.dlinks import hubcloud
from FZBypass.bypass.scrape import hdhub4u
from FZBypass.core.bot_utils import auto_bypass
from FZBypass.core.exceptions import DDLException
from FZBypass.handlers.bypass import bypass_check, extract_inline_link
from FZBypass.core.networking.exceptions import NetworkTimeout


class TestMessageRegressionCases(unittest.IsolatedAsyncioTestCase):
    async def test_buzzheavier_uses_resolver(self):
        link = "https://buzzheavier.com/9rn6r01g0vbf"
        with patch(
            "FZBypass.bypass.checker.buzzheavier",
            new=AsyncMock(return_value="https://cdn.example/file.zip"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://cdn.example/file.zip")
        resolver.assert_awaited_once_with(link)

    async def test_filmyfiy_uses_filmyfly_scraper(self):
        link = (
            "https://www.filmyfiy.mov/page-download/5620/"
            "Pechi-2024-Hindi-Tamil-Dual-Audio-UnCut-South-Movie-HD-ESub.html"
        )
        with patch(
            "FZBypass.bypass.checker.filmyfly",
            new=AsyncMock(return_value="<b>Download Links</b>"),
        ) as scraper:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "<b>Download Links</b>")
        scraper.assert_awaited_once_with(link)

    async def test_vikingfile_uses_resolver(self):
        link = "https://vikingfile.com/f/jYsngeyFfb"
        with patch(
            "FZBypass.bypass.checker.vikingfile",
            new=AsyncMock(return_value="https://cdn.example/file.zip"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://cdn.example/file.zip")
        resolver.assert_awaited_once_with(link)

    async def test_extralink_uses_resolver(self):
        link = "https://extralink.cc/file/AbuODpxJSw0n37q"
        with patch(
            "FZBypass.bypass.checker.extralink",
            new=AsyncMock(return_value="https://cdn.example/file.zip"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://cdn.example/file.zip")
        resolver.assert_awaited_once_with(link)

    async def test_linkshub_uses_scraper(self):
        link = "https://links.linkshub.fun/view/1N6DOzQEHb"
        with patch(
            "FZBypass.bypass.checker.linkshub",
            new=AsyncMock(return_value="<b>Download Links</b>"),
        ) as scraper:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "<b>Download Links</b>")
        scraper.assert_awaited_once_with(link)

    async def test_katlinks_uses_scraper(self):
        link = "https://katlinks.in/archives/80838"
        with patch(
            "FZBypass.bypass.checker.katlinks",
            new=AsyncMock(return_value="<b>Download Links</b>"),
        ) as scraper:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "<b>Download Links</b>")
        scraper.assert_awaited_once_with(link)

    async def test_hubcdn_uses_resolver(self):
        link = "https://hubcdn.club/file/8FkCRe2AAUFgEb8VJgntdxW7V"
        with patch(
            "FZBypass.bypass.checker.hubcdn",
            new=AsyncMock(return_value="https://cdn.example/file.zip"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://cdn.example/file.zip")
        resolver.assert_awaited_once_with(link)

    async def test_vcloud_uses_resolver(self):
        link = "https://vcloud.fit/-cowx63waadr3xw"
        with patch(
            "FZBypass.bypass.checker.vcloud",
            new=AsyncMock(return_value="https://cdn.example/file.mkv"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://cdn.example/file.mkv")
        resolver.assert_awaited_once_with(link)

    async def test_r2_public_object_is_treated_as_direct_link(self):
        link = (
            "https://pub-356c896ad5f742d18f2e8f4e5b5de59a.r2.dev/"
            "f60c899cbb1e8a9209141728c3656ee7?token=1791197243339"
        )

        result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, link)

    async def test_auto_bypass_accepts_caption_url_entities(self):
        entity = SimpleNamespace(type=MessageEntityType.URL)
        message = SimpleNamespace(
            text=None,
            caption="https://example.com/file",
            entities=None,
            caption_entities=[entity],
        )
        client = SimpleNamespace(me=SimpleNamespace(username="testbot"))

        with patch.object(Config, "AUTO_BYPASS", True):
            result = await auto_bypass(None, client, message)

        self.assertTrue(result)

    async def test_bypass_command_without_entities_replies_cleanly(self):
        message = SimpleNamespace(
            reply_to_message=None,
            text="/bypass some-text",
            caption=None,
            entities=None,
            caption_entities=None,
            reply=AsyncMock(return_value="no-link-reply"),
        )
        with patch.object(Config, "AUTO_BYPASS", False):
            result = await bypass_check(None, message)

        self.assertEqual(result, "no-link-reply")
        message.reply.assert_awaited_once_with("<i>No Link Provided!</i>")

    async def test_auto_bypass_handler_processes_caption_link(self):
        entity = SimpleNamespace(type=MessageEntityType.URL, offset=0, length=24)
        wait_message = SimpleNamespace(
            edit=AsyncMock(),
            delete=AsyncMock(),
        )
        message = SimpleNamespace(
            reply_to_message=None,
            text=None,
            caption="https://example.com/file",
            entities=None,
            caption_entities=[entity],
            reply=AsyncMock(return_value=wait_message),
            from_user=SimpleNamespace(mention="Contributor", id=7),
        )
        with (
            patch.object(Config, "AUTO_BYPASS", True),
            patch(
                "FZBypass.handlers.bypass.direct_link_checker",
                new=AsyncMock(return_value="https://downloads.example/file"),
            ),
        ):
            await bypass_check(None, message)

        wait_message.edit.assert_awaited_once()
        self.assertIn(
            "https://downloads.example/file",
            wait_message.edit.await_args.args[0],
        )

    async def test_resolved_passthrough_link_is_on_own_line(self):
        link = "https://filebee.xyz/file/6ac6351169b577b115c59b38"
        text = f"/bypass {link}"
        entity = SimpleNamespace(
            type=MessageEntityType.URL,
            offset=text.index(link),
            length=len(link),
        )
        wait_message = SimpleNamespace(edit=AsyncMock(), delete=AsyncMock())
        message = SimpleNamespace(
            reply_to_message=None,
            text=text,
            caption=None,
            entities=[entity],
            caption_entities=None,
            reply=AsyncMock(return_value=wait_message),
            from_user=SimpleNamespace(mention="Contributor", id=7),
        )

        with patch(
            "FZBypass.handlers.bypass.direct_link_checker",
            new=AsyncMock(return_value=link),
        ):
            await bypass_check(None, message)

        rendered = wait_message.edit.await_args.args[0]
        self.assertIn(f"🔗 <b>Resolved Link</b>\n\n{link}", rendered)

    def test_inline_link_parser_preserves_url_case_and_trailing_letters(self):
        self.assertEqual(
            extract_inline_link("!BP https://example.com/AbC/pathbp"),
            "https://example.com/AbC/pathbp",
        )

    def test_inline_link_parser_rejects_missing_link(self):
        self.assertIsNone(extract_inline_link("!bp   "))

    async def test_google_drive_index_does_not_block_event_loop(self):
        def slow_index_call(*args):
            import time

            time.sleep(0.05)
            return "https://downloads.example/file"

        async def heartbeat():
            await sleep(0.005)

        with patch("FZBypass.bypass.checker.get_dl", side_effect=slow_index_call):
            resolver_task = create_task(
                direct_link_checker(
                    "https://drive.google.com/file/d/example-id/view",
                    onlylink=True,
                )
            )
            heartbeat_task = create_task(heartbeat())
            done, _ = await wait(
                {resolver_task, heartbeat_task},
                return_when=FIRST_COMPLETED,
            )
            self.assertIn(heartbeat_task, done)
            self.assertEqual(
                await resolver_task,
                "https://downloads.example/file",
            )

    async def test_arolinks_uses_partner_chain_resolver(self):
        with patch(
            "FZBypass.bypass.checker.arolinks",
            new=AsyncMock(return_value="https://downloads.example/file"),
        ) as resolver:
            result = await direct_link_checker(
                "https://arolinks.com/IENOLw",
                onlylink=True,
            )

        self.assertEqual(result, "https://downloads.example/file")
        resolver.assert_awaited_once_with("https://arolinks.com/IENOLw")

    async def test_extraflix_uses_scraper(self):
        with patch(
            "FZBypass.bypass.checker.extraflix",
            new=AsyncMock(return_value="https://new1.drivehub.dad/file/3629460"),
        ) as resolver:
            result = await direct_link_checker(
                "https://e8.extraflix.mobi/ten-hours-2025-hindi-tamil/",
                onlylink=True,
            )

        self.assertEqual(result, "https://new1.drivehub.dad/file/3629460")
        resolver.assert_awaited_once_with(
            "https://e8.extraflix.mobi/ten-hours-2025-hindi-tamil/"
        )

    async def test_hdwebmovies_uses_scraper(self):
        with patch(
            "FZBypass.bypass.checker.hdwebmovies",
            new=AsyncMock(return_value="https://tmbcloud.dev/download/FO6UBD"),
        ) as resolver:
            result = await direct_link_checker(
                "https://ww4.hdwebmovies.live/movies/politricks-series-all-episodes-download-watch-online-fridaay-web-dl/",
                onlylink=True,
            )

        self.assertEqual(result, "https://tmbcloud.dev/download/FO6UBD")
        resolver.assert_awaited_once_with(
            "https://ww4.hdwebmovies.live/movies/politricks-series-all-episodes-download-watch-online-fridaay-web-dl/"
        )

    async def test_filmyfly_uses_scraper(self):
        with patch(
            "FZBypass.bypass.checker.filmyfly",
            new=AsyncMock(return_value="https://new1.filesdl.in/cloud/YVp3eilODM"),
        ) as resolver:
            result = await direct_link_checker(
                "https://filmyfly.army/movie/7449/SpiderMan-Brand-New-Day-2026-Hindi-English-Dual-Audio-MCU-Hollywood-Movie-HD-ESub.html",
                onlylink=True,
            )

        self.assertEqual(result, "https://new1.filesdl.in/cloud/YVp3eilODM")
        resolver.assert_awaited_once_with(
            "https://filmyfly.army/movie/7449/SpiderMan-Brand-New-Day-2026-Hindi-English-Dual-Audio-MCU-Hollywood-Movie-HD-ESub.html"
        )

    async def test_filmycab_uses_filmyfly_scraper(self):
        link = (
            "https://filmycab.fyi/page-download/4755/"
            "Dil-Dhadak-Dhadak-Padi-Padi-Leche-Manasu-2018-Dual-Audio-"
            "Hindi-Telugu-Full-Movie-HD-ESub.html"
        )
        with patch(
            "FZBypass.bypass.checker.filmyfly",
            new=AsyncMock(return_value="https://new1.filesdl.in/cloud/dil-dhadak"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://new1.filesdl.in/cloud/dil-dhadak")
        resolver.assert_awaited_once_with(link)

    async def test_drivehub_uses_turnstile_resolver(self):
        link = "https://new1.drivehub.dad/file/6174278"
        with patch(
            "FZBypass.bypass.checker.drivehub",
            new=AsyncMock(return_value="https://drive.google.com/file/d/abc"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://drive.google.com/file/d/abc")
        resolver.assert_awaited_once_with(link)

    async def test_vifix_delegates_file_to_gdflix(self):
        link = "https://gd.vifix.site/file/a20F3BlOJonUC6F"
        with patch(
            "FZBypass.bypass.checker.gdflix",
            new=AsyncMock(return_value="The.Mentalist.S02.720p"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "The.Mentalist.S02.720p")
        resolver.assert_awaited_once_with(
            "https://new4.gdflix.io/file/a20F3BlOJonUC6F"
        )

    async def test_cyberloom_uses_resolver(self):
        link = "https://www.cyberloom.best/l/jZh74nCt"
        with patch(
            "FZBypass.bypass.checker.cyberloom",
            new=AsyncMock(return_value="https://cdn.example/file.mkv"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://cdn.example/file.mkv")
        resolver.assert_awaited_once_with(link)

    async def test_get_to_link_uses_scraper(self):
        link = "https://get-to.link/movie/?id=abc&b=1&x=2"
        with patch(
            "FZBypass.bypass.checker.gettolink",
            new=AsyncMock(return_value="<b>Movie</b><a href='https://send.now/x'>Send</a>"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertIn("https://send.now/x", result)
        resolver.assert_awaited_once_with(link)

    async def test_get_to_link_is_a_terminal_scraper_result(self):
        self.assertTrue(is_excep_link("https://get-to.link/movie/?id=abc"))

    async def test_just2earn_uses_dedicated_resolver(self):
        link = "https://just2earn.com/UyBG57VN"
        with patch(
            "FZBypass.bypass.checker.just2earn",
            new=AsyncMock(return_value="https://example.org/final"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://example.org/final")
        resolver.assert_awaited_once_with(link)
        self.assertTrue(is_excep_link(link))

    async def test_hindianimeszone_download_routes_to_scraper(self):
        link = (
            "https://002.hindianimeszone.com/download1.php"
            "?code=8pzXFWUx1nTo6XaLo9aOV77&q=480p+x264"
        )
        with patch(
            "FZBypass.bypass.checker.hindianimeszone",
            new=AsyncMock(return_value="<b>Download Links</b>"),
        ) as scraper:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "<b>Download Links</b>")
        scraper.assert_awaited_once_with(link)
        self.assertTrue(is_excep_link(link))

    async def test_gdshare_download_is_returned_unchanged(self):
        link = (
            "https://gdshare.top/download/"
            "bdc294ad64e04511feff6bebb665612b"
        )

        with patch(
            "FZBypass.bypass.checker.gcloud",
            new=AsyncMock(return_value="https://video-downloads.googleusercontent.com/signed/"),
        ) as resolver:
            result = await direct_link_checker(link, onlylink=True)

        self.assertEqual(result, "https://video-downloads.googleusercontent.com/signed/")
        resolver.assert_awaited_once_with(link)
        self.assertTrue(is_excep_link(link))

    async def test_filebee_and_drivecloud_file_links_are_returned_unchanged(self):
        links = (
            "https://filebee.xyz/file/6ac6351169b577b115c59b38",
            "https://drivecloud.cc/file/D-atHFSPQrQ",
        )

        for link in links:
            with self.subTest(link=link):
                self.assertEqual(
                    await direct_link_checker(link, onlylink=True),
                    link,
                )
                self.assertTrue(is_excep_link(link))

    async def test_pixeldrain_suffixes_route_to_pixeldrain_resolver(self):
        for host in ("pixeldrain.in", "pixeldrain.me", "pixeldrain.xyz",
                     "pixeldrain.co.uk"):
            with self.subTest(host=host):
                link = f"https://{host}/u/BaXJWBDL"
                with patch(
                    "FZBypass.bypass.checker.pixeldrain",
                    new=AsyncMock(return_value=f"https://{host}/api/file/id?download"),
                ) as resolver:
                    result = await direct_link_checker(link, onlylink=True)

                self.assertEqual(result, f"https://{host}/api/file/id?download")
                resolver.assert_awaited_once_with(link)

    async def test_supported_site_routes_accept_arbitrary_suffixes(self):
        cases = (
            ("https://mediafire.dev/file/id", "mediafire"),
            ("https://gofile.xyz/d/id", "gofile"),
            ("https://shortxlinks.me/id", "shortxlinks"),
            ("https://hubcdn.co.uk/file/id", "hubcdn"),
            ("https://new1.hdhub4u.xyz/movie/id", "hdhub4u"),
            ("https://www.filmyfly.co.uk/movie/id", "filmyfly"),
            ("https://www.hdwebmovies.dev/movie/id", "hdwebmovies"),
        )
        for link, resolver_name in cases:
            with self.subTest(link=link):
                resolver = AsyncMock(return_value="https://downloads.example/file")
                with patch(
                    f"FZBypass.bypass.checker.{resolver_name}",
                    new=resolver,
                ):
                    result = await direct_link_checker(link, onlylink=True)

                self.assertEqual(result, "https://downloads.example/file")
                resolver.assert_awaited_once_with(link)

    async def test_xdmovies_uses_resolver(self):
        with patch(
            "FZBypass.bypass.checker.xdmovies",
            new=AsyncMock(return_value="https://latestnewsonline.sbs/r/yzQf2hDt"),
        ) as resolver:
            result = await direct_link_checker(
                "https://link.xdmovies.wtf/download/ADPZ7A-ND73oxfKxV9oez6RuXq2K5PxdScbt1jCPS9I",
                onlylink=True,
            )

        self.assertEqual(result, "https://latestnewsonline.sbs/r/yzQf2hDt")
        resolver.assert_awaited_once_with(
            "https://link.xdmovies.wtf/download/ADPZ7A-ND73oxfKxV9oez6RuXq2K5PxdScbt1jCPS9I"
        )

    async def test_hdhub4u_extracts_hdstream_episode_links(self):
        html = """
        <html>
          <head><title>The Punisher Season 1</title></head>
          <body>
            <article>
              <h3>
                <a href="https://greenmotors.club/?id=ad">EPiSODE 1</a> |
                <a href="https://hdstream4u.com/file/episode-1">
                  <span>WATCH</span>
                </a>
              </h3>
              <h3>
                <a href="https://greenmotors.club/?id=ad2">EPiSODE 2</a> |
                <a href="https://mirror.hdstream4u.net/file/episode-2">
                  <span>WATCH</span>
                </a>
              </h3>
            </article>
          </body>
        </html>
        """
        response = SimpleNamespace(text=html)

        with patch(
            "FZBypass.bypass.scrape.cf.get",
            new=AsyncMock(return_value=response),
        ):
            result = await hdhub4u(
                "https://new1.hdhub4u.free/the-punisher-season-1/"
            )

        self.assertIn("https://hdstream4u.com/file/episode-1", result)
        self.assertIn("https://mirror.hdstream4u.net/file/episode-2", result)
        self.assertNotIn("greenmotors.club", result)

    async def test_hdhub4u_retries_new2_when_new1_times_out(self):
        response = SimpleNamespace(
            text=(
                "<title>The Punisher Season 1</title>"
                '<a href="https://hdstream4u.com/file/episode-1">Episode 1</a>'
            )
        )
        with patch(
            "FZBypass.bypass.scrape.cf.get",
            new=AsyncMock(
                side_effect=[NetworkTimeout(), response]
            ),
        ) as fetch:
            result = await hdhub4u(
                "https://new1.hdhub4u.free/the-punisher-season-1/"
            )

        self.assertIn("https://hdstream4u.com/file/episode-1", result)
        self.assertEqual(
            [call.args[0] for call in fetch.await_args_list],
            [
                "https://new1.hdhub4u.free/the-punisher-season-1/",
                "https://new2.hdhub4u.free/the-punisher-season-1/",
            ],
        )

    async def test_hdstream4u_file_resolves_download_url(self):
        response = SimpleNamespace(text="""
            <div id="tab_down_link">
              <textarea>https://morencius.com/download/l0aeex0o51q8</textarea>
            </div>
        """)
        download_response = SimpleNamespace(text="<html>Download available</html>")

        with patch(
            "FZBypass.bypass.scrape.cf.get",
            new=AsyncMock(side_effect=[response, download_response]),
        ):
            result = await direct_link_checker(
                "https://hdstream4u.com/file/l0aeex0o51q8",
                onlylink=True,
            )

        self.assertEqual(result, "https://morencius.com/download/l0aeex0o51q8")

    async def test_hdstream4u_reports_disabled_downloads(self):
        response = SimpleNamespace(text="""
            <div id="tab_down_link">
              <textarea>https://morencius.com/download/l0aeex0o51q8</textarea>
            </div>
        """)
        disabled_response = SimpleNamespace(
            text="<div class='alert'>Downloads disabled for this file</div>"
        )

        with (
            patch(
                "FZBypass.bypass.scrape.cf.get",
                new=AsyncMock(side_effect=[response, disabled_response]),
            ),
            self.assertRaisesRegex(
                DDLException, "downloads are disabled for this file"
            ),
        ):
            await direct_link_checker(
                "https://hdstream4u.com/file/l0aeex0o51q8",
                onlylink=True,
            )

    async def test_hubcloud_accepts_current_download_url_markup(self):
        first_response = SimpleNamespace(
            text=(
                '<script>var url = "https://gamerxyt.com/hubcloud.php?token=abc";'
                "</script>"
            )
        )
        second_response = SimpleNamespace(
            text="""
                <title>example.mkv</title>
                <span id="size">13.16 GB</span>
                <a class="btn" href="https://pixeldrain.com/u/example">
                    Download [Pixeldrain]
                </a>
                <a href="https://downloads.example/file">
                    Download [Mirror]
                </a>
            """
        )

        with patch(
            "FZBypass.bypass.dlinks.http.get",
            new=AsyncMock(side_effect=[first_response, second_response]),
        ) as http_get:
            result = await hubcloud(
                "https://hubcloud.foo/drive/bbblwepoe3gelbw"
            )

        self.assertIn("https://pixeldrain.com/u/example", result)
        self.assertEqual(
            http_get.call_args_list[0].args[0],
            "https://hubcloud.ist/drive/bbblwepoe3gelbw",
        )

    async def test_hubcloud_auto_detects_arbitrary_alias(self):
        first_response = SimpleNamespace(
            text='<a id="download" href="https://gamerxyt.com/hubcloud.php?token=abc">'
            "Download</a>"
        )
        second_response = SimpleNamespace(
            text='<title>example.mkv</title><a href="https://downloads.example/file">'
            "Download [Mirror]</a>"
        )

        with (
            patch(
                "FZBypass.bypass.dlinks.http.get",
                new=AsyncMock(side_effect=[first_response, second_response]),
            ) as http_get,
        ):
            await hubcloud("https://mirror.hubcloud.example/drive/example")

        self.assertEqual(
            http_get.call_args_list[0].args[0],
            "https://hubcloud.ist/drive/example",
        )

    async def test_provider_subdomain_and_tld_are_dynamic(self):
        response = SimpleNamespace(text="""
            <html>
              <head><title>Dynamic HDHub4u</title></head>
              <article>
                <a href="https://mirror.hdstream4u.test/file/example">
                  WATCH
                </a>
              </article>
            </html>
        """)

        with patch(
            "FZBypass.bypass.scrape.cf.get",
            new=AsyncMock(return_value=response),
        ) as fetch:
            await direct_link_checker(
                "https://cdn.hdhub4u.test/movie/example",
                onlylink=True,
            )
        fetch.assert_awaited_once()
        fetch.assert_awaited_once()

    def test_provider_classification_accepts_arbitrary_subdomains_and_tlds(self):
        self.assertTrue(is_excep_link("https://new.test.hdhub4u.example/movie"))
        self.assertTrue(is_excep_link("https://new1.hdstream4u.test/file/id"))
        self.assertTrue(is_share_link("https://mirror.gdflix.example/file/id"))
        self.assertFalse(is_excep_link("https://fakehdhub4u.example/movie"))

    async def test_telegram_invites_are_not_counted_as_bypass_links(self):
        entity = SimpleNamespace(type=MessageEntityType.URL, offset=0, length=30)
        message = SimpleNamespace(
            reply_to_message=None,
            text="https://t.me/+nCYlwTXroxJkMTI1",
            caption=None,
            entities=[entity],
            caption_entities=None,
            reply=AsyncMock(return_value=SimpleNamespace(edit=AsyncMock(), delete=AsyncMock())),
            from_user=SimpleNamespace(mention="Contributor", id=7),
        )

        with patch.object(Config, "AUTO_BYPASS", True):
            await bypass_check(None, message)

        wait_message = message.reply.return_value
        wait_message.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
