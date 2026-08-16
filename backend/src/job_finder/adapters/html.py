from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from job_finder.models import RawJob

from .structured import clean_text


_ROLE_TEXT = re.compile(
    r"\b(front[\s-]?end|ui|web|react|vue|angular|javascript|typescript|"
    r"developer|engineer|architect)\b",
    re.IGNORECASE,
)
_JOB_PATH = re.compile(r"/(job|jobs|career|careers|position|positions|vacanc)", re.IGNORECASE)
_GENERIC_LINK_TEXT = re.compile(
    r"^(jobs?|careers?|open positions?|view (?:all )?jobs?|learn more|apply(?: now)?)$",
    re.IGNORECASE,
)
_BOARD_TEXT = re.compile(
    r"\b(jobs?|open positions?|open roles?|vacancies|view (?:all )?jobs?|search jobs?|"
    r"join (?:us|our team)|career opportunities)\b",
    re.IGNORECASE,
)


def _candidate_title(anchor: Tag) -> str:
    text = clean_text(anchor.get_text(" ", strip=True))
    if text and not _GENERIC_LINK_TEXT.fullmatch(text) and _ROLE_TEXT.search(text):
        return text
    parent: Tag | None = anchor
    for _ in range(3):
        parent = parent.parent if isinstance(parent, Tag) else None
        if parent is None:
            break
        heading = parent.find(["h1", "h2", "h3", "h4", "h5", "strong"])
        if heading:
            heading_text = clean_text(heading.get_text(" ", strip=True))
            if 3 <= len(heading_text) <= 180 and _ROLE_TEXT.search(heading_text):
                return heading_text
    return ""


def extract_html_jobs(html: str, page_url: str) -> list[RawJob]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[RawJob] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, str(anchor.get("href")))
        if urlsplit(href).scheme not in {"http", "https"}:
            continue
        title = _candidate_title(anchor)
        if not title or href in seen:
            continue
        if not (_JOB_PATH.search(urlsplit(href).path) or _ROLE_TEXT.search(title)):
            continue
        seen.add(href)
        container: Tag | None = anchor.parent if isinstance(anchor.parent, Tag) else None
        description = clean_text(container.get_text(" ", strip=True)) if container else ""
        jobs.append(
            RawJob(
                title=title,
                url=href,
                description=description[:4000],
                source="html",
            )
        )
    return jobs


def discover_board_links(html: str, page_url: str, limit: int = 2) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    current = urlsplit(page_url)
    scored: list[tuple[int, str]] = []
    seen: set[str] = {page_url.rstrip("/")}
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, str(anchor.get("href")))
        parts = urlsplit(href)
        if parts.scheme not in {"http", "https"} or href.rstrip("/") in seen:
            continue
        text = clean_text(anchor.get_text(" ", strip=True))
        score = 0
        if _BOARD_TEXT.search(text):
            score += 3
        if _JOB_PATH.search(parts.path):
            score += 2
        if parts.netloc != current.netloc:
            score += 1
        if score >= 3:
            seen.add(href.rstrip("/"))
            scored.append((score, href))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [href for _, href in scored[:limit]]
