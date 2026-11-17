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
    out = YouTubeAdapter(None, "k").parse(raw("youtube", "search", {"q": "인형"}, body, "json"))
    assert out[0].text.startswith("[인형]") and out[0].engagement == 15


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
