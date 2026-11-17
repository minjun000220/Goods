"""Hot Score: 여러 신호를 굿즈 종류별 '핫함' 점수 하나로 합친다.

  HotScore = Σ wᵢ · z(signalᵢ) / Σ wᵢ

- z(): robust z-score (중앙값·MAD 기준). 이상치 하나에 전체 스케일이 흔들리지 않는다.
- 값이 없는 신호는 0(중립)으로 취급하되, coverage 로 '근거가 몇 개인지'를 같이 남긴다.
- 가중치는 처음엔 직접 정하고, 나중엔 '실제로 유행한 종류' 라벨로 학습해 교체한다.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from analytics.signals import SIGNALS, compute_type_signals
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


def robust_z(s: pd.Series) -> pd.Series:
    valid = s.dropna()
    if len(valid) < 2:
        return pd.Series(0.0, index=s.index).where(s.notna())
    med = valid.median()
    scale = 1.4826 * (valid - med).abs().median()
    if not scale or np.isnan(scale):
        scale = valid.std(ddof=0)
    if not scale or np.isnan(scale):
        return pd.Series(0.0, index=s.index).where(s.notna())
    return ((s - med) / scale).clip(-Z_CLIP, Z_CLIP)


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for sig in SIGNALS:
        if sig not in df:
            df[sig] = np.nan
        df[f"z_{sig}"] = robust_z(df[sig].astype(float))
    df["score"] = sum(WEIGHTS[s] * df[f"z_{s}"].fillna(0) for s in SIGNALS) / sum(WEIGHTS.values())
    df["coverage"] = df[SIGNALS].notna().sum(axis=1)
    df = df.sort_values("score", ascending=False)
    df["rank"] = np.arange(1, len(df) + 1)
    return df


def _breakdown(row: pd.Series) -> dict:
    sig = {s: {"value": round(float(row[s]), 4), "z": round(float(row[f"z_{s}"]), 2)}
           for s in SIGNALS if pd.notna(row[s])}
    return {"coverage": int(row["coverage"]), "signals": sig,
            "examples": row.get("examples") or [], "mentions_7d": int(row.get("mentions_7d", 0))}


def run_scoring(session: Session, as_of: date) -> pd.DataFrame:
    """굿즈 종류별 점수를 계산해 저장하고, 점수 표를 돌려준다."""
    signals = compute_type_signals(session, as_of)
    if signals.empty:
        return signals
    scored = score_frame(signals)
    Repository(session).replace_scores(as_of, [
        {"goods_type": gt, "score": round(float(r.score), 4), "rank": int(r["rank"]), "breakdown": _breakdown(r)}
        for gt, r in scored.iterrows()
    ])
    session.flush()
    return scored
