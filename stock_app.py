import json
import threading
import time
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import dart
import market
import stock

STATIC = Path(__file__).parent / "static"
BACKTEST = Path(__file__).parent / "backtest.json"
CLOSE_DONE = (15, 40)  # 장 마감 후 종가가 확정되는 시각
CHECK_EVERY = 1800
SUMMARY_SKIP = ("reasons", "series", "rows", "company")
STATE = {"status": "loading", "updated": None, "stocks": {}, "rows": {}, "analysis": {}}
_pool = ThreadPoolExecutor(8)


def refresh(stocks: list[dict], rows_by_code: dict[str, list[dict]]):
    analysis = {}
    for s in stocks:
        rows = rows_by_code.get(s["code"])
        if rows:
            analysis[s["code"]] = {**s, **{k: v for k, v in stock.analyze(rows).items() if k != "series"}}
    STATE.update(stocks={s["code"]: s for s in stocks}, rows=rows_by_code, analysis=analysis, status="ready")


def due(updated: str | None, now: datetime) -> bool:
    if updated is None:
        return True
    return now.weekday() < 5 and (now.hour, now.minute) >= CLOSE_DONE and updated < now.strftime("%Y-%m-%d")


def collector():
    db = market.connect()
    stocks, rows = market.load(db)
    if stocks:
        refresh(stocks, rows)
        STATE["updated"] = market.updated(db)
    while True:
        if due(market.updated(db), datetime.now(market.KST)):
            if not STATE["analysis"]:
                STATE["status"] = "collecting"
            try:
                market.update(db)
                refresh(*market.load(db))
                STATE["updated"] = market.updated(db)
            except Exception:  # 수집이 실패해도 서버는 예전 데이터로 계속 동작
                traceback.print_exc()
                if not STATE["analysis"]:
                    STATE["status"] = "error"
        time.sleep(CHECK_EVERY)


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=collector, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def ready():
    if STATE["status"] != "ready":
        msg = {"error": "시세를 모으지 못했어요. 인터넷 연결을 확인하고 서버를 다시 켜 주세요."}.get(
            STATE["status"], "처음 실행이라 전체 종목 시세를 모으고 있어요. 2~3분 뒤에 새로고침해 주세요.")
        raise HTTPException(503, msg)


def with_company(d: dict) -> dict:
    try:
        info = dart.company(d["code"])
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile):
        info = None  # 공시 서버 문제로 시세 분석까지 막지 않는다
    return dart.adjust(d, info, d["sector"])


def summary(d: dict) -> dict:
    alerts = (d.get("company") or {}).get("alerts") or []
    return {**{k: v for k, v in d.items() if k not in SUMMARY_SKIP},
            "alert": "high" if any(a["level"] == "high" for a in alerts) else "mid" if alerts else None}


def backtest():
    # python backtest.py 로 만든 결과 파일, 없으면 화면에서 과거 성적을 숨김
    try:
        return json.loads(BACKTEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@app.get("/api/stocks")
def api_stocks():
    ready()
    items = list(STATE["analysis"].values())
    if dart.key():
        # 공시·재무는 판정을 낮추기만 하므로 '사볼 만해요' 종목만 확인
        buys = [d for d in items if d["verdict"] == "buy"]
        checked = {d["code"]: d for d in _pool.map(with_company, buys)}
        items = [checked.get(d["code"], d) for d in items]
    bt = backtest()
    keys = ("start", "end", "rules", "signal", "by_verdict", "baseline")
    return {"date": max(d["date"] for d in items), "updated": STATE["updated"], "stocks": [summary(d) for d in items],
            "dart": bool(dart.key()), "backtest": {k: bt[k] for k in keys} if bt else None}


@app.get("/api/stock/{code}")
def api_stock(code: str):
    if not stock.CODE_RE.match(code):
        raise HTTPException(400, f"종목코드는 숫자·영문 6자리여야 합니다: {code}")
    ready()
    if code not in STATE["analysis"]:
        raise HTTPException(404, f"목록에 없는 종목이에요: {code}")
    rows = STATE["rows"][code]
    d = with_company({**STATE["stocks"][code], "rows": rows, **stock.analyze(rows)})
    bt = backtest()
    return {**d, "backtest": {"start": bt["start"], "end": bt["end"], "overall": bt["signal"],
                              "stock": bt["per_stock"].get(code)} if bt else None}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/stock/{code}")
def detail(code: str):
    return FileResponse(STATIC / "stock.html")
