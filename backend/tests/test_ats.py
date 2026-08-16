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
