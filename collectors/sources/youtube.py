"""YouTube Data API v3 어댑터 (공식 API).

키 발급: Google Cloud Console → 'YouTube Data API v3' 사용 설정 → API 키 생성
할당량: 기본 하루 10,000 단위. search.list = 100, videos.list = 1 단위
        → 굿즈 종류 18개를 하루 1번 검색하면 약 1,800 단위.

검색어(굿즈 종류)로 최근 24시간 업로드된 영상을 찾고, 조회 통계(좋아요·댓글)를 붙여
'언급(Mention)'으로 저장한다 → 언박싱·리뷰 영상이 늘면 buzz_momentum 이 오른다.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone

from collectors.base import CrawlTask, MentionRecord, RawDocument, SourceAdapter

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeAdapter(SourceAdapter):
    source_id = "youtube"
    rate_limit = 2.0
    concurrency = 2

    def __init__(self, fetcher, api_key: str, lookback_hours: int = 24, max_results: int = 50):
        super().__init__(fetcher)
        self.api_key = api_key
        self.lookback_hours = lookback_hours
        self.max_results = max_results

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        since = (datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # "인형"만 검색하면 아이 장난감 영상이 대부분 → "인형 굿즈"처럼 굿즈 맥락으로 좁힌다
        return [CrawlTask(self.source_id, "search", {"q": f"{kw} 굿즈", "publishedAfter": since}) for kw in keywords]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        search = (await self.fetcher.request("GET", SEARCH_URL, check_robots=False, params={
            "part": "snippet", "type": "video", "order": "date", "q": task.params["q"],
            "publishedAfter": task.params["publishedAfter"], "regionCode": "KR",
            "relevanceLanguage": "ko", "maxResults": self.max_results, "key": self.api_key,
        })).json()
        ids = [it["id"]["videoId"] for it in search.get("items", []) if it.get("id", {}).get("videoId")]
        stats = {}
        if ids:
            videos = (await self.fetcher.request("GET", VIDEOS_URL, check_robots=False, params={
                "part": "statistics", "id": ",".join(ids), "key": self.api_key,
            })).json()
            stats = {v["id"]: v.get("statistics", {}) for v in videos.get("items", [])}
        body = json.dumps({"search": search, "stats": stats}, ensure_ascii=False)
        return RawDocument(task, SEARCH_URL, datetime.now(), "json", body)

    def parse(self, raw: RawDocument) -> list[MentionRecord]:
        data = json.loads(raw.body)
        out = []
        for it in data["search"].get("items", []):
            vid = it.get("id", {}).get("videoId")
            if not vid:
                continue
            sn = it["snippet"]
            st = data["stats"].get(vid, {})
            published = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            out.append(MentionRecord(
                source_id=self.source_id,
                external_id=vid,
                # 제목 그대로 저장: 종류 이름이 있으면 그 종류의 언급량에, 없으면 '미분류'로 남아
                # 새로 뜨는 단어(예: "훈바루즈") 감시에 쓰인다. (검색어를 붙이면 새 단어를 못 잡음)
                text=html.unescape(sn.get("title", "")),
                url=f"https://www.youtube.com/watch?v={vid}",
                observed_at=published.astimezone().replace(tzinfo=None),
                engagement=int(st.get("likeCount", 0)) + int(st.get("commentCount", 0)),
            ))
        return out
