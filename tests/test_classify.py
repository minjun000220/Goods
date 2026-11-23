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


def test_unknown_type_is_none():
    assert classify_goods_type("치이카와 말랑이 스퀴시") is None
    assert classify_goods_type("albumin 보충제") is None     # 영문 별칭은 단어 경계 지킴
