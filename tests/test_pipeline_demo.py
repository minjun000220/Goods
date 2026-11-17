"""데모 소스로 수집→처리→점수 전체 흐름을 검증하는 통합 테스트."""
import asyncio
from datetime import date, timedelta

from analytics.burst import detect_mention_bursts, discover_new_goods_types
from analytics.scoring import run_scoring
from collectors.sources.demo import DemoSource
from processing.processor import Processor
from storage.repository import Repository


def test_demo_end_to_end(session):
    end = date(2026, 11, 17)
    start = end - timedelta(days=34)
    proc = Processor(Repository(session))
    for i in range(35):
        items, stats = asyncio.run(DemoSource(start + timedelta(days=i), start, end).run([]))
        assert stats.failures == 0
        proc.handle(items)

    run_scoring(session, end - timedelta(days=1))       # 어제 점수도 있어야 '어제 대비' 계산
    scored = run_scoring(session, end)
    assert set(scored.index) == {"인형", "응원봉", "키링", "피규어", "포토카드"}
    ranks = scored["rank"]
    assert ranks["인형"] == 1                 # 막판에 폭발
    assert ranks["응원봉"] > 1                # 늘 크지만 정체 → 1등 아님
    assert ranks["키링"] == len(scored)       # 식는 중 → 꼴찌
    # 아티스트가 달라도 '응원봉' 하나로 합쳐진다
    examples = " ".join(scored.loc["응원봉", "examples"])
    assert sum(a in examples for a in ["BTS", "aespa", "세븐틴", "NewJeans", "아이브"]) >= 2

    b = scored.attrs["breakdowns"]["인형"]
    assert b["hot_index"] >= 85 and b["label"].startswith("🔥")          # 급상승
    assert scored.attrs["breakdowns"]["키링"]["hot_index"] < 50           # 하락 중
    assert b["rank_change"] is not None and b["prev_as_of"] == "2026-11-16"
    assert sum(v["points"] for v in b["signals"].values()) > 30           # 근거 점수 합계

    assert detect_mention_bursts(session, end)[0]["goods_type"] == "인형"
    assert discover_new_goods_types(session, end)[0]["keyword"] == "말랑이"
