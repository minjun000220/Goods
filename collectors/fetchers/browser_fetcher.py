"""JS 로 렌더링되는 페이지용 Fetcher (Playwright).

HTTP Fetcher 보다 10배 이상 느리고 무거우므로, API 나 정적 HTML 로 안 될 때만 쓴다.
설치: pip install -e ".[browser]"
"""
from __future__ import annotations


class BrowserFetcher:
    def __init__(self, user_agent: str, headless: bool = True):
        self.user_agent = user_agent
        self.headless = headless
        self._pw = None
        self._browser = None

    async def __aenter__(self):
        from playwright.async_api import async_playwright  # 선택 의존성

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, *exc):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def get_html(self, url: str, wait_selector: str | None = None, timeout_ms: int = 20000) -> str:
        """페이지를 열고, (있으면) 특정 요소가 나타날 때까지 기다린 뒤 HTML 을 돌려준다."""
        context = await self._browser.new_context(user_agent=self.user_agent, locale="ko-KR")
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=timeout_ms)
            return await page.content()
        finally:
            await context.close()
