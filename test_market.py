import market

KIND_HTML = """<table><tr><th>회사명</th><th>시장구분</th><th>종목코드</th><th>업종</th></tr>
<tr><td>삼성전자</td><td>유가</td><td style="mso-number-format:'@'">005930</td><td>통신 및 방송 장비 제조업</td></tr>
<tr><td>한화머시너리</td><td>유가</td><td>0220W0</td><td>기타 금융업</td></tr>
<tr><td>미래에셋스팩5호</td><td>코스닥</td><td>123450</td><td>금융 지원 서비스업</td></tr></table>"""


def day(d, c):
    return {"date": d, "open": c, "high": c, "low": c, "close": c, "volume": 1}


def test_parse_kind_skips_spac():
    rows = market.parse_kind(KIND_HTML, "코스피")
    assert [r["code"] for r in rows] == ["005930", "0220W0"]
    assert rows[0] == {"code": "005930", "name": "삼성전자", "market": "코스피", "sector": "통신 및 방송 장비 제조업"}


def test_update_incremental_and_delisting(tmp_path):
    db = market.connect(tmp_path / "t.db")
    listed = [{"code": "000001", "name": "가", "market": "코스피", "sector": "x"},
              {"code": "000002", "name": "나", "market": "코스닥", "sector": "y"}]
    asked, fail = {}, set()

    def hist(code, count):
        asked[code] = count
        if code in fail:
            raise OSError("일시 오류")
        return [day("2026-11-19", 100), day("2026-11-20", 110)]

    r = market.update(db, lambda: listed, hist)
    assert r == {"ok": 2, "failed": []} and asked == {"000001": market.KEEP_DAYS, "000002": market.KEEP_DAYS}
    stocks, rows = market.load(db)
    assert len(stocks) == 2 and rows["000001"][-1]["close"] == 110

    # 두 번째 수집: 이미 있는 종목은 며칠 치만 요청, 한 종목 실패해도 나머지는 저장
    asked.clear()
    fail.add("000002")
    r = market.update(db, lambda: listed, hist)
    assert asked["000001"] < 10 and r["failed"] == ["000002"]

    # 목록에서 빠진 종목(상장폐지)은 가격까지 정리
    fail.clear()
    market.update(db, lambda: listed[:1], hist)
    stocks, rows = market.load(db)
    assert [s["code"] for s in stocks] == ["000001"] and set(rows) == {"000001"}
    assert market.updated(db)
