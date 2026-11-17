"""X(트위터) API v2 '최근 게시물 수' 어댑터 (공식 API, 유료).

엔드포인트: GET /2/tweets/counts/recent  — 최근 7일간 검색어별 '일별 게시물 수'
글 내용을 하나하나 가져오지 않고 개수만 받으므로 저렴하고 개인정보도 다루지 않는다.

필요: developer.x.com 에서 앱 생성 → Bearer Token. 이 엔드포인트는 유료 플랜/종량제에서만
      제공되므로, 가입 전에 현재 요금제에서 counts 엔드포인트를 쓸 수 있는지 확인할 것.
결과는 MetricPoint(metric="x_post_count") → sns_momentum 신호.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from collectors.base import CrawlTask, MetricPoint, RawDocument, SourceAdapter

COUNTS_URL = "https://api.x.com/2/tweets/counts/recent"


class XCountsAdapter(SourceAdapter):
    source_id = "x"
    rate_limit = 0.2
    concurrency = 1

    def __init__(self, fetcher, bearer_token: str):
        super().__init__(fetcher)
        self.headers = {"Authorization": f"Bearer {bearer_token}"}

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        return [CrawlTask(self.source_id, "counts", {"keyword": kw}) for kw in keywords]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        params = {"query": f"\"{task.params['keyword']}\" -is:retweet", "granularity": "day"}
        resp = await self.fetcher.request("GET", COUNTS_URL, params=params, headers=self.headers,
                                          check_robots=False)
        return RawDocument(task, COUNTS_URL, datetime.now(), "json", resp.text)

    def parse(self, raw: RawDocument) -> list[MetricPoint]:
        data = json.loads(raw.body)
        kw = raw.task.params["keyword"]
        today = raw.fetched_at.date()
        out = []
        for b in data.get("data", []):
            d = date.fromisoformat(b["start"][:10])
            if d >= today:          # 오늘은 아직 덜 찬 구간 → 제외
                continue
            out.append(MetricPoint(self.source_id, kw, "x_post_count", d, float(b["tweet_count"])))
        return out
