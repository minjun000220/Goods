"""굿즈 종류별 신호(Signal) 계산.

원칙: 절대량이 아니라 '변화율'을 본다. 그래야 늘 많이 팔리는 응원봉이 항상 1등 하지 않고,
      지금 '뜨고 있는' 종류가 위로 올라온다.
윈도우: 최근(recent) 7일 vs 기준(baseline) 그 이전 28일
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from storage.models import Listing, ListingSnapshot, Mention, TypeMetric

RECENT_DAYS = 7
BASELINE_DAYS = 28
TOP_K = 20   # 베스트 랭킹 상위 몇 위까지를 '점유율' 계산에 쓸지

SIGNALS = ["best_share_momentum", "listing_growth", "review_velocity", "sold_out_ratio",
           "resale_momentum", "resale_trade_velocity", "buzz_momentum"]


def _bounds(as_of: date) -> tuple[datetime, datetime]:
    end = datetime.combine(as_of + timedelta(days=1), time.min)
    return end - timedelta(days=RECENT_DAYS + BASELINE_DAYS), end


def _age(series: pd.Series, as_of: date) -> pd.Series:
    """as_of 기준 며칠 전인지 (0 = 당일)."""
    return (pd.Timestamp(as_of) - pd.to_datetime(series).dt.normalize()).dt.days


def _log_ratio(recent: pd.Series, base: pd.Series, eps: float = 1.0) -> pd.Series:
    idx = recent.index.union(base.index)
    r, b = recent.reindex(idx, fill_value=0), base.reindex(idx, fill_value=0)
    return np.log((r + eps) / (b + eps))


def _recent_vs_base_daily(daily: pd.DataFrame, value: str, eps: float = 1.0) -> pd.Series:
    """daily: [goods_type, age, value] → log(최근 일평균 / 기준기간 일평균)."""
    full = (daily.set_index(["goods_type", "age"])[value]
            .unstack(fill_value=0).reindex(columns=range(RECENT_DAYS + BASELINE_DAYS), fill_value=0))
    recent = full.loc[:, : RECENT_DAYS - 1].mean(axis=1)
    base = full.loc[:, RECENT_DAYS:].mean(axis=1)
    return _log_ratio(recent, base, eps)


# ---------------------------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------------------------
def load_snapshots(session: Session, as_of: date, include_unclassified: bool = False) -> pd.DataFrame:
    start, end = _bounds(as_of)
    q = (select(ListingSnapshot.observed_at, ListingSnapshot.price, ListingSnapshot.rank,
                ListingSnapshot.rank_list, ListingSnapshot.stock_status, ListingSnapshot.review_count, ListingSnapshot.sales_count,
                Listing.id.label("listing_id"), Listing.goods_type, Listing.item, Listing.seller_type,
                Listing.title_raw)
         .join(Listing, Listing.id == ListingSnapshot.listing_id)
         .where(ListingSnapshot.observed_at >= start, ListingSnapshot.observed_at < end))
    if not include_unclassified:
        q = q.where(Listing.goods_type.is_not(None))
    df = pd.DataFrame(session.execute(q).all())
    if not df.empty:
        df["age"] = _age(df["observed_at"], as_of)
    return df


def load_mentions(session: Session, as_of: date, include_unclassified: bool = False) -> pd.DataFrame:
    start, end = _bounds(as_of)
    q = select(Mention.observed_at, Mention.goods_type, Mention.item, Mention.engagement, Mention.text) \
        .where(Mention.observed_at >= start, Mention.observed_at < end)
    if not include_unclassified:
        q = q.where(Mention.goods_type.is_not(None))
    df = pd.DataFrame(session.execute(q).all())
    if not df.empty:
        df["age"] = _age(df["observed_at"], as_of)
    return df


def load_metrics(session: Session, as_of: date) -> pd.DataFrame:
    start, end = _bounds(as_of)
    q = select(TypeMetric.goods_type, TypeMetric.metric, TypeMetric.date, TypeMetric.value) \
        .where(TypeMetric.date >= start.date(), TypeMetric.date < end.date(), TypeMetric.goods_type.is_not(None))
    df = pd.DataFrame(session.execute(q).all())
    if not df.empty:
        df["age"] = _age(df["date"], as_of)
    return df


# ---------------------------------------------------------------------------
# 개별 신호
# ---------------------------------------------------------------------------
def best_share(snap: pd.DataFrame) -> pd.DataFrame:
    """일자별·종류별 '베스트 랭킹 상위 TOP_K 중 차지한 비율'."""
    best = snap[snap.rank_list.fillna("").str.startswith("best:") & (snap["rank"] <= TOP_K)]
    if best.empty:
        return pd.DataFrame(columns=["goods_type", "age", "share"])
    # 분모: TOP_K 칸 × (그날 수집된 '랭킹 목록 × 수집 회차' 수). 미분류 상품도 칸을 차지한다.
    # 하루에 여러 번 수집해도 점유율이 부풀지 않게 회차별 평균이 되도록 회차 수로 나눈다.
    # 회차 = 같은 목록을 15분 안에 가져온 묶음 (여러 페이지를 연달아 가져와도 한 회차)
    best = best.assign(run=pd.to_datetime(best["observed_at"]).dt.floor("15min"))
    runs_per_day = best.groupby("age").apply(lambda g: g[["rank_list", "run"]].drop_duplicates().shape[0])
    counts = best.groupby(["goods_type", "age"]).size().reset_index(name="n")
    counts["share"] = counts.n / (TOP_K * counts.age.map(runs_per_day))
    return counts[["goods_type", "age", "share"]]


def best_share_momentum(snap: pd.DataFrame) -> pd.Series:
    """베스트 순위 점유율이 늘었는가. 쇼핑몰 '베스트' 페이지 기반 → 검색어 없이도 잡힌다."""
    share = best_share(snap)
    return pd.Series(dtype=float) if share.empty else _recent_vs_base_daily(share, "share", eps=0.02)


def _counter_velocity(rows: pd.DataFrame, col: str) -> pd.Series:
    """누적 카운터(리뷰 수, 거래 수)의 일별 증가량 → 최근 vs 기준기간 증가 속도 비교."""
    rows = rows[rows[col].notna()]
    if rows.empty:
        return pd.Series(dtype=float)
    per = rows.groupby(["goods_type", "listing_id", "age"])[col].max().reset_index()
    per = per.sort_values(["listing_id", "age"], ascending=[True, False])     # 오래된 날 → 최근
    per["inc"] = per.groupby("listing_id")[col].diff().clip(lower=0)
    daily = per.dropna(subset=["inc"]).groupby(["goods_type", "age"])["inc"].sum().reset_index()
    return pd.Series(dtype=float) if daily.empty else _recent_vs_base_daily(daily, "inc")


def review_velocity(snap: pd.DataFrame) -> pd.Series:
    """리뷰가 쌓이는 속도의 변화 = 실제 구매가 늘었는가."""
    return _counter_velocity(snap[snap.seller_type == "retail"], "review_count")


def resale_trade_velocity(snap: pd.DataFrame) -> pd.Series:
    """리셀 마켓(KREAM 등) 누적 거래 수가 빨리 늘어나는가 = 웃돈 주고라도 사는 사람이 늘었다."""
    return _counter_velocity(snap[snap.seller_type == "resale"], "sales_count")


def sold_out_ratio(snap: pd.DataFrame) -> pd.Series:
    """최근 3일 정가 판매 상품 중 품절 비율 (재고 정보 없는 소스는 제외)."""
    r = snap[(snap.seller_type == "retail") & (snap.age <= 2) & (snap.stock_status != "unknown")]
    return (r.stock_status == "sold_out").groupby(r.goods_type).mean()


def resale_momentum(snap: pd.DataFrame) -> pd.Series:
    """새로 올라오는 중고·리셀 매물 수의 증가율. 되팔 만큼 수요가 있다는 신호."""
    rs = snap[snap.seller_type == "resale"]
    if rs.empty:
        return pd.Series(dtype=float)
    first_seen = rs.groupby(["goods_type", "listing_id"])["age"].max().reset_index()
    daily = first_seen.groupby(["goods_type", "age"]).size().reset_index(name="n")
    return _recent_vs_base_daily(daily, "n")


def buzz_momentum(mentions: pd.DataFrame) -> pd.Series:
    """커뮤니티·SNS 언급량 증가율. 참여도(좋아요·댓글)가 높은 글은 가중치를 더 준다."""
    if mentions.empty:
        return pd.Series(dtype=float)
    m = mentions.assign(w=1 + np.log1p(mentions.engagement) / 3)
    daily = m.groupby(["goods_type", "age"])["w"].sum().reset_index()
    return _recent_vs_base_daily(daily, "w")


def metric_momentum(metrics: pd.DataFrame, name: str) -> pd.Series:
    """키워드 지표(네이버 쇼핑 등록 상품 수 등)의 증가율. 0인 날은 '데이터 없음'으로 보고 평균에서 뺀다."""
    m = metrics[metrics.metric == name]
    if m.empty:
        return pd.Series(dtype=float)
    recent = m[m.age < RECENT_DAYS].groupby("goods_type")["value"].mean()
    base = m[m.age >= RECENT_DAYS].groupby("goods_type")["value"].mean()
    return np.log(recent / base).dropna()


def examples(snap: pd.DataFrame, n: int = 3) -> pd.Series:
    """종류별 대표 상품 예시: 최근 3일 베스트 랭킹에서 순위가 가장 높았던 상품명."""
    recent = snap[(snap.age <= 2) & snap["rank"].notna()]
    if recent.empty:
        return pd.Series(dtype=object)
    best = recent.groupby(["goods_type", "title_raw"])["rank"].min().reset_index().sort_values("rank")
    return best.groupby("goods_type")["title_raw"].apply(lambda s: list(s.head(n)))


# ---------------------------------------------------------------------------
# 합치기
# ---------------------------------------------------------------------------
def compute_type_signals(session: Session, as_of: date, key: str = "goods_type") -> pd.DataFrame:
    """행 = 굿즈 종류(key="goods_type") 또는 주목 아이템(key="item"), 열 = 신호 + 참고 정보.
    값이 없는 신호는 NaN (점수 계산 시 중립 처리)."""
    if key == "item":
        # 아이템 단위: 분류 여부와 상관없이 아이템이 붙은 상품·글만 모아, 같은 계산을 아이템 이름으로 묶어 한다
        snap = load_snapshots(session, as_of, include_unclassified=True)
        mentions = load_mentions(session, as_of, include_unclassified=True)
        snap = snap[snap["item"].notna()].assign(goods_type=lambda d: d["item"]) if not snap.empty else snap
        mentions = (mentions[mentions["item"].notna()].assign(goods_type=lambda d: d["item"])
                    if not mentions.empty else mentions)
        metrics = pd.DataFrame()               # 검색량·판매처 수 지표는 종류 키워드 단위라 아이템엔 없음
    else:
        snap = load_snapshots(session, as_of)
        mentions = load_mentions(session, as_of)
        metrics = load_metrics(session, as_of)
    types = set()
    for df in (snap, mentions, metrics):
        if not df.empty:
            types |= set(df.goods_type.dropna())
    if not types:
        return pd.DataFrame()

    out = pd.DataFrame(index=sorted(types))
    out.index.name = "goods_type"
    if not snap.empty:
        out["best_share_momentum"] = best_share_momentum(snap)
        out["review_velocity"] = review_velocity(snap)
        out["sold_out_ratio"] = sold_out_ratio(snap)
        out["resale_momentum"] = resale_momentum(snap)
        out["resale_trade_velocity"] = resale_trade_velocity(snap)
        share = best_share(snap)
        recent_share = share[share.age <= 2].groupby("goods_type")["share"].sum() / 3 if not share.empty else None
        out["best_share_now"] = recent_share if recent_share is not None else np.nan
        if recent_share is not None:
            out["best_share_now"] = out["best_share_now"].fillna(0.0)   # 상위권에 없음 = 점유율 0
        out["examples"] = examples(snap)
    out["buzz_momentum"] = buzz_momentum(mentions)
    if not metrics.empty:
        out["listing_growth"] = metric_momentum(metrics, "listing_total")
    out["mentions_7d"] = (mentions[mentions.age < RECENT_DAYS].groupby("goods_type").size()
                          if not mentions.empty else 0)
    out["mentions_7d"] = out["mentions_7d"].fillna(0).astype(int)
    for s in SIGNALS + ["best_share_now", "examples"]:
        if s not in out:
            out[s] = np.nan
    out["examples"] = out["examples"].apply(lambda v: v if isinstance(v, list) else [])
    return out
