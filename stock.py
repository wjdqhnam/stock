import re
import urllib.request
import xml.etree.ElementTree as ET

# shortcut: 네이버 비공식 차트 주소라 예고 없이 바뀔 수 있음, 판매 전에는 공식 데이터(KRX 등)로 교체
NAVER_URL = "https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0"
# 2024년부터 영문이 섞인 종목코드(예: 0220W0)도 있음
CODE_RE = re.compile(r"^[0-9A-Z]{6}$")

def fetch(code: str, count: int = 300) -> tuple[str, list[dict]]:
    if not CODE_RE.match(code):
        raise ValueError(f"종목코드는 숫자·영문 6자리여야 합니다: {code}")
    req = urllib.request.Request(NAVER_URL.format(code=code, count=count), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        # expat은 EUC-KR을 못 읽으므로 직접 디코딩하고 선언부를 제거
        text = re.sub(r"^\s*<\?xml[^>]*\?>", "", r.read().decode("euc-kr"))
    root = ET.fromstring(text)
    chart = root.find("chartdata")
    if chart is None or not chart.get("name"):
        raise ValueError(f"없는 종목코드입니다: {code}")
    rows = []
    for item in chart.iter("item"):
        d, *nums = item.get("data").split("|")
        o, h, l, c, v = map(int, nums)
        if o == 0:
            o = h = l = c  # 거래정지일은 시가·고가·저가가 0으로 옴
        rows.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "open": o, "high": h, "low": l, "close": c, "volume": v})
    if not rows:
        raise ValueError(f"가격 데이터가 없습니다: {code}")
    return chart.get("name"), rows


def sma(values: list[float], n: int) -> list:
    out, total = [], 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        out.append(total / n if i >= n - 1 else None)
    return out


def ema(values: list[float], n: int) -> list:
    k, out, prev = 2 / (n + 1), [], None
    for v in values:
        prev = v if prev is None else v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(values: list[float], n: int = 14) -> list:
    out = [None] * len(values)
    if len(values) <= n:
        return out
    gains = [max(values[i] - values[i - 1], 0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0) for i in range(1, len(values))]
    avg_g, avg_l = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(values)):
        if i > n:
            # Wilder 평활
            avg_g = (avg_g * (n - 1) + gains[i - 1]) / n
            avg_l = (avg_l * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def atr(rows: list[dict], n: int = 14) -> float:
    trs = [rows[0]["high"] - rows[0]["low"]] + [
        max(r["high"] - r["low"], abs(r["high"] - p["close"]), abs(r["low"] - p["close"]))
        for p, r in zip(rows, rows[1:])]
    recent = trs[-n:]
    return sum(recent) / len(recent)


def crossed(a: list, b: list, days: int) -> int:
    # 최근 days일 안에 a가 b를 상향돌파 1, 하향돌파 -1, 없음 0
    for i in range(len(a) - 1, max(len(a) - 1 - days, 0), -1):
        if None in (a[i], b[i], a[i - 1], b[i - 1]):
            break
        if a[i - 1] <= b[i - 1] and a[i] > b[i]:
            return 1
        if a[i - 1] >= b[i - 1] and a[i] < b[i]:
            return -1
    return 0


def tick(price: float) -> int:
    # 한국거래소 호가 단위 (2023년 개편 기준)
    for limit, unit in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
        if price < limit:
            return unit
    return 1000


def to_tick(price: float) -> int:
    u = tick(price)
    return max(u, round(price / u) * u)


def won(v: float) -> str:
    return f"{v:,.0f}원"


def analyze(rows: list[dict]) -> dict:
    close = [r["close"] for r in rows]
    vol = [r["volume"] for r in rows]
    c = close[-1]
    ma20, ma60 = sma(close, 20), sma(close, 60)
    r14 = rsi(close)
    macd = [a - b for a, b in zip(ema(close, 12), ema(close, 26))]
    macd_sig = ema(macd, 9)
    vol20 = sma(vol, 20)
    a = atr(rows)
    m20 = ma20[-1] if ma20[-1] is not None else c
    m60 = ma60[-1]
    rv = r14[-1]

    if m60 is None:
        trend = "flat"
    elif c > m60 and m20 > m60:
        trend = "up"
    elif c < m60 and m20 < m60:
        trend = "down"
    else:
        trend = "flat"

    # 상승 추세면 20일선 근처 눌림목을 매수 구간으로, 아니면 현재가 바로 아래를 구간으로 잡는다
    if trend == "up" and c > m20 + 0.5 * a:
        zone_low, zone_high = m20 - 0.5 * a, m20 + 0.5 * a
    else:
        zone_low, zone_high = c - a, c
    zone_low, zone_high = to_tick(zone_low), to_tick(zone_high)
    entry = (zone_low + zone_high) / 2
    stop = to_tick(entry - 2 * a)
    target = to_tick(entry + 4 * a)

    reasons, score = [], 0
    if trend == "up":
        score += 2
        reasons.append((1, "최근 석 달 동안 꾸준히 오르는 흐름이에요. 오르는 주식을 쉬어갈 때 사는 게 기본 전략이에요."))
    elif trend == "down":
        score -= 2
        reasons.append((-1, "최근 석 달 동안 내려가는 흐름이에요. 바닥을 확인하기 전까지는 사지 않는 게 안전해요."))
    else:
        reasons.append((0, "오르지도 내리지도 않고 방향을 정하는 중이에요."))
    cross = crossed(ma20, ma60, 5)
    if cross > 0:
        score += 1
        reasons.append((1, "최근 단기 흐름이 중기 흐름을 넘어섰어요 (골든크로스). 상승 전환 신호로 많이 봐요."))
    elif cross < 0:
        score -= 1
        reasons.append((-1, "최근 단기 흐름이 중기 흐름 아래로 내려갔어요 (데드크로스). 하락 전환 신호로 많이 봐요."))
    if rv is not None and rv >= 70:
        score -= 1
        reasons.append((-1, "짧은 기간에 많이 올랐어요. 잠깐 쉬어가며 가격이 내려올 수 있어요."))
    elif rv is not None and rv <= 30:
        reasons.append((0, "짧은 기간에 많이 떨어졌어요. 반등할 수도 있지만 더 떨어질 수도 있어요."))
    mc = crossed(macd, macd_sig, 3)
    if mc:
        score += mc
        reasons.append((mc, "최근 며칠 사이 오르는 힘이 붙기 시작했어요." if mc > 0 else "최근 며칠 사이 오르는 힘이 빠지고 있어요."))
    if len(vol) > 1 and vol20[-2] and vol[-1] > vol20[-2] * 2:
        reasons.append((0, f"오늘 거래량이 평소의 {vol[-1] / vol20[-2]:.1f}배예요. 큰 관심이 몰렸다는 뜻이라 가격이 크게 움직일 수 있어요."))

    risk_pct = a / c * 100
    risk = "낮음" if risk_pct < 2.5 else "보통" if risk_pct < 4.5 else "높음"
    reasons.append((0, f"하루에 보통 {risk_pct:.1f}% 정도 오르내려요. 위험도는 '{risk}'이에요."))

    # 초보자가 다루기 어려운 종목은 가격 흐름이 좋아도 추천하지 않음
    turnover = sum(r["close"] * r["volume"] for r in rows[-20:]) / min(20, len(rows))
    caution = []
    if turnover < 1e9:
        caution.append("거래가 적어서 원하는 가격에 사고팔기 어려울 수 있어요.")
    if len(rows) < 120:
        caution.append("상장한 지 얼마 안 돼서 판단할 가격 기록이 부족해요.")
    if risk_pct >= 8:
        caution.append("하루에도 가격이 너무 크게 움직여요.")
    reasons += [(-1, t) for t in caution]

    if trend == "down" or score <= -2:
        verdict, label = "avoid", "쉬어가요"
        headline = "지금은 내려가는 흐름이라 사지 않는 걸 권해요. 오름세로 돌아서면 다시 알려드릴게요."
    elif trend == "up" and c <= zone_high and (rv is None or rv < 70):
        verdict, label = "buy", "사볼 만해요"
        headline = f"오름세 속에서 숨을 고르는 중이에요. {won(zone_low)}~{won(zone_high)} 사이에서 나눠 사보세요."
    elif trend == "up":
        verdict, label = "wait", "기다려요"
        headline = f"좋은 흐름이지만 지금은 조금 비싸요. {won(zone_high)} 아래로 내려오면 사보세요."
    else:
        verdict, label = "wait", "기다려요"
        headline = "방향이 정해지지 않았어요. 오름세가 확인될 때까지 지켜보세요."
    if caution and verdict == "buy":
        verdict, label = "wait", "기다려요"
        headline = f"가격 흐름은 좋지만 초보자에게는 권하지 않아요. {caution[0]}"

    change = (c / close[-2] - 1) * 100 if len(close) > 1 else 0.0
    return {
        "close": c, "change": round(change, 2), "change_amt": c - close[-2] if len(close) > 1 else 0,
        "date": rows[-1]["date"], "turnover": round(turnover), "beginner": not caution,
        "trend": trend, "verdict": verdict, "label": label, "headline": headline, "score": score,
        "zone_low": zone_low, "zone_high": zone_high, "target": target, "stop": stop,
        "target_pct": round((target / entry - 1) * 100, 1), "stop_pct": round((stop / entry - 1) * 100, 1),
        "risk": risk, "risk_pct": round(risk_pct, 1), "rsi": None if rv is None else round(rv, 1),
        "reasons": [{"tone": t, "text": x} for t, x in reasons],
        "series": {"ma20": ma20, "ma60": ma60, "rsi": r14},
    }
