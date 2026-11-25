"""소스별 파서 테스트. 실제 페이지 구조(2026-11 확인)를 본뜬 작은 합성 HTML/JSON 을 쓴다."""
import json
from datetime import datetime

from collectors.base import CrawlTask, RawDocument
from collectors.registry import BOARDS, RANKINGS
from collectors.sources.best_ranking import BestRankingAdapter
from collectors.sources.community_board import CommunityBoardAdapter
from collectors.sources.coupang_partners import CoupangPartnersAdapter, authorization
from collectors.sources.kream import KreamAdapter, parse_count
from collectors.sources.youtube import YouTubeAdapter

NOW = datetime(2026, 11, 17, 12, 0)


def raw(source, kind, params, body, ctype="html", url="https://example.test/"):
    return RawDocument(CrawlTask(source, kind, params), url, NOW, ctype, body)


ANIMATE_ITEM = """
<div class="item_cont"><div class="item_info_cont">
  <div class="item_tit_box"><a href="../goods/goods_view.php?goodsNo={no}"><strong class="item_name">{title}</strong></a></div>
  <div class="item_money_box"><strong class="item_price"><span>{price} 원</span></strong></div>
</div></div>"""


def test_animate_ranking_dedupes_double_layout():
    items = "".join(ANIMATE_ITEM.format(no=n, title=t, price=p) for n, t, p in
                    [(1, "【굿즈-캔뱃지】 원신 캔뱃지 호두", "4,200"), (2, "【굿즈-아크릴스탠드】 니케 아크릴스탠드", "18,000")])
    html = f'<div class="goods_list"><div class="goods_list_cont">{items}{items}</div></div>'   # 같은 상품 2번
    ad = BestRankingAdapter(None, RANKINGS[0])
    out = ad.parse(raw(ad.source_id, "ranking", {"page": 1}, html,
                       url="https://www.animate-onlineshop.co.kr/goods/goods_list.php"))
    assert [o.rank for o in out] == [1, 2]
    assert out[0].price == 4200 and out[0].rank_list == "best:animate_new_best"
    assert out[0].url == "https://www.animate-onlineshop.co.kr/goods/goods_view.php?goodsNo=1"


def test_kream_cards():
    html = """
    <a href="/products/111"><p>Toys &amp; Goods</p><p>BTS 공식 응원봉 Ver. 4</p><p>50,000원</p>
       <span>관심</span><span>519</span><span>· 리뷰</span><span>134</span><span>· 거래</span><span>7,040</span></a>
    <a href="/products/111"><img/></a>
    <a href="/products/222"><p>G-DRAGON</p><p>위버멘쉬 공식 응원봉</p><p>13%</p><p>50,000원</p>
       <span>· 거래</span><span>1.2만</span></a>"""
    out = KreamAdapter(None).parse(raw("kream", "search", {"keyword": "응원봉"}, html))
    assert len(out) == 2
    assert out[0].title == "Toys & Goods BTS 공식 응원봉 Ver. 4"
    assert (out[0].price, out[0].review_count, out[0].sales_count) == (50000, 134, 7040)
    assert out[1].title == "G-DRAGON 위버멘쉬 공식 응원봉" and out[1].sales_count == 12000
    assert out[0].seller_type == "resale"
    assert parse_count("3,503") == 3503 and parse_count("관심") is None


def test_dc_board_uses_post_time_and_skips_notice():
    html = """<table><tbody>
    <tr class="ub-content us-post" data-type="icon_notice"><td class="gall_tit"><a href="/n">공지</a></td></tr>
    <tr class="ub-content us-post" data-type="icon_pic">
      <td class="gall_tit ub-word"><a href="/mgallery/board/view/?id=goods&no=242">응원봉 연동 질문</a>
        <a class="reply_numbox" href="#"><span class="reply_num">[3]</span></a></td>
      <td class="gall_date" title="2026-10-21 13:52:47">10.21</td>
      <td class="gall_count">29</td><td class="gall_recommend">2</td>
    </tr></tbody></table>"""
    ad = CommunityBoardAdapter(None, BOARDS[0])
    out = ad.parse(raw(ad.source_id, "board", {"page": 1}, html, url="https://gall.dcinside.com/mgallery/board/lists/?id=goods"))
    assert len(out) == 1
    assert out[0].text == "응원봉 연동 질문"
    assert out[0].observed_at == datetime(2026, 10, 21, 13, 52, 47)
    assert out[0].engagement == 5                     # 추천 2 + 댓글 3 (조회수는 제외)


def test_coupang_signature_and_parse():
    auth = authorization("GET", "/v2/x", "limit=100", "AK", "SK")
    assert auth.startswith("CEA algorithm=HmacSHA256, access-key=AK, signed-date=") and "signature=" in auth
    body = json.dumps({"rCode": "0", "data": [
        {"productId": 9, "productName": "aespa 응원봉", "productPrice": 45000, "productUrl": "u", "rank": 1}]})
    out = CoupangPartnersAdapter(None, "AK", "SK").parse(raw("coupang", "best", {"category": "1020"}, body, "json"))
    assert out[0].rank_list == "best:coupang:1020" and out[0].price == 45000


def test_youtube_parse():
    body = json.dumps({"search": {"items": [{"id": {"videoId": "v1"}, "snippet": {
        "title": "언박싱 하울", "publishedAt": "2026-11-17T01:00:00Z"}}]},
        "stats": {"v1": {"likeCount": "10", "commentCount": "5"}}})
    out = YouTubeAdapter(None, "k").parse(raw("youtube", "search", {"q": "인형 굿즈"}, body, "json"))
    assert out[0].text == "언박싱 하울" and out[0].engagement == 15     # 검색어를 붙이지 않음 → 새 단어 감시 가능
    assert YouTubeAdapter(None, "k").discover(["인형"])[0].params["q"] == "인형 굿즈"


def test_idol_gallery_keeps_only_goods_posts():
    from collectors.registry import IDOL_GALLERIES, dc_gallery
    rows = "".join(f"""<tr class="ub-content us-post" data-type="icon_txt">
      <td class="gall_tit"><a href="/board/view/?id=bts&no={n}">{t}</a></td>
      <td class="gall_date" title="2026-11-17 10:00:00">11.17</td></tr>""" for n, t in
                   [(1, "오늘 무대 미쳤다"), (2, "시그 언박싱 후기"), (3, "제발 포카 나와줘")])
    cfg = dc_gallery(IDOL_GALLERIES[0], minor=False, only_goods=True)
    out = CommunityBoardAdapter(None, cfg).parse(raw(cfg.source_id, "board", {"page": 1}, f"<table>{rows}</table>",
                                                     url="https://gall.dcinside.com/board/lists/?id=bts"))
    assert [o.text for o in out] == ["제발 포카 나와줘"]      # '시그'는 오탐 방지로 사전에서 뺐음


def test_adapter_gives_up_after_consecutive_failures():
    import asyncio

    from collectors.base import SourceAdapter

    class Blocked(SourceAdapter):
        source_id, rate_limit, concurrency = "blocked", 1000.0, 1
        calls = 0

        def discover(self, keywords):
            return [CrawlTask(self.source_id, "x", {"i": i}) for i in range(20)]

        async def fetch(self, task):
            Blocked.calls += 1
            raise ConnectionError("403")

        def parse(self, raw):
            return []

    items, st = asyncio.run(Blocked().run([]))
    assert Blocked.calls == 3 and st.failures == 3            # 20개 중 3번만 시도하고 포기
    assert "차단 의심" in st.errors[-1]


def test_adapter_time_budget_stops_hanging_site():
    import asyncio
    import time as _t

    from collectors.base import SourceAdapter

    class Hangs(SourceAdapter):
        source_id, rate_limit, concurrency, time_budget_sec = "hangs", 1000.0, 1, 0.5

        def discover(self, keywords):
            return [CrawlTask(self.source_id, "x", {"i": i}) for i in range(10)]

        async def fetch(self, task):
            await asyncio.sleep(60)                           # 응답 없는 사이트

        def parse(self, raw):
            return []

    t0 = _t.monotonic()
    _, st = asyncio.run(Hangs().run([]))
    assert _t.monotonic() - t0 < 5 and "시간 초과" in " ".join(st.errors)


def _ktown_page(items):
    data = {"props": {"pageProps": {"result": {"data": items, "currentPage": 1}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data, ensure_ascii=False)}</script></html>'


def test_ktown4u_parses_next_data_and_uses_site_category():
    from collectors.sources.ktown4u import Ktown4uAdapter
    items = [
        {"goodsNo": 166935, "goodsNm": "레드벨벳 (Red Velvet) - [2026 FANCON MD] 응원봉 미니 키링", "dispPrice": 16000,
         "dispDcPrice": 16000, "kindNm": "Keyring", "goodsTotSale": 4200, "sellQtyHideYn": "N", "saleYn": "Y",
         "grpNm": "Red Velvet"},
        {"goodsNo": 168989, "goodsNm": "유나이트 (YOUNITE) - 공식 응원봉", "dispPrice": 49000, "dispDcPrice": 45000,
         "kindNm": "FAN Light", "goodsTotSale": None, "sellQtyHideYn": "Y", "saleYn": "N"},
        {"goodsNo": 1, "goodsNm": "엑소 (EXO) - 콘서트 MD 아크릴 스탠드", "dispPrice": 22000, "kindNm": "Toy",
         "goodsTotSale": 6253, "sellQtyHideYn": "N", "saleYn": "Y"},
        {"goodsNo": 2, "goodsNm": "", "dispPrice": 1000},                              # 이름 없음 → 버림
    ]
    out = Ktown4uAdapter().parse(raw("ktown4u", "search", {"keyword": "응원봉"}, _ktown_page(items)))
    assert [o.external_id for o in out] == ["166935", "168989", "1"]
    kr, ls, toy = out
    assert kr.goods_type_hint == "키링" and kr.price == 16000 and kr.sales_count == 4200 and kr.stock_status == "in_stock"
    assert ls.goods_type_hint == "응원봉" and ls.price == 45000 and ls.sales_count is None and ls.stock_status == "sold_out"
    assert toy.goods_type_hint is None and toy.sales_count == 6253          # 분류가 애매하면 제목으로 (처리 단계)
    assert kr.url == "https://kr.ktown4u.com/iteminfo?goods_no=166935" and kr.rank_list == "search:ktown4u:응원봉"
    assert Ktown4uAdapter().parse(raw("ktown4u", "search", {"keyword": "x"}, "<html>no data</html>")) == []


def test_kind_to_type_season_greetings():
    from collectors.sources.ktown4u import kind_to_type
    assert kind_to_type("2027 SEASON'S GREETINGS") == "시즌그리팅"
    assert kind_to_type("Plush Toys") == "인형" and kind_to_type("Toy") is None and kind_to_type(None) is None
