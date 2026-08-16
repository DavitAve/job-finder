import httpx

from job_finder.adapters.auto import AutoAdapter
from job_finder.adapters.base import FetchError, FetchedPage
from job_finder.adapters.browser import RenderedPage
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
