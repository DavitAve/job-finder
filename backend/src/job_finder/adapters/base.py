from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx


class FetchError(RuntimeError):
    pass


class BlockedError(FetchError):
    pass


class RobotsDeniedError(BlockedError):
    pass


@dataclass(slots=True)
class FetchedPage:
    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes

    @property
    def text(self) -> str:
        encoding = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            encoding = content_type.rsplit("charset=", 1)[-1].split(";", 1)[0].strip()
        try:
            return self.content.decode(encoding, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content)


class HttpFetcher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        per_domain: int = 2,
        timeout_seconds: float = 15.0,
        domain_wait_seconds: float = 5.0,
        retries: int = 2,
        min_domain_delay_seconds: float = 0.25,
        respect_robots: bool = True,
        max_response_bytes: int = 10_000_000,
        user_agent: str = "FrontendJobFinder/0.1 (+local-personal-use)",
    ) -> None:
        self.client = client
        self.per_domain = per_domain
        self.timeout_seconds = timeout_seconds
        self.domain_wait_seconds = domain_wait_seconds
        self.retries = retries
        self.min_domain_delay_seconds = min_domain_delay_seconds
        self.respect_robots = respect_robots
        self.max_response_bytes = max_response_bytes
        self.user_agent = user_agent
        self._domain_semaphores: dict[str, asyncio.Semaphore] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}

    def _domain(self, url: str) -> str:
        return urlsplit(url).netloc.lower()

    async def _wait_for_domain(self, domain: str) -> None:
        lock = self._domain_locks.setdefault(domain, asyncio.Lock())
        async with lock:
            elapsed = time.monotonic() - self._last_request.get(domain, 0.0)
            delay = self.min_domain_delay_seconds - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request[domain] = time.monotonic()

    async def _raw_request(
        self,
        method: str,
        url: str,
        *,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        domain = self._domain(url)
        semaphore = self._domain_semaphores.setdefault(
            domain, asyncio.Semaphore(self.per_domain)
        )
        merged_headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/json"}
        if headers:
            merged_headers.update(headers)
        try:
            await asyncio.wait_for(
                semaphore.acquire(), timeout=self.domain_wait_seconds
            )
        except TimeoutError as exc:
            raise FetchError(
                f"Domain request pool busy for more than {self.domain_wait_seconds:g}s: {domain}"
            ) from exc
        try:
            await self._wait_for_domain(domain)
            return await self.client.request(
                method,
                url,
                json=json_data,
                headers=merged_headers,
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
        finally:
            semaphore.release()

    async def _robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        if origin in self._robots:
            return self._robots[origin]
        lock = self._robots_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin in self._robots:
                return self._robots[origin]
            robots_url = f"{origin}/robots.txt"
            try:
                response = await self._raw_request("GET", robots_url)
                if response.status_code == 200:
                    parser = RobotFileParser()
                    parser.set_url(robots_url)
                    parser.parse(response.text.splitlines())
                    self._robots[origin] = parser
                else:
                    self._robots[origin] = None
            except (httpx.HTTPError, asyncio.TimeoutError):
                self._robots[origin] = None
            return self._robots[origin]

    async def _check_robots(self, url: str) -> None:
        if not self.respect_robots:
            return
        parser = await self._robots_for(url)
        if parser is not None and not parser.can_fetch(self.user_agent, url):
            raise RobotsDeniedError(f"robots.txt disallows {url}")

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return min(float(retry_after), 10.0)
                except ValueError:
                    try:
                        parsed = parsedate_to_datetime(retry_after)
                        return max(0.0, min(parsed.timestamp() - time.time(), 10.0))
                    except (TypeError, ValueError, OverflowError):
                        pass
        return min(0.5 * (2**attempt), 5.0)

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        json_data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> FetchedPage:
        await self._check_robots(url)
        last_error: Exception | None = None
        last_response: httpx.Response | None = None
        for attempt in range(self.retries + 1):
            try:
                response = await self._raw_request(
                    method, url, json_data=json_data, headers=headers
                )
                last_response = response
                if response.status_code in {401, 403, 407}:
                    raise BlockedError(f"HTTP {response.status_code} for {url}")
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.retries:
                        await asyncio.sleep(self._retry_delay(response, attempt))
                        continue
                response.raise_for_status()
                content = response.content
                if len(content) > self.max_response_bytes:
                    raise FetchError(
                        f"Response exceeds {self.max_response_bytes} bytes for {url}"
                    )
                return FetchedPage(
                    url=str(response.url),
                    status_code=response.status_code,
                    headers=response.headers,
                    content=content,
                )
            except BlockedError:
                raise
            except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError) and 400 <= exc.response.status_code < 500:
                    break
                if isinstance(exc, httpx.TooManyRedirects):
                    break
                detail = str(exc).casefold()
                if any(
                    marker in detail
                    for marker in (
                        "certificate verify failed",
                        "getaddrinfo failed",
                        "name or service not known",
                        "nodename nor servname",
                    )
                ):
                    break
                if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
                    # One retry is enough for a transient network timeout. Three
                    # 15-second attempts leave no budget for fallback discovery.
                    if attempt >= min(self.retries, 1):
                        break
                if attempt < self.retries:
                    await asyncio.sleep(self._retry_delay(last_response, attempt))
                    continue
        if last_response is not None and last_response.status_code == 429:
            raise BlockedError(f"HTTP 429 rate limit for {url}")
        detail = str(last_error) if last_error else "request failed"
        raise FetchError(f"Could not fetch {url}: {detail}")
