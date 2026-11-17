"""Repository: DB 접근을 한곳에 모은다. 다른 계층은 SQL 을 직접 쓰지 않는다."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from collectors.base import ListingSnapshot as SnapshotDTO
from collectors.base import MentionRecord, MetricPoint, RunStats
from storage.models import CrawlRun, HotScore, Listing, ListingSnapshot, Mention, TypeMetric


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_listing(self, snap: SnapshotDTO, goods_type: str | None) -> Listing:
        listing = self.session.scalar(select(Listing).where(
            Listing.source_id == snap.source_id, Listing.external_id == snap.external_id))
        if listing is None:
            listing = Listing(source_id=snap.source_id, external_id=snap.external_id, goods_type=goods_type,
                              title_raw=snap.title[:500], url=snap.url[:1000], seller_type=snap.seller_type)
            self.session.add(listing)
            self.session.flush()
        else:
            listing.title_raw = snap.title[:500]
            listing.goods_type = goods_type     # 사전이 갱신되면 재분류 결과를 반영
        return listing

    def add_snapshot(self, listing: Listing, snap: SnapshotDTO) -> bool:
        exists = self.session.scalar(select(ListingSnapshot.id).where(
            ListingSnapshot.listing_id == listing.id, ListingSnapshot.observed_at == snap.observed_at))
        if exists:
            return False
        self.session.add(ListingSnapshot(
            listing_id=listing.id, observed_at=snap.observed_at, price=snap.price, rank=snap.rank,
            rank_list=snap.rank_list, stock_status=snap.stock_status, review_count=snap.review_count,
            sales_count=snap.sales_count))
        return True

    def add_mention(self, rec: MentionRecord, goods_type: str | None) -> bool:
        exists = self.session.scalar(select(Mention.id).where(
            Mention.source_id == rec.source_id, Mention.external_id == rec.external_id))
        if exists:
            return False
        self.session.add(Mention(source_id=rec.source_id, external_id=rec.external_id, goods_type=goods_type,
                                 text=rec.text[:2000], url=rec.url[:1000], observed_at=rec.observed_at,
                                 engagement=rec.engagement))
        return True

    def upsert_metric(self, p: MetricPoint, goods_type: str | None) -> None:
        row = self.session.scalar(select(TypeMetric).where(
            TypeMetric.source_id == p.source_id, TypeMetric.keyword == p.keyword,
            TypeMetric.metric == p.metric, TypeMetric.date == p.date))
        if row is None:
            self.session.add(TypeMetric(source_id=p.source_id, keyword=p.keyword, goods_type=goods_type,
                                        metric=p.metric, date=p.date, value=p.value))
        else:
            row.value = p.value

    def replace_scores(self, as_of: date, rows: list[dict]) -> None:
        self.session.execute(delete(HotScore).where(HotScore.as_of == as_of))
        self.session.add_all(HotScore(as_of=as_of, **r) for r in rows)

    def add_crawl_run(self, s: RunStats) -> None:
        self.session.add(CrawlRun(source_id=s.source_id, started_at=s.started_at, finished_at=s.finished_at,
                                  tasks=s.tasks, failures=s.failures, items=s.items, errors=s.errors[:20]))
