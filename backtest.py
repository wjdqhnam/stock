import json
import sys
import time
from pathlib import Path

import stock

OUT = Path(__file__).parent / "backtest.json"
HISTORY = 1300
WINDOW = 300  # 사이트가 실제로 쓰는 데이터 길이와 같게
HOLD_MAX = 60
COST = 0.25  # 왕복 수수료+세금 (%)
# 과거 1,300일 치를 종목마다 받아야 해서 대형주 68개로만 계산
CODES = ['005930', '000660', '373220', '207940', '005380', '000270', '068270', '035420', '035720', '105560', '055550', '086790', '316140', '005490', '051910', '006400', '012330', '028260', '066570', '003550', '096770', '017670', '030200', '032830', '000810', '015760', '034020', '012450', '329180', '009540', '010140', '042660', '011200', '003670', '018260', '009150', '034730', '010130', '033780', '090430', '051900', '097950', '271560', '004020', '047050', '259960', '036570', '251270', '323410', '377300', '352820', '302440', '011170', '024110', '138040', '064350', '047810', '267260', '010120', '247540', '086520', '196170', '028300', '263750', '293490', '035900', '041510', '112040']


def simulate(rows: list[dict], i: int, plan: dict):
    # i일 종가로 판정, i+1일 시가에 매수. 갭상승으로 매수 구간 위에서 시작하면 사지 않음
    if i + 1 >= len(rows) or rows[i + 1]["open"] > plan["zone_high"]:
        return None
    entry, stop, target = rows[i + 1]["open"], plan["stop"], plan["target"]
    last = min(i + HOLD_MAX, len(rows) - 1)
    for j in range(i + 1, last + 1):
        r = rows[j]
        # 같은 날 손절·목표 둘 다 닿으면 손절로 친다 (보수적)
        if r["low"] <= stop:
            exit_price, result = min(stop, r["open"]), "loss"
        elif r["high"] >= target:
            exit_price, result = max(target, r["open"]), "win"
        else:
            continue
        break
    else:
        if last - i < HOLD_MAX:
            return None  # 아직 끝나지 않은 거래
        exit_price, result = rows[last]["close"], "timeout"
    return {"result": result, "ret": (exit_price / entry - 1) * 100 - COST, "days": j - i, "exit_idx": j}


def stats(trades: list[dict]) -> dict:
    n = len(trades)
    if not n:
        return {"n": 0}
    count = {k: sum(t["result"] == k for t in trades) for k in ("win", "loss", "timeout")}
    return {
        "n": n,
        "win": round(count["win"] / n * 100, 1),
        "loss": round(count["loss"] / n * 100, 1),
        "timeout": round(count["timeout"] / n * 100, 1),
        "avg_ret": round(sum(t["ret"] for t in trades) / n, 2),
        "avg_days": round(sum(t["days"] for t in trades) / n, 1),
    }


def run_one(code: str) -> dict:
    name, rows = stock.fetch(code, HISTORY)
    signals, by_verdict = [], {"buy": [], "wait": [], "avoid": []}
    free_from = 0
    for i in range(WINDOW - 1, len(rows) - 1):
        plan = stock.analyze(rows[i - WINDOW + 1:i + 1])
        t = simulate(rows, i, plan)
        if t is None:
            continue
        by_verdict[plan["verdict"]].append(t)
        # 실제 사용자처럼 한 종목에 한 번에 한 거래만
        if plan["verdict"] == "buy" and i >= free_from:
            signals.append({**t, "date": rows[i]["date"]})
            free_from = t["exit_idx"]
    return {"code": code, "name": name, "start": rows[WINDOW]["date"], "end": rows[-1]["date"],
            "signals": signals, "by_verdict": by_verdict}


def main():
    t0 = time.time()
    per_stock, all_signals, groups = {}, [], {"buy": [], "wait": [], "avoid": []}
    start, end = None, None
    for n, code in enumerate(CODES, 1):
        try:
            r = run_one(code)
        except Exception as e:
            print(f"{code} 건너뜀: {e}", file=sys.stderr)
            continue
        all_signals += r["signals"]
        for k in groups:
            groups[k] += r["by_verdict"][k]
        start = min(start or r["start"], r["start"])
        end = max(end or r["end"], r["end"])
        per_stock[code] = {**stats(r["signals"]),
                           "recent": [{k: t[k] for k in ("date", "result", "days")} | {"ret": round(t["ret"], 1)}
                                      for t in r["signals"][-5:]]}
        print(f"[{n}/{len(CODES)}] {r['name']} 신호 {len(r['signals'])}회", file=sys.stderr)
    result = {
        "generated": time.strftime("%Y-%m-%d"), "start": start, "end": end,
        "rules": {"hold_max": HOLD_MAX, "cost": COST},
        "signal": stats(all_signals),
        "by_verdict": {k: stats(v) for k, v in groups.items()},
        "baseline": stats(groups["buy"] + groups["wait"] + groups["avoid"]),
        "per_stock": per_stock,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("start", "end", "signal", "by_verdict", "baseline")}, ensure_ascii=False, indent=1))
    print(f"{time.time() - t0:.0f}초", file=sys.stderr)


if __name__ == "__main__":
    main()
