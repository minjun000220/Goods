"""간단한 상시 실행 스케줄러 (asyncio).

소스마다 주기가 다르다: 랭킹은 자주, 검색 트렌드는 하루 1번.
규모가 커지면 Prefect/Airflow 로 옮긴다 (재시도, 실행 이력, UI 가 생김).

  python -m pipelines.scheduler
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from collectors.fetchers.http_fetcher import HttpFetcher
from config import settings
from monitoring.health import check_parser_health
from pipelines.run_pipeline import build_adapters, collect_and_process, score
from storage.db import init_db, session_scope

log = logging.getLogger("scheduler")

INTERVALS_MIN = {          # source_id → 수집 주기(분)
    "naver_shopping": 60,
    "youtube": 24 * 60,        # 하루 할당량 때문에 1일 1회
    "coupang": 3 * 60,
    # 베스트 랭킹 소스는 하루 여러 번 (예: "example_mall_best": 3 * 60)
}
DEFAULT_INTERVAL_MIN = 24 * 60   # 굿즈 유행은 하루 단위로 변함 → 하루 1번이면 충분
SCORE_INTERVAL_MIN = 60


async def source_loop(adapter) -> None:
    interval = INTERVALS_MIN.get(adapter.source_id, DEFAULT_INTERVAL_MIN) * 60
    while True:
        try:
            await collect_and_process([adapter], list(settings.keywords))
        except Exception:
            log.exception("collect failed: %s", adapter.source_id)
        await asyncio.sleep(interval)


async def score_loop() -> None:
    while True:
        try:
            score(date.today())
            with session_scope() as s:
                for alert in check_parser_health(s):
                    log.error("PARSER HEALTH: %s", alert)   # → 슬랙/텔레그램 알림으로 연결
        except Exception:
            log.exception("scoring failed")
        await asyncio.sleep(SCORE_INTERVAL_MIN * 60)


async def main() -> None:
    init_db()
    async with HttpFetcher(settings.user_agent) as fetcher:
        adapters = build_adapters(fetcher)
        await asyncio.gather(score_loop(), *(source_loop(a) for a in adapters))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
