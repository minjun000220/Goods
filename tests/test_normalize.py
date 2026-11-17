from processing.normalize import clean_title, normalize_stock, parse_price, strip_html


def test_strip_html():
    assert strip_html("<b>BTS</b> 응원봉 &amp; 케이스") == "BTS 응원봉 & 케이스"


def test_clean_title_removes_sales_noise():
    assert clean_title("[공식] 치이카와 하치와레 인형 M사이즈 ★당일발송★") == "치이카와 하치와레 인형 m"
    assert clean_title("방탄소년단 아미밤 버전4 [무료배송]") == "방탄소년단 아미밤 버전4"


def test_parse_price():
    assert parse_price("12,000원") == 12000
    assert parse_price("₩9900") == 9900
    assert parse_price(15000) == 15000
    assert parse_price("") is None
    assert parse_price(0) is None


def test_normalize_stock():
    assert normalize_stock("일시품절") == "sold_out"
    assert normalize_stock("예약판매") == "preorder"
    assert normalize_stock("판매중") == "in_stock"
    assert normalize_stock(None) == "unknown"
