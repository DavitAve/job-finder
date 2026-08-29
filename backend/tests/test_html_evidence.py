from job_finder.adapters.html import extract_html_jobs, has_visible_job_listings


def test_detects_visible_job_title_that_has_no_extractable_link() -> None:
    html = '<main><h1>Careers</h1><article><h2>Senior Frontend Engineer</h2></article></main>'
    assert has_visible_job_listings(html) is True


def test_explicit_empty_state_is_not_treated_as_visible_jobs() -> None:
    html = '<main><h1>Careers</h1><p>There are no open positions right now.</p></main>'
    assert has_visible_job_listings(html) is False


def test_marketing_list_is_not_treated_as_visible_jobs() -> None:
    html = """
      <main><h1>Careers</h1><ul>
        <li>Technology: Software Development, Data Science, Cloud &amp; DevOps</li>
        <li>Product &amp; Design: UI/UX and Product Management</li>
      </ul></main>
    """
    assert has_visible_job_listings(html) is False


def test_extracts_role_from_adjacent_card_text_for_generic_link() -> None:
    html = """
      <ul><li>
        <div><p>New York City Office</p><p>Senior Frontend Engineer</p></div>
        <a href="/careers/openings/engineering/new-york/senior-frontend-engineer/">
          <span>See role</span>
        </a>
      </li></ul>
    """
    jobs = extract_html_jobs(html, "https://plaid.example/careers/")
    assert len(jobs) == 1
    assert jobs[0].title == "Senior Frontend Engineer"
    assert jobs[0].url.endswith("/senior-frontend-engineer/")
    assert has_visible_job_listings(html) is True
