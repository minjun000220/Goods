"""파서 깨짐 감지.

크롤링 시스템 운영 이슈의 대부분은 '사이트 구조가 바뀌어 파서가 조용히 0건을 내는 것'이다.
에러가 안 나고 결과만 비기 때문에 따로 감시하지 않으면 며칠씩 모른다.

규칙
 - 최근 실행의 아이템 수가 과거 평균의 30% 미만 → 경고
 - 최근 실행의 실패율이 50% 이상 → 경고
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from storage.models import CrawlRun


def check_parser_health(session: Session, history: int = 10, drop_ratio: float = 0.3) -> list[str]:
    alerts = []
    sources = session.scalars(select(CrawlRun.source_id).distinct()).all()
    for src in sources:
        runs = session.scalars(select(CrawlRun).where(CrawlRun.source_id == src)
                               .order_by(CrawlRun.started_at.desc()).limit(history + 1)).all()
        if not runs:
            continue
        last, prev = runs[0], runs[1:]
        if last.tasks and last.failures / last.tasks >= 0.5:
            alerts.append(f"{src}: 실패율 {last.failures}/{last.tasks} — {last.errors[:1]}")
        if prev:
            avg = sum(r.items for r in prev) / len(prev)
            if avg > 0 and last.items < avg * drop_ratio:
                alerts.append(f"{src}: 수집량 급감 {last.items}건 (평균 {avg:.0f}건) — 셀렉터/응답 구조 확인 필요")
    return alerts


if __name__ == "__main__":
    # GitHub Actions 에서 실행하면 경고가 실행 결과 화면에 노란 표시로 뜬다
    from storage.db import init_db, session_scope

    init_db()
    with session_scope() as s:
        alerts = check_parser_health(s)
    for a in alerts:
        print(f"::warning::{a}")
    print(f"수집 상태 점검: 경고 {len(alerts)}건")
