import asyncio

import httpx
import pytest

from job_finder.adapters.auto import AutoAdapter
from job_finder.adapters.base import FetchedPage
from job_finder.adapters.browser import (
    BrowserRenderer,
    BrowserUnavailable,
    RenderedPage,
    RenderedPages,
)
from job_finder.adapters.pagination import (
    discover_next_page_url,
    needs_browser_pagination,
)
from job_finder.models import Company


def test_discovers_explicit_and_numeric_next_pages_without_leaving_domain() -> None:
    assert discover_next_page_url(
        '<link rel="next" href="/jobs?page=2">',
        "https://acme.example/jobs?page=1",
        {"https://acme.example/jobs?page=1"},
    ) == "https://acme.example/jobs?page=2"

    numeric = """
        <nav aria-label="Pagination">
          <span aria-current="page">2</span>
          <a href="/jobs?page=1">1</a>
          <a href="/jobs?page=3">3</a>
        </nav>
    """
    assert discover_next_page_url(
        numeric,
        "https://acme.example/jobs?page=2",
        {"https://acme.example/jobs?page=1", "https://acme.example/jobs?page=2"},
    ) == "https://acme.example/jobs?page=3"

    assert discover_next_page_url(
        '<a rel="next" href="https://tracking.example/jobs?page=2">Next</a>',
        "https://acme.example/jobs",
        {"https://acme.example/jobs"},
    ) is None


def test_detects_pages_that_need_browser_expansion() -> None:
    assert needs_browser_pagination("<button>Load more jobs</button>") is True
    assert needs_browser_pagination('<button aria-label="Next page"></button>') is True
    assert needs_browser_pagination("<div class='infinite-scroll'></div>") is True
    assert needs_browser_pagination("<main>All open roles</main>") is False


class PaginatedFetcher:
    def __init__(self) -> None:
        self.requested: list[str] = []

    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        self.requested.append(url)
        pages = {
            "https://acme.example/jobs": """
                <a href="/jobs/react">React Developer</a>
                <a rel="next" href="/jobs?page=2">Next</a>
            """,
            "https://acme.example/jobs?page=2": """
                <a href="/jobs/vue">Vue Developer</a>
                <a rel="next" href="/jobs?page=3">Next</a>
            """,
            "https://acme.example/jobs?page=3": """
                <a href="/jobs/angular">Angular Developer</a>
            """,
        }
        return FetchedPage(
            url=url,
            status_code=200,
            headers=httpx.Headers({"content-type": "text/html"}),
            content=pages[url].encode(),
        )


async def test_auto_adapter_collects_html_pages_and_reports_page_limit() -> None:
    fetcher = PaginatedFetcher()
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example",
        careers_url="https://acme.example/jobs",
    )
    result = await AutoAdapter(
        fetcher,  # type: ignore[arg-type]
        browser_enabled=False,
        max_pagination_pages=2,
    ).extract(company)

    assert [job.title for job in result.jobs] == ["React Developer", "Vue Developer"]
    assert result.adapter == "html+pagination"
    assert fetcher.requested == [
        "https://acme.example/jobs",
        "https://acme.example/jobs?page=2",
    ]
    assert any("stopped at 2 pages" in warning for warning in result.warnings)


async def test_auto_adapter_follows_every_available_html_page() -> None:
    fetcher = PaginatedFetcher()
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example",
        careers_url="https://acme.example/jobs",
    )

    result = await AutoAdapter(
        fetcher,  # type: ignore[arg-type]
        browser_enabled=False,
    ).extract(company)

    assert [job.title for job in result.jobs] == [
        "React Developer",
        "Vue Developer",
        "Angular Developer",
    ]
    assert result.warnings == []


class LoadMoreFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        return FetchedPage(
            url=url,
            status_code=200,
            headers=httpx.Headers({"content-type": "text/html"}),
            content=b'<a href="/jobs/react">React Developer</a><button>Load more jobs</button>',
        )


class LoadMoreBrowser:
    async def render_paginated(self, url: str) -> RenderedPages:
        return RenderedPages(
            pages=[
                RenderedPage(
                    url=url,
                    html='<a href="/jobs/react">React Developer</a><button>Load more jobs</button>',
                ),
                RenderedPage(
                    url=url,
                    html=(
                        '<a href="/jobs/react">React Developer</a>'
                        '<a href="/jobs/vue">Vue Developer</a>'
                    ),
                ),
            ],
            warnings=[],
        )


async def test_auto_adapter_merges_jobs_revealed_by_load_more() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example",
        careers_url="https://acme.example/jobs",
    )
    result = await AutoAdapter(
        LoadMoreFetcher(),  # type: ignore[arg-type]
        browser=LoadMoreBrowser(),  # type: ignore[arg-type]
    ).extract(company)

    assert [job.title for job in result.jobs] == ["React Developer", "Vue Developer"]
    assert result.adapter == "browser+html+pagination"


class FakeLoadMoreControl:
    def __init__(self, page) -> None:
        self.page = page

    async def is_visible(self) -> bool:
        return True

    async def is_enabled(self) -> bool:
        return True

    async def click(self, timeout: int) -> None:
        self.page.expanded = True


class FakeLoadMoreLocator:
    def __init__(self, page) -> None:
        self.page = page

    def filter(self, **kwargs):
        return self

    async def count(self) -> int:
        return 0 if self.page.expanded else 1

    def nth(self, index: int) -> FakeLoadMoreControl:
        return FakeLoadMoreControl(self.page)


class FakeLoadMorePage:
    url = "https://acme.example/jobs"
    expanded = False

    async def goto(self, url: str, **kwargs) -> None:
        self.url = url

    async def wait_for_timeout(self, milliseconds: int) -> None:
        pass

    async def wait_for_load_state(self, state: str, timeout: int) -> None:
        pass

    async def content(self) -> str:
        if self.expanded:
            return (
                '<a href="/jobs/react">React Developer</a>'
                '<a href="/jobs/vue">Vue Developer</a>'
            )
        return '<a href="/jobs/react">React Developer</a><button>Load more jobs</button>'

    def locator(self, selector: str) -> FakeLoadMoreLocator:
        return FakeLoadMoreLocator(self)

    async def evaluate(self, expression: str):
        return 100 if expression.startswith("Math.max") else None

    async def close(self) -> None:
        pass


class FakeBrowser:
    def __init__(self, page: FakeLoadMorePage) -> None:
        self.page = page

    async def new_page(self) -> FakeLoadMorePage:
        return self.page


async def test_browser_renderer_clicks_load_more_until_content_stops_changing() -> None:
    page = FakeLoadMorePage()
    renderer = BrowserRenderer(
        max_pagination_pages=5,
        max_interactions=5,
        infinite_scroll_rounds=1,
    )
    renderer._browser = FakeBrowser(page)  # type: ignore[assignment]

    result = await renderer.render_paginated(page.url)

    assert len(result.pages) == 2
    assert "Vue Developer" in result.pages[-1].html
    assert result.warnings == []


class FakeEmptyLocator(FakeLoadMoreLocator):
    async def count(self) -> int:
        return 0


class FakeInfinitePage(FakeLoadMorePage):
    async def content(self) -> str:
        base = '<a href="/jobs/react">React Developer</a>'
        return base + ('<a href="/jobs/vue">Vue Developer</a>' if self.expanded else "")

    def locator(self, selector: str) -> FakeEmptyLocator:
        return FakeEmptyLocator(self)

    async def evaluate(self, expression: str):
        if expression.startswith("Math.max"):
            return 200 if self.expanded else 100
        if expression.startswith("window.scrollTo"):
            self.expanded = True
        return None
async def test_browser_renderer_captures_infinite_scroll_growth() -> None:
    page = FakeInfinitePage()
    renderer = BrowserRenderer(
        max_pagination_pages=5,
        max_interactions=5,
        infinite_scroll_rounds=2,
    )
    renderer._browser = FakeBrowser(page)  # type: ignore[assignment]

    result = await renderer.render_paginated(page.url)

    assert len(result.pages) == 2
    assert "Vue Developer" in result.pages[-1].html


class FakeNavigationRacePage(FakeInfinitePage):
    content_attempts = 0

    async def goto(self, url: str, **kwargs) -> None:
        self.url = url
        raise RuntimeError("Page.goto: Timeout 25000ms exceeded")

    async def content(self) -> str:
        self.content_attempts += 1
        if self.content_attempts < 3:
            raise RuntimeError(
                "Page.content: Unable to retrieve content because the page is navigating"
            )
        return '<a href="/jobs/react">React Developer</a>'


async def test_browser_renderer_keeps_partial_dom_after_timeout_and_navigation_race() -> None:
    page = FakeNavigationRacePage()
    renderer = BrowserRenderer(
        max_pagination_pages=3,
        max_interactions=3,
        infinite_scroll_rounds=1,
    )
    renderer._browser = FakeBrowser(page)  # type: ignore[assignment]

    result = await renderer.render_paginated(page.url)

    assert len(result.pages) == 1
    assert "React Developer" in result.pages[0].html
    assert any("using partially loaded page" in warning for warning in result.warnings)


async def test_browser_renderer_does_not_wait_indefinitely_for_page_pool() -> None:
    renderer = BrowserRenderer(max_pages=1, pool_wait_seconds=0.01)
    renderer._browser = FakeBrowser(FakeLoadMorePage())  # type: ignore[assignment]
    await renderer._semaphore.acquire()
    try:
        with pytest.raises(BrowserUnavailable, match="page pool busy"):
            await renderer.render("https://acme.example/jobs")
    finally:
        renderer._semaphore.release()


async def test_browser_renderer_waits_for_a_temporarily_busy_page_pool() -> None:
    renderer = BrowserRenderer(max_pages=1, pool_wait_seconds=0.2)
    await renderer._semaphore.acquire()

    async def release_slot() -> None:
        await asyncio.sleep(0.01)
        renderer._semaphore.release()

    release_task = asyncio.create_task(release_slot())
    async with renderer._page_slot():
        assert renderer._semaphore.locked()
    await release_task
