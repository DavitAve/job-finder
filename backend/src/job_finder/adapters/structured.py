from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_finder.models import RawJob


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if "<" not in text and ">" not in text:
        return " ".join(text.split())
    return " ".join(BeautifulSoup(text, "lxml").get_text(" ", strip=True).split())


def _walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        job_type = value.get("@type")
        types = job_type if isinstance(job_type, list) else [job_type]
        if any(str(item).casefold() == "jobposting" for item in types):
            yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _address_text(address: Any) -> str:
    if isinstance(address, str):
        return clean_text(address)
    if not isinstance(address, dict):
        return ""
    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("addressCountry"),
    ]
    return ", ".join(clean_text(part) for part in parts if clean_text(part))


def _location(job: dict[str, Any]) -> tuple[str | None, bool | None]:
    values: list[str] = []
    locations = job.get("jobLocation") or []
    if not isinstance(locations, list):
        locations = [locations]
    for location in locations:
        if isinstance(location, dict):
            text = _address_text(location.get("address"))
            if text:
                values.append(text)

    remote = None
    location_type = str(job.get("jobLocationType") or "")
    if "TELECOMMUTE" in location_type.upper():
        remote = True
        values.append("Remote")

    requirements = job.get("applicantLocationRequirements") or []
    if not isinstance(requirements, list):
        requirements = [requirements]
    for requirement in requirements:
        if isinstance(requirement, dict):
            name = clean_text(requirement.get("name"))
            if name:
                values.append(name)
    unique = list(dict.fromkeys(values))
    return ("; ".join(unique) or None), remote


def extract_jsonld_jobs(html: str, page_url: str) -> list[RawJob]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[RawJob] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        payload = script.string or script.get_text()
        if not payload.strip():
            continue
        try:
            document = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _walk_json(document):
            title = clean_text(item.get("title"))
            url = urljoin(page_url, str(item.get("url") or page_url))
            if not title:
                continue
            identifier = item.get("identifier")
            if isinstance(identifier, dict):
                identifier = identifier.get("value") or identifier.get("name")
            source_job_id = clean_text(identifier) or None
            location, remote = _location(item)
            jobs.append(
                RawJob(
                    title=title,
                    url=url,
                    location=location,
                    remote=remote,
                    description=clean_text(item.get("description")),
                    published_at=clean_text(item.get("datePosted")) or None,
                    source="jsonld",
                    source_job_id=source_job_id,
                )
            )
    return jobs
