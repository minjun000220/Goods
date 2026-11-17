"""정규화: 사이트마다 제각각인 표기를 하나로 맞춘다."""
from __future__ import annotations

import html
import re

TAG_RE = re.compile(r"<[^>]+>")
# [무료배송], (정품), 【당일발송】 처럼 괄호 안에 판매 문구가 든 부분
BRACKET_NOISE_RE = re.compile(
    r"[\[\(【](?:[^\]\)】]*?(?:무료배송|당일발송|당일출고|특가|할인|이벤트|공식|정품|국내배송|빠른배송|단독|한정)"
    r"[^\]\)】]*?)[\]\)】]"
)
STAR_NOISE_RE = re.compile(r"[★☆][^★☆]{0,20}[★☆]")       # ★당일발송★
SYMBOL_RE = re.compile(r"[★☆♥♡◆◇■□▶►✔✨※#|/~!?,·•]+")
SIZE_RE = re.compile(r"\b([smlx]{1,3})\s*사이즈")             # M사이즈 → m
SPACE_RE = re.compile(r"\s+")


def strip_html(text: str) -> str:
    """API 가 주는 <b>강조</b> 태그와 &amp; 같은 엔티티 제거."""
    return html.unescape(TAG_RE.sub("", text or "")).strip()


def clean_title(title: str) -> str:
    """매칭용 정규화 제목: 소문자, 판매 문구 제거, 공백 정리."""
    t = strip_html(title).lower()
    t = BRACKET_NOISE_RE.sub(" ", t)
    t = STAR_NOISE_RE.sub(" ", t)
    t = SIZE_RE.sub(r"\1", t)
    t = SYMBOL_RE.sub(" ", t)
    t = t.replace("[", " ").replace("]", " ").replace("(", " ").replace(")", " ")
    return SPACE_RE.sub(" ", t).strip()


def parse_price(value) -> int | None:
    """'12,000원', '₩12000', 12000, '' → 정수 원화 또는 None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    digits = re.sub(r"[^\d]", "", str(value).split("~")[0])
    return int(digits) if digits and int(digits) > 0 else None


def normalize_stock(text: str | None) -> str:
    if not text:
        return "unknown"
    t = text.lower()
    if any(k in t for k in ("품절", "sold out", "soldout", "일시품절", "재고없음")):
        return "sold_out"
    if any(k in t for k in ("예약", "preorder", "pre-order")):
        return "preorder"
    return "in_stock"
