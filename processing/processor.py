"""처리 계층의 진입점: 파싱된 아이템마다 굿즈 종류를 판별해 저장한다.

  "BTS 공식 응원봉 ver.4"  → 응원봉
  "aespa 응원봉 [무료배송]" → 응원봉
  "세븐틴 캐럿봉 ver.3"     → 응원봉
  "치이카와 말랑이"         → None (사전에 없음 → 저장은 하고, 신규 종류 발견에 쓰임)
"""
from __future__ import annotations

from collections import Counter

from collectors.base import ListingSnapshot, MentionRecord, MetricPoint, ParsedItem
from processing.nlp import classify_goods_type
from storage.repository import Repository


class Processor:
    def __init__(self, repo: Repository):
        self.repo = repo

    def handle(self, items: list[ParsedItem]) -> Counter:
        stats: Counter = Counter()
        for item in items:
            if isinstance(item, ListingSnapshot):
                gt = classify_goods_type(item.title)
                stats["listing" if gt else "listing_unclassified"] += 1
                listing = self.repo.upsert_listing(item, gt)
                self.repo.add_snapshot(listing, item)
            elif isinstance(item, MentionRecord):
                gt = classify_goods_type(item.text)
                if self.repo.add_mention(item, gt):
                    stats["mention" if gt else "mention_unclassified"] += 1
            elif isinstance(item, MetricPoint):
                self.repo.upsert_metric(item, classify_goods_type(item.keyword))
                stats["metric"] += 1
        self.repo.session.flush()
        return stats
