from job_finder.adapters.careers import discover_careers_links


def test_discovery_allows_own_site_and_known_ats_but_rejects_external_sites() -> None:
    html = """
        <a href="/careers">Careers</a>
        <a href="https://apply.workable.com/acme/">Join our team</a>
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
    assert all("evil.example" not in link for link in links)
    assert all("social.example" not in link for link in links)


def test_discovery_limits_number_of_candidates() -> None:
    html = "".join(f'<a href="/jobs/{index}">Jobs {index}</a>' for index in range(20))
    assert len(discover_careers_links(html, "https://acme.example", "https://acme.example", limit=5)) == 5
