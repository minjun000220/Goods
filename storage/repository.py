"""Repository: DB 접근을 한곳에 모은다. 다른 계층은 SQL 을 직접 쓰지 않는다."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from collectors.base import ListingSnapshot as SnapshotDTO
from collectors.base import MentionRecord, MetricPoint, RunStats
from storage.models import CrawlRun, HotScore, Listing, ListingSnapshot, Mention, TypeMetric


CHUNK = 500   # IN (...) 한 번에 넣는 개수
# 참고: ORM 대량 INSERT 는 기본적으로 "None 인 칸 조합"이 다른 행끼리 쿼리를 쪼갠다 → render_nulls=True 로 한 번에 보냄


def _chunks(seq, n=CHUNK):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


class _IdOnly:
    """새로 넣은 리스팅의 ID 만 담는 가벼운 객체."""
    __slots__ = ("id",)

    def __init__(self, id_: int):
        self.id = id_


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # -- 대량 저장 (클라우드 DB 왕복 횟수를 줄이기 위해 수백 건을 몇 번의 쿼리로 처리) ------------
    def bulk_save_listings(self, pairs: list[tuple[SnapshotDTO, str | None]]) -> int:
        """(스냅샷, 굿즈 종류) 목록을 저장. 새로 저장한 스냅샷 수를 돌려준다."""
        if not pairs:
            return 0
        latest: dict[tuple[str, str], tuple[SnapshotDTO, str | None]] = {}
        for snap, gt in pairs:
            latest[(snap.source_id, snap.external_id)] = (snap, gt)

        listings: dict[tuple[str, str], Listing] = {}
        for source in {k[0] for k in latest}:
            ids = [k[1] for k in latest if k[0] == source]
            for chunk in _chunks(ids):
                for row in self.session.scalars(select(Listing).where(
                        Listing.source_id == source, Listing.external_id.in_(chunk))):
                    listings[(source, row.external_id)] = row

        new = []
        for key, (snap, gt) in latest.items():
            row = listings.get(key)
            if row is None:
                new.append({"source_id": snap.source_id, "external_id": snap.external_id, "goods_type": gt,
                            "title_raw": snap.title[:500], "url": snap.url[:1000], "seller_type": snap.seller_type})
            else:
                if row.title_raw != snap.title[:500]:
                    row.title_raw = snap.title[:500]
                if row.goods_type != gt:
                    row.goods_type = gt
        if new:
            # 여러 줄을 한 번에 INSERT 한 뒤, 새 ID 는 묶음 SELECT 로 받아온다
            for chunk in _chunks(new):
                self.session.execute(insert(Listing).execution_options(render_nulls=True), chunk)
            for source in {r["source_id"] for r in new}:
                ids = [r["external_id"] for r in new if r["source_id"] == source]
                for chunk in _chunks(ids):
                    for lid, ext in self.session.execute(select(Listing.id, Listing.external_id).where(
                            Listing.source_id == source, Listing.external_id.in_(chunk))):
                        listings[(source, ext)] = _IdOnly(lid)
        self.session.flush()

        ids = {listings[(s.source_id, s.external_id)].id for s, _ in pairs}
        times = {s.observed_at for s, _ in pairs}
        existing: set[tuple[int, object]] = set()
        for chunk in _chunks(ids):
            existing |= set(self.session.execute(select(ListingSnapshot.listing_id, ListingSnapshot.observed_at)
                                                 .where(ListingSnapshot.listing_id.in_(chunk),
                                                        ListingSnapshot.observed_at.in_(times))).all())
        snaps = []
        for snap, _ in pairs:
            lid = listings[(snap.source_id, snap.external_id)].id
            if (lid, snap.observed_at) in existing:
                continue
            existing.add((lid, snap.observed_at))
            snaps.append({"listing_id": lid, "observed_at": snap.observed_at, "price": snap.price,
                          "rank": snap.rank, "rank_list": snap.rank_list, "stock_status": snap.stock_status,
                          "review_count": snap.review_count, "sales_count": snap.sales_count})
        for chunk in _chunks(snaps):
            self.session.execute(insert(ListingSnapshot).execution_options(render_nulls=True), chunk)
        return len(snaps)

    def bulk_add_mentions(self, pairs: list[tuple[MentionRecord, str | None]]) -> list[str | None]:
        """새 언급만 저장하고, 저장된 것들의 굿즈 종류 목록을 돌려준다 (통계용)."""
        existing: set[tuple[str, str]] = set()
        for source in {m.source_id for m, _ in pairs}:
            ids = [m.external_id for m, _ in pairs if m.source_id == source]
            for chunk in _chunks(ids):
                existing |= {(source, e) for e in self.session.scalars(select(Mention.external_id).where(
                    Mention.source_id == source, Mention.external_id.in_(chunk)))}
        added, rows = [], []
        for m, gt in pairs:
            key = (m.source_id, m.external_id)
            if key in existing:
                continue
            existing.add(key)
            rows.append({"source_id": m.source_id, "external_id": m.external_id, "goods_type": gt,
                         "text": m.text[:2000], "url": m.url[:1000], "observed_at": m.observed_at,
                         "engagement": m.engagement})
            added.append(gt)
        for chunk in _chunks(rows):
            self.session.execute(insert(Mention).execution_options(render_nulls=True), chunk)
        return added

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
