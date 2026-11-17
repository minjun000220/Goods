"""자동 패턴 찾기: 사이트마다 셀렉터를 직접 정하지 않고 상품 목록을 뽑아낸다.

원리
 1) 페이지에서 가격처럼 생긴 글자("12,000원", "₩12,000")를 모두 찾는다.
 2) 각 가격의 조상 요소들을 (태그, 클래스) 모양으로 묶는다. 상품 목록이라면
    '같은 모양의 칸'이 여러 번 반복되고, 칸마다 가격이 하나씩 들어 있다.
 3) 상품명(긴 글자)과 링크가 들어 있는 칸 중 가장 많이 반복되는 모양 = 상품 칸.
 4) 칸마다 상품명·가격·링크를 뽑고, 같은 링크는 한 번만 센다 (순서 = 순위).

한계: 가격이 화면에 없는 페이지(커뮤니티 글 목록 등), JS 로만 그려지는 페이지,
      한 페이지에 상품 목록이 여러 개(추천 상품 등) 섞인 경우 가장 큰 목록만 잡힌다.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

PRICE_RE = re.compile(r"(?<![\d,.])(\d{1,3}(?:,\d{3})+|\d{4,8})\s*원|₩\s*(\d{1,3}(?:,\d{3})+|\d{4,8})")
SKIP_TAGS = {"script", "style", "noscript", "option", "select", "template", "head"}
# 상품명이 아닌 문구 (배송·후기·버튼 등)
NOISE_RE = re.compile(r"배송|도착|리뷰|후기|관심|장바구니|찜|구매하기|쿠폰|적립|평점|별점|품절|판매중|할인|무료|"
                      r"바로가기|더보기|옵션|원산지|^\W+$")
NUMERIC_RE = re.compile(r"^[\d,.%·()\s\-+/x]+$")
MAX_DEPTH = 12


@dataclass
class AutoItem:
    title: str
    price: int | None
    url: str
    rank: int


def _sig(el: Tag | None):
    if el is None:
        return None
    return el.name, tuple(sorted(el.get("class") or []))


def _prices(text: str) -> list[int]:
    out = []
    for m in PRICE_RE.finditer(text):
        v = int((m.group(1) or m.group(2)).replace(",", ""))
        if 100 <= v <= 50_000_000:
            out.append(v)
    return out


def best_title(el: Tag) -> str | None:
    """칸 안에서 상품명으로 보이는 글자: 가격·숫자·안내 문구를 뺀 것 중 가장 긴 것."""
    cands = []
    for s in el.stripped_strings:
        s = re.sub(r"\s+", " ", s)
        if len(s) < 4 or NUMERIC_RE.match(s) or _prices(s) or NOISE_RE.search(s):
            continue
        cands.append(s)
    if cands:
        return max(cands, key=len)
    img = el.find("img", alt=True)
    alt = (img.get("alt") or "").strip() if img else ""
    return alt if len(alt) >= 4 else None


def _link(el: Tag, title: str) -> str | None:
    if el.name == "a" and el.get("href"):
        return el["href"]
    anchors = [a for a in el.find_all("a", href=True) if not a["href"].startswith(("javascript", "#"))]
    for a in anchors:
        if title in a.get_text(" ", strip=True) or (a.find("img", alt=title)):
            return a["href"]
    if anchors:
        return anchors[0]["href"]
    parent = el.find_parent("a", href=True)
    return parent["href"] if parent else None


def extract_products(html: str, base_url: str, min_items: int = 3) -> list[AutoItem]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all(SKIP_TAGS):
        t.decompose()

    price_nodes = [s for s in soup.find_all(string=PRICE_RE) if isinstance(s, NavigableString) and _prices(s)]
    if len(price_nodes) < min_items:
        return []

    # 가격의 조상들을 (자기 모양, 부모 모양) 으로 묶는다
    groups: dict[tuple, dict[int, Tag]] = defaultdict(dict)
    for p in price_nodes:
        el, depth = p.parent, 0
        while isinstance(el, Tag) and el.name not in ("body", "html", "[document]") and depth < MAX_DEPTH:
            groups[(_sig(el), _sig(el.parent))][id(el)] = el
            el, depth = el.parent, depth + 1

    best_key, best_els, best_score = None, [], (0, 0)
    for key, members in groups.items():
        els = list(members.values())
        if len(els) < min_items:
            continue
        titled = [e for e in els if best_title(e) and _link(e, best_title(e))]
        if len(titled) < max(min_items, 0.8 * len(els)):
            continue
        # 반복 횟수가 많을수록, 같으면 더 큰 칸(정보가 더 많이 들어 있는 칸)일수록 좋다
        score = (len(titled), sum(len(e.get_text()) for e in titled) / len(titled))
        if score > best_score:
            best_key, best_els, best_score = key, titled, score
    if best_key is None:
        return []

    out, seen = [], set()
    for el in best_els:                       # 문서 순서 유지 (dict 삽입 순서 = 발견 순서)
        title = best_title(el)
        href = _link(el, title)
        url = urljoin(base_url, href) if href else base_url
        key = url if href else title
        if key in seen:
            continue
        seen.add(key)
        prices = _prices(el.get_text(" "))
        out.append(AutoItem(title=title, price=min(prices) if prices else None, url=url, rank=len(out) + 1))
    return out
