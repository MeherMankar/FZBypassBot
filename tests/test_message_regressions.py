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
from FZBypass.bypass.checker import direct_link_checker
from FZBypass.core.bot_utils import auto_bypass
from FZBypass.handlers.bypass import bypass_check, extract_inline_link


class TestMessageRegressionCases(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
