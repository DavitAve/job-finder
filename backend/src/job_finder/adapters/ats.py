from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

from job_finder.models import RawJob

from .base import HttpFetcher
from .structured import clean_text


@dataclass(frozen=True, slots=True)
class AtsTarget:
    kind: str
    token: str
    url: str
    site: str | None = None


_GREENHOUSE = re.compile(
    r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
_GREENHOUSE_API = re.compile(
    r"boards-api\.greenhouse\.io/v1/boards/([a-zA-Z0-9_-]+)", re.IGNORECASE
)
_LEVER = re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", re.IGNORECASE)
_WORKDAY = re.compile(
    r"https?://([a-zA-Z0-9_-]+)\.[a-zA-Z0-9_-]+\.myworkdayjobs\.com/"
    r"(?:(?:en|fr|de|es|pt)-[a-zA-Z]{2}/)?([a-zA-Z0-9_-]+)(?:/job|[/?\"'])",
    re.IGNORECASE,
)


def discover_ats(page_url: str, html: str) -> AtsTarget | None:
    searchable = f"{page_url}\n{html}"
    match = _GREENHOUSE.search(searchable) or _GREENHOUSE_API.search(searchable)
    if match:
        return AtsTarget("greenhouse", match.group(1), page_url)
    match = _LEVER.search(searchable)
    if match:
        return AtsTarget("lever", match.group(1), page_url)
    match = _WORKDAY.search(searchable)
    if match:
        embedded_url = match.group(0).split("/job", 1)[0].rstrip("/?\"'")
        return AtsTarget("workday", match.group(1), embedded_url, match.group(2))

    parts = urlsplit(page_url)
    if parts.netloc.lower().endswith("myworkdayjobs.com"):
        tenant = parts.netloc.split(".", 1)[0]
        path_parts = [part for part in parts.path.split("/") if part]
        if path_parts and path_parts[0].lower() in {"en-us", "en-gb", "en-ca"}:
            path_parts = path_parts[1:]
        if path_parts:
            return AtsTarget("workday", tenant, page_url, path_parts[0])
    return None


def _greenhouse_location(job: dict[str, Any]) -> str | None:
    location = job.get("location")
    if isinstance(location, dict):
        return clean_text(location.get("name")) or None
    return clean_text(location) or None


async def _greenhouse(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{target.token}/jobs?content=true"
    payload = (await fetcher.fetch(url)).json()
    return [
        RawJob(
            title=clean_text(item.get("title")),
            url=str(item.get("absolute_url") or ""),
            location=_greenhouse_location(item),
            description=clean_text(item.get("content")),
            published_at=clean_text(item.get("updated_at")) or None,
            source="greenhouse",
            source_job_id=str(item.get("id")) if item.get("id") is not None else None,
        )
        for item in payload.get("jobs", [])
        if item.get("title") and item.get("absolute_url")
    ]


async def _lever(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    url = f"https://api.lever.co/v0/postings/{target.token}?mode=json"
    payload = (await fetcher.fetch(url)).json()
    jobs: list[RawJob] = []
    for item in payload:
        categories = item.get("categories") or {}
        location = clean_text(categories.get("location")) or None
        created = item.get("createdAt")
        published_at = None
        if isinstance(created, (int, float)):
            published_at = datetime.fromtimestamp(created / 1000, timezone.utc).isoformat()
        jobs.append(
            RawJob(
                title=clean_text(item.get("text")),
                url=str(item.get("hostedUrl") or item.get("applyUrl") or ""),
                location=location,
                description=clean_text(
                    item.get("descriptionPlain") or item.get("description")
                ),
                published_at=published_at,
                source="lever",
                source_job_id=str(item.get("id")) if item.get("id") is not None else None,
            )
        )
    return [job for job in jobs if job.title and job.url]


async def _workday(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    parts = urlsplit(target.url)
    origin = f"{parts.scheme}://{parts.netloc}"
    site = target.site or ""
    api_url = f"{origin}/wday/cxs/{target.token}/{site}/jobs"
    page_size = 20
    max_full_board_jobs = 1_000
    frontend_searches = (
        "frontend",
        "front end",
        "UI engineer",
        "web developer",
        "React",
        "Vue",
        "Angular",
        "JavaScript",
        "TypeScript",
    )

    async def page(offset: int, search_text: str) -> dict[str, Any]:
        response = await fetcher.fetch(
            api_url,
            method="POST",
            json_data={
                "appliedFacets": {},
                "limit": page_size,
                "offset": offset,
                "searchText": search_text,
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        return response.json()

    jobs: dict[str, RawJob] = {}

    def add_postings(payload: dict[str, Any]) -> int:
        postings = payload.get("jobPostings") or []
        for item in postings:
            external_path = str(item.get("externalPath") or "")
            url = urljoin(f"{origin}/{site}/", external_path.lstrip("/"))
            locations = item.get("locationsText") or item.get("location")
            job = RawJob(
                title=clean_text(item.get("title")),
                url=url,
                location=clean_text(locations) or None,
                description=clean_text(item.get("bulletFields")),
                published_at=clean_text(item.get("postedOn")) or None,
                source="workday",
                source_job_id=external_path or None,
            )
            if job.title and job.url:
                jobs.setdefault(job.url, job)
        return len(postings)

    first = await page(0, "")
    total = int(first.get("total") or len(first.get("jobPostings") or []))
    if total <= max_full_board_jobs:
        count = add_postings(first)
        offset = count
        while count and offset < total:
            payload = await page(offset, "")
            count = add_postings(payload)
            offset += count
    else:
        # Very large global boards can contain tens of thousands of jobs. Query
        # Workday server-side for frontend signals instead of silently truncating.
        for search_text in frontend_searches:
            offset = 0
            while True:
                payload = await page(offset, search_text)
                count = add_postings(payload)
                search_total = int(payload.get("total") or count)
                offset += count
                if not count or offset >= search_total:
                    break
    return list(jobs.values())


async def fetch_ats_jobs(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    if target.kind == "greenhouse":
        return await _greenhouse(fetcher, target)
    if target.kind == "lever":
        return await _lever(fetcher, target)
    if target.kind == "workday":
        return await _workday(fetcher, target)
    return []
