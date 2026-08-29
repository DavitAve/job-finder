import json

import httpx

from job_finder.adapters.ats import AtsTarget, discover_ats, fetch_ats_jobs
from job_finder.adapters.base import FetchedPage


class FakeWorkdayFetcher:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        offset = kwargs["json_data"]["offset"]
        self.offsets.append(offset)
        postings = []
        if offset == 0:
            postings = [
                {
                    "title": f"Frontend Engineer {index}",
                    "externalPath": f"/job/frontend-{index}",
                    "locationsText": "Yerevan",
                }
                for index in range(20)
            ]
        elif offset == 20:
            postings = [
                {
                    "title": "Vue Developer",
                    "externalPath": "/job/vue-20",
                    "locationsText": "Remote",
                }
            ]
        content = json.dumps({"total": 21, "jobPostings": postings}).encode()
        return FetchedPage(url, 200, httpx.Headers({"content-type": "application/json"}), content)


async def test_workday_pagination() -> None:
    fetcher = FakeWorkdayFetcher()
    target = AtsTarget(
        kind="workday",
        token="acme",
        site="External",
        url="https://acme.wd5.myworkdayjobs.com/External",
    )
    jobs = await fetch_ats_jobs(fetcher, target)  # type: ignore[arg-type]
    assert len(jobs) == 21
    assert fetcher.offsets == [0, 20]
    assert jobs[-1].url == "https://acme.wd5.myworkdayjobs.com/External/job/vue-20"


class LargeWorkdayFetcher:
    def __init__(self) -> None:
        self.searches: list[str] = []

    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        search = kwargs["json_data"]["searchText"]
        self.searches.append(search)
        if not search:
            payload = {"total": 5_000, "jobPostings": [{"title": "Sales", "externalPath": "/job/sales"}]}
        else:
            payload = {
                "total": 1,
                "jobPostings": [
                    {"title": "Frontend Engineer", "externalPath": "/job/frontend"}
                ],
            }
        return FetchedPage(
            url,
            200,
            httpx.Headers({"content-type": "application/json"}),
            json.dumps(payload).encode(),
        )


async def test_large_workday_board_uses_targeted_search_and_deduplicates() -> None:
    fetcher = LargeWorkdayFetcher()
    target = AtsTarget(
        kind="workday",
        token="acme",
        site="External",
        url="https://acme.wd5.myworkdayjobs.com/External",
    )
    jobs = await fetch_ats_jobs(fetcher, target)  # type: ignore[arg-type]
    assert fetcher.searches[0] == ""
    assert "frontend" in fetcher.searches
    assert "React" in fetcher.searches
    assert len(jobs) == 1
    assert jobs[0].title == "Frontend Engineer"


def test_discovers_workday_from_embedded_job_link() -> None:
    html = (
        '<a href="https://servicetitan.wd1.myworkdayjobs.com/'
        'ServiceTitan/job/Yerevan/Engineer_JR1">Engineer</a>'
    )
    target = discover_ats("https://example.com/careers", html)
    assert target is not None
    assert target.kind == "workday"
    assert target.token == "servicetitan"
    assert target.site == "ServiceTitan"


def test_greenhouse_embed_without_board_token_is_not_misdetected() -> None:
    html = '<iframe src="https://job-boards.greenhouse.io/embed/job_board?for="></iframe>'
    assert discover_ats("https://example.com/careers", html) is None


def test_discovers_additional_public_ats_targets() -> None:
    cases = [
        ("https://jobs.ashbyhq.com/acme", "ashby", "acme"),
        ("https://jobs.smartrecruiters.com/Acme", "smartrecruiters", "Acme"),
        ("https://acme.recruitee.com/o/frontend", "recruitee", "acme"),
        ("https://apply.workable.com/acme/", "workable", "acme"),
        ("https://acme.pinpointhq.com/", "pinpoint", "acme"),
        ("https://acme.bamboohr.com/careers", "bamboohr", "acme"),
        ("https://ats.rippling.com/acme/jobs", "rippling", "acme"),
    ]
    for url, kind, token in cases:
        target = discover_ats(url, "")
        assert target is not None
        assert (target.kind, target.token) == (kind, token)


class AdditionalAtsFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if "ashbyhq" in url:
            payload = {"jobs": [{"id": "a1", "title": "React Engineer", "jobUrl": "https://jobs.ashbyhq.com/acme/a1", "location": "Remote"}]}
        elif "smartrecruiters" in url:
            payload = {"totalFound": 1, "content": [{"id": "s1", "name": "Vue Developer", "ref": "https://jobs.smartrecruiters.com/acme/s1", "location": {"city": "Yerevan", "country": "Armenia"}}]}
        else:
            payload = {"offers": [{"id": 3, "title": "Frontend Developer", "careers_url": "https://acme.recruitee.com/o/frontend", "location": "Remote"}]}
        return FetchedPage(url, 200, httpx.Headers({"content-type": "application/json"}), json.dumps(payload).encode())


async def test_fetches_additional_public_ats_jobs() -> None:
    fetcher = AdditionalAtsFetcher()
    targets = [
        AtsTarget("ashby", "acme", "https://jobs.ashbyhq.com/acme"),
        AtsTarget("smartrecruiters", "acme", "https://jobs.smartrecruiters.com/acme"),
        AtsTarget("recruitee", "acme", "https://acme.recruitee.com"),
    ]
    jobs = [await fetch_ats_jobs(fetcher, target) for target in targets]  # type: ignore[arg-type]
    assert [items[0].source for items in jobs] == ["ashby", "smartrecruiters", "recruitee"]


def test_ignores_single_unrelated_or_tracking_ats_link() -> None:
    html = """
      <a href="https://job-boards.greenhouse.io/other-company">Customer story</a>
      <script src="https://careers-analytics.recruitee.com/tracker.js"></script>
    """
    assert discover_ats("https://acme.example/careers", html) is None
    assert discover_ats("https://support.recruitee.com/", "") is None
    assert discover_ats("https://landing.recruitee.com/", "") is None


class WorkableFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        payload = {
            "jobs": [
                {
                    "title": "React Developer",
                    "shortcode": "ABC123",
                    "shortlink": "https://apply.workable.com/j/ABC123",
                    "published_on": "2026-08-20",
                    "telecommuting": True,
                    "locations": [
                        {"city": "Yerevan", "country": "Armenia"},
                        {"country": "Remote"},
                    ],
                    "description": "Build our frontend",
                }
            ]
        }
        return FetchedPage(
            url,
            200,
            httpx.Headers({"content-type": "application/json"}),
            json.dumps(payload).encode(),
        )


async def test_fetches_public_workable_jobs() -> None:
    jobs = await fetch_ats_jobs(  # type: ignore[arg-type]
        WorkableFetcher(),
        AtsTarget("workable", "acme", "https://apply.workable.com/acme/"),
    )
    assert len(jobs) == 1
    assert jobs[0].source == "workable"
    assert jobs[0].source_job_id == "ABC123"
    assert jobs[0].remote is True
    assert jobs[0].location == "Yerevan, Armenia; Remote"


class StructuredPublicAtsFetcher:
    async def fetch(self, url: str, **kwargs) -> FetchedPage:
        if "pinpointhq.com/postings.json" in url:
            payload = {
                "data": [{
                    "id": "p1",
                    "title": "Senior Frontend Engineer",
                    "url": "https://acme.pinpointhq.com/postings/p1",
                    "location": {"name": "Remote"},
                    "description": "<p>Build React applications</p>",
                    "skills_knowledge_expertise": "TypeScript",
                }]
            }
        elif "bamboohr.com/careers/list" in url:
            payload = {
                "result": [{
                    "id": "b1",
                    "jobOpeningName": "Vue Developer",
                    "location": {"city": "Yerevan", "state": None},
                    "atsLocation": {"country": "Armenia"},
                    "isRemote": False,
                }]
            }
        else:
            payload = [
                {
                    "uuid": "r1",
                    "name": "React Engineer",
                    "url": "https://ats.rippling.com/acme/jobs/r1",
                    "workLocation": {"label": "Armenia (Remote)"},
                },
                {
                    "uuid": "r1",
                    "name": "React Engineer",
                    "url": "https://ats.rippling.com/acme/jobs/r1",
                    "workLocation": {"label": "Georgia (Remote)"},
                },
            ]
        return FetchedPage(
            url,
            200,
            httpx.Headers({"content-type": "application/json"}),
            json.dumps(payload).encode(),
        )


async def test_fetches_pinpoint_bamboohr_and_rippling_jobs() -> None:
    fetcher = StructuredPublicAtsFetcher()
    targets = [
        AtsTarget("pinpoint", "acme", "https://acme.pinpointhq.com/"),
        AtsTarget("bamboohr", "acme", "https://acme.bamboohr.com/careers"),
        AtsTarget("rippling", "acme", "https://ats.rippling.com/acme/jobs"),
    ]
    pinpoint, bamboohr, rippling = [
        await fetch_ats_jobs(fetcher, target) for target in targets  # type: ignore[arg-type]
    ]

    assert pinpoint[0].source_job_id == "p1"
    assert pinpoint[0].description == "Build React applications TypeScript"
    assert pinpoint[0].remote is True
    assert bamboohr[0].url == "https://acme.bamboohr.com/careers/b1"
    assert bamboohr[0].location == "Yerevan; Armenia"
    assert len(rippling) == 1
    assert rippling[0].source_job_id == "r1"
    assert rippling[0].location == "Armenia (Remote); Georgia (Remote)"
