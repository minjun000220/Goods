"""수집 소스 등록부. 어떤 사이트에서 무엇을 가져오는지 이 파일 한 곳에서 관리한다.

사이트별 상태 (robots.txt·접근 확인: 2026-11)
┌──────────────┬──────────┬─────────────────────────────────────────────────────────────┐
│ 사이트        │ 상태      │ 방식 / 사유                                                  │
├──────────────┼──────────┼─────────────────────────────────────────────────────────────┤
│ 네이버 쇼핑    │ ✅ 키 필요 │ 공식 검색 API                                               │
│ 네이버 데이터랩 │ ✅ 키 필요 │ 공식 검색어트렌드 API                                         │
│ 쿠팡          │ ✅ 키 필요 │ 웹은 봇 차단(403) → 쿠팡 파트너스 공식 API (베스트 카테고리)       │
│ 애니메이트     │ ✅ 바로 됨 │ HTML. robots.txt 가 /goods/ 허용. 판매인기순 목록              │
│ KREAM        │ ✅ 바로 됨 │ HTML 검색 결과. robots.txt 가 /search 허용. 거래 수·시세        │
│ 디시인사이드    │ ✅ 바로 됨 │ HTML 갤러리 목록. robots.txt 의 차단 갤러리는 fetcher 가 자동 회피 │
│ 유튜브        │ ✅ 키 필요 │ YouTube Data API v3                                          │
│ X(트위터)     │ ✅ 유료 키 │ X API v2 counts (게시물 수만)                                  │
│ 중고나라       │ ❌ 제외   │ 봇 요청을 방화벽이 차단(403) — 우회하지 않음                      │
│ 더쿠          │ ❌ 제외   │ 보안 검사(CAPTCHA) 페이지 반환 — 우회하지 않음                    │
│ 구글 트렌드    │ ❌ 제외   │ robots.txt 가 /explore 금지, 공식 API 는 신청제(알파)            │
│ 번개장터       │ ⏸ 보류   │ 웹이 JS 앱이라 HTML 에 데이터 없음. 내부 API 는 공개 API 가 아님   │
└──────────────┴──────────┴─────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging

from collectors.base import SourceAdapter
from collectors.sources.best_ranking import BestRankingAdapter, RankingConfig
from collectors.sources.community_board import BoardConfig, CommunityBoardAdapter
from collectors.sources.coupang_partners import CoupangPartnersAdapter
from collectors.sources.kream import KreamAdapter
from collectors.sources.naver_datalab import NaverDataLabAdapter
from collectors.sources.naver_shopping import NaverShoppingAdapter
from collectors.sources.x_api import XCountsAdapter
from collectors.sources.youtube import YouTubeAdapter
from config import settings

log = logging.getLogger(__name__)

ANIMATE_LIST = ("https://www.animate-onlineshop.co.kr/goods/goods_list.php"
                "?cateCd={cate}&sort=orderCnt%20desc%2Cg.regDt%20desc&page={{page}}")

# 쇼핑몰 '판매인기순/베스트' 목록 — 검색어 없이 지금 잘 팔리는 것을 통째로 수집
RANKINGS: list[RankingConfig] = [
    RankingConfig(
        source_id="animate_new_best",                 # 애니메이트 신상품 판매인기순
        url=ANIMATE_LIST.format(cate="008"),
        item_selector=".goods_list_cont .item_cont",
        title_selector=".item_tit_box a",
        price_selector=".item_price",
        pages=2,
        rate_limit=0.1,                               # 10초에 1회 (robots.txt 의 Crawl-delay 10 존중)
    ),
    RankingConfig(
        source_id="animate_preorder_best",            # 애니메이트 예약상품 판매인기순 (출시 전 수요)
        url=ANIMATE_LIST.format(cate="010"),
        item_selector=".goods_list_cont .item_cont",
        title_selector=".item_tit_box a",
        price_selector=".item_price",
        pages=1,
        rate_limit=0.1,
    ),
]

DC_ROW = 'tr.ub-content.us-post:not([data-type="icon_notice"])'


def dc_gallery(gallery_id: str, minor: bool = True, pages: int = 2) -> BoardConfig:
    """디시인사이드 갤러리 목록. minor=True 면 마이너 갤러리 주소를 쓴다."""
    prefix = "/mgallery" if minor else ""
    return BoardConfig(
        source_id=f"dc_{gallery_id}",
        list_url=f"https://gall.dcinside.com{prefix}/board/lists/?id={gallery_id}&page={{page}}",
        row_selector=DC_ROW,
        title_selector="td.gall_tit a:not(.reply_numbox)",
        engagement_selectors=("td.gall_recommend", "span.reply_num"),
        date_selector="td.gall_date", date_attr="title",
        pages=pages,
        rate_limit=0.3,
    )


# 커뮤니티 게시판 — 굿즈 이야기가 많은 갤러리를 추가한다 (예: 팬덤·캐릭터 갤러리)
BOARDS: list[BoardConfig] = [
    dc_gallery("goods"),                              # 굿즈 마이너 갤러리
]


def build_adapters(fetcher) -> list[SourceAdapter]:
    s = settings
    adapters: list[SourceAdapter] = []

    if s.naver_client_id and s.naver_client_secret:
        adapters.append(NaverShoppingAdapter(fetcher, s.naver_client_id, s.naver_client_secret))
        adapters.append(NaverDataLabAdapter(fetcher, s.naver_client_id, s.naver_client_secret))
    else:
        log.warning("NAVER_CLIENT_ID/SECRET 없음 → 네이버 쇼핑·데이터랩 건너뜀")

    if s.coupang_access_key and s.coupang_secret_key:
        adapters.append(CoupangPartnersAdapter(fetcher, s.coupang_access_key, s.coupang_secret_key))
    else:
        log.warning("COUPANG_ACCESS_KEY/SECRET_KEY 없음 → 쿠팡 건너뜀")

    if s.youtube_api_key:
        adapters.append(YouTubeAdapter(fetcher, s.youtube_api_key))
    else:
        log.warning("YOUTUBE_API_KEY 없음 → 유튜브 건너뜀")

    if s.x_bearer_token:
        adapters.append(XCountsAdapter(fetcher, s.x_bearer_token))
    else:
        log.warning("X_BEARER_TOKEN 없음 → X 건너뜀")

    # 키 없이 바로 되는 소스
    adapters.append(KreamAdapter(fetcher))
    adapters += [BestRankingAdapter(fetcher, cfg) for cfg in RANKINGS]
    adapters += [CommunityBoardAdapter(fetcher, cfg) for cfg in BOARDS]
    return adapters
