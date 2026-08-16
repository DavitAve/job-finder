from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from job_finder.models import RawJob

from .structured import clean_text


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _localized(value: Any) -> str:
    if isinstance(value, str):
        return clean_text(value)
    if not isinstance(value, dict):
        return ""
    for language in ("en", "am_en", "ru", "am"):
        if value.get(language):
            return clean_text(value[language])
    return ""


def extract_staff_am_jobs(html: str, page_url: str, company_name: str) -> list[RawJob]:
    if not urlsplit(page_url).netloc.lower().endswith("staff.am"):
        return []
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None:
        return []
    try:
        payload = json.loads(script.string or script.get_text())
    except (json.JSONDecodeError, TypeError):
        return []

    jobs: dict[int, RawJob] = {}
    for item in _walk(payload):
        job_id = item.get("id")
        company = item.get("companiesStruct")
        category = item.get("category")
        slug = item.get("slug")
        if not isinstance(job_id, int) or not isinstance(company, dict):
            continue
        if _localized(company.get("title")).casefold() != company_name.casefold():
            continue
        if not isinstance(category, dict) or not isinstance(slug, (dict, str)):
            continue
        title = _localized(item.get("title"))
        category_code = clean_text(category.get("code"))
        slug_text = _localized(slug)
        if not title or not category_code or not slug_text:
            continue
        city = item.get("job_city")
        location = _localized(city.get("title")) if isinstance(city, dict) else None
        activated = item.get("activated_at")
        published_at = None
        if isinstance(activated, dict):
            published_at = clean_text(activated.get("staffam")) or None
        jobs[job_id] = RawJob(
            title=title,
            url=f"https://staff.am/jobs/{category_code}/{slug_text}",
            location=location or None,
            published_at=published_at,
            source="staff.am",
            source_job_id=str(job_id),
        )
    return list(jobs.values())
