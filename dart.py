import io
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from pathlib import Path

BASE = "https://opendart.fss.or.kr/api/"
CORP_FILE = Path(__file__).parent / "dart_corp.json"
FIN_TTL, NEWS_TTL = 24 * 3600, 3600
_cache: dict[tuple, tuple[float, object]] = {}
_corp: dict[str, str] | None = None

# 공시 제목에 이 단어가 있으면 경고. high는 판정을 '쉬어가요'로, mid는 '사볼 만해요'를 '기다려요'로 낮춘다
RISK_WORDS = [
    ("high", "횡령", "회사 돈을 빼돌린 혐의가 공시됐어요."),
    ("high", "배임", "경영진이 회사에 손해를 끼친 혐의가 공시됐어요."),
    ("high", "거래정지", "주식 거래가 정지된 적이 있어요."),
    ("high", "관리종목", "관리종목으로 지정됐어요. 상장폐지 위험이 있는 종목이에요."),
    ("high", "상장폐지", "상장폐지 관련 공시가 있어요."),
    ("high", "회생절차", "회생절차 관련 공시가 있어요."),
    ("high", "파산", "파산 관련 공시가 있어요."),
    ("high", "감자결정", "자본금을 줄이는 감자 결정이 있었어요. 보통 주주에게 불리해요."),
    ("high", "불성실공시", "불성실공시법인으로 지정됐어요."),
    ("high", "의견거절", "감사인이 재무제표에 의견을 거절했어요."),
    ("mid", "유상증자", "새 주식을 발행해 돈을 모으기로 했어요. 기존 주식의 가치가 묽어질 수 있어요."),
    ("mid", "전환사채", "나중에 주식으로 바뀔 수 있는 채권을 발행했어요. 주식 수가 늘 수 있어요."),
    ("mid", "신주인수권부사채", "나중에 새 주식을 살 권리가 붙은 채권을 발행했어요. 주식 수가 늘 수 있어요."),
]
FINANCE_SECTORS = {"금융", "보험"}


def key() -> str | None:
    return os.environ.get("DART_API_KEY") or None


def _get(path: str, **params) -> bytes:
    url = BASE + path + "?" + urllib.parse.urlencode({"crtfc_key": key(), **params})
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.read()


def _json(path: str, **params) -> dict | None:
    data = json.loads(_get(path, **params))
    if data["status"] == "013":
        return None  # 조회된 데이터 없음
    if data["status"] != "000":
        raise RuntimeError(f"OpenDART 오류 {data['status']}: {data.get('message')}")
    return data


def parse_corp_zip(raw: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root = ET.fromstring(z.read(z.namelist()[0]))
    # 상장사만 (stock_code가 있는 것) 종목코드 → 고유번호
    return {e.findtext("stock_code").strip(): e.findtext("corp_code").strip()
            for e in root.iter() if e.find("corp_code") is not None and (e.findtext("stock_code") or "").strip()}


def corp_code(stock_code: str) -> str | None:
    global _corp
    if _corp is None:
        if CORP_FILE.exists():
            _corp = json.loads(CORP_FILE.read_text(encoding="utf-8"))
        else:
            _corp = parse_corp_zip(_get("corpCode.xml"))
            CORP_FILE.write_text(json.dumps(_corp), encoding="utf-8")
    return _corp.get(stock_code)


def _num(s) -> float | None:
    s = (s or "").replace(",", "").strip()
    return float(s) if s and s != "-" else None


def parse_financials(items: list[dict]) -> dict:
    # 연결재무제표(CFS) 우선, 없으면 개별(OFS)
    fs = "CFS" if any(i.get("fs_div") == "CFS" for i in items) else "OFS"
    acc = {i["account_nm"]: i for i in items if i.get("fs_div") == fs}
    cur = lambda n: _num(acc[n]["thstrm_amount"]) if n in acc else None
    prev = lambda n: _num(acc[n]["frmtrm_amount"]) if n in acc else None
    debt, equity = cur("부채총계"), cur("자본총계")
    return {
        "year": items[0]["bsns_year"], "consolidated": fs == "CFS",
        "revenue": cur("매출액"), "revenue_prev": prev("매출액"),
        "op_income": cur("영업이익"), "op_income_prev": prev("영업이익"),
        "net_income": cur("당기순이익"), "equity": equity,
        "debt_ratio": round(debt / equity * 100, 1) if debt is not None and equity and equity > 0 else None,
    }


def parse_alerts(items: list[dict]) -> list[dict]:
    out = []
    for i in items:
        for level, word, text in RISK_WORDS:
            if word in i["report_nm"]:
                out.append({"level": level, "title": i["report_nm"].strip(), "date": i["rcept_dt"],
                            "text": text, "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={i['rcept_no']}"})
                break
    return out


def _cached(k: tuple, ttl: int, fn):
    hit = _cache.get(k)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    v = fn()
    _cache[k] = (time.time(), v)
    return v


def financials(corp: str) -> dict | None:
    def load():
        # 올해 사업보고서는 3월 말에야 나오므로 작년 → 재작년 순으로 찾는다
        for year in (date.today().year - 1, date.today().year - 2):
            data = _json("fnlttSinglAcnt.json", corp_code=corp, bsns_year=year, reprt_code="11011")
            if data and data.get("list"):
                return parse_financials(data["list"])
        return None
    return _cached(("fin", corp), FIN_TTL, load)


def alerts(corp: str) -> list[dict]:
    def load():
        bgn = (date.today() - timedelta(days=90)).strftime("%Y%m%d")
        data = _json("list.json", corp_code=corp, bgn_de=bgn, page_count=100)
        return parse_alerts(data["list"]) if data else []
    return _cached(("news", corp), NEWS_TTL, load)


def company(stock_code: str) -> dict | None:
    if not key():
        return None
    corp = corp_code(stock_code)
    if corp is None:
        return None
    return {"financials": financials(corp), "alerts": alerts(corp)}


def adjust(d: dict, info: dict | None, sector: str) -> dict:
    # 가격 판정 위에 재무·공시 근거를 덧씌운다 (이 규칙은 백테스트로 검증되지 않음)
    if not info:
        return d
    d = {**d, "reasons": list(d["reasons"])}
    f, al = info.get("financials"), info.get("alerts") or []
    downgrade, avoid = [], []
    if f:
        if f["equity"] is not None and f["equity"] <= 0:
            avoid.append("빚이 재산보다 많은 자본잠식 상태예요.")
        if f["op_income"] is not None and f["op_income"] < 0:
            downgrade.append(f"{f['year']}년에 본업에서 손해를 봤어요 (영업적자).")
        elif f["op_income"] and f["op_income_prev"] and f["op_income"] > f["op_income_prev"] > 0:
            d["reasons"].append({"tone": 1, "text": f"{f['year']}년 영업이익이 전년보다 {(f['op_income'] / f['op_income_prev'] - 1) * 100:.0f}% 늘었어요. 장사가 잘되고 있어요."})
        if f["debt_ratio"] and f["debt_ratio"] > 200 and sector not in FINANCE_SECTORS:
            d["reasons"].append({"tone": -1, "text": f"부채비율이 {f['debt_ratio']:.0f}%로 높은 편이에요. 경기가 나빠지면 버티기 힘들 수 있어요."})
    for a in al:
        (avoid if a["level"] == "high" else downgrade).append(f"최근 공시: {a['text']}")
    for t in avoid + downgrade:
        d["reasons"].append({"tone": -1, "text": t})
    if avoid and d["verdict"] != "avoid":
        d.update(verdict="avoid", label="쉬어가요", headline=f"가격 흐름과 상관없이 조심해야 할 일이 있어요. {avoid[0]}")
    elif downgrade and d["verdict"] == "buy":
        d.update(verdict="wait", label="기다려요", headline=f"가격 흐름은 좋지만 확인할 게 있어요. {downgrade[0]}")
    d["company"] = info
    return d
