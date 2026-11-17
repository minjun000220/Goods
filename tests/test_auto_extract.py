"""자동 패턴 찾기: 서로 다른 구조의 페이지에서 상품 목록을 제대로 찾는지."""
from collectors.auto_extract import extract_products
from collectors.sources.auto_site import AutoSiteAdapter, AutoSiteConfig

BASE = "https://shop.example/list"


def test_ul_li_grid_with_discount_and_banner_noise():
    items = "".join(f"""<li class="prd"><a href="/p/{i}"><img alt="x"><p class="nm">{n}</p></a>
        <del>{p+5000:,}원</del> <b class="sale">{p:,}원</b> <span>리뷰 {i*3}</span></li>"""
                    for i, (n, p) in enumerate([("에스파 공식 응원봉", 45000), ("치이카와 하치와레 인형 M", 32000),
                                                 ("세븐틴 시즌그리팅 2027", 38000), ("원신 캔뱃지 랜덤", 4500)], 1))
    html = f"""<div class="banner">5만원 이상 구매시 무료배송 50,000원</div><ul class="grid">{items}</ul>"""
    out = extract_products(html, BASE)
    assert [o.title for o in out] == ["에스파 공식 응원봉", "치이카와 하치와레 인형 M", "세븐틴 시즌그리팅 2027", "원신 캔뱃지 랜덤"]
    assert out[0].price == 45000                      # 할인 전 가격이 아니라 판매가(더 낮은 값)
    assert out[1].url == "https://shop.example/p/2" and out[3].rank == 4


def test_table_rows():
    rows = "".join(f'<tr><td>{i}</td><td><a href="?no={i}">{n}</a></td><td>₩{p:,}</td></tr>'
                   for i, (n, p) in enumerate([("포켓몬 피카츄 피규어", 45000), ("BTS 포토카드 세트", 12000),
                                                ("산리오 쿠로미 키링", 9000)], 1))
    out = extract_products(f"<table>{rows}</table>", BASE)
    assert [(o.title, o.price) for o in out] == [("포켓몬 피카츄 피규어", 45000), ("BTS 포토카드 세트", 12000),
                                                 ("산리오 쿠로미 키링", 9000)]


def test_main_list_beats_small_recommend_box():
    card = '<div class="{c}"><a href="/{c}/{i}">{c} 상품 이름 {i}</a><span>{p:,}원</span></div>'
    rec = "".join(card.format(c="rec", i=i, p=10000 + i) for i in range(3))
    main = "".join(card.format(c="item", i=i, p=20000 + i) for i in range(8))
    out = extract_products(f'<aside>{rec}</aside><section>{main}</section>', BASE)
    assert len(out) == 8 and all("item" in o.title for o in out)


def test_duplicate_layouts_counted_once():
    card = '<div class="it"><a href="/g/{i}">굿즈 상품 {i}번</a><em>{p:,}원</em></div>'
    block = "".join(card.format(i=i, p=1000 * (i + 5)) for i in range(4))
    out = extract_products(f'<div class="list">{block}{block}</div>', BASE)
    assert [o.rank for o in out] == [1, 2, 3, 4]


def test_page_without_prices_returns_nothing():
    html = "".join(f'<tr><td><a href="/b/{i}">게시글 제목 {i}</a></td><td>조회 {i}</td></tr>' for i in range(10))
    assert extract_products(f"<table>{html}</table>", BASE) == []


def test_auto_site_adapter_search_mode():
    from datetime import datetime

    from collectors.base import CrawlTask, RawDocument
    ad = AutoSiteAdapter(None, AutoSiteConfig("mall", "https://shop.example/s?q={kw}&p={page}"))
    tasks = ad.discover(["응원봉", "인형"])
    assert ad.is_search and len(tasks) == 2
    html = "".join(f'<div class="c"><a href="/x/{i}">응원봉 상품 {i}</a><b>{30000+i:,}원</b></div>' for i in range(3))
    out = ad.parse(RawDocument(tasks[0], "https://shop.example/s?q=x", datetime.now(), "html", html))
    assert len(out) == 3 and out[0].rank_list == "search:mall:응원봉" and out[0].price == 30000
