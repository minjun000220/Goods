"""KREAM 검색 결과 어댑터 (HTML).

robots.txt: User-agent * 에 대해 /search 허용 (/my*, /history*, /bridge/ 만 금지) — 2026-11 확인.
검색어 = 굿즈 종류 ("응원봉" 등). 상품 카드 텍스트 예:
  "Toys & Goods | BTS 공식 응원봉 Ver. 4 | 50,000원 | 관심 | 519 | · 리뷰 | 134 | · 거래 | 7,040 | …"

얻는 신호: 리셀 시세(가격), 누적 거래 수(sales_count) → 거래가 빨라지는가, 리뷰 수.
KREAM 은 리셀 마켓이므로 seller_type="resale".
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote

from bs4 import BeautifulSoup

from collectors.base import CrawlTask, ListingSnapshot, RawDocument, SourceAdapter
from processing.normalize import parse_price

SEARCH_URL = "https://kream.co.kr/search?keyword={kw}"
PRICE_RE = re.compile(r"^[\d,]+원$")


def parse_count(text: str) -> int | None:
    """'7,040' → 7040, '1.2만' → 12000"""
    t = text.replace(",", "").strip()
    m = re.match(r"^([\d.]+)\s*(만)?$", t)
    if not m:
        return None
    n = float(m.group(1)) * (10000 if m.group(2) else 1)
    return int(n)


class KreamAdapter(SourceAdapter):
    source_id = "kream"
    rate_limit = 0.2       # 5초에 1회
    concurrency = 1

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        return [CrawlTask(self.source_id, "search", {"keyword": kw}) for kw in keywords]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        url = SEARCH_URL.format(kw=quote(task.params["keyword"]))
        return RawDocument(task, url, datetime.now(), "html", await self.fetcher.get_text(url))

    def parse(self, raw: RawDocument) -> list[ListingSnapshot]:
        soup = BeautifulSoup(raw.body, "html.parser")
        kw = raw.task.params["keyword"]
        out, seen = [], set()
        for a in soup.select('a[href^="/products/"]'):
            m = re.match(r"^/products/(\d+)", a["href"])
            pieces = [p.strip() for p in a.get_text(" | ", strip=True).split(" | ") if p.strip()]
            if not m or m.group(1) in seen or not pieces:
                continue
            price_i = next((i for i, p in enumerate(pieces) if PRICE_RE.match(p)), None)
            if price_i is None:
                continue
            # 가격 바로 앞 (할인율 '13%' 는 건너뜀) = 상품명, 맨 앞 = 브랜드
            name_i = price_i - 1
            while name_i > 0 and pieces[name_i].endswith("%"):
                name_i -= 1
            brand = pieces[0] if name_i > 0 else ""
            seen.add(m.group(1))

            def after(label: str):
                for i, p in enumerate(pieces[:-1]):
                    if p.lstrip("· ").strip() == label:
                        return parse_count(pieces[i + 1])
                return None

            out.append(ListingSnapshot(
                source_id=self.source_id,
                external_id=m.group(1),
                title=f"{brand} {pieces[name_i]}".strip(),
                url=f"https://kream.co.kr/products/{m.group(1)}",
                observed_at=raw.fetched_at,
                price=parse_price(pieces[price_i]),
                rank=len(out) + 1,
                rank_list=f"search:kream:{kw}",
                review_count=after("리뷰"),
                sales_count=after("거래"),
                seller_type="resale",
            ))
        return out
