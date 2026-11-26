"""오프라인 데모 소스.

실제 사이트 대신 그럴듯한 가짜 데이터를 만들어 전체 파이프라인을 API 키나 네트워크 없이
돌려볼 수 있게 한다. 다른 어댑터와 똑같이 JSON 원본을 만들고 parse() 로 해석한다.

시나리오 (굿즈 종류 단위, as_of 날짜에 따라 인기도 heat 가 변한다):
  - 인형      : 막판에 폭발적으로 뜸          ← 1등이 나와야 정상
  - 응원봉    : 늘 많이 팔리지만 변화 없음     ← 절대량이 크다고 1등 하면 안 됨
                (BTS·aespa·세븐틴 응원봉이 모두 '응원봉' 하나로 합쳐지는지도 확인)
  - 키링      : 식는 중
  - 피규어    : 천천히 상승
  - 포토카드  : 조용함
  - 말랑이    : 사전에 없는 새 종류가 막판에 등장 ← '신규 굿즈 종류 후보'로 발견돼야 정상
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, time, timedelta

from collectors.base import (CrawlTask, ListingSnapshot, MentionRecord, MetricPoint, RawDocument,
                             SourceAdapter)

GOODS = {
    "인형": {"profile": "explode", "price": 32000, "titles": [
        "[공식] 치이카와 하치와레 인형 M사이즈", "먼작귀 우사기 누이 M", "산리오 쿠로미 봉제인형",
        "포켓몬 잠만보 인형 대형", "소니엔젤 훈바루즈 자세교정 인형 판다"],
        "mentions": ["인형 어디서 구해요?", "하치와레 인형 품절 ㅠㅠ", "인형 드디어 득템", "누이 재입고 언제?",
                     "훈바루즈 인형 효과 있음?", "훈바루즈 자세교정 인형 샀어요"]},
    "응원봉": {"profile": "steady_high", "price": 55000, "titles": [
        "BTS 공식 응원봉 ver.4", "aespa 응원봉 [무료배송]", "세븐틴 캐럿봉 ver.3",
        "NewJeans OFFICIAL LIGHT STICK", "아이브 응원봉"],
        "mentions": ["응원봉 블루투스 연동 질문", "콘서트 응원봉 배터리 추천", "응원봉 케이스 정보"]},
    "키링": {"profile": "declining", "price": 9000, "titles": [
        "산리오 쿠로미 키링 [당일출고]", "치이카와 키홀더", "포켓몬 피카츄 키링",
        "짱구 키링 랜덤", "젤리캣 버니 키링"],
        "mentions": ["키링 가방에 달았어요", "키홀더 색깔 추천"]},
    "피규어": {"profile": "rising_slow", "price": 45000, "titles": [
        "포켓몬 피카츄 피규어 ★한정★", "원피스 루피 피규어", "넨도로이드 신작", "치이카와 가챠 피규어", "짱구 피규어"],
        "mentions": ["피규어 퀄리티 좋네요", "가챠 또 돌렸다"]},
    "포토카드": {"profile": "steady_low", "price": 5000, "titles": [
        "BTS 포토카드 세트", "aespa 포카 랜덤", "세븐틴 포토카드", "아이브 포카 바인더용", "뉴진스 포카"],
        "mentions": ["포카 교환 구해요"]},
    "_말랑이(미등록)": {"profile": "new", "price": 15000, "titles": [
        "치이카와 말랑이 스퀴시", "산리오 말랑이", "포켓몬 말랑이 스퀴시", "고양이 말랑이", "두부 말랑이"],
        "mentions": ["말랑이 어디서 사요", "요즘 말랑이 유행이래", "말랑이 스퀴시 촉감 미쳤다"]},
}


def heat(profile: str, t: float) -> float:
    """t: 0(기간 시작) ~ 1(기간 끝). 반환: 인기도 (대략 0 ~ 3)."""
    if profile == "explode":
        return 0.4 + 2.6 * max(0.0, (t - 0.65) / 0.35) ** 1.5
    if profile == "steady_high":
        return 1.6
    if profile == "declining":
        return 1.6 - 1.2 * t
    if profile == "rising_slow":
        return 0.6 + 0.7 * t
    if profile == "new":
        return 0.0 if t < 0.75 else 2.2 * (t - 0.75) / 0.25
    return 0.5


def _poisson(rng: random.Random, lam: float) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


class DemoSource(SourceAdapter):
    source_id = "demo"
    rate_limit = 1000.0

    def __init__(self, as_of: date, start: date, end: date):
        super().__init__(fetcher=None)
        self.as_of, self.start, self.end = as_of, start, end

    def _t(self, d: date) -> float:
        return (d - self.start).days / max(1, (self.end - self.start).days)

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        return [CrawlTask(self.source_id, "demo_day", {"date": self.as_of.isoformat()})]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        d = date.fromisoformat(task.params["date"])
        payload = {"listings": [], "mentions": [], "metrics": []}
        products = []   # (점수, 종류키, 제목인덱스)

        for gkey, g in GOODS.items():
            h = heat(g["profile"], self._t(d))
            rng = random.Random(f"{gkey}-{d}")
            for ti in range(len(g["titles"])):
                if h > 0:
                    products.append((h * random.Random(f"{gkey}-{ti}-{d}").uniform(0.6, 1.4), gkey, ti))
            # 리셀 매물: 인기가 높을수록 새 매물이 많이 올라온다
            for i in range(_poisson(rng, 3 * h)):
                payload["listings"].append({
                    "id": f"resale-{gkey}-{d}-{i}", "title": rng.choice(g["titles"]) + " 미개봉 양도",
                    "price": int(g["price"] * (0.8 + 0.3 * h)), "rank": None, "rank_list": None,
                    "stock": "판매중", "reviews": None, "seller": "resale"})
            # 커뮤니티 언급
            for i in range(_poisson(rng, 5 * h)):
                payload["mentions"].append({
                    "id": f"m-{gkey}-{d}-{i}", "text": rng.choice(g["mentions"]),
                    "engagement": int(rng.random() * 30 * h)})
            # 종류 키워드 지표 (사전에 있는 종류만 검색어로 추적된다 → 말랑이는 없음)
            if not gkey.startswith("_"):
                payload["metrics"].append({"keyword": gkey, "metric": "listing_total",
                                           "value": round(800 * (1 + 0.25 * h) * rng.uniform(0.97, 1.03))})

        # 쇼핑몰 베스트 랭킹: 인기 점수 순으로 줄 세우기
        products.sort(reverse=True)
        for rank, (_, gkey, ti) in enumerate(products, start=1):
            g = GOODS[gkey]
            h = heat(g["profile"], self._t(d))
            rng = random.Random(f"st-{gkey}-{ti}-{d}")
            reviews = sum(_poisson(random.Random(f"rv-{gkey}-{ti}-{x}"), 4 * heat(g["profile"], self._t(x)))
                          for x in (self.start + timedelta(days=k) for k in range((d - self.start).days + 1)))
            payload["listings"].append({
                "id": f"best-{gkey}-{ti}", "title": g["titles"][ti], "price": f"{g['price']:,}원",
                "rank": rank, "rank_list": "best:demo_mall",
                "stock": "품절" if rng.random() < min(0.9, 0.1 * h ** 2) else "판매중",
                "reviews": reviews, "seller": "retail"})

        return RawDocument(CrawlTask(self.source_id, "demo_day", task.params), f"https://demo.local/{d}",
                           datetime.combine(d, time(12)), "json", json.dumps(payload, ensure_ascii=False))

    def parse(self, raw: RawDocument):
        from processing.normalize import normalize_stock, parse_price

        data = json.loads(raw.body)
        out: list = []
        for it in data["listings"]:
            out.append(ListingSnapshot(
                source_id=self.source_id, external_id=it["id"], title=it["title"],
                url=f"https://demo.local/item/{it['id']}", observed_at=raw.fetched_at,
                price=parse_price(it["price"]), rank=it["rank"], rank_list=it["rank_list"],
                stock_status=normalize_stock(it["stock"]), review_count=it["reviews"], seller_type=it["seller"]))
        for it in data["mentions"]:
            out.append(MentionRecord(self.source_id, it["id"], it["text"], f"https://demo.local/post/{it['id']}",
                                     raw.fetched_at, it["engagement"]))
        for it in data["metrics"]:
            out.append(MetricPoint(self.source_id, it["keyword"], it["metric"], raw.fetched_at.date(), it["value"]))
        return out
