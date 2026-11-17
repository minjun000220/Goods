"""자동 사이트 어댑터: 주소만 넣으면 자동 패턴 찾기(collectors/auto_extract.py)로 상품 목록을 뽑는다.

  AutoSiteConfig(source_id="some_mall_best", url="https://mall.example/best?page={page}")
  AutoSiteConfig(source_id="some_mall_search", url="https://mall.example/search?q={kw}")

- url 에 {kw} 가 있으면 검색 페이지 (굿즈 종류마다 검색), 없으면 베스트/랭킹 페이지
- robots.txt 확인은 HttpFetcher 가 자동으로 한다
- 새 사이트를 넣기 전에 먼저 확인:  python -m tools.try_auto "<주소>"
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from collectors.auto_extract import extract_products
from collectors.base import CrawlTask, ListingSnapshot, RawDocument, SourceAdapter


@dataclass(frozen=True)
class AutoSiteConfig:
    source_id: str
    url: str                       # {page} 와/또는 {kw} 자리표시자 사용 가능
    pages: int = 1
    seller_type: str = "retail"    # 중고·리셀 사이트면 "resale"
    rate_limit: float = 0.2


class AutoSiteAdapter(SourceAdapter):
    concurrency = 1

    def __init__(self, fetcher, config: AutoSiteConfig):
        self.rate_limit = config.rate_limit
        super().__init__(fetcher)
        self.config = config
        self.source_id = config.source_id

    @property
    def is_search(self) -> bool:
        return "{kw}" in self.config.url

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        pages = range(1, self.config.pages + 1)
        if self.is_search:
            return [CrawlTask(self.source_id, "search", {"kw": kw, "page": p}) for kw in keywords for p in pages]
        return [CrawlTask(self.source_id, "ranking", {"page": p}) for p in pages]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        url = self.config.url.format(page=task.params["page"], kw=quote(task.params.get("kw", "")))
        return RawDocument(task, url, datetime.now(), "html", await self.fetcher.get_text(url))

    def parse(self, raw: RawDocument) -> list[ListingSnapshot]:
        items = extract_products(raw.body, raw.url)
        if self.is_search:
            rank_list = f"search:{self.source_id}:{raw.task.params['kw']}"
        else:
            rank_list = f"best:{self.source_id}"
        offset = (raw.task.params["page"] - 1) * len(items)
        return [ListingSnapshot(
            source_id=self.source_id,
            external_id=hashlib.sha1(it.url.encode()).hexdigest()[:20],
            title=it.title, url=it.url, observed_at=raw.fetched_at,
            price=it.price, rank=offset + it.rank, rank_list=rank_list,
            seller_type=self.config.seller_type,
        ) for it in items]
