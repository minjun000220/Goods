"""아무 쇼핑몰 주소에서 자동 패턴 찾기가 잘 되는지 미리 확인하는 도구.

  python -m tools.try_auto "https://www.animate-onlineshop.co.kr/goods/goods_list.php?cateCd=008"

robots.txt 가 허용하는 주소만 가져온다. 결과가 괜찮으면 collectors/registry.py 의
AUTO_SITES 에 AutoSiteConfig 로 추가하면 다음 수집부터 포함된다.
"""
import asyncio
import sys

from collectors.auto_extract import extract_products
from collectors.fetchers.http_fetcher import HttpFetcher, RobotsDisallowed
from config import settings
from processing.nlp import classify_goods_type


async def main(url: str) -> None:
    async with HttpFetcher(settings.user_agent) as f:
        try:
            html = await f.get_text(url)
        except RobotsDisallowed:
            print("❌ robots.txt 가 이 주소의 수집을 허용하지 않습니다.")
            return
        except Exception as e:  # noqa: BLE001
            print(f"❌ 페이지를 가져오지 못했습니다: {e!r} (봇 차단·로그인 필요·주소 오류 등)")
            return
    items = extract_products(html, url)
    if not items:
        print("❌ 상품 목록을 찾지 못했습니다. (가격이 화면에 없거나, JS 로만 그려지는 페이지일 수 있음)")
        return
    typed = sum(1 for it in items if classify_goods_type(it.title))
    print(f"✅ 상품 {len(items)}개 발견, 그중 굿즈 종류 판별 {typed}개\n")
    for it in items[:20]:
        price = f"{it.price:,}원" if it.price else "-"
        print(f"{it.rank:>3}. {price:>10}  [{classify_goods_type(it.title) or '?'}] {it.title[:60]}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
