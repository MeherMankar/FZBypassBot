import unittest
from pathlib import Path
from unittest.mock import patch

from FZBypass.bypass.ddl import mediafire
from FZBypass.core.exceptions import ResolverStepError

from resolver_cassette import ResolverCassette

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
        with patch("FZBypass.bypass.ddl.cf.get", side_effect=cassette.get):
            with self.assertRaises(ResolverStepError) as raised:
                await mediafire(cassette.fixture["input_url"])

        self.assertEqual(raised.exception.resolver, "MediaFire")
        self.assertEqual(raised.exception.step, "extract-download-link")


if __name__ == "__main__":
    unittest.main()
