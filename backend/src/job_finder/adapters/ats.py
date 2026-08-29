from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from job_finder.models import RawJob

from .base import HttpFetcher
from .structured import clean_text


@dataclass(frozen=True, slots=True)
class AtsTarget:
    kind: str
    token: str
    url: str
    site: str | None = None


_GREENHOUSE_EMBED = re.compile(
    r"(?:boards|job-boards)\.greenhouse\.io/embed/job_board\?[^\s\"']*\bfor=([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
_GREENHOUSE = re.compile(
    r"(?:boards|job-boards)\.greenhouse\.io/(?!embed(?:/|\b))([a-zA-Z0-9_-]+)", re.IGNORECASE
)
_GREENHOUSE_API = re.compile(
    r"boards-api\.greenhouse\.io/v1/boards/([a-zA-Z0-9_-]+)", re.IGNORECASE
)
_LEVER = re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", re.IGNORECASE)
_ASHBY = re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)", re.IGNORECASE)
_SMARTRECRUITERS = re.compile(r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)", re.IGNORECASE)
_RECRUITEE = re.compile(r"https?://([a-zA-Z0-9_-]+)\.recruitee\.com", re.IGNORECASE)
_PINPOINT = re.compile(r"https?://([a-zA-Z0-9_-]+)\.pinpointhq\.com", re.IGNORECASE)
_BAMBOOHR = re.compile(r"https?://([a-zA-Z0-9_-]+)\.bamboohr\.com", re.IGNORECASE)
_RIPPLING = re.compile(
    r"https?://ats\.rippling\.com/([a-zA-Z0-9_-]+)/jobs(?:/|\b)", re.IGNORECASE
)
_WORKABLE_APPLY = re.compile(
    r"https?://apply\.workable\.com/(?!j(?:/|$))([a-zA-Z0-9_-]+)", re.IGNORECASE
)
_WORKABLE_SUBDOMAIN = re.compile(
    r"https?://(?!www\.)([a-zA-Z0-9_-]+)\.workable\.com", re.IGNORECASE
)
_WORKDAY = re.compile(
    r"https?://([a-zA-Z0-9_-]+)\.[a-zA-Z0-9_-]+\.myworkdayjobs\.com/"
    r"(?:(?:en|fr|de|es|pt)-[a-zA-Z]{2}/)?([a-zA-Z0-9_-]+)(?:/job|[/?\"'])",
    re.IGNORECASE,
)
_RESERVED_RECRUITEE_SUBDOMAINS = {
    "careers-analytics",
    "help",
    "landing",
    "status",
    "support",
    "tagging-server",
    "www",
}


def _target_from_url(url: str) -> AtsTarget | None:
    match = _GREENHOUSE_EMBED.search(url) or _GREENHOUSE.search(url) or _GREENHOUSE_API.search(url)
    if match:
        return AtsTarget("greenhouse", match.group(1), url)
    match = _LEVER.search(url)
    if match:
        return AtsTarget("lever", match.group(1), url)
    match = _ASHBY.search(url)
    if match:
        return AtsTarget("ashby", match.group(1), url)
    match = _SMARTRECRUITERS.search(url)
    if match:
        return AtsTarget("smartrecruiters", match.group(1), url)
    match = _RECRUITEE.search(url)
    if match and match.group(1).casefold() not in _RESERVED_RECRUITEE_SUBDOMAINS:
        return AtsTarget("recruitee", match.group(1), url)
    match = _PINPOINT.search(url)
    if match:
        return AtsTarget("pinpoint", match.group(1), url)
    match = _BAMBOOHR.search(url)
    if match and match.group(1).casefold() not in {"www"}:
        return AtsTarget("bamboohr", match.group(1), url)
    match = _RIPPLING.search(url)
    if match:
        return AtsTarget("rippling", match.group(1), url)
    match = _WORKABLE_APPLY.search(url) or _WORKABLE_SUBDOMAIN.search(url)
    if match:
        return AtsTarget("workable", match.group(1), url)
    match = _WORKDAY.search(url)
    if match:
        embedded_url = match.group(0).split("/job", 1)[0].rstrip("/?\"'")
        return AtsTarget("workday", match.group(1), embedded_url, match.group(2))

    parts = urlsplit(url)
    if parts.netloc.lower().endswith("myworkdayjobs.com"):
        tenant = parts.netloc.split(".", 1)[0]
        path_parts = [part for part in parts.path.split("/") if part]
        if path_parts and path_parts[0].lower() in {"en-us", "en-gb", "en-ca"}:
            path_parts = path_parts[1:]
        if path_parts:
            return AtsTarget("workday", tenant, url, path_parts[0])
    return None


def discover_ats(page_url: str, html: str) -> AtsTarget | None:
    direct = _target_from_url(page_url)
    if direct is not None:
        return direct

    embed = _GREENHOUSE_EMBED.search(html) or _GREENHOUSE_API.search(html)
    if embed:
        return AtsTarget("greenhouse", embed.group(1), page_url)

    soup = BeautifulSoup(html, "lxml")
    occurrences: dict[tuple[str, str, str | None], list[AtsTarget]] = {}
    for element in soup.find_all(["a", "iframe", "script"]):
        raw_url = element.get("href") or element.get("src")
        if not raw_url:
            continue
        absolute_url = urljoin(page_url, str(raw_url))
        target = _target_from_url(absolute_url)
        if target is None:
            continue
        # A single external board link is followed by the normal board discovery
        # flow. Detect it immediately only when it is an embedded board or a real
        # job link; this avoids unrelated customer/logo links selecting a false ATS.
        if element.name in {"iframe", "script"} or "/job/" in absolute_url.casefold():
            return target
        key = (target.kind, target.token.casefold(), target.site)
        occurrences.setdefault(key, []).append(target)
    repeated = next((targets[0] for targets in occurrences.values() if len(targets) >= 2), None)
    return repeated


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


async def _ashby(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{target.token}"
    payload = (await fetcher.fetch(url, headers={"Accept": "application/json"})).json()
    jobs = payload.get("jobs") or []
    return [
        RawJob(
            title=clean_text(item.get("title")),
            url=str(item.get("jobUrl") or item.get("applyUrl") or ""),
            location=clean_text(item.get("location")) or None,
            description=clean_text(item.get("descriptionPlain") or item.get("descriptionHtml")),
            published_at=clean_text(item.get("publishedAt")) or None,
            remote=item.get("isRemote") if isinstance(item.get("isRemote"), bool) else None,
            source="ashby",
            source_job_id=str(item.get("id")) if item.get("id") is not None else None,
        )
        for item in jobs
        if item.get("title") and (item.get("jobUrl") or item.get("applyUrl"))
    ]


async def _smartrecruiters(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    jobs: list[RawJob] = []
    offset = 0
    limit = 100
    while True:
        url = f"https://api.smartrecruiters.com/v1/companies/{target.token}/postings?limit={limit}&offset={offset}"
        payload = (await fetcher.fetch(url, headers={"Accept": "application/json"})).json()
        content = payload.get("content") or []
        for item in content:
            location = item.get("location") or {}
            location_text = ", ".join(
                clean_text(location.get(key))
                for key in ("city", "region", "country")
                if clean_text(location.get(key))
            ) or None
            identifier = str(item.get("id") or "")
            job_url = str(item.get("ref") or "")
            if not job_url and identifier:
                job_url = f"https://jobs.smartrecruiters.com/{target.token}/{identifier}"
            jobs.append(RawJob(
                title=clean_text(item.get("name")), url=job_url, location=location_text,
                published_at=clean_text(item.get("releasedDate")) or None,
                source="smartrecruiters", source_job_id=identifier or None,
            ))
        offset += len(content)
        total = int(payload.get("totalFound") or len(content))
        if not content or offset >= total:
            break
    return [job for job in jobs if job.title and job.url]


async def _recruitee(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    url = f"https://{target.token}.recruitee.com/api/offers/"
    payload = (await fetcher.fetch(url, headers={"Accept": "application/json"})).json()
    offers = payload.get("offers") or []
    return [
        RawJob(
            title=clean_text(item.get("title")),
            url=str(item.get("careers_url") or item.get("careers_apply_url") or ""),
            location=clean_text(item.get("location")) or None,
            description=clean_text(item.get("description")),
            published_at=clean_text(item.get("published_at")) or None,
            remote=item.get("remote") if isinstance(item.get("remote"), bool) else None,
            source="recruitee",
            source_job_id=str(item.get("id") or item.get("slug") or "") or None,
        )
        for item in offers
        if item.get("title") and (item.get("careers_url") or item.get("careers_apply_url"))
    ]


async def _workable(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    url = f"https://www.workable.com/api/accounts/{target.token}?details=true"
    payload = (await fetcher.fetch(url, headers={"Accept": "application/json"})).json()
    jobs = payload.get("jobs") or []
    results: list[RawJob] = []
    for item in jobs:
        locations = item.get("locations") or []
        location_parts: list[str] = []
        for location in locations:
            if not isinstance(location, dict):
                continue
            value = ", ".join(
                part
                for part in (
                    clean_text(location.get("city")),
                    clean_text(location.get("region")),
                    clean_text(location.get("country") or location.get("country_name")),
                )
                if part
            )
            if value and value not in location_parts:
                location_parts.append(value)
        fallback_location = ", ".join(
            part
            for part in (
                clean_text(item.get("city")),
                clean_text(item.get("state")),
                clean_text(item.get("country")),
            )
            if part
        )
        workplace_type = clean_text(item.get("workplace_type")).casefold()
        results.append(
            RawJob(
                title=clean_text(item.get("title")),
                url=str(item.get("shortlink") or item.get("url") or ""),
                location="; ".join(location_parts) or fallback_location or None,
                description=clean_text(item.get("description")),
                published_at=clean_text(item.get("published_on") or item.get("created_at")) or None,
                remote=(
                    True
                    if item.get("telecommuting") is True or workplace_type == "remote"
                    else None
                ),
                source="workable",
                source_job_id=clean_text(item.get("shortcode")) or None,
            )
        )
    return [job for job in results if job.title and job.url]


async def _pinpoint(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    origin = f"https://{target.token}.pinpointhq.com"
    payload = (
        await fetcher.fetch(
            f"{origin}/postings.json", headers={"Accept": "application/json"}
        )
    ).json()
    postings = payload.get("data") or []
    jobs: list[RawJob] = []
    for item in postings:
        location = item.get("location") or {}
        location_text = clean_text(
            location.get("name") if isinstance(location, dict) else location
        ) or None
        description = clean_text(
            " ".join(
                str(item.get(field) or "")
                for field in (
                    "description",
                    "key_responsibilities",
                    "skills_knowledge_expertise",
                    "benefits",
                )
            )
        )
        identifier = clean_text(item.get("id") or item.get("requisition_id"))
        path = str(item.get("path") or "")
        job_url = str(item.get("url") or (urljoin(f"{origin}/", path) if path else ""))
        jobs.append(
            RawJob(
                title=clean_text(item.get("title")),
                url=job_url,
                location=location_text,
                description=description,
                published_at=clean_text(item.get("published_at")) or None,
                remote=(
                    True
                    if "remote" in f"{location_text or ''} {item.get('workplace_type') or ''}".casefold()
                    else None
                ),
                source="pinpoint",
                source_job_id=identifier or None,
            )
        )
    return [job for job in jobs if job.title and job.url]


async def _bamboohr(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    origin = f"https://{target.token}.bamboohr.com"
    payload = (
        await fetcher.fetch(
            f"{origin}/careers/list", headers={"Accept": "application/json"}
        )
    ).json()
    jobs: list[RawJob] = []
    for item in payload.get("result") or []:
        identifier = clean_text(item.get("id"))
        locations: list[str] = []
        for location_key in ("location", "atsLocation"):
            location = item.get(location_key) or {}
            if not isinstance(location, dict):
                continue
            value = ", ".join(
                clean_text(location.get(key))
                for key in ("city", "state", "province", "country")
                if clean_text(location.get(key))
            )
            if value and value not in locations:
                locations.append(value)
        location_text = "; ".join(locations) or None
        jobs.append(
            RawJob(
                title=clean_text(item.get("jobOpeningName") or item.get("title")),
                url=f"{origin}/careers/{identifier}" if identifier else str(target.url),
                location=location_text,
                remote=(
                    True
                    if item.get("isRemote") is True
                    or "remote" in f"{location_text or ''} {item.get('locationType') or ''}".casefold()
                    else None
                ),
                source="bamboohr",
                source_job_id=identifier or None,
            )
        )
    return [job for job in jobs if job.title and job.url]


async def _rippling(fetcher: HttpFetcher, target: AtsTarget) -> list[RawJob]:
    url = f"https://api.rippling.com/platform/api/ats/v1/board/{target.token}/jobs"
    payload = (await fetcher.fetch(url, headers={"Accept": "application/json"})).json()
    items = payload if isinstance(payload, list) else payload.get("jobs") or payload.get("data") or []
    grouped: dict[str, dict[str, Any]] = {}
    for item in items:
        identifier = clean_text(item.get("uuid") or item.get("id"))
        key = identifier or str(item.get("url") or item.get("name") or "")
        if not key:
            continue
        current = grouped.setdefault(key, {"item": item, "locations": []})
        location = item.get("workLocation") or item.get("location") or {}
        location_text = clean_text(
            location.get("label") if isinstance(location, dict) else location
        )
        if location_text and location_text not in current["locations"]:
            current["locations"].append(location_text)
    jobs: list[RawJob] = []
    for identifier, grouped_item in grouped.items():
        item = grouped_item["item"]
        location_text = "; ".join(grouped_item["locations"]) or None
        jobs.append(
            RawJob(
                title=clean_text(item.get("name") or item.get("title")),
                url=str(
                    item.get("url")
                    or f"https://ats.rippling.com/{target.token}/jobs/{identifier}"
                ),
                location=location_text,
                description=clean_text(item.get("description")),
                remote=True if "remote" in (location_text or "").casefold() else None,
                source="rippling",
                source_job_id=identifier or None,
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
    if target.kind == "ashby":
        return await _ashby(fetcher, target)
    if target.kind == "smartrecruiters":
        return await _smartrecruiters(fetcher, target)
    if target.kind == "recruitee":
        return await _recruitee(fetcher, target)
    if target.kind == "workable":
        return await _workable(fetcher, target)
    if target.kind == "pinpoint":
        return await _pinpoint(fetcher, target)
    if target.kind == "bamboohr":
        return await _bamboohr(fetcher, target)
    if target.kind == "rippling":
        return await _rippling(fetcher, target)
    return []
