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
_CAREER_HEADING = re.compile(
    r"\b(careers?|jobs?|vacanc(?:y|ies)|open (?:roles?|positions?))\b|"
    r"РєР°СЂСЊРµСЂ[Р°С‹]|РІР°РєР°РЅСЃРёРё|ХЎХ·Х­ХЎХїХЎХїХҐХІ|ХЇХЎЦЂХ«ХҐЦЂХЎ",
    re.IGNORECASE,
)
_CAREER_PATH = re.compile(
    r"/(?:careers?|jobs?|vacanc(?:y|ies)|openings?|positions?|join-us|work-with-us)(?:/|$)",
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
    "join.com",
    "jobvite.com",
    "lever.co",
    "myworkdayjobs.com",
    "personio.com",
    "pinpointhq.com",
    "recruitee.com",
    "recruitcrm.io",
    "rippling.com",
    "smartrecruiters.com",
    "teamtailor.com",
    "zohorecruit.com",
    "freshteam.com",
    "workable.com",
)
_COMMON_CAREERS_PATHS = (
    "/careers",
    "/jobs",
    "/career",
    "/vacancies",
    "/about/careers",
    "/company/careers",
    "/join-us",
    "/open-positions",
    "/work-with-us",
    "/about-us/careers",
    "/en/careers",
    "/en/jobs",
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
    parts = urlsplit(url)
    host_prefix = (parts.hostname or "").casefold().split(".", 1)[0]
    if (
        _known_ats(url)
        or _CAREER_PATH.search(parts.path)
        or host_prefix in {"career", "careers", "job", "jobs"}
    ):
        return True
    return looks_like_careers_content(html)


def looks_like_careers_content(html: str) -> bool:
    """Verify careers semantics from content, without trusting a guessed URL path."""
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find(["title", "h1"])
    return bool(
        heading
        and _CAREER_HEADING.search(clean_text(heading.get_text(" ", strip=True)))
    )


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


def discover_sitemap_careers(xml: str, website_url: str, *, limit: int = 5) -> list[str]:
    """Return safe careers/job URLs from a site's sitemap or sitemap index."""
    soup = BeautifulSoup(xml, "xml")
    candidates: list[str] = []
    seen: set[str] = set()
    for location in soup.find_all("loc"):
        href = _canonical_candidate(clean_text(location.get_text(" ", strip=True)))
        parts = urlsplit(href)
        if (
            parts.scheme in {"http", "https"}
            and href not in seen
            and (_same_organization(href, website_url) or _known_ats(href))
            and (_CAREER_PATH.search(parts.path) or _known_ats(href))
        ):
            seen.add(href)
            candidates.append(href)
            if len(candidates) >= limit:
                break
    return candidates


def discover_sitemap_documents(xml: str, website_url: str, *, limit: int = 3) -> list[str]:
    """Find bounded same-organization child sitemap documents."""
    soup = BeautifulSoup(xml, "xml")
    documents: list[str] = []
    seen: set[str] = set()
    for location in soup.find_all("loc"):
        href = _canonical_candidate(clean_text(location.get_text(" ", strip=True)))
        path = urlsplit(href).path.casefold()
        if (
            href not in seen
            and _same_organization(href, website_url)
            and (path.endswith(".xml") or "sitemap" in path)
        ):
            seen.add(href)
            documents.append(href)
            if len(documents) >= limit:
                break
    return documents


def website_homepage_candidates(website_url: str) -> list[str]:
    """Return the configured site plus a safe www/non-www origin alternative."""
    parts = urlsplit(website_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return [website_url]
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    origin = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
    alternate_host = host.removeprefix("www.") if host.startswith("www.") else f"www.{host}"
    alternate = urlunsplit((parts.scheme, f"{alternate_host}{port}", "/", "", ""))
    configured = _canonical_candidate(website_url)
    values = [configured]
    if _canonical_candidate(origin) not in values:
        values.append(_canonical_candidate(origin))
    if _canonical_candidate(alternate) not in values:
        values.append(_canonical_candidate(alternate))
    return values


def common_careers_candidates(
    website_url: str,
    *,
    excluded: set[str] | None = None,
    limit: int = 5,
) -> list[str]:
    parts = urlsplit(website_url)
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    excluded = {value.rstrip("/") for value in (excluded or set())}
    return [
        urljoin(f"{origin}/", path.lstrip("/"))
        for path in _COMMON_CAREERS_PATHS
        if urljoin(f"{origin}/", path.lstrip("/")).rstrip("/") not in excluded
    ][:limit]
