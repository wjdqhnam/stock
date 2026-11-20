import backtest


def day(o, h, l, c):
    return {"date": "2026-01-01", "open": o, "high": h, "low": l, "close": c, "volume": 1}


PLAN = {"zone_high": 100, "stop": 90, "target": 120}


def test_win_loss_and_same_day_counts_as_loss():
    rows = [day(100, 100, 100, 100), day(100, 105, 99, 104), day(104, 121, 103, 118)]
    assert backtest.simulate(rows, 0, PLAN)["result"] == "win"
    rows = [day(100, 100, 100, 100), day(100, 101, 89, 90)]
    assert backtest.simulate(rows, 0, PLAN)["result"] == "loss"
    rows = [day(100, 100, 100, 100), day(100, 125, 85, 100)]
    assert backtest.simulate(rows, 0, PLAN)["result"] == "loss"


def test_gaps_and_skips():
    # 갭상승으로 매수 구간 위에서 시작하면 안 삼
    assert backtest.simulate([day(100, 100, 100, 100), day(101, 101, 101, 101)], 0, PLAN) is None
    # 갭하락이면 손절가가 아니라 시가에 팜
    t = backtest.simulate([day(100, 100, 100, 100), day(95, 95, 95, 95), day(80, 82, 78, 80)], 0, PLAN)
    assert t["result"] == "loss" and abs(t["ret"] - ((80 / 95 - 1) * 100 - backtest.COST)) < 1e-9


def test_timeout_and_unfinished():
    flat = [day(100, 101, 99, 100)] * (backtest.HOLD_MAX + 1)
    assert backtest.simulate(flat, 0, PLAN)["result"] == "timeout"
    assert backtest.simulate(flat[:10], 0, PLAN) is None


def test_stats():
    s = backtest.stats([{"result": "win", "ret": 10, "days": 5}, {"result": "loss", "ret": -5, "days": 3}])
    assert s == {"n": 2, "win": 50.0, "loss": 50.0, "timeout": 0.0, "avg_ret": 2.5, "avg_days": 4.0}
    assert backtest.stats([]) == {"n": 0}
