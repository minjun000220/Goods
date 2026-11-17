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
