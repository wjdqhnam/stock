import io
import zipfile

import dart

BASE_D = {"verdict": "buy", "label": "사볼 만해요", "headline": "h", "reasons": []}


def acc(name, cur, prev, fs="CFS"):
    return {"bsns_year": "2025", "account_nm": name, "fs_div": fs, "thstrm_amount": cur, "frmtrm_amount": prev}


def test_parse_corp_zip_keeps_listed_only():
    xml = ("<result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list>"
           "<list><corp_code>00000001</corp_code><corp_name>비상장</corp_name><stock_code> </stock_code></list></result>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", xml)
    assert dart.parse_corp_zip(buf.getvalue()) == {"005930": "00126380"}


def test_parse_financials_prefers_consolidated():
    items = [acc("매출액", "300,000", "250,000"), acc("영업이익", "-1,000", "2,000"),
             acc("부채총계", "300", "0"), acc("자본총계", "100", "0"), acc("매출액", "1", "1", fs="OFS")]
    f = dart.parse_financials(items)
    assert f["consolidated"] and f["revenue"] == 300000 and f["op_income"] == -1000 and f["debt_ratio"] == 300.0
    assert f["net_income"] is None


def test_parse_alerts():
    items = [{"report_nm": "주요사항보고서(유상증자결정)", "rcept_dt": "20261101", "rcept_no": "1"},
             {"report_nm": "횡령ㆍ배임혐의발생", "rcept_dt": "20261102", "rcept_no": "2"},
             {"report_nm": "분기보고서 (2026.09)", "rcept_dt": "20261103", "rcept_no": "3"}]
    al = dart.parse_alerts(items)
    assert [a["level"] for a in al] == ["mid", "high"] and al[0]["url"].endswith("rcpNo=1")


def test_adjust_rules():
    assert dart.adjust(BASE_D, None, "반도체") is BASE_D
    loss = {"financials": {"year": "2025", "equity": 100, "op_income": -5, "op_income_prev": 3, "debt_ratio": 50}, "alerts": []}
    assert dart.adjust(BASE_D, loss, "반도체")["verdict"] == "wait"
    fraud = {"financials": None, "alerts": [{"level": "high", "text": "횡령"}]}
    assert dart.adjust(BASE_D, fraud, "반도체")["verdict"] == "avoid"
    growing = {"financials": {"year": "2025", "equity": 100, "op_income": 12, "op_income_prev": 10, "debt_ratio": 250}, "alerts": []}
    d = dart.adjust(BASE_D, growing, "금융")
    assert d["verdict"] == "buy" and len(d["reasons"]) == 1  # 금융업은 부채비율 경고 제외
    assert BASE_D["reasons"] == []  # 원본은 건드리지 않음


def test_company_off_without_key(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    assert dart.company("005930") is None
