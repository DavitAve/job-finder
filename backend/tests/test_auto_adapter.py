import httpx

from job_finder.adapters.auto import AutoAdapter
from job_finder.adapters.base import BlockedError, FetchError, FetchedPage, RobotsDeniedError
from job_finder.adapters.browser import RenderedPage, RenderedPages
from job_finder.models import Company


class EmptyFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        return FetchedPage(
            url=url,
            status_code=200,
            headers=httpx.Headers({"content-type": "text/html"}),
            content=b"<html><body><h1>Careers</h1></body></html>",
        )


class JsonLdBrowser:
    async def render(self, url: str) -> RenderedPage:
        return RenderedPage(
            url=url,
            html="""
            <script type="application/ld+json">
            {"@type":"JobPosting","title":"Vue Developer","url":"/jobs/vue"}
            </script>
            """,
        )


async def test_browser_is_used_only_after_http_extractors_are_empty() -> None:
    company = Company(
        id="dynamic",
        name="Dynamic",
        website_url="https://dynamic.example",
        careers_url="https://dynamic.example/careers",
    )
    adapter = AutoAdapter(
        EmptyFetcher(),  # type: ignore[arg-type]
        browser=JsonLdBrowser(),  # type: ignore[arg-type]
        browser_enabled=True,
    )
    result = await adapter.extract(company)
    assert result.adapter == "browser+jsonld"
    assert [job.title for job in result.jobs] == ["Vue Developer"]


async def test_configured_browser_adapter_skips_initial_http_fetch() -> None:
    class FailingFetcher:
        async def fetch(self, url: str, **kwargs):
            raise AssertionError("HTTP fetch must not run in forced browser mode")

    company = Company(
        id="browser-only",
        name="Browser Only",
        website_url="https://dynamic.example",
        careers_url="https://dynamic.example/careers",
        adapter="browser",
    )
    adapter = AutoAdapter(
        FailingFetcher(),  # type: ignore[arg-type]
        browser=JsonLdBrowser(),  # type: ignore[arg-type]
        browser_enabled=True,
    )

    result = await adapter.extract(company)

    assert result.adapter == "browser+jsonld"
    assert [job.title for job in result.jobs] == ["Vue Developer"]


async def test_configured_html_adapter_disables_ats_and_browser_fallback() -> None:
    class JsonLdFetcher:
        async def fetch(self, url: str, **kwargs) -> FetchedPage:
            return FetchedPage(
                url=url,
                status_code=200,
                headers=httpx.Headers({"content-type": "text/html"}),
                content=b'<script type="application/ld+json">'
                b'{"@type":"JobPosting","title":"React Developer","url":"/jobs/react"}'
                b'</script>',
            )

    company = Company(
        id="html-only",
        name="HTML Only",
        website_url="https://html.example",
        careers_url="https://html.example/careers",
        adapter="html",
    )
    adapter = AutoAdapter(
        JsonLdFetcher(),  # type: ignore[arg-type]
        browser=JsonLdBrowser(),  # type: ignore[arg-type]
        browser_enabled=True,
    )

    result = await adapter.extract(company)

    assert result.adapter == "jsonld"
    assert [job.title for job in result.jobs] == ["React Developer"]


def test_captcha_word_inside_javascript_is_not_a_block() -> None:
    html = """
    <html><head><title>Careers at Acme</title></head>
    <body><h1>Open roles</h1><script>window.captchaProvider = 'recaptcha'</script></body>
    </html>
    """
    AutoAdapter._check_blocked(html, "https://example.com/careers")


def test_visible_security_checkpoint_is_a_block() -> None:
    html = "<html><head><title>Vercel Security Checkpoint</title></head></html>"
    try:
        AutoAdapter._check_blocked(html, "https://example.com/careers")
    except Exception as exc:
        assert "Blocked page" in str(exc)
    else:
        raise AssertionError("security checkpoint was not detected")


class DiscoveryFetcher:
    def __init__(self) -> None:
        self.requested: list[str] = []

    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        self.requested.append(url)
        if url == "https://acme.example/missing-careers":
            raise FetchError("HTTP 404")
        if url == "https://acme.example/":
            content = b'<a href="https://apply.workable.com/acme/">Join our team</a>'
        elif url == "https://apply.workable.com/acme/":
            content = b"""
                <script type="application/ld+json">
                {"@type":"JobPosting","title":"React Developer","url":"/j/123"}
                </script>
            """
        elif url == "https://www.workable.com/api/accounts/acme?details=true":
            content = b'{"jobs":[{"title":"React Developer","shortcode":"123","shortlink":"https://apply.workable.com/j/123"}]}'
        else:
            raise AssertionError(f"Unexpected URL: {url}")
        return FetchedPage(
            url=url,
            status_code=200,
            headers=httpx.Headers({"content-type": "text/html"}),
            content=content,
        )


async def test_missing_careers_url_is_discovered_from_company_homepage() -> None:
    fetcher = DiscoveryFetcher()
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
        careers_url="https://acme.example/missing-careers",
    )

    result = await AutoAdapter(
        fetcher,  # type: ignore[arg-type]
        browser_enabled=False,
    ).extract(company)

    assert [job.title for job in result.jobs] == ["React Developer"]
    assert result.resolved_careers_url == "https://apply.workable.com/acme/"
    assert result.careers_url_discovered is True
    assert fetcher.requested == [
        "https://acme.example/missing-careers",
        "https://acme.example/",
        "https://apply.workable.com/acme/",
        "https://www.workable.com/api/accounts/acme?details=true",
    ]


class RedirectFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://acme.example/old-careers":
            return FetchedPage(
                url="https://acme.example/",
                status_code=200,
                headers=httpx.Headers({"content-type": "text/html"}),
                content=b'<a href="/jobs">Careers</a>',
            )
        if url == "https://acme.example/jobs":
            return FetchedPage(
                url=url,
                status_code=200,
                headers=httpx.Headers({"content-type": "text/html"}),
                content=b'<a href="/jobs/frontend-engineer">Frontend Engineer</a>',
            )
        raise AssertionError(f"Unexpected URL: {url}")


async def test_homepage_redirect_triggers_careers_discovery() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
        careers_url="https://acme.example/old-careers",
    )
    result = await AutoAdapter(
        RedirectFetcher(),  # type: ignore[arg-type]
        browser_enabled=False,
    ).extract(company)

    assert result.careers_url_discovered is True
    assert result.resolved_careers_url == "https://acme.example/jobs"
    assert [job.title for job in result.jobs] == ["Frontend Engineer"]


class NoConfiguredCareersFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://acme.example/":
            content = b'<a href="/careers">Join us</a>'
        elif url == "https://acme.example/careers":
            content = b'<a href="/careers/vue-developer">Vue Developer</a>'
        else:
            raise AssertionError(f"Unexpected URL: {url}")
        return FetchedPage(
            url=url,
            status_code=200,
            headers=httpx.Headers({"content-type": "text/html"}),
            content=content,
        )


async def test_company_without_careers_url_discovers_it_from_website() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
    )

    result = await AutoAdapter(
        NoConfiguredCareersFetcher(),  # type: ignore[arg-type]
        browser_enabled=False,
    ).extract(company)

    assert result.careers_url_discovered is True
    assert result.resolved_careers_url == "https://acme.example/careers"
    assert [job.title for job in result.jobs] == ["Vue Developer"]


class DynamicHomepageFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://acme.example/":
            content = b"<html><body></body></html>"
        elif url == "https://acme.example/jobs":
            content = b'<a href="/jobs/frontend">Frontend Developer</a>'
        else:
            raise AssertionError(f"Unexpected URL: {url}")
        return FetchedPage(
            url=url,
            status_code=200,
            headers=httpx.Headers({"content-type": "text/html"}),
            content=content,
        )


class DynamicHomepageBrowser:
    async def render(self, url: str) -> RenderedPage:
        return RenderedPage(
            url=url,
            html='<html><body><a href="/jobs">Careers</a></body></html>',
        )


async def test_missing_careers_url_uses_browser_for_dynamic_homepage_navigation() -> None:
    company = Company(id="acme", name="Acme", website_url="https://acme.example/")

    result = await AutoAdapter(
        DynamicHomepageFetcher(),  # type: ignore[arg-type]
        browser=DynamicHomepageBrowser(),  # type: ignore[arg-type]
        browser_enabled=True,
    ).extract(company)

    assert result.resolved_careers_url == "https://acme.example/jobs"
    assert [job.title for job in result.jobs] == ["Frontend Developer"]


class FullyDynamicFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://acme.example/":
            content = b"<html><body></body></html>"
        elif url == "https://acme.example/careers":
            content = b"<title>Careers at Acme</title><h1>Open roles</h1>"
        else:
            raise AssertionError(f"Unexpected URL: {url}")
        return FetchedPage(
            url=url,
            status_code=200,
            headers=httpx.Headers({"content-type": "text/html"}),
            content=content,
        )


class FullyDynamicBrowser:
    async def render(self, url: str) -> RenderedPage:
        if url == "https://acme.example/":
            return RenderedPage(url, '<a href="/careers">Careers</a>')
        assert url == "https://acme.example/careers"
        return RenderedPage(url, '<a href="/careers/react">React Developer</a>')

    async def render_paginated(self, url: str) -> RenderedPages:
        assert url == "https://acme.example/careers"
        return RenderedPages(
            [RenderedPage(url, '<a href="/careers/react">React Developer</a>')],
            [],
        )


async def test_dynamic_homepage_does_not_consume_careers_browser_fallback() -> None:
    company = Company(id="acme", name="Acme", website_url="https://acme.example/")
    result = await AutoAdapter(
        FullyDynamicFetcher(),  # type: ignore[arg-type]
        browser=FullyDynamicBrowser(),  # type: ignore[arg-type]
        browser_enabled=True,
    ).extract(company)

    assert result.adapter == "browser+html"
    assert [job.title for job in result.jobs] == ["React Developer"]
    assert result.resolved_careers_url == "https://acme.example/careers"


class Soft404Fetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://acme.example/old-jobs":
            content = b"<html><title>Page not found</title><h1>404</h1></html>"
        elif url == "https://acme.example/":
            content = b'<a href="/new-jobs">Careers</a>'
        elif url == "https://acme.example/new-jobs":
            content = b'<a href="/new-jobs/react">React Engineer</a>'
        else:
            raise AssertionError(f"Unexpected URL: {url}")
        return FetchedPage(
            url=url,
            status_code=200,
            headers=httpx.Headers({"content-type": "text/html"}),
            content=content,
        )


async def test_custom_404_with_http_200_triggers_discovery() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
        careers_url="https://acme.example/old-jobs",
    )

    result = await AutoAdapter(
        Soft404Fetcher(),  # type: ignore[arg-type]
        browser_enabled=False,
    ).extract(company)

    assert result.careers_url_discovered is True
    assert result.resolved_careers_url == "https://acme.example/new-jobs"
    assert [job.title for job in result.jobs] == ["React Engineer"]
    assert any("Custom not-found page" in warning for warning in result.warnings)


class BlockedCareersFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://jobs.example/acme":
            raise BlockedError("HTTP 403")
        if url == "https://acme.example/":
            content = b'<a href="/careers">Careers</a>'
        elif url == "https://acme.example/careers":
            content = b'<a href="/careers/react-engineer">React Engineer</a>'
        else:
            raise AssertionError(url)
        return FetchedPage(url, 200, httpx.Headers({"content-type": "text/html"}), content)


async def test_blocked_configured_board_falls_back_to_company_website() -> None:
    company = Company(id="acme", name="Acme", website_url="https://acme.example/", careers_url="https://jobs.example/acme")
    result = await AutoAdapter(BlockedCareersFetcher(), browser_enabled=False).extract(company)  # type: ignore[arg-type]
    assert [job.title for job in result.jobs] == ["React Engineer"]
    assert result.careers_url_discovered is True


class SitemapFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://acme.example/":
            content = b"<html><body>Acme</body></html>"
        elif url == "https://acme.example/sitemap.xml":
            content = b"<urlset><url><loc>https://acme.example/careers</loc></url></urlset>"
        elif url == "https://acme.example/careers":
            content = b'<a href="/careers/vue-developer">Vue Developer</a>'
        else:
            raise AssertionError(url)
        content_type = "application/xml" if url.endswith(".xml") else "text/html"
        return FetchedPage(url, 200, httpx.Headers({"content-type": content_type}), content)


async def test_careers_page_is_discovered_from_sitemap() -> None:
    company = Company(id="acme", name="Acme", website_url="https://acme.example/")
    result = await AutoAdapter(SitemapFetcher(), browser_enabled=False).extract(company)  # type: ignore[arg-type]
    assert [job.title for job in result.jobs] == ["Vue Developer"]
    assert any("sitemap.xml" in warning for warning in result.warnings)


class CommonPathFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://acme.example/old-careers":
            raise FetchError("HTTP 404")
        if url == "https://acme.example/":
            content = b"<html><h1>Acme</h1></html>"
        elif url in {
            "https://acme.example/sitemap.xml",
            "https://acme.example/sitemap_index.xml",
        }:
            raise FetchError("HTTP 404")
        elif url == "https://acme.example/jobs":
            content = b'<a href="/jobs/react">React Developer</a>'
        else:
            raise FetchError("HTTP 404")
        return FetchedPage(url, 200, httpx.Headers({"content-type": "text/html"}), content)


async def test_stale_configured_url_falls_back_to_common_careers_paths() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
        careers_url="https://acme.example/old-careers",
    )
    result = await AutoAdapter(CommonPathFetcher(), browser_enabled=False).extract(company)  # type: ignore[arg-type]
    assert [job.title for job in result.jobs] == ["React Developer"]
    assert result.resolved_careers_url == "https://acme.example/jobs"
    assert result.careers_url_discovered is True


class AlternateOriginFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url in {"https://acme.example/about", "https://acme.example/"}:
            raise FetchError("getaddrinfo failed")
        if url == "https://www.acme.example/":
            content = b'<a href="/careers">Careers</a>'
        elif url == "https://www.acme.example/careers":
            content = b'<a href="/careers/vue">Vue Developer</a>'
        else:
            raise AssertionError(url)
        return FetchedPage(url, 200, httpx.Headers({"content-type": "text/html"}), content)


async def test_failed_origin_retries_safe_www_alternative() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/about",
    )
    result = await AutoAdapter(AlternateOriginFetcher(), browser_enabled=False).extract(company)  # type: ignore[arg-type]
    assert [job.title for job in result.jobs] == ["Vue Developer"]
    assert any("Website fallback succeeded" in warning for warning in result.warnings)


class ForbiddenFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        raise BlockedError(f"HTTP 403 for {url}")


class ForbiddenBrowser:
    async def render_paginated(self, url: str) -> RenderedPages:
        return RenderedPages(
            [RenderedPage(url, '<a href="/careers/react">React Developer</a>')],
            [],
        )


class FastFallbackBrowser:
    def __init__(self) -> None:
        self.render_calls = 0
        self.paginated_calls = 0

    async def render(self, url: str) -> RenderedPage:
        self.render_calls += 1
        return RenderedPage(url, '<a href="/careers/react">React Developer</a>')

    async def render_paginated(self, url: str) -> RenderedPages:
        self.paginated_calls += 1
        raise AssertionError("A plain 403 fallback must not run interactive pagination")


async def test_http_403_uses_browser_fallback() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
        careers_url="https://acme.example/careers",
    )
    result = await AutoAdapter(
        ForbiddenFetcher(),  # type: ignore[arg-type]
        browser=ForbiddenBrowser(),  # type: ignore[arg-type]
    ).extract(company)
    assert [job.title for job in result.jobs] == ["React Developer"]
    assert any("403 recovered" in warning for warning in result.warnings)


async def test_http_403_uses_single_fast_browser_render() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
        careers_url="https://acme.example/careers",
    )
    browser = FastFallbackBrowser()
    result = await AutoAdapter(
        ForbiddenFetcher(),  # type: ignore[arg-type]
        browser=browser,  # type: ignore[arg-type]
    ).extract(company)

    assert [job.title for job in result.jobs] == ["React Developer"]
    assert browser.render_calls == 1
    assert browser.paginated_calls == 0


class RobotsFallbackFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url.endswith("/careers"):
            raise RobotsDeniedError(f"robots.txt disallows {url}")
        content = b'<a href="/jobs/react">React Developer</a>'
        return FetchedPage(url, 200, httpx.Headers({"content-type": "text/html"}), content)


class BrowserMustNotRun:
    async def render_paginated(self, url: str) -> RenderedPages:
        raise AssertionError("robots.txt must not be bypassed with Playwright")


async def test_robots_denial_is_not_bypassed_with_browser() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
        careers_url="https://acme.example/careers",
    )
    result = await AutoAdapter(
        RobotsFallbackFetcher(),  # type: ignore[arg-type]
        browser=BrowserMustNotRun(),  # type: ignore[arg-type]
    ).extract(company)
    assert [job.title for job in result.jobs] == ["React Developer"]


class ValidEmptyCareersFetcher:
    def __init__(self) -> None:
        self.requested: list[str] = []

    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        self.requested.append(url)
        if url == "https://acme.example/careers":
            content = b"<title>Careers at Acme</title><h1>Open positions</h1>"
            return FetchedPage(url, 200, httpx.Headers({"content-type": "text/html"}), content)
        raise AssertionError("A valid empty careers page must not trigger homepage guessing")


class EmptyCareersBrowser:
    async def render(self, url: str) -> RenderedPage:
        return RenderedPage(url, "<title>Careers at Acme</title><h1>No openings</h1>")


async def test_valid_empty_configured_careers_page_stops_discovery() -> None:
    fetcher = ValidEmptyCareersFetcher()
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
        careers_url="https://acme.example/careers",
    )
    result = await AutoAdapter(
        fetcher,  # type: ignore[arg-type]
        browser=EmptyCareersBrowser(),  # type: ignore[arg-type]
    ).extract(company)

    assert result.jobs == []
    assert result.resolved_careers_url == "https://acme.example/careers"
    assert fetcher.requested == ["https://acme.example/careers"]


class MissingEverywhereFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://acme.example/":
            return FetchedPage(
                url,
                200,
                httpx.Headers({"content-type": "text/html"}),
                b"<title>Acme</title><h1>Welcome to Acme</h1>",
            )
        raise FetchError("HTTP 404")


async def test_missing_careers_page_is_reported_as_not_found() -> None:
    company = Company(
        id="acme",
        name="Acme",
        website_url="https://acme.example/",
    )
    result = await AutoAdapter(
        MissingEverywhereFetcher(),  # type: ignore[arg-type]
        browser_enabled=False,
    ).extract(company)

    assert result.jobs == []
    assert any("Careers page was not found" in warning for warning in result.warnings)


class MarketingHomepageFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if url == "https://acme.example/":
            return FetchedPage(
                url,
                200,
                httpx.Headers({"content-type": "text/html"}),
                b'<title>Acme platform</title><a href="/product/frontend">Frontend platform</a>',
            )
        raise FetchError("HTTP 404")


async def test_marketing_homepage_links_do_not_verify_careers() -> None:
    company = Company(id="acme", name="Acme", website_url="https://acme.example/")
    result = await AutoAdapter(
        MarketingHomepageFetcher(),  # type: ignore[arg-type]
        browser_enabled=False,
    ).extract(company)

    assert result.jobs == []
    assert any("Careers page was not found" in warning for warning in result.warnings)
