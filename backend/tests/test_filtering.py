from datetime import datetime, timezone

from job_finder.filtering import frontend_match, normalize_job
from job_finder.models import Company, RawJob, WorkFormat


def test_explicit_frontend_title_matches() -> None:
    matched, reasons = frontend_match("Senior Front-end Engineer", "React and TypeScript")
    assert matched
    assert any("title" in reason for reason in reasons)


def test_backend_title_is_excluded() -> None:
    matched, reasons = frontend_match(
        "Senior Backend Engineer", "Our dashboard uses React, Vue and TypeScript"
    )
    assert not matched
    assert reasons == ["excluded title: backend"]


def test_hardware_front_end_role_is_excluded() -> None:
    matched, reasons = frontend_match(
        "Senior ASIC Front End Infrastructure Engineer",
        "Develop silicon emulation infrastructure and RTL workflows.",
    )
    assert not matched
    assert reasons == ["excluded hardware role: asic"]


def test_front_end_integration_hardware_title_is_excluded() -> None:
    matched, reasons = frontend_match("Front-End Integration Engineer", "")
    assert not matched
    assert reasons == ["excluded hardware role: front-end integration"]


def test_hardware_company_web_frontend_role_still_matches() -> None:
    matched, _ = frontend_match(
        "Senior Frontend Engineer, Marketplace",
        "Build React and TypeScript web applications.",
    )
    assert matched


def test_generic_engineer_requires_multiple_frontend_signals() -> None:
    matched, reasons = frontend_match(
        "Software Engineer", "Build user interfaces with React, TypeScript and CSS."
    )
    assert matched
    assert any("multiple" in reason for reason in reasons)


def test_normalization_has_stable_id_and_removes_tracking() -> None:
    company = Company(
        id="example",
        name="Example",
        website_url="https://example.com",
        careers_url="https://example.com/jobs",
    )
    raw = RawJob(
        title="Senior React Developer",
        url="https://example.com/jobs/123/?utm_source=test#apply",
        location=" Remote ",
        description="React and TypeScript",
        source="html",
    )
    now = datetime.now(timezone.utc)
    first = normalize_job(raw, company, now)
    second = normalize_job(raw, company, now)
    assert first is not None and second is not None
    assert first.job_id == second.job_id
    assert first.url == "https://example.com/jobs/123"
    assert first.remote is True
    assert first.work_format == WorkFormat.REMOTE


def test_source_job_id_is_stable_when_url_changes() -> None:
    company = Company(
        id="example",
        name="Example",
        website_url="https://example.com",
        careers_url="https://example.com/jobs",
    )
    first = normalize_job(
        RawJob(
            title="Frontend Developer",
            url="https://example.com/jobs/old",
            source="greenhouse",
            source_job_id="42",
        ),
        company,
        datetime.now(timezone.utc),
    )
    second = normalize_job(
        RawJob(
            title="Frontend Developer",
            url="https://example.com/jobs/new",
            source="greenhouse",
            source_job_id="42",
        ),
        company,
        datetime.now(timezone.utc),
    )
    assert first is not None and second is not None
    assert first.job_id == second.job_id


def test_explicit_hybrid_and_onsite_formats() -> None:
    company = Company(
        id="example",
        name="Example",
        website_url="https://example.com",
        careers_url="https://example.com/jobs",
    )
    hybrid = normalize_job(
        RawJob(
            title="Frontend Developer",
            url="https://example.com/jobs/1",
            description="Hybrid work in Yerevan",
            source="html",
        ),
        company,
        datetime.now(timezone.utc),
    )
    onsite = normalize_job(
        RawJob(
            title="Frontend Developer",
            url="https://example.com/jobs/2",
            description="This is an in-office role",
            source="html",
        ),
        company,
        datetime.now(timezone.utc),
    )
    assert hybrid is not None and hybrid.work_format == WorkFormat.HYBRID
    assert onsite is not None and onsite.work_format == WorkFormat.ONSITE


def test_location_alone_does_not_guess_work_format() -> None:
    company = Company(
        id="example",
        name="Example",
        website_url="https://example.com",
        careers_url="https://example.com/jobs",
    )
    job = normalize_job(
        RawJob(
            title="Frontend Developer",
            url="https://example.com/jobs/unknown-format",
            location="Yerevan, Armenia",
            source="html",
        ),
        company,
        datetime.now(timezone.utc),
    )
    assert job is not None and job.work_format == WorkFormat.UNKNOWN
