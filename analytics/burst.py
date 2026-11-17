"""급상승 탐지 & 신규 굿즈 종류 발견.

- detect_mention_bursts    : 종류별 언급량이 평소보다 통계적으로 크게 늘었는지
- discover_new_goods_types : 종류를 판별 못 한 상품명·글에서 갑자기 많이 나오는 단어
                             → 사전에 없는 새 굿즈 종류 후보 (예: '말랑이')
                             사람이 확인 후 processing/dictionaries.py 에 추가한다.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

import numpy as np
from sqlalchemy.orm import Session

from analytics.signals import load_mentions, load_snapshots
from processing.dictionaries import GOODS_TYPE_ALIASES, IGNORE_WORDS, STOPWORDS
from processing.nlp import nouns

KNOWN_WORDS = {a.lower() for al in GOODS_TYPE_ALIASES.values() for a in al} | STOPWORDS | IGNORE_WORDS


def detect_mention_bursts(session: Session, as_of: date, z_threshold: float = 3.0,
                          min_daily: float = 3.0, recent_days: int = 3, gap_days: int = 7) -> list[dict]:
    """최근 recent_days 일 평균 언급량을 gap_days 이전의 기준기간과 비교한다.

    하루치만 보면 며칠에 걸친 상승을 놓치고(기준선이 같이 올라감),
    기준기간을 최근과 붙여 두면 상승 초반이 기준선에 섞인다 → 사이에 간격을 둔다.
    """
    m = load_mentions(session, as_of)
    if m.empty:
        return []
    out = []
    for gt, g in m.groupby("goods_type"):
        daily = g.groupby("age").size().reindex(range(0, 35), fill_value=0)
        recent = daily.loc[: recent_days - 1].mean()
        hist = daily.loc[gap_days:]
        mean = hist.mean()
        std = max(hist.std(ddof=0), np.sqrt(mean), 1.0) / np.sqrt(recent_days)  # 포아송 하한
        z = (recent - mean) / std
        if recent >= min_daily and z >= z_threshold:
            out.append({"goods_type": gt, "recent_daily": round(float(recent), 2),
                        "baseline_daily": round(float(mean), 2), "z": round(float(z), 2)})
    return sorted(out, key=lambda r: -r["z"])


def discover_new_goods_types(session: Session, as_of: date, recent_days: int = 7,
                             min_count: int = 5, min_ratio: float = 4.0) -> list[dict]:
    texts: list[tuple[str, int]] = []
    snap = load_snapshots(session, as_of, include_unclassified=True)
    if not snap.empty:
        u = snap[snap.goods_type.isna()].groupby("listing_id").agg(title=("title_raw", "first"), age=("age", "max"))
        texts += list(zip(u.title, u.age))          # 상품은 처음 보인 날 기준 1회만
    m = load_mentions(session, as_of, include_unclassified=True)
    if not m.empty:
        u = m[m.goods_type.isna()]
        texts += list(zip(u.text, u.age))
    if not texts:
        return []

    recent, base = Counter(), Counter()
    for text, age in texts:
        (recent if age < recent_days else base).update(set(nouns(text)))
    base_days = 35 - recent_days
    out = []
    for word, c in recent.items():
        if word in KNOWN_WORDS or c < min_count:
            continue
        ratio = (c / recent_days + 0.1) / (base.get(word, 0) / base_days + 0.1)
        if ratio >= min_ratio:
            out.append({"keyword": word, "recent_count": c, "ratio": round(ratio, 1)})
    return sorted(out, key=lambda r: (-r["recent_count"], -r["ratio"]))
