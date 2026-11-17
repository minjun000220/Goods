"""범용 '베스트/인기 랭킹 페이지' 어댑터 (HTML + CSS 셀렉터).

검색어 없이 쇼핑몰의 베스트 순위를 통째로 가져온다.
→ 내가 모르는 새 굿즈 종류도 순위에 올라오면 잡힌다 (키워드 검색 방식의 한계 보완).

랭킹 목록은 rank_list="best:<source_id>" 로 저장되어, 굿즈 종류별 '베스트 순위 점유율'
신호 계산에 쓰인다.

반드시 대상 사이트의 robots.txt 와 이용약관을 확인하고 허용된 범위에서만 사용할 것.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.auto_extract import extract_products
from collectors.base import CrawlTask, ListingSnapshot, RawDocument, SourceAdapter
from processing.normalize import normalize_stock, parse_price

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RankingConfig:
    source_id: str
    url: str                      # 예: "https://shop.example.com/best?category=goods&page={page}"
    item_selector: str            # 상품 한 칸
    title_selector: str           # 상품명 (a 태그면 href 도 사용)
    price_selector: str | None = None
    soldout_selector: str | None = None   # 품절 표시 요소 (있으면 품절)
    review_selector: str | None = None    # 리뷰 수 요소
    pages: int = 1
    seller_type: str = "retail"           # 중고거래 인기 매물 페이지면 "resale"
    rate_limit: float = 0.2               # 초당 요청 수


class BestRankingAdapter(SourceAdapter):
    rate_limit = 0.5
    concurrency = 1

    def __init__(self, fetcher, config: RankingConfig):
        self.rate_limit = config.rate_limit
        super().__init__(fetcher)
        self.config = config
        self.source_id = config.source_id

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        return [CrawlTask(self.source_id, "ranking", {"page": p}) for p in range(1, self.config.pages + 1)]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        url = self.config.url.format(page=task.params["page"])
        return RawDocument(task, url, datetime.now(), "html", await self.fetcher.get_text(url))

    def parse(self, raw: RawDocument) -> list[ListingSnapshot]:
        c = self.config
        soup = BeautifulSoup(raw.body, "html.parser")
        # 같은 상품이 한 페이지에 두 번 나오는 사이트가 있다 (갤러리형/리스트형 레이아웃 동시 출력)
        # → 링크 기준으로 중복 제거한 뒤 순위를 매긴다
        rows, seen = [], set()
        for el in soup.select(c.item_selector):
            t = el.select_one(c.title_selector)
            if t is None:
                continue
            link = urljoin(raw.url, t.get("href") or "")
            if link in seen:
                continue
            seen.add(link)
            rows.append((el, t, link))
        if not rows:
            return self._auto_fallback(raw)
        offset = (raw.task.params["page"] - 1) * len(rows)
        out = []
        for i, (el, t, link) in enumerate(rows):
            price = el.select_one(c.price_selector) if c.price_selector else None
            review = el.select_one(c.review_selector) if c.review_selector else None
            m = re.search(r"\d[\d,]*", review.get_text()) if review else None
            soldout = el.select_one(c.soldout_selector) if c.soldout_selector else None
            out.append(ListingSnapshot(
                source_id=self.source_id,
                external_id=hashlib.sha1(link.encode()).hexdigest()[:20],
                title=t.get_text(" ", strip=True),
                url=link,
                observed_at=raw.fetched_at,
                price=parse_price(price.get_text()) if price else None,
                rank=offset + i + 1,
                rank_list=f"best:{self.source_id}",
                stock_status="sold_out" if soldout else (normalize_stock(el.get_text()) if c.soldout_selector else "unknown"),
                review_count=int(m.group().replace(",", "")) if m else None,
                seller_type=c.seller_type,
            ))
        return out

    def _auto_fallback(self, raw: RawDocument) -> list[ListingSnapshot]:
        """셀렉터로 아무것도 못 찾으면(사이트 개편 등) 자동 패턴 찾기로 대신 뽑는다."""
        items = extract_products(raw.body, raw.url)
        if items:
            log.warning("[%s] 셀렉터 결과 0개 → 자동 패턴 찾기로 %d개 추출 (셀렉터 점검 필요)",
                        self.source_id, len(items))
        offset = (raw.task.params["page"] - 1) * len(items)
        return [ListingSnapshot(
            source_id=self.source_id, external_id=hashlib.sha1(it.url.encode()).hexdigest()[:20],
            title=it.title, url=it.url, observed_at=raw.fetched_at, price=it.price,
            rank=offset + it.rank, rank_list=f"best:{self.source_id}", seller_type=self.config.seller_type,
        ) for it in items]
