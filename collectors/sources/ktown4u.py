"""케이타운포유(Ktown4u) 검색 결과 어댑터 — K-pop 공식 굿즈·앨범 판매처.

robots.txt: User-agent * 에 대해 /cart, /mypage, /checkout 등 주문·회원 경로만 금지, 검색 목록(/searchList) 허용 — 2026-11 확인.
검색 결과 페이지가 Next.js 라서 화면 글자 대신 페이지에 함께 담긴 데이터(__NEXT_DATA__)를 읽는다:
  goodsNo(상품 번호) · goodsNm(상품명, "에스파 (aespa) - …" 처럼 아티스트 포함) · dispDcPrice/dispPrice(판매가, 원)
  grpNm(아티스트) · kindNm(사이트 분류: Keyring, FAN Light, Slogan …) · goodsTotSale(누적 판매 수량, 숨김이면 없음)
  saleYn(판매 중 여부)

굿즈 종류는 사이트 분류(kindNm)를 우선 쓴다. 제목만 보면 "응원봉 미니 키링" 이 응원봉으로 잡히는데,
사이트는 이것을 Keyring 으로 분류해 두었기 때문이다. 분류가 애매하면(Toy, Card 등) 제목으로 판별한다.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import quote

from collectors.base import CrawlTask, ListingSnapshot, RawDocument, SourceAdapter

SEARCH_URL = "https://kr.ktown4u.com/searchList?goodsTextSearch={kw}"
ITEM_URL = "https://kr.ktown4u.com/iteminfo?goods_no={no}"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# 사이트 분류 → 굿즈 종류 (processing/dictionaries.py 의 이름). 없는 분류는 제목으로 판별
KIND_TO_TYPE = {
    "keyring": "키링",
    "fan light": "응원봉",
    "light stick": "응원봉",
    "slogan": "슬로건",
    "photocards": "포토카드",
    "photocard": "포토카드",
    "plush toys": "인형",
    "doll": "인형",
    "badge": "뱃지",
    "photobook": "포토북",
    "t-shirts": "티셔츠",
    "sticker": "스티커",
    "poster": "포스터",
    "cushion": "쿠션",
    "mug": "머그컵",
    "acrylic stand": "아크릴스탠드",
}


def kind_to_type(kind: str | None) -> str | None:
    if not kind:
        return None
    k = kind.strip().lower()
    if "season" in k and "greeting" in k:          # "2027 SEASON'S GREETINGS"
        return "시즌그리팅"
    return KIND_TO_TYPE.get(k)


def parse_items(html: str) -> list[dict]:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        return (data["props"]["pageProps"].get("result") or {}).get("data") or []
    except (ValueError, KeyError, TypeError):
        return []


class Ktown4uAdapter(SourceAdapter):
    source_id = "ktown4u"
    rate_limit = 0.2       # 5초에 1회
    concurrency = 1

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        return [CrawlTask(self.source_id, "search", {"keyword": kw}) for kw in keywords]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        url = SEARCH_URL.format(kw=quote(task.params["keyword"]))
        return RawDocument(task, url, datetime.now(), "html", await self.fetcher.get_text(url))

    def parse(self, raw: RawDocument) -> list[ListingSnapshot]:
        kw = raw.task.params["keyword"]
        out = []
        for i, it in enumerate(parse_items(raw.body), 1):
            no, title = it.get("goodsNo"), (it.get("goodsNm") or "").strip()
            price = it.get("dispDcPrice") or it.get("dispPrice")
            if not no or not title:
                continue
            sales = it.get("goodsTotSale") if it.get("sellQtyHideYn") != "Y" else None
            out.append(ListingSnapshot(
                source_id=self.source_id,
                external_id=str(no),
                title=title,
                url=ITEM_URL.format(no=no),
                observed_at=raw.fetched_at,
                price=int(price) if price else None,
                rank=i,
                rank_list=f"search:ktown4u:{kw}",
                stock_status="in_stock" if it.get("saleYn") == "Y" else "sold_out" if it.get("saleYn") == "N" else "unknown",
                sales_count=int(sales) if isinstance(sales, (int, float)) else None,
                seller_type="retail",
                goods_type_hint=kind_to_type(it.get("kindNm")),
            ))
        return out
