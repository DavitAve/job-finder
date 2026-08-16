from job_finder.adapters.html import extract_html_jobs
from job_finder.adapters.structured import extract_jsonld_jobs


def test_extracts_jobposting_jsonld() -> None:
    html = """
    <html><script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@graph": [{
        "@type": "JobPosting",
        "title": "Frontend Developer",
        "url": "/jobs/frontend",
        "description": "<p>Vue and TypeScript</p>",
        "datePosted": "2026-08-01",
        "identifier": {"value": "frontend-42"},
        "jobLocationType": "TELECOMMUTE",
        "applicantLocationRequirements": {"name": "Armenia"}
      }]
    }
    </script></html>
    """
    jobs = extract_jsonld_jobs(html, "https://example.com/careers")
    assert len(jobs) == 1
    assert jobs[0].url == "https://example.com/jobs/frontend"
    assert jobs[0].location == "Remote; Armenia"
    assert jobs[0].remote is True
    assert jobs[0].source_job_id == "frontend-42"


def test_malformed_jsonld_and_html_do_not_crash() -> None:
    html = """
    <script type="application/ld+json">{not valid</script>
    <div><h3>React Engineer</h3><a href="/jobs/42">Apply now
    """
    assert extract_jsonld_jobs(html, "https://example.com/careers") == []
    jobs = extract_html_jobs(html, "https://example.com/careers")
    assert len(jobs) == 1
    assert jobs[0].title == "React Engineer"
