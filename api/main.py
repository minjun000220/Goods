"""조회 API (FastAPI).

  uvicorn api.main:app --reload
  GET /trending                 요즘 핫한 굿즈 종류 순위 (핫지수 0~100, 어제 대비 변동, 신호별 기여 점수)
  GET /goods/{goods_type}/scores     종류별 날짜별 핫지수·순위 추이
  GET /goods/{goods_type}/timeline   종류별 일자 데이터 (베스트 점유율, 언급량, 품절률 …)
  GET /bursts                   언급량 급상승 + 사전에 없는 새 굿즈 종류 후보
  문서: http://localhost:8000/docs
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analytics.burst import detect_mention_bursts, discover_new_goods_types
from analytics.signals import best_share, load_mentions, load_snapshots
from storage.db import SessionLocal, init_db
from storage.models import HotScore

app = FastAPI(title="Goods Trend API", version="0.2.0")


@app.on_event("startup")
def _startup() -> None:
    init_db()


def get_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _latest_as_of(s: Session) -> date | None:
    return s.scalar(select(func.max(HotScore.as_of)))


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/trending")
def trending(as_of: date | None = None, limit: int = Query(20, le=100), s: Session = Depends(get_session)):
    as_of = as_of or _latest_as_of(s)
    if as_of is None:
        return {"as_of": None, "items": []}
    rows = s.scalars(select(HotScore).where(HotScore.as_of == as_of).order_by(HotScore.rank).limit(limit)).all()
    return {"as_of": as_of,
            "items": [{"rank": r.rank, "goods_type": r.goods_type, "score": r.score, **r.breakdown} for r in rows]}


@app.get("/goods/{goods_type}/scores")
def score_history(goods_type: str, days: int = Query(30, le=365), s: Session = Depends(get_session)):
    """날짜별 핫지수·순위 추이 (트렌드 그래프용)."""
    rows = s.scalars(select(HotScore).where(HotScore.goods_type == goods_type)
                     .order_by(HotScore.as_of.desc()).limit(days)).all()
    if not rows:
        raise HTTPException(404, "no scores for this goods type")
    return {"goods_type": goods_type, "history": [
        {"date": r.as_of, "hot_index": r.breakdown.get("hot_index"), "rank": r.rank, "score": r.score}
        for r in reversed(rows)]}


@app.get("/goods/{goods_type}/timeline")
def timeline(goods_type: str, as_of: date | None = None, s: Session = Depends(get_session)):
    as_of = as_of or _latest_as_of(s) or date.today()
    snap = load_snapshots(s, as_of)
    ment = load_mentions(s, as_of)
    if (snap.empty or goods_type not in set(snap.goods_type)) and (ment.empty or goods_type not in set(ment.goods_type)):
        raise HTTPException(404, "no data for this goods type")

    share = best_share(snap) if not snap.empty else pd.DataFrame(columns=["goods_type", "age", "share"])
    share = share[share.goods_type == goods_type].set_index("age")["share"]
    snap = snap[snap.goods_type == goods_type] if not snap.empty else snap
    ment = ment[ment.goods_type == goods_type] if not ment.empty else ment

    days = []
    for age in range(34, -1, -1):
        day = snap[snap.age == age] if not snap.empty else snap
        retail = day[(day.seller_type == "retail") & (day.stock_status != "unknown")] if not day.empty else day
        resale = day[day.seller_type == "resale"] if not day.empty else day
        days.append({
            "date": as_of - timedelta(days=age),
            "best_share": float(share.get(age, 0.0)),
            "mentions": int((ment.age == age).sum()) if not ment.empty else 0,
            "sold_out_ratio": float((retail.stock_status == "sold_out").mean()) if not retail.empty else None,
            "resale_listings": int(resale.listing_id.nunique()) if not resale.empty else 0,
        })
    return {"goods_type": goods_type, "timeline": days}


@app.get("/bursts")
def bursts(as_of: date | None = None, s: Session = Depends(get_session)):
    as_of = as_of or _latest_as_of(s) or date.today()
    return {"as_of": as_of, "mention_bursts": detect_mention_bursts(s, as_of),
            "new_goods_type_candidates": discover_new_goods_types(s, as_of)}
