"""Hot Score: 여러 신호를 굿즈 종류별 '핫함' 점수 하나로 합친다.

  HotScore = Σ wᵢ · z(signalᵢ) / Σ wᵢ

- z(): robust z-score (중앙값·MAD 기준). 이상치 하나에 전체 스케일이 흔들리지 않는다.
- 값이 없는 신호는 0(중립)으로 취급하되, coverage 로 '근거가 몇 개인지'를 같이 남긴다.
- 가중치는 처음엔 직접 정하고, 나중엔 '실제로 유행한 종류' 라벨로 학습해 교체한다.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analytics.signals import SIGNALS, compute_type_signals
from storage.models import HotScore, ItemScore
from storage.repository import Repository

WEIGHTS: dict[str, float] = {
    "best_share_momentum": 1.5,  # 베스트 랭킹을 점점 더 많이 차지한다 = 실제로 팔린다
    "buzz_momentum": 1.2,        # 커뮤니티·유튜브에서 이야기가 늘었다 (판매보다 먼저 반응)
    "sold_out_ratio": 1.2,       # 공급이 수요를 못 따라간다
    "resale_momentum": 1.0,      # 되팔 만큼 수요가 있다
    "resale_trade_velocity": 1.2,  # 리셀 마켓 거래가 빨라졌다 (웃돈 주고도 산다)
    "review_velocity": 0.8,      # 구매 후기가 빨리 쌓인다
    "listing_growth": 0.5,       # 파는 곳이 늘었다 (공급 쪽 반응, 늦게 따라옴)
}
Z_CLIP = 4.0

SIGNAL_LABELS: dict[str, str] = {
    "best_share_momentum": "베스트 순위 점유율",
    "buzz_momentum": "커뮤니티 언급량",
    "sold_out_ratio": "품절 비율",
    "resale_momentum": "리셀 매물",
    "resale_trade_velocity": "리셀 거래 속도",
    "review_velocity": "리뷰 증가",
    "listing_growth": "판매처 증가",
}


def hot_index(score: float) -> int:
    """내부 점수(대략 -2~+2) → 핫지수 0~100. 50 = 평소 수준, 70 이상 = 뜨는 중, 85 이상 = 급상승."""
    return int(round(100 / (1 + math.exp(-1.5 * score))))


def index_label(idx: int) -> str:
    if idx >= 85:
        return "🔥 급상승"
    if idx >= 70:
        return "📈 상승"
    if idx > 30:
        return "➖ 보합"
    if idx > 15:
        return "📉 하락"
    return "🧊 급하락"


def robust_z(s: pd.Series, ref: pd.Series | None = None) -> pd.Series:
    """ref 가 주어지면 그 분포(중앙값·MAD)를 잣대로 s 를 잰다.
    주목 아이템은 몇 개뿐이라 자기들끼리 비교하면 의미가 없어서, 굿즈 종류들의 분포를 잣대로 쓴다."""
    valid = (s if ref is None else ref).dropna()
    if len(valid) < 2:
        return pd.Series(0.0, index=s.index).where(s.notna())
    med = valid.median()
    scale = 1.4826 * (valid - med).abs().median()
    if not scale or np.isnan(scale):
        scale = valid.std(ddof=0)
    if not scale or np.isnan(scale):
        return pd.Series(0.0, index=s.index).where(s.notna())
    return ((s - med) / scale).clip(-Z_CLIP, Z_CLIP)


def score_frame(df: pd.DataFrame, ref: pd.DataFrame | None = None) -> pd.DataFrame:
    df = df.copy()
    for sig in SIGNALS:
        if sig not in df:
            df[sig] = np.nan
        ref_s = None if ref is None else (ref[sig].astype(float) if sig in ref else pd.Series(dtype=float))
        df[f"z_{sig}"] = robust_z(df[sig].astype(float), ref_s)
    df["score"] = sum(WEIGHTS[s] * df[f"z_{s}"].fillna(0) for s in SIGNALS) / sum(WEIGHTS.values())
    df["coverage"] = df[SIGNALS].notna().sum(axis=1)
    df["hot_index"] = df["score"].apply(hot_index)
    df = df.sort_values("score", ascending=False)
    df["rank"] = np.arange(1, len(df) + 1)
    return df


def contributions(row: pd.Series) -> dict[str, float]:
    """신호별 기여 점수 (핫지수 단위). 모두 더하면 '핫지수 - 50' 과 대략 같다."""
    total_w = sum(WEIGHTS.values())
    raw = {s: WEIGHTS[s] * float(row[f"z_{s}"]) / total_w for s in SIGNALS if pd.notna(row[f"z_{s}"])}
    score = sum(raw.values())
    if abs(score) < 1e-9:
        return {s: 0.0 for s in raw}
    total_pts = hot_index(score) - 50
    return {s: round(v / score * total_pts, 1) for s, v in raw.items()}


def previous_scores(session: Session, as_of: date, model=HotScore) -> dict[str, dict]:
    """as_of 직전 계산일의 순위·핫지수 (어제 대비 변동 계산용). model = HotScore(종류) 또는 ItemScore(아이템)."""
    prev_day = session.scalar(select(func.max(model.as_of)).where(model.as_of < as_of))
    if prev_day is None:
        return {}
    rows = session.scalars(select(model).where(model.as_of == prev_day)).all()
    name = "goods_type" if model is HotScore else "item"
    return {getattr(r, name): {"rank": r.rank, "hot_index": r.breakdown.get("hot_index", hot_index(r.score)),
                               "as_of": prev_day.isoformat()} for r in rows}


def _breakdown(row: pd.Series, prev: dict | None) -> dict:
    pts = contributions(row)
    sig = {s: {"label": SIGNAL_LABELS[s], "value": round(float(row[s]), 4),
               "z": round(float(row[f"z_{s}"]), 2), "points": pts.get(s, 0.0)}
           for s in SIGNALS if pd.notna(row[s])}
    idx = int(row["hot_index"])
    return {
        "hot_index": idx,
        "label": index_label(idx),
        # 어제 대비: rank_change 양수 = 순위 상승, None = 비교할 이전 기록 없음 (새로 등장)
        "rank_change": (prev["rank"] - int(row["rank"])) if prev else None,
        "index_change": (idx - prev["hot_index"]) if prev else None,
        "prev_as_of": prev["as_of"] if prev else None,
        "coverage": int(row["coverage"]), "signals": sig,
        "examples": row.get("examples") or [], "mentions_7d": int(row.get("mentions_7d", 0)),
    }


def run_scoring(session: Session, as_of: date) -> pd.DataFrame:
    """굿즈 종류별 점수를 계산해 저장하고, 점수 표를 돌려준다."""
    signals = compute_type_signals(session, as_of)
    if signals.empty:
        return signals
    scored = score_frame(signals)
    prev = previous_scores(session, as_of)
    rows = [{"goods_type": gt, "score": round(float(r.score), 4), "rank": int(r["rank"]),
             "breakdown": _breakdown(r, prev.get(gt))} for gt, r in scored.iterrows()]
    Repository(session).replace_scores(as_of, rows)
    session.flush()
    for (gt, _), row in zip(scored.iterrows(), rows):
        scored.loc[gt, "rank_change"] = row["breakdown"]["rank_change"]
        scored.loc[gt, "index_change"] = row["breakdown"]["index_change"]
    scored.attrs["breakdowns"] = {r["goods_type"]: r["breakdown"] for r in rows}
    scored.attrs["items"] = run_item_scoring(session, as_of, ref=signals)
    return scored


def run_item_scoring(session: Session, as_of: date, ref: pd.DataFrame) -> pd.DataFrame:
    """주목 아이템 점수: 신호 계산은 종류와 똑같이, 표준화 잣대는 '굿즈 종류들의 분포'(ref).
    → 아이템 90점과 종류 90점이 같은 뜻이 된다."""
    signals = compute_type_signals(session, as_of, key="item")
    if signals.empty:
        Repository(session).replace_item_scores(as_of, [])
        return signals
    scored = score_frame(signals, ref=ref)
    prev = previous_scores(session, as_of, model=ItemScore)
    rows = [{"item": it, "score": round(float(r.score), 4), "rank": int(r["rank"]),
             "breakdown": _breakdown(r, prev.get(it))} for it, r in scored.iterrows()]
    Repository(session).replace_item_scores(as_of, rows)
    session.flush()
    scored.attrs["breakdowns"] = {r["item"]: r["breakdown"] for r in rows}
    return scored
