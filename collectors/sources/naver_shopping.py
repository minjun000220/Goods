"""네이버 쇼핑 검색 API 어댑터 (공식 API, 일 25,000회 무료).

문서: https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md
검색어 = 굿즈 종류 ("응원봉" 으로 검색하면 BTS·aespa·세븐틴 응원봉이 모두 나온다)

얻는 신호
 - listing_total : 검색 결과 상품 수 → 파는 곳이 늘고 있는가 (공급 쪽 반응)
 - 상위 상품 목록 : 대시보드에 '이 종류에서 요즘 많이 보이는 상품' 예시로 사용
한계: 리뷰 수·품절 여부는 제공되지 않는다.
"""
from __future__ import annotations

import json
from datetime import datetime

from collectors.base import CrawlTask, ListingSnapshot, MetricPoint, RawDocument, SourceAdapter
from processing.normalize import parse_price, strip_html

API_URL = "https://openapi.naver.com/v1/search/shop.json"


class NaverShoppingAdapter(SourceAdapter):
    source_id = "naver_shopping"
    rate_limit = 5.0
    concurrency = 3

    def __init__(self, fetcher, client_id: str, client_secret: str, display: int = 100):
        super().__init__(fetcher)
        self.headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
        self.display = display

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        return [CrawlTask(self.source_id, "search",
                          {"query": kw, "start": 1, "display": self.display, "sort": "sim"})
                for kw in keywords]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        resp = await self.fetcher.request(
            "GET", API_URL, params=task.params, headers=self.headers, check_robots=False
        )
        return RawDocument(task, str(resp.url), datetime.now(), "json", resp.text)

    def parse(self, raw: RawDocument) -> list:
        data = json.loads(raw.body)
        query = raw.task.params["query"]
        out: list = [MetricPoint(self.source_id, query, "listing_total",
                                 raw.fetched_at.date(), float(data.get("total", 0)))]
        for i, item in enumerate(data.get("items", [])):
            out.append(ListingSnapshot(
                source_id=self.source_id,
                external_id=str(item["productId"]),
                title=strip_html(item.get("title", "")),
                url=item.get("link", ""),
                observed_at=raw.fetched_at,
                price=parse_price(item.get("lprice")),
                rank=i + 1,
                rank_list=f"search:{query}",
                seller_type="retail",
            ))
        return out
