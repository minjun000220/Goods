"""정적 페이지·API 용 HTTP Fetcher.

- 재시도: 429/5xx 와 네트워크 오류는 지수 백오프로 재시도
- robots.txt: 웹페이지를 긁을 때는 허용 여부를 먼저 확인 (공식 API는 확인 생략)
"""
from __future__ import annotations

import asyncio
import logging
import random
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class RobotsDisallowed(Exception):
    pass


class HttpFetcher:
    def __init__(self, user_agent: str, timeout: float = 15.0, max_retries: int = 4):
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept-Language": "ko-KR,ko;q=0.9"},
            follow_redirects=True,
        )
        self._robots: dict[str, RobotFileParser | None] = {}

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # -- robots.txt --------------------------------------------------------
    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                resp = await self.client.get(f"{origin}/robots.txt")
                if resp.status_code >= 400:
                    rp = None  # robots.txt 없음 → 제한 없음으로 간주
                else:
                    rp.parse(resp.text.splitlines())
            except httpx.HTTPError:
                rp = None
            self._robots[origin] = rp
        rp = self._robots[origin]
        return True if rp is None else rp.can_fetch(self.user_agent, url)

    # -- 요청 --------------------------------------------------------------
    async def request(
        self,
        method: str,
        url: str,
        *,
        check_robots: bool = True,
        **kwargs,
    ) -> httpx.Response:
        if check_robots and not await self.allowed(url):
            raise RobotsDisallowed(url)

        for attempt in range(self.max_retries + 1):
            try:
                resp = await self.client.request(method, url, **kwargs)
                if resp.status_code in RETRY_STATUS and attempt < self.max_retries:
                    delay = _retry_delay(resp, attempt)
                    log.info("retry %s %s in %.1fs (status %d)", method, url, delay, resp.status_code)
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.TimeoutException):
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(_retry_delay(None, attempt))
        raise RuntimeError("unreachable")

    async def get_text(self, url: str, **kwargs) -> str:
        return (await self.request("GET", url, **kwargs)).text


def _retry_delay(resp: httpx.Response | None, attempt: int) -> float:
    if resp is not None and (ra := resp.headers.get("Retry-After", "")).isdigit():
        return float(ra)
    return min(60.0, 2 ** attempt) + random.uniform(0, 1)
