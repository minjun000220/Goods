"""파이프라인: 수집 → 처리 → 저장 → 점수 계산을 순서대로 묶는다.

사용법 (프로젝트 루트에서):
  python -m pipelines.run_pipeline demo --days 35        # 네트워크 없이 가짜 데이터로 전체 흐름 확인
  python -m pipelines.run_pipeline collect               # 실제 소스 수집 (키 없는 소스는 바로, 나머지는 키 필요)
  python -m pipelines.run_pipeline score --as-of 2026-11-17
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, timedelta

from analytics.burst import detect_mention_bursts, discover_new_goods_types
from analytics.scoring import run_scoring
from collectors.base import SourceAdapter
from collectors.fetchers.http_fetcher import HttpFetcher
from collectors.raw_store import make_raw_store
from collectors.registry import build_adapters
from collectors.sources.demo import DemoSource
from config import settings
from processing.processor import Processor
from storage.db import init_db, session_scope
from storage.repository import Repository

log = logging.getLogger("pipeline")

# 수집 소스 목록·설정은 collectors/registry.py 에서 관리한다.


async def collect_and_process(adapters: list[SourceAdapter], keywords: list[str]) -> None:
    raw_store = make_raw_store(settings.raw_store, settings.raw_dir, settings.raw_keep_days)
    raw_store.cleanup()
    # 소스들은 서로 독립 → 동시에 수집
    log.info("수집 시작: 소스 %d개, 검색어 %d개", len(adapters), len(keywords))
    results = await asyncio.gather(*(a.run(keywords, raw_store) for a in adapters))
    log.info("수집 완료 → DB 저장")
    with session_scope() as session:
        repo = Repository(session)
        processor = Processor(repo)
        for items, stats in results:
            repo.add_crawl_run(stats)
            counts = processor.handle(items)
            log.info("[%s] processed %s", stats.source_id, dict(counts))


def score(as_of: date, top: int = 10) -> None:
    with session_scope() as session:
        scored = run_scoring(session, as_of)
        bursts = detect_mention_bursts(session, as_of)
        new_types = discover_new_goods_types(session, as_of)
    if scored.empty:
        print("점수를 계산할 데이터가 없습니다.")
        return
    bds = scored.attrs.get("breakdowns", {})
    print(f"\n=== 🔥 요즘 핫한 굿즈 (기준일 {as_of}) — 핫지수 0~100, 50 = 평소 수준 ===")
    for gt, r in scored.head(top).iterrows():
        b = bds[gt]
        if b["rank_change"] is None:
            change = "  NEW  "
        else:
            arrow = "▲" if b["rank_change"] > 0 else ("▼" if b["rank_change"] < 0 else "-")
            change = f"{arrow}{abs(b['rank_change']) or '':<2} {b['index_change']:+3d}"
        top_sig = sorted(b["signals"].values(), key=lambda v: -abs(v["points"]))[:2]
        why = ", ".join(f"{v['label']} {v['points']:+.0f}" for v in top_sig if v["points"])
        print(f"{int(r['rank']):>2}. {gt:<7} 핫지수 {b['hot_index']:>3}점 {b['label']:<6} [{change}]  "
              f"근거: {why or '-'}")
        if r["examples"]:
            print(f"      예) {', '.join(r['examples'][:3])}")
    print("\n=== 📈 언급량 급상승 ===")
    print(bursts or "없음")
    print("\n=== 🆕 사전에 없는 새 굿즈 종류 후보 (확인 후 dictionaries.py 에 추가) ===")
    print(new_types[:10] or "없음")


async def run_demo(days: int) -> None:
    end = date.today()
    start = end - timedelta(days=days - 1)
    for i in range(days):
        d = start + timedelta(days=i)
        await collect_and_process([DemoSource(as_of=d, start=start, end=end)], [])
        if i < days - 1:                    # 날짜별 점수 기록 → 어제 대비 변동, 핫지수 추이 그래프
            with session_scope() as session:
                run_scoring(session, d)
    score(end)


async def run_collect() -> None:
    async with HttpFetcher(settings.user_agent) as fetcher:
        adapters = build_adapters(fetcher)
        if not adapters:
            print("활성화된 소스가 없습니다. .env/환경변수 설정을 확인하세요.")
            return
        await collect_and_process(adapters, list(settings.keywords))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo"); d.add_argument("--days", type=int, default=35)
    sub.add_parser("collect")
    s = sub.add_parser("score"); s.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = p.parse_args()

    init_db()
    if args.cmd == "demo":
        asyncio.run(run_demo(args.days))
    elif args.cmd == "collect":
        asyncio.run(run_collect())
    else:
        score(args.as_of)


if __name__ == "__main__":
    main()
