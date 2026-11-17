# goods-trend

웹(쇼핑몰·중고거래·커뮤니티·검색 트렌드)에서 데이터를 모아 **요즘 뜨는 굿즈 종류**(응원봉, 인형, 키링 …)를 점수로 뽑는 시스템.
아티스트·캐릭터는 구분하지 않는다: BTS 응원봉, aespa 응원봉 → 모두 '응원봉'.

```
수집(collectors) → 처리(processing) → 저장(storage) → 분석(analytics) → 서빙(api, dashboard)
                                   운영(pipelines, monitoring)
```

## 빠른 시작
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,nlp]"
python -m pipelines.run_pipeline demo --days 35   # 네트워크 없이 가짜 데이터로 전체 흐름 실행
pytest -q
uvicorn api.main:app --reload                     # http://localhost:8000/docs
```

## 수집 소스 (robots.txt·접근 확인: 2026-11)
| 사이트 | 상태 | 방식 |
|---|---|---|
| 애니메이트 | ✅ 키 없이 됨 | 신상품·예약상품 판매인기순 (HTML) |
| KREAM | ✅ 키 없이 됨 | 검색 결과: 리셀 시세·누적 거래 수 (HTML) |
| 디시인사이드 | ✅ 키 없이 됨 | 굿즈 갤러리 + 아이돌 갤러리 16곳 최신 글 중 굿즈 언급 글 (HTML) |
| 쿠팡 | ⏸ 꺼둠 (키 필요) | 웹은 봇 차단 → 쿠팡 파트너스 공식 API |
| 유튜브 | ⏸ 꺼둠 (키 필요) | YouTube Data API v3 |
| 네이버 쇼핑 | 🔑 키 필요 | 공식 API. 2026-07 개발자센터 신규 등록 중단, 쇼핑 검색 종료 보도 있음 |

차단된 사이트는 우회하지 않는다. 소스 추가·수정은 `collectors/registry.py` 한 곳에서 한다. 쿠팡·유튜브는 키 발급 후 `ENABLE_COUPANG` / `ENABLE_YOUTUBE` 를 True 로.
아이돌 갤러리는 `IDOL_GALLERIES` 에 갤러리 id 를 추가하면 된다.

## 실제 데이터 수집
```bash
cp .env.example .env    # 키 입력 후
set -a && source .env && set +a
python -m pipelines.run_pipeline collect      # 1회 수집 (키 없는 소스는 바로 동작)
python -m pipelines.run_pipeline score        # 점수 계산
python -m pipelines.scheduler                 # 상시 실행
```
## 자동 패턴 찾기 (주소만 넣으면 되는 사이트 추가)
셀렉터를 직접 정하지 않아도 페이지에서 "가격이 붙어 반복되는 칸"을 찾아 상품명·가격·링크·순위를 뽑는다.
```bash
python -m tools.try_auto "https://쇼핑몰주소/best?page=1"     # 먼저 잘 뽑히는지 확인
```
결과가 괜찮으면 `collectors/registry.py` 의 `AUTO_SITES` 에 추가한다 (`{page}`, `{kw}` 자리표시자 지원).
직접 셀렉터를 정한 사이트도 셀렉터가 0개를 내면(사이트 개편) 자동 패턴 찾기로 대신 수집하고 경고를 남긴다.
안 되는 경우: 가격이 화면에 없는 페이지(게시판), JS 로만 그려지는 페이지, 봇 차단·로그인 필요 사이트.

## 새 소스 추가
`collectors/base.py` 의 `SourceAdapter` 를 상속해 `discover / fetch / parse` 세 메서드만 구현하고
`build_adapters()` 에 등록한다.
