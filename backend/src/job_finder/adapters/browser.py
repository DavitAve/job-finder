from __future__ import annotations

import asyncio
from dataclasses import dataclass


class BrowserUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class RenderedPage:
    url: str
    html: str


class BrowserRenderer:
    def __init__(self, *, max_pages: int = 2, timeout_seconds: float = 25.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_pages)
        self._playwright = None
        self._browser = None
        self._start_lock = asyncio.Lock()
        self._unavailable_reason: str | None = None

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

    async def render(self, url: str) -> RenderedPage:
        await self._start()
        async with self._semaphore:
            page = await self._browser.new_page()
            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(self.timeout_seconds * 1000),
                )
                await page.wait_for_timeout(1000)
                return RenderedPage(url=page.url, html=await page.content())
            except Exception as exc:
                raise BrowserUnavailable(f"Browser render failed for {url}: {exc}") from exc
            finally:
                await page.close()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

