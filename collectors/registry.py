"""수집 소스 등록부. 어떤 사이트에서 무엇을 가져오는지 이 파일 한 곳에서 관리한다.

사용하는 소스 (robots.txt·접근 확인: 2026-11)
┌──────────────┬──────────┬─────────────────────────────────────────────────────────────┐
│ 사이트        │ 상태      │ 방식                                                         │
├──────────────┼──────────┼─────────────────────────────────────────────────────────────┤
│ 애니메이트     │ ✅ 바로 됨 │ HTML. robots.txt 가 /goods/ 허용. 신상품·예약상품 판매인기순      │
│ KREAM        │ ✅ 바로 됨 │ HTML 검색 결과. robots.txt 가 /search 허용. 거래 수·시세        │
│ 디시인사이드    │ ✅ 바로 됨 │ 굿즈 갤러리 + 아이돌 갤러리 17곳 최신 글 중 굿즈 언급 글만 (HTML)   │
│ 쿠팡          │ ⏸ 꺼둠   │ 웹은 봇 차단(403) → 쿠팡 파트너스 공식 API (베스트 카테고리)       │
│ 유튜브        │ ⏸ 꺼둠   │ YouTube Data API v3                                          │
│ 네이버 쇼핑    │ 🔑 키 필요 │ 공식 검색 API. ⚠️ 2026-07-31 개발자센터 신규 등록 중단,            │
│              │          │ 쇼핑 검색 종료 보도 있음 → 키를 못 받으면 자동으로 건너뜀           │
└──────────────┴──────────┴─────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging

from collectors.base import SourceAdapter
from collectors.sources.auto_site import AutoSiteAdapter, AutoSiteConfig
from collectors.sources.best_ranking import BestRankingAdapter, RankingConfig
from collectors.sources.community_board import BoardConfig, CommunityBoardAdapter
from collectors.sources.coupang_partners import CoupangPartnersAdapter
from collectors.sources.kream import KreamAdapter
from collectors.sources.naver_shopping import NaverShoppingAdapter
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


def dc_gallery(gallery_id: str, minor: bool = True, pages: int = 2, only_goods: bool = False) -> BoardConfig:
    """디시인사이드 갤러리 최신 글 목록. minor=True 면 마이너 갤러리 주소를 쓴다.
    (갤러리 내 검색은 오래된 글 위주로 나와서 '요즘' 수요 파악에 맞지 않음 → 최신 글 목록을 훑는다)"""
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
        only_goods=only_goods,
    )


# 아이돌 갤러리 (2026-11 존재 확인). 잡담이 대부분이라 굿즈 종류가 언급된 글만 남긴다.
# 갤러리를 추가하려면 주소의 id= 값을 넣는다. (twice 는 2019년까지의 보관 갤러리라 제외)
IDOL_GALLERIES = [
    "bts", "seventeen", "straykids", "nct", "blackpink",                    # 정식 갤러리
    "aespa", "newjeans", "lesserafim", "riize", "plave", "babymonster",     # 마이너 갤러리
    "illit", "txt", "boynextdoor", "tws", "kissoflife",
]

# 커뮤니티 게시판
BOARDS: list[BoardConfig] = [
    dc_gallery("goods"),                              # 굿즈 마이너 갤러리 (전체 글)
    *[dc_gallery(g, minor=False, pages=3, only_goods=True) for g in IDOL_GALLERIES],
]

# 자동 패턴 찾기로 수집하는 사이트: 주소만 넣으면 된다 (셀렉터 불필요)
# 넣기 전에 확인: python -m tools.try_auto "<주소>"   ({page}, {kw} 자리표시자 사용 가능)
AUTO_SITES: list[AutoSiteConfig] = [
    # AutoSiteConfig(source_id="some_mall_best", url="https://mall.example/best?page={page}", pages=2),
    # AutoSiteConfig(source_id="some_mall_search", url="https://mall.example/search?q={kw}"),
]

# 지금은 꺼둔 소스 (키를 발급받은 뒤 True 로 바꾼다)
ENABLE_COUPANG = False
ENABLE_YOUTUBE = False


def build_adapters(fetcher) -> list[SourceAdapter]:
    s = settings
    adapters: list[SourceAdapter] = []

    if s.naver_client_id and s.naver_client_secret:
        adapters.append(NaverShoppingAdapter(fetcher, s.naver_client_id, s.naver_client_secret))
    else:
        log.warning("NAVER_CLIENT_ID/SECRET 없음 → 네이버 쇼핑 건너뜀")

    if not ENABLE_COUPANG:
        pass
    elif s.coupang_access_key and s.coupang_secret_key:
        adapters.append(CoupangPartnersAdapter(fetcher, s.coupang_access_key, s.coupang_secret_key))
    else:
        log.warning("COUPANG_ACCESS_KEY/SECRET_KEY 없음 → 쿠팡 건너뜀")

    if not ENABLE_YOUTUBE:
        pass
    elif s.youtube_api_key:
        adapters.append(YouTubeAdapter(fetcher, s.youtube_api_key))
    else:
        log.warning("YOUTUBE_API_KEY 없음 → 유튜브 건너뜀")

    # 키 없이 바로 되는 소스
    adapters.append(KreamAdapter(fetcher))
    adapters += [BestRankingAdapter(fetcher, cfg) for cfg in RANKINGS]
    adapters += [AutoSiteAdapter(fetcher, cfg) for cfg in AUTO_SITES]
    adapters += [CommunityBoardAdapter(fetcher, cfg) for cfg in BOARDS]
    return adapters
