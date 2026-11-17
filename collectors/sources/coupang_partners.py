"""쿠팡 파트너스 Open API 어댑터 (공식 API).

쿠팡 웹사이트는 봇 접근을 차단한다 (robots.txt 조차 403, 2026-11 확인) → 웹 크롤링 대신 공식 API 사용.
필요: 쿠팡 파트너스 가입 + API 사용 승인 후 Access Key / Secret Key 발급
      https://partners.coupang.com → 추가기능 → 오픈 API

- bestcategories : 카테고리별 베스트 상품 순위 → '베스트 랭킹 점유율' 신호의 핵심 소스
- search         : 검색어(굿즈 종류) 결과. 호출 한도가 매우 작으므로(시간당 소수) 기본은 끔.

인증: HMAC-SHA256 서명 (CEA). 서명 메시지 = signed-date + METHOD + path + query
카테고리 ID 는 파트너스 API 문서의 카테고리 표에서 확인 후 바꿀 것.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime
from urllib.parse import urlencode

from collectors.base import CrawlTask, ListingSnapshot, RawDocument, SourceAdapter
from processing.normalize import parse_price

DOMAIN = "https://api-gateway.coupang.com"
BASE = "/v2/providers/affiliate_open_api/apis/openapi/products"

# 문서의 카테고리 표 기준 (사용 전 확인 필요): 1019 도서/음반/DVD, 1020 완구/취미, 1021 문구/오피스
DEFAULT_CATEGORIES = ("1020", "1019", "1021")


def authorization(method: str, path: str, query: str, access_key: str, secret_key: str) -> str:
    signed_date = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    message = f"{signed_date}{method}{path}{query}"
    signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return (f"CEA algorithm=HmacSHA256, access-key={access_key}, "
            f"signed-date={signed_date}, signature={signature}")


class CoupangPartnersAdapter(SourceAdapter):
    source_id = "coupang"
    rate_limit = 0.5
    concurrency = 1

    def __init__(self, fetcher, access_key: str, secret_key: str,
                 categories: tuple[str, ...] = DEFAULT_CATEGORIES, use_search: bool = False):
        super().__init__(fetcher)
        self.access_key, self.secret_key = access_key, secret_key
        self.categories = categories
        self.use_search = use_search

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        tasks = [CrawlTask(self.source_id, "best", {"category": c}) for c in self.categories]
        if self.use_search:
            tasks += [CrawlTask(self.source_id, "search", {"keyword": kw}) for kw in keywords]
        return tasks

    async def fetch(self, task: CrawlTask) -> RawDocument:
        if task.kind == "best":
            path, query = f"{BASE}/bestcategories/{task.params['category']}", urlencode({"limit": 100})
        else:
            path, query = f"{BASE}/search", urlencode({"keyword": task.params["keyword"], "limit": 10})
        headers = {"Authorization": authorization("GET", path, query, self.access_key, self.secret_key),
                   "Content-Type": "application/json;charset=UTF-8"}
        url = f"{DOMAIN}{path}?{query}"
        resp = await self.fetcher.request("GET", url, headers=headers, check_robots=False)
        return RawDocument(task, url, datetime.now(), "json", resp.text)

    def parse(self, raw: RawDocument) -> list[ListingSnapshot]:
        body = json.loads(raw.body)
        if str(body.get("rCode", "0")) != "0":
            raise RuntimeError(f"coupang api error: {body.get('rCode')} {body.get('rMessage')}")
        data = body.get("data") or []
        items = data.get("productData", []) if isinstance(data, dict) else data
        if raw.task.kind == "best":
            rank_list = f"best:coupang:{raw.task.params['category']}"
        else:
            rank_list = f"search:coupang:{raw.task.params['keyword']}"
        return [ListingSnapshot(
            source_id=self.source_id,
            external_id=str(it["productId"]),
            title=it.get("productName", ""),
            url=it.get("productUrl", ""),
            observed_at=raw.fetched_at,
            price=parse_price(it.get("productPrice")),
            rank=int(it.get("rank") or i + 1),
            rank_list=rank_list,
            seller_type="retail",
        ) for i, it in enumerate(items)]
