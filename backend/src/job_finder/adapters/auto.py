from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from job_finder.models import Company, RawJob

from .ats import AtsTarget, discover_ats, fetch_ats_jobs
from .base import BlockedError, FetchError, HttpFetcher, RobotsDeniedError
from .browser import BrowserRenderer, BrowserUnavailable, RenderedPage
from .careers import (
    discover_careers_links,
    discover_sitemap_careers,
    discover_sitemap_documents,
    common_careers_candidates,
    is_homepage_redirect,
    is_soft_404,
    looks_like_careers_content,
    looks_like_careers_page,
    website_homepage_candidates,
)
from .html import discover_board_links, extract_html_jobs, has_visible_job_listings
from .pagination import (
    canonical_page_url,
    discover_next_page_url,
    needs_browser_pagination,
)
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


_VISIBLE_UNPARSED_WARNING = "Visible job listings were found, but the parser extracted none"
_CAREERS_NOT_FOUND_WARNING = "Careers page was not found on the company website"


def _warn_visible_unparsed(html: str, warnings: list[str]) -> None:
    if has_visible_job_listings(html) and _VISIBLE_UNPARSED_WARNING not in warnings:
        warnings.append(_VISIBLE_UNPARSED_WARNING)


def _deduplicate_raw(jobs: list[RawJob]) -> list[RawJob]:
    unique: dict[tuple[str, str], RawJob] = {}
    for job in jobs:
        key = (job.url.rstrip("/"), job.title.casefold())
        unique.setdefault(key, job)
    return list(unique.values())


def _is_generic_adapter(adapter: str) -> bool:
    return adapter.split("+", 1)[0] in {"html", "jsonld", "staff.am"}


class AutoAdapter:
    def __init__(
        self,
        fetcher: HttpFetcher,
        *,
        browser: BrowserRenderer | None = None,
        browser_enabled: bool = True,
        max_board_links: int = 3,
        max_careers_candidates: int = 10,
        max_pagination_pages: int = 20,
        max_jobs_per_company: int = 500,
    ) -> None:
        self.fetcher = fetcher
        self.browser = browser
        self.browser_enabled = browser_enabled
        self.max_board_links = max_board_links
        self.max_careers_candidates = max_careers_candidates
        self.max_pagination_pages = max_pagination_pages
        self.max_jobs_per_company = max_jobs_per_company

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
        self,
        company: Company,
        page_url: str,
        html: str,
        warnings: list[str],
        *,
        detect_ats: bool = True,
    ) -> tuple[list[RawJob], str]:
        target = discover_ats(page_url, html) if detect_ats else None
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
        if looks_like_careers_page(html, page_url):
            _warn_visible_unparsed(html, warnings)
        return [], "html"

    async def _extract_http_paginated(
        self,
        company: Company,
        page_url: str,
        html: str,
        warnings: list[str],
        *,
        allow_browser: bool = True,
        detect_ats: bool = True,
    ) -> tuple[list[RawJob], str]:
        jobs, adapter = await self._extract_page(
            company, page_url, html, warnings, detect_ats=detect_ats
        )
        if adapter not in {"html", "jsonld", "staff.am"}:
            return jobs, adapter

        current_url = page_url
        current_html = html
        visited = {canonical_page_url(page_url)}
        seen_content = {
            hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()
        }
        browser_pagination_needed = needs_browser_pagination(html)
        page_count = 1
        while page_count < self.max_pagination_pages:
            next_url = discover_next_page_url(current_html, current_url, visited)
            if next_url is None:
                break
            try:
                page = await self.fetcher.fetch(next_url)
                self._check_blocked(page.text, page.url)
                if is_soft_404(page.text):
                    warnings.append(f"Pagination reached a custom not-found page: {page.url}")
                    break
            except (FetchError, BlockedError) as exc:
                warnings.append(f"Pagination page failed: {exc}")
                break

            canonical = canonical_page_url(page.url)
            digest = hashlib.sha256(
                page.text.encode("utf-8", errors="replace")
            ).hexdigest()
            if canonical in visited or digest in seen_content:
                warnings.append(f"Pagination loop stopped at {page.url}")
                break
            visited.add(canonical)
            seen_content.add(digest)
            page_count += 1
            had_jobs = bool(jobs)
            page_jobs, page_adapter = await self._extract_page(
                company,
                page.url,
                page.text,
                warnings,
                detect_ats=detect_ats,
            )
            jobs.extend(page_jobs)
            if page_adapter not in {"html", "jsonld", "staff.am"}:
                adapter = page_adapter
                break
            if not had_jobs and page_jobs:
                adapter = page_adapter
            current_url = page.url
            current_html = page.text
            browser_pagination_needed = (
                browser_pagination_needed or needs_browser_pagination(page.text)
            )
            jobs = _deduplicate_raw(jobs)
            if len(jobs) >= self.max_jobs_per_company:
                warnings.append(
                    f"Pagination stopped at {self.max_jobs_per_company} raw jobs"
                )
                return jobs[: self.max_jobs_per_company], f"{adapter}+pagination"

        if page_count >= self.max_pagination_pages and discover_next_page_url(
            current_html, current_url, visited
        ):
            warnings.append(
                f"HTML pagination stopped at {self.max_pagination_pages} pages"
            )
        suffix = "+pagination" if page_count > 1 and not adapter.endswith("+pagination") else ""
        jobs = _deduplicate_raw(jobs)[: self.max_jobs_per_company]
        if (
            self.browser_enabled
            and self.browser is not None
            and browser_pagination_needed
            and allow_browser
        ):
            try:
                browser_jobs, browser_adapter, _ = await self._extract_browser_paginated(
                    company, page_url, warnings
                )
                if browser_jobs:
                    return (
                        _deduplicate_raw([*jobs, *browser_jobs])[: self.max_jobs_per_company],
                        browser_adapter,
                    )
            except BrowserUnavailable as exc:
                warnings.append(str(exc))
        return jobs, f"{adapter}{suffix}"

    async def _extract_browser_paginated(
        self,
        company: Company,
        url: str,
        warnings: list[str],
        *,
        paginate: bool = True,
    ) -> tuple[list[RawJob], str, str]:
        assert self.browser is not None
        render_paginated = getattr(self.browser, "render_paginated", None)
        render = getattr(self.browser, "render", None)
        if paginate and callable(render_paginated):
            batch = await render_paginated(url)
            rendered_pages = batch.pages
            warnings.extend(batch.warnings)
        elif callable(render):
            rendered_pages = [await render(url)]
        elif callable(render_paginated):
            # Keep compatibility with small custom renderers that expose only
            # the paginated interface.
            batch = await render_paginated(url)
            rendered_pages = batch.pages[:1]
            warnings.extend(batch.warnings)
        else:
            raise BrowserUnavailable("Browser renderer has no render method")

        jobs: list[RawJob] = []
        adapter = "html"
        resolved_url = url
        for index, rendered in enumerate(rendered_pages):
            if not isinstance(rendered, RenderedPage):
                continue
            self._check_blocked(rendered.html, rendered.url)
            page_jobs, page_adapter = await self._extract_page(
                company, rendered.url, rendered.html, warnings
            )
            if index == 0 or (not jobs and page_jobs):
                adapter = page_adapter
                resolved_url = rendered.url
            jobs.extend(page_jobs)
            jobs = _deduplicate_raw(jobs)
            if page_adapter not in {"html", "jsonld", "staff.am"}:
                break
            if len(jobs) >= self.max_jobs_per_company:
                warnings.append(
                    f"Browser pagination stopped at {self.max_jobs_per_company} raw jobs"
                )
                jobs = jobs[: self.max_jobs_per_company]
                break
        suffix = "+pagination" if len(rendered_pages) > 1 else ""
        return jobs, f"browser+{adapter}{suffix}", resolved_url

    async def extract(self, company: Company) -> ExtractionResult:
        warnings: list[str] = []
        discovery_browser_used = False
        candidate_browser_used = False
        configured_url = str(company.careers_url or company.website_url)
        if company.adapter == "browser":
            if not self.browser_enabled or self.browser is None:
                raise BrowserUnavailable("Configured browser adapter is unavailable")
            jobs, adapter, rendered_url = await self._extract_browser_paginated(
                company, configured_url, warnings
            )
            return ExtractionResult(
                _deduplicate_raw(jobs),
                adapter,
                warnings,
                resolved_careers_url=rendered_url,
            )
        if company.adapter == "html":
            page = await self.fetcher.fetch(configured_url)
            self._check_blocked(page.text, page.url)
            if is_soft_404(page.text):
                raise FetchError(f"Custom not-found page detected at {page.url}")
            jobs, adapter = await self._extract_http_paginated(
                company,
                page.url,
                page.text,
                warnings,
                allow_browser=False,
                detect_ats=False,
            )
            return ExtractionResult(
                _deduplicate_raw(jobs),
                adapter,
                warnings,
                resolved_careers_url=page.url,
            )
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
            direct_ats = discover_ats(configured_url, "")
            if direct_ats is not None:
                try:
                    jobs = await fetch_ats_jobs(self.fetcher, direct_ats)
                    return ExtractionResult(
                        _deduplicate_raw(jobs),
                        direct_ats.kind,
                        warnings,
                        resolved_careers_url=configured_url,
                    )
                except FetchError as exc:
                    warnings.append(f"{direct_ats.kind} adapter failed: {exc}")
            try:
                initial = await self.fetcher.fetch(configured_url)
                self._check_blocked(initial.text, initial.url)
                if is_soft_404(initial.text):
                    initial_error = FetchError(
                        f"Custom not-found page detected at {initial.url}"
                    )
                    warnings.append(f"Configured careers URL failed: {initial_error}")
                    initial = None
            except BlockedError as exc:
                initial_error = exc
                warnings.append(f"Configured careers URL blocked: {exc}")
            except FetchError as exc:
                initial_error = exc
                warnings.append(f"Configured careers URL failed: {exc}")

        if (
            initial is None
            and configured_url is not None
            and isinstance(initial_error, BlockedError)
            and not isinstance(initial_error, RobotsDeniedError)
            and "HTTP 403" in str(initial_error)
            and self.browser_enabled
            and self.browser is not None
        ):
            try:
                jobs, adapter, rendered_url = await self._extract_browser_paginated(
                    company, configured_url, warnings, paginate=False
                )
                warnings.append("HTTP 403 recovered with browser fallback")
                return ExtractionResult(
                    _deduplicate_raw(jobs), adapter, warnings, rendered_url
                )
            except (BrowserUnavailable, BlockedError) as exc:
                warnings.append(f"Blocked careers browser fallback failed: {exc}")
            # A reachable but protected careers URL is authoritative. Looking for
            # guessed alternatives on the homepage only adds delay and can hide
            # the real blocked status.
            raise initial_error

        if initial is not None and configured_url is not None and not is_homepage_redirect(
            configured_url, initial.url, str(company.website_url)
        ):
            jobs, adapter = await self._extract_http_paginated(
                company, initial.url, initial.text, warnings
            )
            if jobs:
                return ExtractionResult(
                    _deduplicate_raw(jobs), adapter, warnings, initial.url
                )
            if not _is_generic_adapter(adapter):
                return ExtractionResult(
                    [], adapter, warnings, resolved_careers_url=initial.url
                )

            board_links = discover_board_links(
                initial.text, initial.url, limit=self.max_board_links
            )
            for board_url in board_links:
                try:
                    page = await self.fetcher.fetch(board_url)
                    self._check_blocked(page.text, page.url)
                    jobs, adapter = await self._extract_http_paginated(
                        company, page.url, page.text, warnings, allow_browser=False
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
            and not needs_browser_pagination(initial.text)
        ):
            try:
                jobs, adapter, rendered_url = await self._extract_browser_paginated(
                    company,
                    initial.url,
                    warnings,
                    paginate=needs_browser_pagination(initial.text),
                )
                if jobs:
                    return ExtractionResult(
                        _deduplicate_raw(jobs), adapter, warnings, rendered_url
                    )
            except BrowserUnavailable as exc:
                warnings.append(str(exc))

        if (
            initial is not None
            and configured_url is not None
            and not is_homepage_redirect(configured_url, initial.url, str(company.website_url))
            and looks_like_careers_page(initial.text, initial.url)
        ):
            return ExtractionResult(
                [], "html", warnings, resolved_careers_url=initial.url
            )

        homepage = initial if initial is not None and configured_url is not None and is_homepage_redirect(
            configured_url, initial.url, str(company.website_url)
        ) else None
        if homepage is not None:
            warnings.append(
                f"Configured careers URL redirected to the homepage: {initial.url}"
            )
        else:
            for homepage_url in website_homepage_candidates(str(company.website_url)):
                if configured_url and homepage_url.rstrip("/") == configured_url.rstrip("/"):
                    continue
                try:
                    homepage = await self.fetcher.fetch(homepage_url)
                    self._check_blocked(homepage.text, homepage.url)
                    if is_soft_404(homepage.text):
                        warnings.append(
                            f"Careers discovery homepage is a custom not-found page: {homepage.url}"
                        )
                        homepage = None
                        continue
                    if homepage_url != str(company.website_url):
                        warnings.append(f"Website fallback succeeded: {homepage.url}")
                    break
                except (FetchError, BlockedError) as exc:
                    warnings.append(f"Careers discovery homepage failed: {exc}")

        if homepage is not None:
            homepage_jobs, homepage_adapter = await self._extract_page(
                company, homepage.url, homepage.text, warnings
            )
            if homepage_jobs and (
                not _is_generic_adapter(homepage_adapter)
                or looks_like_careers_page(homepage.text, homepage.url)
            ):
                return ExtractionResult(
                    _deduplicate_raw(homepage_jobs),
                    homepage_adapter,
                    warnings,
                    resolved_careers_url=homepage.url,
                    careers_url_discovered=configured_url is None or homepage.url != configured_url,
                )
            candidates = discover_careers_links(
                homepage.text,
                homepage.url,
                str(company.website_url),
                limit=self.max_careers_candidates,
            )
            if not candidates and self.browser_enabled and self.browser is not None:
                try:
                    discovery_browser_used = True
                    rendered_homepage = await self.browser.render(homepage.url)
                    self._check_blocked(rendered_homepage.html, rendered_homepage.url)
                    if not is_soft_404(rendered_homepage.html):
                        candidates = discover_careers_links(
                            rendered_homepage.html,
                            rendered_homepage.url,
                            str(company.website_url),
                            limit=self.max_careers_candidates,
                        )
                except BrowserUnavailable as exc:
                    warnings.append(f"Careers discovery browser failed: {exc}")
            if not candidates:
                parts = urlsplit(homepage.url)
                sitemap_urls = [
                    f"{parts.scheme}://{parts.netloc}/sitemap.xml",
                    f"{parts.scheme}://{parts.netloc}/sitemap_index.xml",
                ]
                for sitemap_url in sitemap_urls:
                    try:
                        sitemap = await self.fetcher.fetch(sitemap_url)
                        candidates.extend(
                            discover_sitemap_careers(
                                sitemap.text,
                                str(company.website_url),
                                limit=self.max_careers_candidates,
                            )
                        )
                        for document_url in discover_sitemap_documents(
                            sitemap.text, str(company.website_url), limit=3
                        ):
                            try:
                                document = await self.fetcher.fetch(document_url)
                                candidates.extend(
                                    discover_sitemap_careers(
                                        document.text,
                                        str(company.website_url),
                                        limit=self.max_careers_candidates - len(candidates),
                                    )
                                )
                            except (FetchError, BlockedError):
                                continue
                            if len(candidates) >= self.max_careers_candidates:
                                break
                        if candidates:
                            warnings.append("Careers candidates discovered from sitemap.xml or child sitemap")
                            break
                    except (FetchError, BlockedError):
                        continue
            rejected_urls = {
                url.rstrip("/")
                for url in company.metadata.get("Rejected Careers URLs", "").splitlines()
                if url.strip()
            }
            candidates = [
                url for url in candidates if url.rstrip("/") not in rejected_urls
            ]
            known_candidates = {url.rstrip("/") for url in candidates} | rejected_urls
            if configured_url:
                known_candidates.add(configured_url.rstrip("/"))
            guessed_candidates = set(
                common_careers_candidates(
                    homepage.url,
                    excluded=known_candidates,
                    limit=max(0, self.max_careers_candidates - len(candidates)),
                )
            )
            candidates.extend(guessed_candidates)
            empty_candidate: tuple[str, str] | None = None
            for candidate_url in candidates:
                if configured_url and candidate_url.rstrip("/") == configured_url.rstrip("/"):
                    continue
                try:
                    page = await self.fetcher.fetch(candidate_url)
                    resolved_candidate_url = page.url
                    self._check_blocked(page.text, page.url)
                    if is_soft_404(page.text):
                        warnings.append(
                            f"Discovered candidate is a custom not-found page: {page.url}"
                        )
                        continue
                    candidate_needs_browser = needs_browser_pagination(page.text)
                    allow_candidate_browser = (
                        candidate_needs_browser and not candidate_browser_used
                    )
                    if allow_candidate_browser:
                        candidate_browser_used = True
                    jobs, candidate_adapter = await self._extract_http_paginated(
                        company,
                        page.url,
                        page.text,
                        warnings,
                        allow_browser=allow_candidate_browser,
                    )
                    if not jobs and _is_generic_adapter(candidate_adapter):
                        for board_url in discover_board_links(
                            page.text, page.url, limit=self.max_board_links
                        ):
                            try:
                                board = await self.fetcher.fetch(board_url)
                                self._check_blocked(board.text, board.url)
                                jobs, candidate_adapter = await self._extract_http_paginated(
                                    company,
                                    board.url,
                                    board.text,
                                    warnings,
                                    allow_browser=False,
                                )
                                if jobs or not _is_generic_adapter(candidate_adapter):
                                    page = board
                                    resolved_candidate_url = board.url
                                    break
                            except (FetchError, BlockedError) as exc:
                                warnings.append(f"Nested job board failed: {exc}")
                    candidate_is_verified = (
                        candidate_url not in guessed_candidates
                        or looks_like_careers_content(page.text)
                    )
                    if (
                        not jobs
                        and self.browser_enabled
                        and self.browser is not None
                        and candidate_is_verified
                        and not candidate_browser_used
                        and _is_generic_adapter(candidate_adapter)
                    ):
                        try:
                            candidate_browser_used = True
                            jobs, candidate_adapter, rendered_url = (
                                await self._extract_browser_paginated(
                                    company,
                                    page.url,
                                    warnings,
                                    paginate=needs_browser_pagination(page.text),
                                )
                            )
                            if jobs:
                                resolved_candidate_url = rendered_url
                        except (BrowserUnavailable, BlockedError) as exc:
                            warnings.append(f"Discovered careers browser failed: {exc}")
                    if jobs:
                        warnings.append(
                            f"Discovered careers URL from website: {resolved_candidate_url}"
                        )
                        return ExtractionResult(
                            _deduplicate_raw(jobs),
                            candidate_adapter,
                            warnings,
                            resolved_careers_url=resolved_candidate_url,
                            careers_url_discovered=True,
                        )
                    if candidate_is_verified and looks_like_careers_page(page.text, page.url):
                        empty_candidate = empty_candidate or (page.url, candidate_adapter)
                        if candidate_url not in guessed_candidates:
                            warnings.append(
                                f"Discovered careers URL from website: {page.url}"
                            )
                            return ExtractionResult(
                                [],
                                candidate_adapter,
                                warnings,
                                resolved_careers_url=page.url,
                                careers_url_discovered=True,
                            )
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

        if initial_error is not None and homepage is None:
            raise initial_error
        if initial_error is not None and homepage is not None:
            warnings.append(
                "Careers page could not be verified after the configured URL failed"
            )
        if (
            initial_error is None
            and not any("Discovered careers URL from website" in warning for warning in warnings)
        ):
            warnings.append(_CAREERS_NOT_FOUND_WARNING)
        resolved_url = (
            initial.url
            if initial is not None
            else homepage.url
            if homepage is not None
            else configured_url
        )
        return ExtractionResult([], "html", warnings, resolved_url)
