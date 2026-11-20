from fastapi.testclient import TestClient

import stock
import stock_app


def rows_from(closes, spread=0.02):
    return [{"date": f"2026-{i // 28 % 12 + 1:02d}-{i % 28 + 1:02d}", "open": c, "high": round(c * (1 + spread)),
             "low": round(c * (1 - spread)), "close": c, "volume": 100_000} for i, c in enumerate(closes)]


def test_sma_ema_rsi():
    assert stock.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert stock.ema([10, 10, 10], 5) == [10, 10, 10]
    assert stock.rsi(list(range(1, 30)))[-1] == 100.0
    assert stock.rsi([1, 2, 3])[-1] is None


def test_crossed():
    assert stock.crossed([1, 1, 3], [2, 2, 2], 3) == 1
    assert stock.crossed([3, 3, 1], [2, 2, 2], 3) == -1
    assert stock.crossed([3, 3, 3], [2, 2, 2], 3) == 0


def test_tick_size():
    assert stock.to_tick(1234.4) == 1234
    assert stock.to_tick(12346) == 12350
    assert stock.to_tick(181_620) == 181_600
    assert stock.to_tick(1_104_400) == 1_104_000


def test_plan_is_ordered_and_on_ticks():
    for closes in ([100_000 + i * 300 for i in range(200)], [200_000 - i * 300 for i in range(200)], [50_000] * 200):
        d = stock.analyze(rows_from(closes))
        assert d["stop"] < d["zone_low"] <= d["zone_high"] < d["target"]
        for k in ("stop", "zone_low", "zone_high", "target"):
            assert d[k] % stock.tick(d[k]) == 0


def test_verdicts():
    down = stock.analyze(rows_from([200_000 - i * 300 for i in range(200)]))
    assert down["verdict"] == "avoid" and down["trend"] == "down"
    # 오르다가 20일선 근처로 눌림 → 매수
    dip = [100_000 + i * 300 for i in range(190)] + [156_700 - j * 300 for j in range(1, 11)]
    d = stock.analyze(rows_from(dip))
    assert d["trend"] == "up" and d["verdict"] == "buy", d["headline"]
    # 계속 급등 → 과열이라 기다림
    hot = stock.analyze(rows_from([100_000 + i * 600 for i in range(200)]))
    assert hot["verdict"] == "wait"
    short = stock.analyze(rows_from([100, 101]))
    assert short["verdict"] == "wait" and short["rsi"] is None


def test_fetch_rejects_bad_code():
    for bad in ["abc", "12345", "1234567", "../x"]:
        try:
            stock.fetch(bad)
            assert False
        except ValueError:
            pass


def test_beginner_caution_blocks_buy():
    dip = [100_000 + i * 300 for i in range(190)] + [156_700 - j * 300 for j in range(1, 11)]
    rows = rows_from(dip)
    assert stock.analyze(rows)["verdict"] == "buy"
    thin = [{**r, "volume": 10} for r in rows]  # 거래대금이 거의 없는 종목
    d = stock.analyze(thin)
    assert d["verdict"] == "wait" and not d["beginner"] and "초보자" in d["headline"]
    assert not stock.analyze(rows[-100:])["beginner"]  # 상장 초기라 기록 부족


def test_code_format():
    assert stock.CODE_RE.match("0220W0") and stock.CODE_RE.match("005930")
    assert not stock.CODE_RE.match("02a0w0")


def test_due():
    from datetime import datetime
    kst = stock_app.market.KST
    fri_after = datetime(2026, 11, 20, 16, 0, tzinfo=kst)
    assert stock_app.due(None, fri_after)
    assert stock_app.due("2026-11-19", fri_after)
    assert not stock_app.due("2026-11-20", fri_after)
    assert not stock_app.due("2026-11-19", datetime(2026, 11, 20, 10, 0, tzinfo=kst))  # 장 마감 전
    assert not stock_app.due("2026-11-20", datetime(2026, 11, 21, 16, 0, tzinfo=kst))  # 토요일


def test_api(monkeypatch):
    c = TestClient(stock_app.app)
    monkeypatch.setitem(stock_app.STATE, "status", "collecting")
    assert c.get("/api/stocks").status_code == 503
    stocks = [{"code": "005930", "name": "테스트전자", "market": "코스피", "sector": "반도체"},
              {"code": "0220W0", "name": "새회사", "market": "코스닥", "sector": "금융"}]
    rows = rows_from([100_000 + i * 300 for i in range(200)])
    monkeypatch.setattr(stock_app, "STATE", dict(stock_app.STATE))
    stock_app.refresh(stocks, {"005930": rows, "0220W0": rows[-30:]})
    data = c.get("/api/stocks").json()
    assert len(data["stocks"]) == 2 and "reasons" not in data["stocks"][0]
    d = c.get("/api/stock/005930").json()
    assert d["sector"] == "반도체" and "series" in d and "backtest" in d
    assert c.get("/api/stock/0220W0").status_code == 200
    monkeypatch.setattr(stock_app, "BACKTEST", stock_app.BACKTEST.with_name("없는파일.json"))
    assert c.get("/api/stock/005930").json()["backtest"] is None
    assert c.get("/api/stock/999999").status_code == 404
    assert c.get("/api/stock/12ab56").status_code == 400
    assert c.get("/").status_code == 200 and c.get("/stock/005930").status_code == 200
