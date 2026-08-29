from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from .structured import clean_text


NEXT_TEXT = re.compile(
    r"^(?:(?:go to\s+)?next(?:\s+page)?|older|more|следующая|далее|след\.?|"
    r"следующая страница|հաջորդ|հաջորդ էջ)\s*[›»→>]?$|^[›»→>]$",
    re.IGNORECASE,
)
_PAGINATION_HINT = re.compile(r"pag(?:e|ing|ination)|pager", re.IGNORECASE)
LOAD_MORE_TEXT = re.compile(
    r"^(?:load|show|view)\s+more(?:\s+(?:jobs?|roles?|positions?|vacancies))?$|"
    r"^(?:показать|загрузить)\s+(?:ещ[её]|больше)(?:\s+вакансий)?$|"
    r"^ցույց տալ ավելին$",
    re.IGNORECASE,
)


def canonical_page_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    return urlunsplit(
        (parts.scheme.casefold(), parts.netloc.casefold(), path.rstrip("/") or "/", parts.query, "")
    )


def _safe_link(anchor: Tag, page_url: str) -> str | None:
    raw_href = anchor.get("href")
    if not raw_href:
        return None
    href = urljoin(page_url, str(raw_href))
    current = urlsplit(page_url)
    target = urlsplit(href)
    if target.scheme not in {"http", "https"} or target.netloc.casefold() != current.netloc.casefold():
        return None
    return href


def _is_disabled(anchor: Tag) -> bool:
    classes = " ".join(str(value) for value in anchor.get("class", []))
    parent_classes = " ".join(
        str(value) for value in anchor.parent.get("class", [])
    ) if isinstance(anchor.parent, Tag) else ""
    return (
        anchor.get("aria-disabled") == "true"
        or "disabled" in {value.casefold() for value in classes.split()}
        or "disabled" in {value.casefold() for value in parent_classes.split()}
    )


def discover_next_page_url(html: str, page_url: str, visited: set[str]) -> str | None:
    """Return one conservative same-domain next-page URL, or ``None``.

    Explicit ``rel=next`` and labelled Next controls take precedence. Numeric links
    are considered only inside a pagination-like container, which avoids following
    years, addresses, or unrelated navigation numbers.
    """
    soup = BeautifulSoup(html, "lxml")
    canonical_visited = {canonical_page_url(url) for url in visited}

    for anchor in soup.find_all(["a", "link"], href=True):
        rel = {str(value).casefold() for value in (anchor.get("rel") or [])}
        if "next" not in rel or _is_disabled(anchor):
            continue
        href = _safe_link(anchor, page_url)
        if href and canonical_page_url(href) not in canonical_visited:
            return href

    for anchor in soup.find_all("a", href=True):
        if _is_disabled(anchor):
            continue
        text = clean_text(anchor.get_text(" ", strip=True))
        aria = clean_text(str(anchor.get("aria-label") or ""))
        title = clean_text(str(anchor.get("title") or ""))
        if not any(NEXT_TEXT.fullmatch(value) for value in (text, aria, title) if value):
            continue
        href = _safe_link(anchor, page_url)
        if href and canonical_page_url(href) not in canonical_visited:
            return href

    containers: list[Tag] = []
    for element in soup.find_all(["nav", "ul", "ol", "div"]):
        marker = " ".join(
            [
                str(element.get("aria-label") or ""),
                str(element.get("id") or ""),
                " ".join(str(value) for value in element.get("class", [])),
            ]
        )
        if _PAGINATION_HINT.search(marker):
            containers.append(element)

    for container in containers:
        current_number: int | None = None
        for element in container.find_all(["a", "span", "li"]):
            text = clean_text(element.get_text(" ", strip=True))
            if not text.isdigit():
                continue
            classes = {str(value).casefold() for value in element.get("class", [])}
            parent_classes = {
                str(value).casefold() for value in element.parent.get("class", [])
            } if isinstance(element.parent, Tag) else set()
            if element.get("aria-current") in {"page", "true"} or "active" in classes | parent_classes:
                current_number = int(text)
                break
        if current_number is None:
            query = parse_qs(urlsplit(page_url).query)
            for key in ("page", "paged", "p", "pageNumber"):
                value = query.get(key, [""])[0]
                if value.isdigit():
                    current_number = int(value)
                    break

        numeric: list[tuple[int, str]] = []
        for anchor in container.find_all("a", href=True):
            if _is_disabled(anchor):
                continue
            text = clean_text(anchor.get_text(" ", strip=True))
            if not text.isdigit():
                continue
            href = _safe_link(anchor, page_url)
            if href and canonical_page_url(href) not in canonical_visited:
                numeric.append((int(text), href))
        if not numeric:
            continue
        numeric.sort(key=lambda item: item[0])
        if current_number is not None:
            exact = next((href for number, href in numeric if number == current_number + 1), None)
            if exact:
                return exact
            later = next((href for number, href in numeric if number > current_number), None)
            if later:
                return later
        return numeric[0][1]
    return None


def needs_browser_pagination(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    for control in soup.find_all(["button", "a", "div"]):
        is_button = control.name == "button" or control.get("role") == "button"
        values = (
            clean_text(control.get_text(" ", strip=True)),
            clean_text(str(control.get("aria-label") or "")),
            clean_text(str(control.get("title") or "")),
        )
        if (control.name == "a" or is_button) and any(
            LOAD_MORE_TEXT.fullmatch(value) for value in values if value
        ):
            return True
        if is_button and any(
            NEXT_TEXT.fullmatch(value) for value in values if value
        ):
            return True
    return bool(
        re.search(
            r"(?:infinite[-_ ]?scroll|load[-_ ]?more|data-(?:next|page)|"
            r"IntersectionObserver|hasNextPage)",
            html,
            re.IGNORECASE,
        )
    )
