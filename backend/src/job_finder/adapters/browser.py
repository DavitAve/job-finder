from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from dataclasses import dataclass

from .pagination import (
    LOAD_MORE_TEXT,
    NEXT_TEXT,
    canonical_page_url,
    discover_next_page_url,
)


class BrowserUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class RenderedPage:
    url: str
    html: str


@dataclass(slots=True)
class RenderedPages:
    pages: list[RenderedPage]
    warnings: list[str]


class BrowserRenderer:
    def __init__(
        self,
        *,
        max_pages: int = 2,
        timeout_seconds: float = 20.0,
        pool_wait_seconds: float = 30.0,
        max_pagination_pages: int = 20,
        max_interactions: int = 6,
        infinite_scroll_rounds: int = 2,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.pool_wait_seconds = pool_wait_seconds
        self.max_pagination_pages = max_pagination_pages
        self.max_interactions = max_interactions
        self.infinite_scroll_rounds = infinite_scroll_rounds
        self._semaphore = asyncio.Semaphore(max_pages)
        self._playwright = None
        self._browser = None
        self._start_lock = asyncio.Lock()
        self._unavailable_reason: str | None = None

    @asynccontextmanager
    async def _page_slot(self):
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(), timeout=self.pool_wait_seconds
            )
        except TimeoutError as exc:
            raise BrowserUnavailable(
                f"Playwright page pool busy for more than {self.pool_wait_seconds:g}s"
            ) from exc
        try:
            yield
        finally:
            self._semaphore.release()

    async def _start(self) -> None:
        if self._browser is not None:
            return
        if self._unavailable_reason:
            raise BrowserUnavailable(self._unavailable_reason)
        async with self._start_lock:
            if self._browser is not None:
                return
            try:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
            except Exception as exc:  # Playwright provides multiple platform errors.
                self._unavailable_reason = f"Playwright unavailable: {exc}"
                if self._playwright is not None:
                    await self._playwright.stop()
                    self._playwright = None
                raise BrowserUnavailable(self._unavailable_reason) from exc

    async def _prepare_page(self, page) -> None:
        if not hasattr(page, "route"):
            return

        async def handle_route(route) -> None:
            if route.request.resource_type in {"image", "media", "font"}:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", handle_route)

    async def _goto(self, page, url: str) -> bool:
        """Navigate and keep usable partial DOM when only the timeout expires."""
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=int(self.timeout_seconds * 1000),
            )
            return True
        except Exception as exc:
            if "timeout" not in str(exc).casefold():
                raise
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=2_000)
            except Exception:
                pass
            return False

    @staticmethod
    async def _content(page) -> str:
        last_error: Exception | None = None
        for _ in range(4):
            try:
                return await page.content()
            except Exception as exc:
                last_error = exc
                await page.wait_for_timeout(250)
        assert last_error is not None
        raise last_error

    async def render(self, url: str) -> RenderedPage:
        await self._start()
        async with self._page_slot():
            page = await self._browser.new_page()
            try:
                await self._prepare_page(page)
                await self._goto(page, url)
                await page.wait_for_timeout(1000)
                return RenderedPage(url=page.url, html=await self._content(page))
            except Exception as exc:
                raise BrowserUnavailable(f"Browser render failed for {url}: {exc}") from exc
            finally:
                await page.close()

    async def render_paginated(self, url: str) -> RenderedPages:
        """Render a page and safely expand Load more, scrolling, and Next pages."""
        await self._start()
        async with self._page_slot():
            page = await self._browser.new_page()
            snapshots: list[RenderedPage] = []
            warnings: list[str] = []
            seen_content: set[str] = set()
            visited_urls: set[str] = set()
            interactions = 0

            async def capture() -> bool:
                html = await self._content(page)
                digest = hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()
                if digest in seen_content:
                    return False
                seen_content.add(digest)
                snapshots.append(RenderedPage(url=page.url, html=html))
                visited_urls.add(canonical_page_url(page.url))
                return True

            async def settle() -> None:
                try:
                    await page.wait_for_load_state("networkidle", timeout=3_000)
                except Exception:
                    pass
                await page.wait_for_timeout(600)

            try:
                await self._prepare_page(page)
                completed = await self._goto(page, url)
                if not completed:
                    warnings.append(
                        f"Browser navigation timed out; using partially loaded page: {url}"
                    )
                await page.wait_for_timeout(1000)
                await capture()

                while (
                    len(snapshots) < self.max_pagination_pages
                    and interactions < self.max_interactions
                ):
                    expanded = False
                    controls = page.locator("button, a, [role='button']").filter(
                        has_text=LOAD_MORE_TEXT
                    )
                    for index in range(min(await controls.count(), 30)):
                        control = controls.nth(index)
                        try:
                            if not await control.is_visible() or not await control.is_enabled():
                                continue
                            await control.click(timeout=2_500)
                            interactions += 1
                            await settle()
                            expanded = await capture()
                            break
                        except Exception:
                            continue
                    if expanded:
                        continue

                    scrolled = False
                    for _ in range(self.infinite_scroll_rounds):
                        if interactions >= self.max_interactions:
                            break
                        before_height = await page.evaluate(
                            "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
                        )
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        interactions += 1
                        await settle()
                        after_height = await page.evaluate(
                            "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
                        )
                        changed = await capture()
                        grew = after_height > before_height
                        scrolled = scrolled or (changed and grew)
                        if not grew:
                            break
                    if scrolled:
                        continue

                    html = await self._content(page)
                    next_url = discover_next_page_url(html, page.url, visited_urls)
                    if next_url is not None:
                        completed = await self._goto(page, next_url)
                        if not completed:
                            warnings.append(
                                f"Browser navigation timed out; using partially loaded page: {next_url}"
                            )
                        interactions += 1
                        await settle()
                        if not await capture():
                            break
                        continue

                    clicked_next = False
                    next_controls = page.locator("button, [role='button']").filter(
                        has_text=NEXT_TEXT
                    )
                    for index in range(min(await next_controls.count(), 20)):
                        control = next_controls.nth(index)
                        try:
                            if not await control.is_visible() or not await control.is_enabled():
                                continue
                            await control.click(timeout=2_500)
                            interactions += 1
                            await settle()
                            clicked_next = await capture()
                            break
                        except Exception:
                            continue
                    if not clicked_next:
                        break

                if len(snapshots) >= self.max_pagination_pages:
                    warnings.append(
                        f"Browser pagination stopped at {self.max_pagination_pages} pages"
                    )
                if interactions >= self.max_interactions:
                    warnings.append(
                        f"Browser pagination stopped at {self.max_interactions} interactions"
                    )
                return RenderedPages(snapshots, warnings)
            except Exception as exc:
                raise BrowserUnavailable(
                    f"Browser pagination failed for {url}: {exc}"
                ) from exc
            finally:
                await page.close()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
