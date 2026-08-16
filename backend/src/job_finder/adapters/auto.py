from __future__ import annotations

import re
from dataclasses import dataclass, field

from job_finder.models import Company, RawJob

from .ats import AtsTarget, discover_ats, fetch_ats_jobs
from .base import BlockedError, FetchError, HttpFetcher
from .browser import BrowserRenderer, BrowserUnavailable
from .careers import (
    discover_careers_links,
    is_homepage_redirect,
    is_soft_404,
    looks_like_careers_page,
)
from .html import discover_board_links, extract_html_jobs
from .staffam import extract_staff_am_jobs
from .structured import extract_jsonld_jobs


_BLOCKED_TITLE = re.compile(
    r"\b(just a moment|security checkpoint|access denied|attention required|"
    r"verify (?:that )?you are human|robot check)\b",
    re.IGNORECASE,
)
_BLOCKED_VISIBLE_TEXT = re.compile(
    r"\b(verify (?:that )?you are human|checking your browser|unusual traffic|"
    r"automated queries|enable javascript and cookies to continue|"
    r"complete the security check)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ExtractionResult:
    jobs: list[RawJob]
    adapter: str
    warnings: list[str] = field(default_factory=list)
    resolved_careers_url: str | None = None
    careers_url_discovered: bool = False


def _deduplicate_raw(jobs: list[RawJob]) -> list[RawJob]:
    unique: dict[tuple[str, str], RawJob] = {}
    for job in jobs:
        key = (job.url.rstrip("/"), job.title.casefold())
        unique.setdefault(key, job)
    return list(unique.values())


class AutoAdapter:
    def __init__(
        self,
        fetcher: HttpFetcher,
        *,
        browser: BrowserRenderer | None = None,
        browser_enabled: bool = True,
        max_board_links: int = 2,
    ) -> None:
        self.fetcher = fetcher
        self.browser = browser
        self.browser_enabled = browser_enabled
        self.max_board_links = max_board_links

    @staticmethod
    def _check_blocked(html: str, url: str) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        match = _BLOCKED_TITLE.search(title)
        if match:
            raise BlockedError(f"Blocked page detected at {url}: {match.group(0)[:80]}")
        for element in soup(["script", "style", "template", "noscript", "svg"]):
            element.decompose()
        visible_text = " ".join(soup.get_text(" ", strip=True).split())
        match = _BLOCKED_VISIBLE_TEXT.search(visible_text[:20_000])
        if match:
            raise BlockedError(f"Blocked page detected at {url}: {match.group(0)[:80]}")
        # A bare "captcha" in application JavaScript is common and is not proof of a
        # challenge. Only treat it as blocking on a small, challenge-like document.
        if len(visible_text) < 2_000 and re.search(
            r"\b(?:complete|solve|enter).{0,80}captcha\b|\bcaptcha.{0,80}(?:required|verification)\b",
            visible_text,
            re.IGNORECASE,
        ):
            raise BlockedError(f"CAPTCHA challenge detected at {url}")

    async def _extract_page(
        self, company: Company, page_url: str, html: str, warnings: list[str]
    ) -> tuple[list[RawJob], str]:
        target = discover_ats(page_url, html)
        if target is not None:
            try:
                return await fetch_ats_jobs(self.fetcher, target), target.kind
            except FetchError as exc:
                warnings.append(f"{target.kind} adapter failed: {exc}")

        jobs = extract_staff_am_jobs(html, page_url, company.name)
        if jobs:
            return jobs, "staff.am"

        jobs = extract_jsonld_jobs(html, page_url)
        if jobs:
            return jobs, "jsonld"
        jobs = extract_html_jobs(html, page_url)
        if jobs:
            return jobs, "html"
        return [], "html"

    async def extract(self, company: Company) -> ExtractionResult:
        warnings: list[str] = []
        ats_options = company.adapter_options.get("ats")
        if isinstance(ats_options, dict):
            kind = str(ats_options.get("kind") or "")
            token = str(ats_options.get("token") or "")
            if kind and token:
                target = AtsTarget(
                    kind=kind,
                    token=token,
                    url=str(
                        ats_options.get("url")
                        or company.careers_url
                        or company.website_url
                    ),
                    site=str(ats_options["site"]) if ats_options.get("site") else None,
                )
                try:
                    jobs = await fetch_ats_jobs(self.fetcher, target)
                    return ExtractionResult(
                        _deduplicate_raw(jobs),
                        kind,
                        warnings,
                        resolved_careers_url=target.url,
                    )
                except FetchError as exc:
                    warnings.append(f"Configured {kind} adapter failed: {exc}")
        configured_url = str(company.careers_url) if company.careers_url else None
        initial_error: FetchError | None = None
        initial = None
        if configured_url is not None:
            try:
                initial = await self.fetcher.fetch(configured_url)
                self._check_blocked(initial.text, initial.url)
                if is_soft_404(initial.text):
                    initial_error = FetchError(
                        f"Custom not-found page detected at {initial.url}"
                    )
                    warnings.append(f"Configured careers URL failed: {initial_error}")
                    initial = None
            except BlockedError:
                raise
            except FetchError as exc:
                initial_error = exc
                warnings.append(f"Configured careers URL failed: {exc}")

        if initial is not None and configured_url is not None and not is_homepage_redirect(
            configured_url, initial.url, str(company.website_url)
        ):
            jobs, adapter = await self._extract_page(company, initial.url, initial.text, warnings)
            if jobs:
                return ExtractionResult(
                    _deduplicate_raw(jobs), adapter, warnings, initial.url
                )

            board_links = discover_board_links(
                initial.text, initial.url, limit=self.max_board_links
            )
            for board_url in board_links:
                try:
                    page = await self.fetcher.fetch(board_url)
                    self._check_blocked(page.text, page.url)
                    jobs, adapter = await self._extract_page(
                        company, page.url, page.text, warnings
                    )
                    if jobs:
                        return ExtractionResult(
                            _deduplicate_raw(jobs), adapter, warnings, page.url
                        )
                except BlockedError as exc:
                    warnings.append(str(exc))
                except FetchError as exc:
                    warnings.append(f"Linked job board failed: {exc}")

        if (
            initial is not None
            and configured_url is not None
            and not is_homepage_redirect(configured_url, initial.url, str(company.website_url))
            and self.browser_enabled
            and self.browser is not None
        ):
            try:
                rendered = await self.browser.render(initial.url)
                self._check_blocked(rendered.html, rendered.url)
                jobs, adapter = await self._extract_page(
                    company, rendered.url, rendered.html, warnings
                )
                if jobs:
                    return ExtractionResult(
                        _deduplicate_raw(jobs), f"browser+{adapter}", warnings, rendered.url
                    )
            except BrowserUnavailable as exc:
                warnings.append(str(exc))

        homepage = initial if initial is not None and configured_url is not None and is_homepage_redirect(
            configured_url, initial.url, str(company.website_url)
        ) else None
        if homepage is not None:
            warnings.append(
                f"Configured careers URL redirected to the homepage: {initial.url}"
            )
        else:
            try:
                homepage = await self.fetcher.fetch(str(company.website_url))
                self._check_blocked(homepage.text, homepage.url)
            except (FetchError, BlockedError) as exc:
                warnings.append(f"Careers discovery homepage failed: {exc}")

        if homepage is not None:
            candidates = discover_careers_links(
                homepage.text,
                homepage.url,
                str(company.website_url),
                limit=5,
            )
            if not candidates and self.browser_enabled and self.browser is not None:
                try:
                    rendered_homepage = await self.browser.render(homepage.url)
                    self._check_blocked(rendered_homepage.html, rendered_homepage.url)
                    if not is_soft_404(rendered_homepage.html):
                        candidates = discover_careers_links(
                            rendered_homepage.html,
                            rendered_homepage.url,
                            str(company.website_url),
                            limit=5,
                        )
                except BrowserUnavailable as exc:
                    warnings.append(f"Careers discovery browser failed: {exc}")
            rejected_urls = {
                url.rstrip("/")
                for url in company.metadata.get("Rejected Careers URLs", "").splitlines()
                if url.strip()
            }
            candidates = [
                url for url in candidates if url.rstrip("/") not in rejected_urls
            ]
            empty_candidate: tuple[str, str] | None = None
            for candidate_url in candidates:
                if configured_url and candidate_url.rstrip("/") == configured_url.rstrip("/"):
                    continue
                try:
                    page = await self.fetcher.fetch(candidate_url)
                    self._check_blocked(page.text, page.url)
                    if is_soft_404(page.text):
                        warnings.append(
                            f"Discovered candidate is a custom not-found page: {page.url}"
                        )
                        continue
                    jobs, candidate_adapter = await self._extract_page(
                        company, page.url, page.text, warnings
                    )
                    if jobs:
                        warnings.append(
                            f"Discovered careers URL from website: {page.url}"
                        )
                        return ExtractionResult(
                            _deduplicate_raw(jobs),
                            candidate_adapter,
                            warnings,
                            resolved_careers_url=page.url,
                            careers_url_discovered=True,
                        )
                    if looks_like_careers_page(page.text, page.url):
                        empty_candidate = empty_candidate or (page.url, candidate_adapter)
                except BlockedError as exc:
                    warnings.append(f"Discovered careers page blocked: {exc}")
                except FetchError as exc:
                    warnings.append(f"Discovered careers page failed: {exc}")
            if empty_candidate is not None:
                resolved_url, candidate_adapter = empty_candidate
                warnings.append(f"Discovered careers URL from website: {resolved_url}")
                return ExtractionResult(
                    [],
                    candidate_adapter,
                    warnings,
                    resolved_careers_url=resolved_url,
                    careers_url_discovered=True,
                )

        if initial_error is not None:
            raise initial_error
        resolved_url = initial.url if initial is not None else configured_url
        return ExtractionResult([], "html", warnings, resolved_url)
