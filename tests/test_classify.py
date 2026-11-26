from processing.nlp import classify_goods_type


def test_lightsticks_of_any_artist_are_one_type():
    for title in ["BTS 공식 응원봉 ver.4", "aespa 응원봉 [무료배송]", "세븐틴 캐럿봉 ver.3",
                  "NewJeans OFFICIAL LIGHT STICK", "방탄소년단 아미밤 버전4"]:
        assert classify_goods_type(title) == "응원봉", title


def test_longest_alias_wins():
    assert classify_goods_type("산리오 쿠로미 봉제인형") == "인형"
    assert classify_goods_type("치이카와 캔뱃지 세트") == "뱃지"


def test_mentions_and_noise():
    assert classify_goods_type("하치와레 누이 품절 ㅠㅠ") == "인형"
    assert classify_goods_type("[공식] 포카 랜덤 ★당일발송★") == "포토카드"


def test_spacing_variants_and_new_aliases():
    assert classify_goods_type("세븐틴 2027 시즌 그리팅") == "시즌그리팅"
    assert classify_goods_type("아이브 포토 카드 세트") == "포토카드"
    assert classify_goods_type("토이스토리 맥세이프 케이스") == "폰케이스"


def test_trending_item_aliases():
    assert classify_goods_type("소니엔젤 훈바루즈 자세교정 인형 20종") == "인형"
    assert classify_goods_type("치이카와 하치와레 훈바루즈") == "인형"
    assert classify_goods_type("JELLYCAT 바쉬풀 버니") == "인형"


def test_tracked_item_is_separate_from_type():
    from processing.nlp import classify_item
    t = "소니엔젤 훈바루즈 자세교정 인형 판다"
    assert classify_goods_type(t) == "인형"          # 종류 집계에도 그대로 들어가고
    assert classify_item(t) == "훈바루즈"             # 아이템으로도 따로 잡힌다
    assert classify_item("치이카와 하치와레 훈 바루즈") == "훈바루즈"   # 띄어쓰기 달라도
    assert classify_item("BTS 응원봉") is None


def test_unknown_type_is_none():
    assert classify_goods_type("치이카와 말랑이 스퀴시") is None
    assert classify_goods_type("albumin 보충제") is None     # 영문 별칭은 단어 경계 지킴


def test_fanlight_is_light_stick():
    from processing.nlp import classify_goods_type
    assert classify_goods_type("OFFICIAL FANLIGHT VER.3.0") == "응원봉"
    assert classify_goods_type("공식 팬라이트") == "응원봉"


def test_processor_prefers_site_category():
    from datetime import datetime
    from unittest.mock import MagicMock

    from collectors.base import ListingSnapshot
    from processing.processor import Processor
    repo = MagicMock()
    repo.bulk_add_mentions.return_value = []
    snap = ListingSnapshot("ktown4u", "1", "응원봉 미니 키링", "u", datetime(2026, 11, 1), goods_type_hint="키링")
    Processor(repo).handle([snap])
    (pairs,), _ = repo.bulk_save_listings.call_args
    assert pairs[0][1] == "키링"
