import os
import re
import random
import time
import threading
from logging import getLogger
from typing import Optional, List, Dict

import requests

LOGGER = getLogger(__name__)


def _mask_key(key: str) -> str:
    """Safely mask API key for logging (e.g. abcd...1234)."""
    if not key or len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


class WebshareManager:
    """
    Manages Webshare Proxy API integration.
    Supports multiple Webshare API keys (api1, api2, api3, api4, ...).

    Proxy Selection Strategy:
      1. Randomly selects an API key from configured keys.
      2. Randomly selects a proxy from that chosen API's pool.
      3. If an API has no proxies or errors, attempts other configured APIs.
      4. Auto-caches proxies in memory and refreshes periodically in the background.
    """

    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        mode: str = "direct",
        refresh_interval: int = 1800,
    ):
        self._mode = mode
        self._refresh_interval = refresh_interval
        self._lock = threading.Lock()

        # Configured API keys
        self.api_keys: List[str] = []
        if api_keys:
            self.set_api_keys(api_keys)
        else:
            self.load_from_env()

        # Cache: api_key -> list of formatted proxy URLs
        self._proxies_by_api: Dict[str, List[str]] = {}
        # Last fetch timestamp: api_key -> float
        self._last_fetch: Dict[str, float] = {}
        # Cooldown on errors: api_key -> float expiry timestamp
        self._cooldown: Dict[str, float] = {}
        # Consecutive errors: api_key -> int
        self._fail_count: Dict[str, int] = {}
        # Background thread control
        self._bg_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def load_from_env(self) -> None:
        """Collect all Webshare API keys from environment variables or config."""
        keys: List[str] = []

        # 1. Check WEBSHARE_API_KEYS (comma, space, or newline separated)
        raw_keys = os.getenv("WEBSHARE_API_KEYS", "")
        if raw_keys:
            for k in re.split(r"[\s,]+", raw_keys):
                k = k.strip()
                if k and k not in keys:
                    keys.append(k)

        # 2. Check WEBSHARE_API_KEY (can be single or comma/space separated)
        raw_key = os.getenv("WEBSHARE_API_KEY", "")
        if raw_key:
            for k in re.split(r"[\s,]+", raw_key):
                k = k.strip()
                if k and k not in keys:
                    keys.append(k)

        # 3. Check numbered variables: WEBSHARE_API_KEY_1, WEBSHARE_KEY_1, WEBSHARE_API_KEY1, etc.
        pattern = re.compile(r"^WEBSHARE_(?:API_)?KEY(?:_)?(\d+)$", re.IGNORECASE)
        numbered_keys = []
        for env_var, val in os.environ.items():
            m = pattern.match(env_var)
            if m and val.strip():
                try:
                    idx = int(m.group(1))
                except ValueError:
                    idx = 999
                numbered_keys.append((idx, val.strip()))

        # Sort numbered keys by index (e.g. 1, 2, 3, ...)
        numbered_keys.sort(key=lambda x: x[0])
        for _, val in numbered_keys:
            if val not in keys:
                keys.append(val)

        # Optional mode: "direct" or "backbone"
        self._mode = os.getenv("WEBSHARE_MODE", self._mode).strip() or "direct"
        try:
            self._refresh_interval = int(
                os.getenv("WEBSHARE_REFRESH_INTERVAL", str(self._refresh_interval))
            )
        except (ValueError, TypeError):
            self._refresh_interval = 1800

        self.set_api_keys(keys)

    def set_api_keys(self, keys: List[str]) -> None:
        """Update active API keys, deduplicating while preserving order."""
        cleaned = [k.strip() for k in keys if k and k.strip()]
        seen = set()
        deduped = []
        for k in cleaned:
            if k not in seen:
                seen.add(k)
                deduped.append(k)
        self.api_keys = deduped
        if self.api_keys:
            LOGGER.info(f"Configured {len(self.api_keys)} Webshare API key(s)")

    def has_keys(self) -> bool:
        """Return True if at least one Webshare API key is configured."""
        return len(self.api_keys) > 0

    def _fetch_from_api(self, api_key: str) -> List[str]:
        """Call Webshare API v2 to retrieve direct/backbone proxy list for the given API key."""
        now = time.time()
        masked = _mask_key(api_key)

        # Check cooldown if previously errored
        if api_key in self._cooldown and now < self._cooldown[api_key]:
            return self._proxies_by_api.get(api_key, [])

        url = f"https://proxy.webshare.io/api/v2/proxy/list/?mode={self._mode}&page=1&page_size=100"
        headers = {
            "Authorization": f"Token {api_key}",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            ),
        }

        proxies: List[str] = []
        pages = 0
        max_pages = 10  # Cap at 10 pages (1,000 proxies) per key

        try:
            while url and pages < max_pages:
                pages += 1
                resp = requests.get(url, headers=headers, timeout=12)
                if resp.status_code in (401, 403):
                    LOGGER.error(
                        f"Webshare API key {masked} unauthorized/forbidden (HTTP {resp.status_code})"
                    )
                    self._cooldown[api_key] = now + 600  # 10 minute cooldown
                    self._fail_count[api_key] = self._fail_count.get(api_key, 0) + 1
                    return self._proxies_by_api.get(api_key, [])
                elif resp.status_code == 429:
                    LOGGER.warning(f"Webshare API key {masked} rate limited (HTTP 429)")
                    self._cooldown[api_key] = now + 60  # 1 minute cooldown
                    return self._proxies_by_api.get(api_key, [])
                elif resp.status_code != 200:
                    LOGGER.warning(
                        f"Webshare API key {masked} returned HTTP {resp.status_code}: {resp.text[:100]}"
                    )
                    self._cooldown[api_key] = now + 60
                    return self._proxies_by_api.get(api_key, [])

                data = resp.json()
                results = data.get("results", [])
                for item in results:
                    # Skip proxies explicitly marked invalid
                    if item.get("valid") is False:
                        continue
                    ip = item.get("proxy_address")
                    port = item.get("port")
                    if not ip or not port:
                        continue
                    username = item.get("username")
                    password = item.get("password")
                    if username and password:
                        proxy_url = f"http://{username}:{password}@{ip}:{port}"
                    else:
                        proxy_url = f"http://{ip}:{port}"
                    proxies.append(proxy_url)

                url = data.get("next")

            # Successfully fetched and parsed
            self._proxies_by_api[api_key] = proxies
            self._last_fetch[api_key] = now
            self._fail_count[api_key] = 0
            self._cooldown.pop(api_key, None)
            LOGGER.info(
                f"Webshare API [{masked}]: cached {len(proxies)} proxies (mode={self._mode})"
            )
            return proxies

        except Exception as e:
            LOGGER.warning(f"Webshare API request failed for {masked}: {e}")
            self._cooldown[api_key] = now + 30
            self._fail_count[api_key] = self._fail_count.get(api_key, 0) + 1
            return self._proxies_by_api.get(api_key, [])

    def get_api_proxies(self, api_key: str, force_refresh: bool = False) -> List[str]:
        """Get proxies for a specific API key from cache or fetch if expired."""
        now = time.time()
        cached = self._proxies_by_api.get(api_key)
        last_time = self._last_fetch.get(api_key, 0)

        # Fast path: return cached if fresh
        if not force_refresh and cached and (now - last_time < self._refresh_interval):
            return cached

        # Slow path: fetch under thread lock
        with self._lock:
            cached = self._proxies_by_api.get(api_key)
            last_time = self._last_fetch.get(api_key, 0)
            if not force_refresh and cached and (now - last_time < self._refresh_interval):
                return cached
            return self._fetch_from_api(api_key)

    def get_proxy(self) -> Optional[str]:
        """
        Randomly select one of the configured Webshare APIs, then randomly
        select a proxy from that API's pool.

        If the chosen API has no proxies or fails, attempts the remaining
        configured APIs in random order.
        """
        if not self.api_keys:
            return None

        # Randomize order of API candidates to ensure load balancing across APIs
        candidates = list(self.api_keys)
        random.shuffle(candidates)

        for api_key in candidates:
            proxies = self.get_api_proxies(api_key)
            if proxies:
                chosen = random.choice(proxies)
                LOGGER.debug(
                    f"Webshare: selected API [{_mask_key(api_key)}] with proxy {chosen.split('@')[-1] if '@' in chosen else chosen}"
                )
                return chosen

        return None

    def refresh_all(self, force: bool = False) -> None:
        """Fetch/refresh proxies for all configured API keys."""
        if not self.api_keys:
            return
        LOGGER.info(
            f"Refreshing Webshare proxies for {len(self.api_keys)} configured API key(s)..."
        )
        for key in self.api_keys:
            try:
                self.get_api_proxies(key, force_refresh=force)
            except Exception as e:
                LOGGER.warning(f"Error refreshing proxies for {_mask_key(key)}: {e}")

    def start_background_refresher(self) -> None:
        """Start a daemon background thread to periodically refresh proxy pools."""
        if not self.api_keys:
            return
        if self._bg_thread and self._bg_thread.is_alive():
            return

        def _refresher_loop():
            # Initial pre-fetch on startup
            self.refresh_all(force=True)
            while not self._stop_event.is_set():
                self._stop_event.wait(self._refresh_interval)
                if self._stop_event.is_set():
                    break
                self.refresh_all(force=True)

        self._bg_thread = threading.Thread(
            target=_refresher_loop, daemon=True, name="WebshareRefresher"
        )
        self._bg_thread.start()

    def stop_background_refresher(self) -> None:
        """Stop the background refresher thread."""
        self._stop_event.set()

    def stats(self) -> Dict[str, object]:
        """Return diagnostic statistics about configured Webshare APIs and proxies."""
        total_proxies = sum(len(p) for p in self._proxies_by_api.values())
        active_keys = sum(1 for p in self._proxies_by_api.values() if p)
        return {
            "total_keys": len(self.api_keys),
            "active_keys": active_keys,
            "total_proxies": total_proxies,
            "per_key_counts": {
                _mask_key(k): len(self._proxies_by_api.get(k, []))
                for k in self.api_keys
            },
        }


# Singleton instance
webshare = WebshareManager()
