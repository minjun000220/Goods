import numpy as np
import pandas as pd

from analytics.scoring import robust_z, score_frame
from analytics.signals import SIGNALS


def test_robust_z_ignores_outlier_scale():
    z = robust_z(pd.Series([1, 1.1, 0.9, 1.0, 50]))
    assert z.iloc[-1] == 4.0          # clip
    assert abs(z.iloc[0]) < 1


def test_score_prefers_rising_over_big_but_flat():
    base = {s: 0.0 for s in SIGNALS}
    df = pd.DataFrame([
        {**base, "best_share_momentum": 0.0, "sold_out_ratio": 0.3},                              # 응원봉: 크지만 정체
        {**base, "best_share_momentum": 1.2, "buzz_momentum": 1.5, "sold_out_ratio": 0.8},        # 인형: 상승
        {**base, "best_share_momentum": -0.5, "buzz_momentum": -0.6},                             # 키링: 하락
        {**base, "best_share_momentum": 0.2, "buzz_momentum": 0.1},
    ], index=["응원봉", "인형", "키링", "피규어"])
    out = score_frame(df)
    assert out.index[0] == "인형" and out.index[-1] == "키링"
    assert out["rank"].tolist() == [1, 2, 3, 4]


def test_missing_signal_is_neutral():
    df = pd.DataFrame([{s: np.nan for s in SIGNALS}] * 2, index=["a", "b"])
    out = score_frame(df)
    assert (out["score"] == 0).all() and (out["coverage"] == 0).all()


def test_hot_index_scale_and_labels():
    from analytics.scoring import hot_index, index_label
    assert hot_index(0) == 50
    assert hot_index(2) > 90 and hot_index(-2) < 10
    assert 0 <= hot_index(-50) <= hot_index(50) <= 100
    assert index_label(90).startswith("🔥") and index_label(50).startswith("➖")


def test_contributions_sum_to_index_minus_50():
    from analytics.scoring import contributions, hot_index
    base = {s: 0.0 for s in SIGNALS}
    df = pd.DataFrame([
        {**base, "best_share_momentum": 1.2, "buzz_momentum": 1.5, "sold_out_ratio": 0.8},
        {**base, "best_share_momentum": 0.0, "sold_out_ratio": 0.3},
        {**base, "best_share_momentum": -0.5, "buzz_momentum": -0.6},
        {**base, "best_share_momentum": 0.2, "buzz_momentum": 0.1},
    ], index=["인형", "응원봉", "키링", "피규어"])
    out = score_frame(df)
    row = out.loc["인형"]
    pts = contributions(row)
    assert abs(sum(pts.values()) - (row["hot_index"] - 50)) <= 1
    assert pts["buzz_momentum"] > 0


def test_best_share_not_inflated_by_multiple_runs_per_day():
    from datetime import datetime

    from analytics.signals import best_share

    def run(t, types):
        return [{"observed_at": t, "age": 0, "rank": i + 1, "rank_list": "best:shop", "goods_type": g}
                for i, g in enumerate(types)]
    types = ["인형"] * 10 + ["키링"] * 10
    once = pd.DataFrame(run(datetime(2026, 11, 17, 9), types))
    thrice = pd.DataFrame(run(datetime(2026, 11, 17, 9), types) + run(datetime(2026, 11, 17, 10), types)
                          + run(datetime(2026, 11, 17, 11), types))
    a = best_share(once).set_index("goods_type")["share"]
    b = best_share(thrice).set_index("goods_type")["share"]
    assert a["인형"] == b["인형"] == 0.5
