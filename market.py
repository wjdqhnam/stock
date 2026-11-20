import re
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import stock

DB = Path(__file__).parent / "market.db"
KIND_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType={}"
MARKETS = {"stockMkt": "코스피", "kosdaqMkt": "코스닥"}
KEEP_DAYS = 300
KST = timezone(timedelta(hours=9))
WORKERS = 4  # 상대 서버 부담을 줄이려고 동시 요청 수를 낮게 유지

# shortcut: 목록은 KIND, 시세는 네이버 비공식 주소로 임시 수집, KRX Open API 키가 나오면 listing()·history()만 교체


def parse_kind(html: str, market: str) -> list[dict]:
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", html, re.S)[1:]:
        cells = [re.sub(r"<[^>]+>|\s+", " ", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 4 or not stock.CODE_RE.match(cells[2]) or "스팩" in cells[0]:
            continue  # 스팩은 합병용 빈 회사라 분석 대상에서 뺌
        out.append({"code": cells[2], "name": cells[0], "market": market, "sector": cells[3]})
    return out


def listing() -> list[dict]:
    out = []
    for key, market in MARKETS.items():
        req = urllib.request.Request(KIND_URL.format(key), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            out += parse_kind(r.read().decode("euc-kr", "replace"), market)
    if len(out) < 1000:
        raise RuntimeError(f"종목 목록이 비정상적으로 적습니다: {len(out)}개")
    return out


def history(code: str, count: int) -> list[dict]:
    return stock.fetch(code, count)[1]


def connect(path: Path = DB) -> sqlite3.Connection:
    db = sqlite3.connect(path, check_same_thread=False)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS stocks (code TEXT PRIMARY KEY, name TEXT, market TEXT, sector TEXT);
        CREATE TABLE IF NOT EXISTS prices (code TEXT, date TEXT, open INT, high INT, low INT, close INT, volume INT,
                                           PRIMARY KEY (code, date));
        CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    return db


def update(db: sqlite3.Connection, list_fn=listing, history_fn=history, log=lambda m: None) -> dict:
    stocks = list_fn()
    last = dict(db.execute("SELECT code, MAX(date) FROM prices GROUP BY code"))
    today = datetime.now(KST).strftime("%Y-%m-%d")

    def need(code):
        if code not in last:
            return KEEP_DAYS
        gap = (time.mktime(time.strptime(today, "%Y-%m-%d")) - time.mktime(time.strptime(last[code], "%Y-%m-%d"))) / 86400
        return min(KEEP_DAYS, int(gap) + 3)  # 겹치게 받아서 정정된 값도 덮어씀

    ok, failed = 0, []
    with ThreadPoolExecutor(WORKERS) as ex:
        futures = {ex.submit(history_fn, s["code"], need(s["code"])): s["code"] for s in stocks}
        for n, f in enumerate(as_completed(futures), 1):
            code = futures[f]
            try:
                rows = f.result()
            except Exception as e:  # 한 종목 실패로 전체 수집을 멈추지 않음
                failed.append(code)
                log(f"{code} 실패: {e}")
                continue
            db.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
                           [(code, r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows])
            ok += 1
            if n % 200 == 0:
                db.commit()
                log(f"{n}/{len(stocks)}")
    # 종목 목록은 수집이 끝난 뒤 교체해서, 도중에 실패해도 예전 목록이 남게 함
    with db:
        db.execute("DELETE FROM stocks")
        db.executemany("INSERT INTO stocks VALUES (:code, :name, :market, :sector)", stocks)
        db.execute("DELETE FROM prices WHERE code NOT IN (SELECT code FROM stocks)")
        db.execute("INSERT OR REPLACE INTO meta VALUES ('updated', ?)", (today,))
    return {"ok": ok, "failed": failed}


def load(db: sqlite3.Connection) -> tuple[list[dict], dict[str, list[dict]]]:
    stocks = [dict(zip(("code", "name", "market", "sector"), r)) for r in db.execute("SELECT * FROM stocks")]
    rows: dict[str, list[dict]] = {}
    for code, *r in db.execute("SELECT * FROM prices ORDER BY code, date"):
        rows.setdefault(code, []).append(dict(zip(("date", "open", "high", "low", "close", "volume"), r)))
    return stocks, {c: v[-KEEP_DAYS:] for c, v in rows.items()}


def updated(db: sqlite3.Connection) -> str | None:
    r = db.execute("SELECT v FROM meta WHERE k = 'updated'").fetchone()
    return r[0] if r else None


if __name__ == "__main__":
    t0 = time.time()
    result = update(connect(), log=lambda m: print(m, file=sys.stderr))
    print(f"완료: {result['ok']}개, 실패 {len(result['failed'])}개, {time.time() - t0:.0f}초")
