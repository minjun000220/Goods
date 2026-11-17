"""대량 저장: 수백 건을 저장해도 DB 쿼리 수가 적어야 한다 (클라우드 DB 는 왕복 1번이 느림)."""
from datetime import datetime

from sqlalchemy import event, func, select

from collectors.base import ListingSnapshot, MentionRecord
from processing.processor import Processor
from storage.models import Listing, ListingSnapshot as SnapRow, Mention


def _items(t, n=400):
    # 실제 데이터처럼 값이 있는 칸/없는 칸(None) 조합이 섞여 있게 만든다
    out = [ListingSnapshot("kream", str(i), f"BTS 응원봉 {i}", f"https://k/{i}", t, price=50000 if i % 3 else None,
                           rank=i + 1, review_count=i if i % 2 else None, sales_count=i if i % 5 else None,
                           seller_type="resale") for i in range(n)]
    out += [MentionRecord("dc_bts", f"m{i}", f"포카 {i}", f"https://d/{i}", t, 1) for i in range(100)]
    return out


def test_bulk_save_few_queries_and_idempotent(session):
    queries = []
    event.listen(session.get_bind(), "before_cursor_execute", lambda *a, **k: queries.append(1))
    proc = Processor.__new__(Processor)
    from storage.repository import Repository
    proc.repo = Repository(session)

    t1 = datetime(2026, 11, 17, 9)
    stats = proc.handle(_items(t1))
    assert stats["listing"] == 400 and stats["mention"] == 100
    assert len(queries) < 30, len(queries)                    # 건당이 아니라 묶음 단위 쿼리

    # 같은 데이터를 다시 넣어도 중복 저장 안 됨, 다음 날 수집은 스냅샷만 추가
    proc.handle(_items(t1))
    proc.handle(_items(datetime(2026, 11, 18, 9)))
    session.flush()
    assert session.scalar(select(func.count()).select_from(Listing)) == 400
    assert session.scalar(select(func.count()).select_from(SnapRow)) == 800
    assert session.scalar(select(func.count()).select_from(Mention)) == 100
