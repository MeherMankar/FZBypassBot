"""Small offline replay helper for resolver HTTP flow fixtures."""
import json
from pathlib import Path
from typing import Any

from FZBypass.core.networking.models import HTTPResponse


class ResolverCassette:
    def __init__(self, fixture: dict[str, Any]):
        self.fixture = fixture
        self._exchanges = fixture["exchanges"]
        self._position = 0

    @classmethod
    def load(cls, path: Path) -> "ResolverCassette":
        with path.open(encoding="utf-8") as fixture_file:
            return cls(json.load(fixture_file))

    async def get(self, url: str, **kwargs: Any) -> HTTPResponse:
        return self._replay("GET", url, kwargs)

    async def post(self, url: str, **kwargs: Any) -> HTTPResponse:
        return self._replay("POST", url, kwargs)

    def _replay(
        self, method: str, url: str, kwargs: dict[str, Any]
    ) -> HTTPResponse:
        if self._position >= len(self._exchanges):
            raise AssertionError(f"Unexpected {method} request: {url}")

        exchange = self._exchanges[self._position]
        expected = exchange["request"]
        actual = {"method": method, "url": url, **kwargs}
        for key, expected_value in expected.items():
            actual_value = actual.get(key)
            if key in ("headers", "cookies") and actual_value is None:
                actual_value = {}
            if actual_value != expected_value:
                raise AssertionError(
                    f"Exchange {self._position + 1} {key} mismatch: "
                    f"expected {expected_value!r}, got {actual_value!r}"
                )

        self._position += 1
        response = exchange["response"]
        body = response.get("body_text", "")
        return HTTPResponse(
            status_code=response["status"],
            url=response["url"],
            headers=response.get("headers", {}),
            content=body.encode("utf-8"),
            _text=body,
        )

    def assert_complete(self) -> None:
        if self._position != len(self._exchanges):
            raise AssertionError(
                f"Only replayed {self._position} of {len(self._exchanges)} exchanges"
            )
