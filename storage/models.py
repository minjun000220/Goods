"""DB 스키마 (SQLAlchemy 2.0). 분석 단위 = 굿즈 종류 (goods_type 문자열: "응원봉", "인형" …)

수집 데이터  : Listing(+ListingSnapshot), Mention, TypeMetric   (운영에서는 TimescaleDB 권장)
분석 결과    : HotScore
운영 데이터  : CrawlRun (수집 실행 기록 → 파서 깨짐 감지)

종류를 판별하지 못한 상품·글도 goods_type=NULL 로 저장한다.
→ 이 안에서 자주 나오는 단어가 '사전에 없는 새 굿즈 종류' 후보가 된다.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Listing(Base):
    """특정 사이트에 올라온 상품 페이지 1개."""
    __tablename__ = "listing"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(200))
    goods_type: Mapped[str | None] = mapped_column(String(50), index=True)
    item: Mapped[str | None] = mapped_column(String(50), index=True)      # 주목 아이템 (훈바루즈 등)
    title_raw: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    seller_type: Mapped[str] = mapped_column(String(20), default="retail")


class ListingSnapshot(Base):
    """Listing 의 시점별 상태 (가격, 순위, 재고, 리뷰 수)."""
    __tablename__ = "listing_snapshot"
    __table_args__ = (UniqueConstraint("listing_id", "observed_at"),
                      Index("ix_snapshot_time", "observed_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listing.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    price: Mapped[int | None] = mapped_column(Integer)
    rank: Mapped[int | None] = mapped_column(Integer)
    rank_list: Mapped[str | None] = mapped_column(String(100))
    stock_status: Mapped[str] = mapped_column(String(20), default="unknown")
    review_count: Mapped[int | None] = mapped_column(Integer)
    sales_count: Mapped[int | None] = mapped_column(Integer)


class Mention(Base):
    """SNS/커뮤니티 언급. 작성자 정보는 저장하지 않는다."""
    __tablename__ = "mention"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),
                      Index("ix_mention_time", "observed_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(200))
    goods_type: Mapped[str | None] = mapped_column(String(50), index=True)
    item: Mapped[str | None] = mapped_column(String(50), index=True)
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000))
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    engagement: Mapped[int] = mapped_column(Integer, default=0)


class TypeMetric(Base):
    """굿즈 종류 키워드 단위 일별 지표 (검색량, 검색 결과 상품 수 등)."""
    __tablename__ = "type_metric"
    __table_args__ = (UniqueConstraint("source_id", "keyword", "metric", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(50))
    keyword: Mapped[str] = mapped_column(String(100))
    goods_type: Mapped[str | None] = mapped_column(String(50), index=True)
    metric: Mapped[str] = mapped_column(String(50))
    date: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)


class HotScore(Base):
    """분석 결과. breakdown 에 '왜 핫한가'(신호별 값과 z-score)와 대표 상품 예시를 저장한다."""
    __tablename__ = "hot_score"
    __table_args__ = (UniqueConstraint("goods_type", "as_of"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    goods_type: Mapped[str] = mapped_column(String(50))
    as_of: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    breakdown: Mapped[dict] = mapped_column(JSON)


class ItemScore(Base):
    """주목 아이템 점수. 굿즈 종류와 같은 잣대(종류들의 분포 기준)로 계산한다."""
    __tablename__ = "item_score"
    __table_args__ = (UniqueConstraint("item", "as_of"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    item: Mapped[str] = mapped_column(String(50))
    as_of: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    breakdown: Mapped[dict] = mapped_column(JSON)


class DailyInsight(Base):
    """그날의 부가 분석 결과 (언급량 급상승, 사전에 없는 새 굿즈 후보) — 웹 화면이 읽는다."""
    __tablename__ = "daily_insight"
    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, unique=True)
    bursts: Mapped[list] = mapped_column(JSON, default=list)
    new_types: Mapped[list] = mapped_column(JSON, default=list)


class CrawlRun(Base):
    __tablename__ = "crawl_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(50), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    tasks: Mapped[int] = mapped_column(Integer)
    failures: Mapped[int] = mapped_column(Integer)
    items: Mapped[int] = mapped_column(Integer)
    errors: Mapped[list] = mapped_column(JSON, default=list)
