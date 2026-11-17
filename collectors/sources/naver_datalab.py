"""네이버 데이터랩 검색어 트렌드 API 어댑터. 검색어 = 굿즈 종류 ("응원봉", "키링" …).

문서: https://developers.naver.com/docs/serviceapi/datalab/search/search.md
주의: 값(ratio)은 '요청 안에서 최댓값=100' 인 상대값이다. 요청마다 기준이 달라지므로
      같은 키워드는 항상 같은 묶음/같은 기간으로 요청하거나, 기준 키워드를 함께 넣어
      스케일을 맞춰야 한다. 여기서는 키워드마다 단독 요청 → 키워드 내부 추세만 비교한다.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from collectors.base import CrawlTask, MetricPoint, RawDocument, SourceAdapter

API_URL = "https://openapi.naver.com/v1/datalab/search"


class NaverDataLabAdapter(SourceAdapter):
    source_id = "naver_datalab"
    rate_limit = 2.0

    def __init__(self, fetcher, client_id: str, client_secret: str, lookback_days: int = 60):
        super().__init__(fetcher)
        self.headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "Content-Type": "application/json",
        }
        self.lookback_days = lookback_days

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        end = date.today()
        start = end - timedelta(days=self.lookback_days)
        return [
            CrawlTask(self.source_id, "trend",
                      {"keyword": kw, "startDate": start.isoformat(), "endDate": end.isoformat()})
            for kw in keywords
        ]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        body = {
            "startDate": task.params["startDate"],
            "endDate": task.params["endDate"],
            "timeUnit": "date",
            "keywordGroups": [{"groupName": task.params["keyword"], "keywords": [task.params["keyword"]]}],
        }
        resp = await self.fetcher.request(
            "POST", API_URL, content=json.dumps(body, ensure_ascii=False).encode(),
            headers=self.headers, check_robots=False,
        )
        return RawDocument(task, API_URL, datetime.now(), "json", resp.text)

    def parse(self, raw: RawDocument) -> list[MetricPoint]:
        data = json.loads(raw.body)
        out = []
        for group in data.get("results", []):
            for point in group.get("data", []):
                out.append(MetricPoint(
                    source_id=self.source_id,
                    keyword=group["title"],
                    metric="search_volume",
                    date=date.fromisoformat(point["period"]),
                    value=float(point["ratio"]),
                ))
        return out
