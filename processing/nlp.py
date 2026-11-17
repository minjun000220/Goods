"""상품 제목·글에서 굿즈 종류를 판별하고, 신규 키워드 발견용 명사를 뽑는다.

- 사전 매칭은 '긴 별칭 우선' (봉제인형 > 인형, 캔뱃지 > 뱃지)
- 영문 별칭은 단어 경계를 지킨다 (album 이 'albumin' 안에서 잡히지 않게)
- 형태소 분석기 Kiwi 가 설치돼 있으면 명사 추출에 사용, 없으면 정규식 토큰화
"""
from __future__ import annotations

import re
from functools import lru_cache

from processing.dictionaries import GOODS_TYPE_ALIASES
from processing.normalize import clean_title

TOKEN_RE = re.compile(r"[가-힣]+|[a-z0-9]+")


def _index(d: dict[str, list[str]]) -> list[tuple[re.Pattern, str, str]]:
    rows = []
    for canonical, aliases in d.items():
        for a in aliases:
            a = a.lower()
            pat = re.escape(a)
            if a.isascii():
                pat = rf"(?<![a-z0-9]){pat}(?![a-z0-9])"
            rows.append((re.compile(pat), canonical, a))
    return sorted(rows, key=lambda r: -len(r[2]))


TYPE_INDEX = _index(GOODS_TYPE_ALIASES)

# 띄어쓰기를 무시한 비교용: 한글 별칭(3글자 이상)을 공백 없이 저장
_COMPACT_ALIASES = sorted(
    {(a.replace(" ", "").lower(), canonical)
     for canonical, aliases in GOODS_TYPE_ALIASES.items() for a in aliases
     if not a.isascii() and len(a.replace(" ", "")) >= 3},
    key=lambda r: -len(r[0]),
)


def classify_goods_type(text: str) -> str | None:
    """'[공식] aespa 응원봉 ★당일발송★' → '응원봉'. 판별 불가면 None."""
    t = clean_title(text)
    for pat, canonical, _ in TYPE_INDEX:
        if pat.search(t):
            return canonical
    compact = t.replace(" ", "")              # "시즌 그리팅", "포토 카드", "봉제 인형" 처럼 띄어 쓴 표기
    for alias, canonical in _COMPACT_ALIASES:
        if alias in compact:
            return canonical
    return None


@lru_cache(maxsize=1)
def _kiwi():
    try:
        from kiwipiepy import Kiwi
    except ImportError:
        return None
    return Kiwi()


def nouns(text: str) -> list[str]:
    """신규 키워드 발견용 명사 추출. Kiwi 가 없으면 정규식 토큰으로 대체."""
    text = clean_title(text)
    kiwi = _kiwi()
    if kiwi is None:
        return [t for t in TOKEN_RE.findall(text) if len(t) >= 2]
    return [tok.form.lower() for tok in kiwi.tokenize(text)
            if tok.tag in ("NNG", "NNP", "SL") and len(tok.form) >= 2]
