import asyncio

import httpx
import pytest

from job_finder.adapters.base import FetchError, HttpFetcher


async def test_fetcher_retries_server_error() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(500, request=request)
        return httpx.Response(200, text="ok", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpFetcher(
            client,
            retries=2,
            respect_robots=False,
            min_domain_delay_seconds=0,
        )
        page = await fetcher.fetch("https://example.com/jobs")
    assert page.text == "ok"
    assert attempts == 3


async def test_fetcher_does_not_retry_permanent_client_error() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpFetcher(
            client,
            retries=2,
            respect_robots=False,
            min_domain_delay_seconds=0,
        )
        with pytest.raises(FetchError, match="404"):
            await fetcher.fetch("https://example.com/missing")
    assert attempts == 1


async def test_fetcher_retries_network_timeout_only_once() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpFetcher(
            client,
            retries=3,
            respect_robots=False,
            min_domain_delay_seconds=0,
        )
        with pytest.raises(FetchError, match="timed out"):
            await fetcher.fetch("https://example.com/jobs")
    assert attempts == 2


async def test_fetcher_does_not_wait_indefinitely_for_domain_pool() -> None:
    async with httpx.AsyncClient() as client:
        fetcher = HttpFetcher(
            client,
            per_domain=1,
            domain_wait_seconds=0.01,
            respect_robots=False,
        )
        semaphore = fetcher._domain_semaphores.setdefault(
            "example.com", asyncio.Semaphore(1)
        )
        await semaphore.acquire()
        try:
            with pytest.raises(FetchError, match="Domain request pool busy"):
                await fetcher.fetch("https://example.com/jobs")
        finally:
            semaphore.release()
