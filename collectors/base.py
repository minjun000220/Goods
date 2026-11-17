"""수집 계층의 공통 뼈대.

모든 소스(쇼핑몰, 중고거래, 커뮤니티, 검색 트렌드)는 SourceAdapter 를 상속해
discover → fetch → parse 세 단계만 구현하면 된다. 나머지(속도 제한, 에러 처리,
통계 집계)는 여기서 공통으로 처리한다.
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Union

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 공통 데이터 구조: 어떤 사이트에서 왔든 이 형태로 변환된다
# ---------------------------------------------------------------------------
@dataclass
class CrawlTask:
    """'무엇을 가져올지' 한 단위. 예: 네이버쇼핑에서 '치이카와 인형' 검색 1페이지."""
    source_id: str
    kind: str                                   # "search" | "ranking" | "trend" | "board" ...
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawDocument:
    """가져온 원본. 파서를 고친 뒤 재처리할 수 있게 그대로 보관한다."""
    task: CrawlTask
    url: str
    fetched_at: datetime
    content_type: Literal["json", "html"]
    body: str


@dataclass
class ListingSnapshot:
    """판매처에 올라온 상품 1개의 '한 시점' 상태."""
    source_id: str
    external_id: str             # 사이트 내 상품 ID
    title: str
    url: str
    observed_at: datetime
    price: int | None = None
    rank: int | None = None      # 순위 (1이 최상위)
    rank_list: str | None = None  # 어느 목록의 순위인지. "best:<쇼핑몰>" = 전체 베스트 랭킹,
                                  # "search:<검색어>" = 검색 결과 순위 (종류끼리 비교 불가)
    stock_status: str = "unknown"  # in_stock | sold_out | preorder | unknown
    review_count: int | None = None
    sales_count: int | None = None  # 누적 판매/거래 수 (KREAM '거래' 수 등)
    seller_type: str = "retail"  # retail(정가 판매) | resale(중고/리셀)


@dataclass
class MentionRecord:
    """SNS·커뮤니티 언급 1건."""
    source_id: str
    external_id: str
    text: str
    url: str
    observed_at: datetime
    engagement: int = 0          # 좋아요+댓글+RT 등


@dataclass
class MetricPoint:
    """키워드(=굿즈 종류) 단위의 일별 지표.
    metric 예: "search_volume"(검색량), "listing_total"(검색 결과 상품 수 = 파는 곳이 늘었나)"""
    source_id: str
    keyword: str
    metric: str
    date: date
    value: float


ParsedItem = Union[ListingSnapshot, MentionRecord, MetricPoint]


@dataclass
class RunStats:
    """한 번의 수집 실행 결과. 파서가 깨졌는지 감지하는 데 쓴다."""
    source_id: str
    started_at: datetime
    finished_at: datetime | None = None
    tasks: int = 0
    failures: int = 0
    items: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 속도 제한 (토큰 버킷)
# ---------------------------------------------------------------------------
class RateLimiter:
    """초당 rate 회까지만 요청을 허용한다. 사이트에 부담을 주거나 차단당하지 않기 위함."""

    def __init__(self, rate_per_sec: float, burst: int = 1):
        self.rate = rate_per_sec
        self.capacity = burst
        self.tokens = float(burst)
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)


# ---------------------------------------------------------------------------
# 어댑터 인터페이스
# ---------------------------------------------------------------------------
class SourceAdapter(ABC):
    source_id: str = "unknown"
    rate_limit: float = 1.0      # 초당 요청 수
    concurrency: int = 2         # 동시 요청 수
    max_consecutive_failures: int = 3   # 연속 이만큼 실패하면 이 사이트는 이번 실행에서 포기 (차단 의심)
    time_budget_sec: float = 600.0      # 사이트 하나에 쓰는 최대 시간 (넘으면 모은 것까지만 저장)

    def __init__(self, fetcher=None):
        self.fetcher = fetcher
        self.limiter = RateLimiter(self.rate_limit)

    @abstractmethod
    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        """이번 실행에서 가져올 작업 목록을 만든다."""

    @abstractmethod
    async def fetch(self, task: CrawlTask) -> RawDocument:
        """작업 1개에 해당하는 원본을 가져온다."""

    @abstractmethod
    def parse(self, raw: RawDocument) -> list[ParsedItem]:
        """원본을 공통 데이터 구조로 변환한다."""

    async def run(
        self, keywords: list[str], raw_store=None
    ) -> tuple[list[ParsedItem], RunStats]:
        """discover → (rate limit) → fetch → 원본 저장 → parse 를 수행한다.

        - 작업 하나가 실패해도 나머지는 계속 진행한다.
        - 연속으로 max_consecutive_failures 번 실패하면 사이트가 막은 것으로 보고 남은 작업을 건너뛴다.
        - time_budget_sec 를 넘기면 남은 작업을 건너뛰고, 그때까지 모은 것만 돌려준다.
        """
        stats = RunStats(source_id=self.source_id, started_at=datetime.now())
        tasks = self.discover(keywords)
        stats.tasks = len(tasks)
        sem = asyncio.Semaphore(self.concurrency)
        items: list[ParsedItem] = []
        state = {"consecutive": 0, "gave_up": None}
        deadline = time.monotonic() + self.time_budget_sec

        async def _one(task: CrawlTask) -> None:
            async with sem:
                if state["gave_up"]:
                    return
                if time.monotonic() > deadline:
                    state["gave_up"] = f"시간 초과 ({self.time_budget_sec:.0f}초)"
                    return
                await self.limiter.acquire()
                try:
                    raw = await asyncio.wait_for(self.fetch(task), timeout=max(1.0, deadline - time.monotonic()))
                    if raw_store is not None:
                        raw_store.save(raw)
                    parsed = self.parse(raw)
                    items.extend(parsed)
                    state["consecutive"] = 0
                except Exception as exc:  # noqa: BLE001 - 소스 하나의 실패가 전체를 멈추면 안 된다
                    stats.failures += 1
                    stats.errors.append(f"{task.params}: {exc!r}")
                    log.warning("[%s] task failed %s: %r", self.source_id, task.params, exc)
                    state["consecutive"] += 1
                    if state["consecutive"] >= self.max_consecutive_failures and not state["gave_up"]:
                        state["gave_up"] = f"연속 {state['consecutive']}회 실패 (차단 의심)"

        await asyncio.gather(*(_one(t) for t in tasks))
        if state["gave_up"]:
            stats.errors.append(f"중단: {state['gave_up']}")
            log.warning("[%s] 남은 작업을 건너뜀 — %s", self.source_id, state["gave_up"])
        stats.items = len(items)
        stats.finished_at = datetime.now()
        log.info("[%s] tasks=%d failures=%d items=%d",
                 self.source_id, stats.tasks, stats.failures, stats.items)
        return items, stats
