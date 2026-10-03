"""Manual, networked smoke check; intentionally excluded from unittest discovery."""

import asyncio
import sys

from FZBypass.bypass.ddl import mediafire


async def main(url: str) -> None:
    print(await mediafire(url))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tests/live_mediafire.py <MediaFire-URL>")
    asyncio.run(main(sys.argv[1]))
