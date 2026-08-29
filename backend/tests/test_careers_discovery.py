from job_finder.adapters.careers import (
    common_careers_candidates,
    discover_careers_links,
    discover_sitemap_careers,
    discover_sitemap_documents,
    website_homepage_candidates,
)


def test_discovery_allows_own_site_and_known_ats_but_rejects_external_sites() -> None:
    html = """
        <a href="/careers">Careers</a>
        <a href="https://apply.workable.com/acme/">Join our team</a>
        <a href="https://join.com/companies/acme">Open positions</a>
        <a href="https://evil.example/jobs">Jobs</a>
        <a href="https://social.example/acme">Follow us</a>
    """

    links = discover_careers_links(
        html,
        "https://www.acme.example/",
        "https://acme.example/",
    )

    assert "https://www.acme.example/careers" in links
    assert "https://apply.workable.com/acme/" in links
    assert "https://join.com/companies/acme" in links
    assert all("evil.example" not in link for link in links)
    assert all("social.example" not in link for link in links)


def test_discovery_limits_number_of_candidates() -> None:
    html = "".join(f'<a href="/jobs/{index}">Jobs {index}</a>' for index in range(20))
    assert len(discover_careers_links(html, "https://acme.example", "https://acme.example", limit=5)) == 5


def test_discovery_allows_pinpoint_careers_link() -> None:
    html = '<a href="https://acme.pinpointhq.com/">Careers</a>'
    assert discover_careers_links(
        html,
        "https://acme.example/",
        "https://acme.example/",
    ) == ["https://acme.pinpointhq.com/"]


def test_sitemap_discovery_keeps_only_safe_careers_urls() -> None:
    xml = """<urlset>
      <url><loc>https://acme.example/about</loc></url>
      <url><loc>https://acme.example/careers</loc></url>
      <url><loc>https://other.example/jobs</loc></url>
    </urlset>"""
    assert discover_sitemap_careers(xml, "https://acme.example") == ["https://acme.example/careers"]


def test_discovers_child_sitemaps_and_safe_common_fallbacks() -> None:
    xml = """<sitemapindex>
      <sitemap><loc>https://www.acme.example/jobs-sitemap.xml</loc></sitemap>
      <sitemap><loc>https://external.example/sitemap.xml</loc></sitemap>
    </sitemapindex>"""
    assert discover_sitemap_documents(xml, "https://acme.example") == [
        "https://www.acme.example/jobs-sitemap.xml"
    ]
    assert website_homepage_candidates("https://acme.example/about") == [
        "https://acme.example/about",
        "https://acme.example/",
        "https://www.acme.example/",
    ]
    candidates = common_careers_candidates(
        "https://acme.example",
        excluded={"https://acme.example/careers"},
        limit=2,
    )
    assert candidates == ["https://acme.example/jobs", "https://acme.example/career"]


def test_common_discovery_includes_additional_bounded_paths() -> None:
    candidates = common_careers_candidates("https://acme.example", limit=20)
    assert "https://acme.example/join-us" in candidates
    assert "https://acme.example/open-positions" in candidates
    assert "https://acme.example/work-with-us" in candidates
    assert "https://acme.example/en/careers" in candidates


def test_exact_join_us_path_is_careers_but_event_article_is_not() -> None:
    from job_finder.adapters.careers import looks_like_careers_page

    assert looks_like_careers_page(
        "<title>Join our team</title>",
        "https://acme.example/join-us",
    )
    assert not looks_like_careers_page(
        "<title>Join us at LeadsCon 2026</title>",
        "https://acme.example/news/join-us-at-leadscon-2026",
    )
