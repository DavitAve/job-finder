import httpx

from job_finder.adapters.base import HttpFetcher


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

