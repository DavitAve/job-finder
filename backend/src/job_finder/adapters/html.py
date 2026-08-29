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
_NO_OPENINGS = re.compile(
    r"\b(no (?:current |open )?(?:jobs?|openings?|vacancies|positions)|"
    r"there are no .{0,30}(?:jobs?|openings?|vacancies|positions))\b",
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
        # Many custom career cards use a generic "See role" link and keep the
        # actual title in an adjacent paragraph/span instead of a heading.
        for candidate in parent.find_all(
            ["p", "span", "h1", "h2", "h3", "h4", "h5", "strong"],
            recursive=True,
        ):
            candidate_text = clean_text(candidate.get_text(" ", strip=True))
            if (
                3 <= len(candidate_text) <= 180
                and not _GENERIC_LINK_TEXT.fullmatch(candidate_text)
                and _ROLE_TEXT.search(candidate_text)
            ):
                return candidate_text
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


def has_visible_job_listings(html: str) -> bool:
    """Conservatively detect rendered vacancy titles that generic parsing missed."""
    soup = BeautifulSoup(html, "lxml")
    for element in soup(["script", "style", "template", "noscript", "svg"]):
        element.decompose()
    visible = clean_text(soup.get_text(" ", strip=True))
    if _NO_OPENINGS.search(visible):
        return False
    strong_containers = (
        "article, [role='listitem'], [data-job-id], [class*='job-card'], "
        "[class*='job_card'], [class*='job-listing'], [class*='job_listing']"
    )
    for element in soup.select(strong_containers):
        text = clean_text(element.get_text(" ", strip=True))
        if 4 <= len(text) <= 300 and _ROLE_TEXT.search(text):
            return True
    # A plain list item or table row is weak evidence: marketing/FAQ lists often
    # mention software development. Require a vacancy/apply link in that row.
    for element in soup.select("li, tr"):
        text = clean_text(element.get_text(" ", strip=True))
        if not (4 <= len(text) <= 300 and _ROLE_TEXT.search(text)):
            continue
        for anchor in element.find_all("a", href=True):
            href = urljoin("https://placeholder.invalid", str(anchor.get("href")))
            anchor_text = clean_text(anchor.get_text(" ", strip=True))
            if _JOB_PATH.search(urlsplit(href).path) or re.search(
                r"\b(?:apply|see|view)\s+(?:role|job)|apply now\b",
                anchor_text,
                re.IGNORECASE,
            ):
                return True
    return False


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
