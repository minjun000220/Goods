"""범용 커뮤니티 게시판 어댑터 (HTML + CSS 셀렉터).

사이트마다 클래스를 새로 만들지 않고 BoardConfig 만 추가하면 된다.
사이트 구조가 바뀌면 셀렉터만 고치면 된다 (→ monitoring/health.py 가 깨짐을 감지).

반드시 대상 사이트의 robots.txt 와 이용약관을 확인하고, 허용된 범위에서만 사용할 것.
게시글 작성자 정보는 수집하지 않는다.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.base import CrawlTask, MentionRecord, RawDocument, SourceAdapter
from processing.nlp import classify_goods_type


@dataclass(frozen=True)
class BoardConfig:
    source_id: str
    list_url: str              # 예: "https://example.com/board?page={page}"
    row_selector: str          # 게시글 한 줄
    title_selector: str        # 줄 안의 제목 요소 (a 태그면 href 도 사용)
    engagement_selectors: tuple[str, ...] = ()   # 댓글 수, 추천 수 등 숫자 요소
    date_selector: str | None = None             # 작성 시각 요소 (없으면 수집 시각으로 대체)
    date_attr: str | None = None                 # 시각이 속성에 있으면 속성 이름 (예: "title")
    date_format: str = "%Y-%m-%d %H:%M:%S"
    pages: int = 3
    rate_limit: float = 0.5                      # 초당 요청 수 (커뮤니티는 보수적으로)
    only_goods: bool = False                     # True: 굿즈 종류가 언급된 글만 남김 (아이돌 갤러리처럼
                                                 #       잡담이 대부분인 곳에서 굿즈 수요만 골라내기)


class CommunityBoardAdapter(SourceAdapter):
    rate_limit = 0.5   # 2초에 1회: 커뮤니티는 보수적으로
    concurrency = 1

    def __init__(self, fetcher, config: BoardConfig):
        self.rate_limit = config.rate_limit
        super().__init__(fetcher)
        self.config = config
        self.source_id = config.source_id

    def discover(self, keywords: list[str]) -> list[CrawlTask]:
        # 게시판은 키워드 검색 대신 최신 글 목록을 훑는다 (키워드 매칭은 처리 계층에서)
        return [CrawlTask(self.source_id, "board", {"page": p}) for p in range(1, self.config.pages + 1)]

    async def fetch(self, task: CrawlTask) -> RawDocument:
        url = self.config.list_url.format(page=task.params["page"])
        html = await self.fetcher.get_text(url)   # robots.txt 확인 포함
        return RawDocument(task, url, datetime.now(), "html", html)

    def parse(self, raw: RawDocument) -> list[MentionRecord]:
        soup = BeautifulSoup(raw.body, "html.parser")
        out = []
        for row in soup.select(self.config.row_selector):
            title_el = row.select_one(self.config.title_selector)
            if title_el is None:
                continue
            title = title_el.get_text(" ", strip=True)
            if self.config.only_goods and classify_goods_type(title) is None:
                continue
            href = title_el.get("href") or ""
            link = urljoin(raw.url, href) if href else raw.url
            engagement = 0
            for sel in self.config.engagement_selectors:
                el = row.select_one(sel)
                if el and (m := re.search(r"\d[\d,]*", el.get_text())):
                    engagement += int(m.group().replace(",", ""))
            out.append(MentionRecord(
                source_id=self.source_id,
                external_id=hashlib.sha1(link.encode()).hexdigest()[:20],
                text=title,
                url=link,
                observed_at=self._posted_at(row) or raw.fetched_at,
                engagement=engagement,
            ))
        return out

    def _posted_at(self, row) -> datetime | None:
        c = self.config
        if not c.date_selector:
            return None
        el = row.select_one(c.date_selector)
        if el is None:
            return None
        raw = (el.get(c.date_attr) if c.date_attr else el.get_text(strip=True)) or ""
        try:
            return datetime.strptime(raw.strip(), c.date_format)
        except ValueError:
            return None
