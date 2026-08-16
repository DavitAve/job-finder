from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .structured import clean_text


_CAREER_TEXT = re.compile(
    r"\b(careers?|jobs?|vacanc(?:y|ies)|open (?:roles?|positions?)|"
    r"join (?:us|our team)|work with us|карьер[аы]|вакансии)\b|"
    r"աշխատատեղ|կարիերա",
    re.IGNORECASE,
)
_CAREER_PATH = re.compile(
    r"/(?:careers?|jobs?|vacanc(?:y|ies)|openings?|positions?)(?:/|$)",
    re.IGNORECASE,
)
_SOFT_404 = re.compile(
    r"\b(?:404|page not found|not found|page (?:does not|doesn't) exist|"
    r"we can't find (?:that|this) page|nothing here)\b|"
    r"страниц[аы] не найден[аы]?|такой страницы не существует|"
    r"էջը չի գտնվել|էջը գոյություն չունի",
    re.IGNORECASE,
)
_KNOWN_ATS_DOMAINS = (
    "ashbyhq.com",
    "bamboohr.com",
    "breezy.hr",
    "comeet.co",
    "gem.com",
    "greenhouse.io",
    "jobvite.com",
    "lever.co",
    "myworkdayjobs.com",
    "personio.com",
    "recruitee.com",
    "smartrecruiters.com",
    "teamtailor.com",
    "workable.com",
)


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _same_organization(left: str, right: str) -> bool:
    left_host, right_host = _host(left), _host(right)
    if not left_host or not right_host:
        return False
    return (
        left_host == right_host
        or left_host.endswith(f".{right_host}")
        or right_host.endswith(f".{left_host}")
    )


def _known_ats(url: str) -> bool:
    host = _host(url)
    return any(host == domain or host.endswith(f".{domain}") for domain in _KNOWN_ATS_DOMAINS)


def looks_like_careers_page(html: str, url: str) -> bool:
    if _known_ats(url) or _CAREER_PATH.search(urlsplit(url).path):
        return True
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find(["title", "h1"])
    return bool(heading and _CAREER_TEXT.search(clean_text(heading.get_text(" ", strip=True))))


def is_soft_404(html: str) -> bool:
    """Detect custom not-found pages that incorrectly return HTTP 200."""
    soup = BeautifulSoup(html, "lxml")
    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    heading = soup.find("h1")
    heading_text = clean_text(heading.get_text(" ", strip=True)) if heading else ""
    if _SOFT_404.search(f"{title} {heading_text}"):
        return True
    for element in soup(["script", "style", "template", "noscript", "svg"]):
        element.decompose()
    visible = clean_text(soup.get_text(" ", strip=True))
    return len(visible) <= 5_000 and bool(_SOFT_404.search(visible))


def _canonical_candidate(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def is_homepage_redirect(requested_url: str, final_url: str, website_url: str) -> bool:
    """Return true when a careers request silently lands on the company homepage."""
    requested_path = urlsplit(requested_url).path.rstrip("/")
    final = urlsplit(final_url)
    website = urlsplit(website_url)
    return bool(
        requested_path
        and requested_path != "/"
        and _same_organization(final_url, website_url)
        and final.path.rstrip("/") in {"", website.path.rstrip("/")}
    )


def discover_careers_links(
    html: str,
    page_url: str,
    website_url: str,
    *,
    limit: int = 5,
) -> list[str]:
    """Find bounded, safe careers candidates on a company's own website."""
    soup = BeautifulSoup(html, "lxml")
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for order, anchor in enumerate(soup.find_all("a", href=True)):
        href = _canonical_candidate(urljoin(page_url, str(anchor.get("href"))))
        parts = urlsplit(href)
        if parts.scheme not in {"http", "https"} or href in seen:
            continue
        if not (_same_organization(href, website_url) or _known_ats(href)):
            continue
        text = clean_text(anchor.get_text(" ", strip=True))
        score = 0
        if _CAREER_TEXT.search(text):
            score += 5
        if _CAREER_PATH.search(parts.path):
            score += 3
        if _known_ats(href):
            score += 4
        if score < 3:
            continue
        seen.add(href)
        scored.append((score, -order, href))
    scored.sort(reverse=True)
    return [href for _, _, href in scored[:limit]]
