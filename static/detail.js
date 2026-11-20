const code = location.pathname.split("/").pop();
const el = document.getElementById("content");

function calcText(d, amount) {
  const entry = (d.zone_low + d.zone_high) / 2;
  if (!(amount > 0)) return "투자할 금액을 숫자로 입력해 주세요.";
  const n = Math.floor(amount / entry);
  if (!n) return `이 금액으로는 1주도 살 수 없어요. 매수 구간 기준으로 최소 <b>${won(entry)}</b>이 필요해요.`;
  const gain = n * (d.target - entry), loss = n * (entry - d.stop);
  const warn = d.verdict === "avoid" ? "<br><span class='muted'>다만 지금은 쉬어가는 걸 권하는 종목이에요.</span>" : "";
  return `살 가격 가운데(${won(entry)}) 기준 약 <b>${n.toLocaleString("ko-KR")}주</b>를 살 수 있어요.<br>
    목표가에 팔면 <b class="up">+${won(gain)}</b>, 손절가에 팔면 <b class="down">−${won(loss)}</b>이에요.${warn}`;
}

const RESULT = { win: "목표 도달", loss: "손절", timeout: "기한 만료" };

function historyPanel(bt) {
  if (!bt) return "";
  const s = bt.stock, o = bt.overall, years = Math.round((new Date(bt.end) - new Date(bt.start)) / 3.15e10);
  const head = `<div class="card-h"><h2>이 종목의 과거 신호</h2><small>최근 ${years}년</small></div>`;
  if (s === undefined || s === null) {
    return `<section class="card">${head}<p class="none">과거 성적은 대형주 68개로만 계산해서 이 종목은 기록이 없어요. 대형주 전체 기준으로는 '사볼 만해요' 신호의 10번 중 ${+(o.win / 10).toFixed(1)}번이 목표가에 닿았어요.</p></section>`;
  }
  if (!s.n) {
    return `<section class="card">${head}<p class="none">이 기간에 '사볼 만해요' 신호가 나온 적이 없어요. 전체 종목 기준으로는 10번 중 ${(o.win / 10).toFixed(1)}번 목표가에 닿았어요.</p></section>`;
  }
  const few = s.n < 10 ? `<p class="hint">신호가 ${s.n}번뿐이라 우연의 영향이 커요. 전체 종목 기준(목표 도달 ${o.win}%)도 같이 보세요.</p>` : "";
  return `<section class="card">${head}
    <p class="big-num">신호 ${s.n}번 중 ${Math.round(s.n * s.win / 100)}번 목표가 도달</p>
    ${outcomeBar(s)}
    <ul class="kv"><li><span>거래당 평균 수익</span><b class="${tone(s.avg_ret)}">${pct(s.avg_ret)}</b></li>
      <li><span>평균 보유 기간</span><b>${Math.round(s.avg_days)}거래일</b></li></ul>${few}
    <ul class="hist">${s.recent.slice().reverse().map(t => `<li><span>${t.date}</span><span class="muted">${RESULT[t.result]} · ${t.days}일</span><b class="${tone(t.ret)}">${pct(t.ret)}</b></li>`).join("")}</ul>
  </section>`;
}

const money = v => v == null ? "-" : Math.abs(v) >= 1e12 ? `${(v / 1e12).toFixed(1)}조원` : `${Math.round(v / 1e8).toLocaleString("ko-KR")}억원`;
const growth = (cur, prev) => cur == null || !prev || prev < 0 ? "" :
  ` <small class="${tone(cur - prev)}">${pct(Math.round((cur / prev - 1) * 100))}</small>`;

function companyPanel(c) {
  if (!c) return "";
  const f = c.financials, al = c.alerts;
  const fin = f ? `
    <ul class="kv" style="margin-top:0">
      <li><span>매출</span><b>${money(f.revenue)}${growth(f.revenue, f.revenue_prev)}</b></li>
      <li><span>영업이익 (본업으로 번 돈)</span><b class="${f.op_income < 0 ? "down" : ""}">${money(f.op_income)}${growth(f.op_income, f.op_income_prev)}</b></li>
      <li><span>순이익</span><b>${money(f.net_income)}</b></li>
      <li><span>부채비율 (빚 ÷ 자기 돈)</span><b>${f.debt_ratio == null ? "-" : f.debt_ratio + "%"}</b></li>
    </ul>
    <p class="hint">${f.year}년 사업보고서${f.consolidated ? " 연결 기준" : ""}, 괄호는 전년 대비 · 출처 금융감독원 전자공시</p>`
    : `<p class="none">사업보고서 재무 정보를 찾지 못했어요.</p>`;
  const alertHtml = al.length ? `<ul class="alerts">${al.map(a => `
      <li class="a-${a.level}"><b>${esc(a.text)}</b><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)} · ${a.date.slice(0, 4)}.${a.date.slice(4, 6)}.${a.date.slice(6)}</a></li>`).join("")}</ul>`
    : `<p class="none">최근 3개월 동안 주의할 공시가 없었어요.</p>`;
  return `<div class="two">
    <section class="card"><div class="card-h"><h2>회사 실적</h2></div>${fin}</section>
    <section class="card"><div class="card-h"><h2>주의할 공시</h2><small>최근 3개월</small></div>${alertHtml}</section>
  </div>`;
}

function render(d) {
  document.title = `${d.name} ${won(d.close)} - 첫주식`;
  el.innerHTML = `
  <main class="main">
    <section class="card">
      <div class="head">${avatar(d, true)}<div><h1>${esc(d.name)}</h1><small>${d.market} · ${d.code} · ${esc(d.sector)}</small></div></div>
      <div class="price">${won(d.close)}</div>
      <div class="chg">어제보다 ${change(d)} · ${day(d.date)} 장 마감</div>
      <div class="chart-bar">
        <div class="keys" style="margin:0">
          <span><i style="background:#e0a100"></i>20일 평균</span><span><i style="background:#8e5cc7"></i>60일 평균</span>
          <span><i style="background:var(--brand)"></i>매수 구간·목표가</span><span><i style="background:var(--avoid)"></i>손절가</span>
        </div>
        <div class="seg" id="range" role="group" aria-label="기간">
          <button data-n="63" aria-pressed="true">3개월</button><button data-n="126" aria-pressed="false">6개월</button><button data-n="250" aria-pressed="false">1년</button>
        </div>
      </div>
      <div id="chart"></div>
      <div id="rsi"></div>
      <p class="hint">아래 선은 과열 정도(RSI)예요. 70 위면 너무 많이 올라 쉬어갈 수 있고, 30 아래면 너무 많이 떨어진 상태예요.</p>
    </section>

    <section class="card">
      <div class="card-h"><h2>왜 이렇게 판단했나요?</h2><small>최근 1년 가격·거래량 기준</small></div>
      <ul class="reasons">${d.reasons.map(r => `<li class="${r.tone > 0 ? "pos" : r.tone < 0 ? "neg" : ""}">${esc(r.text)}</li>`).join("")}</ul>
    </section>

    ${companyPanel(d.company)}
    ${historyPanel(d.backtest)}

    <section class="card terms">
      <details style="margin:0">
        <summary>차트 보는 법</summary>
        <dl>
          <dt>빨간 막대와 파란 막대</dt><dd>하루의 가격 움직임이에요. 빨강은 오른 날, 파랑은 내린 날이에요.</dd>
          <dt>20일 · 60일 평균</dt><dd>최근 한 달, 석 달 평균 가격을 이은 선이에요. 가격이 이 선들 위에 있으면 오르는 흐름이에요.</dd>
          <dt>골든크로스</dt><dd>짧은 평균선이 긴 평균선을 뚫고 올라가는 것. 오름세로 바뀌는 신호로 많이 봐요.</dd>
          <dt>목표가는 어떻게 정했나요?</dt><dd>이 종목이 평소 하루에 움직이는 폭을 기준으로, 손실 폭의 두 배를 목표로 잡았어요.</dd>
        </dl>
      </details>
    </section>
  </main>

  <aside class="side">
    <section class="card decide">
      ${verdict(d)}
      <p class="lead">${esc(d.headline)}</p>
      ${ladder(d, true)}${ladderNums(d)}
      <ul class="kv">
        <li><span>${d.verdict === "avoid" ? "오름세로 바뀌면 살 가격" : "살 가격"}</span><b>${won(d.zone_low)} ~ ${won(d.zone_high)}</b></li>
        <li><span>팔 가격 (목표가)</span><b>${won(d.target)} <small class="up">${pct(d.target_pct)}</small></b></li>
        <li><span>팔 가격 (손절가)</span><b>${won(d.stop)} <small class="down">${pct(d.stop_pct)}</small></b></li>
        <li><span>출렁임</span><b>${esc(d.risk)} <small class="muted">하루 ±${d.risk_pct}%</small></b></li>
      </ul>
      <div class="calc">
        <label for="amount">투자 금액으로 계산해 보기</label>
        <div class="field"><input id="amount" inputmode="numeric" value="1,000,000"><span>원</span></div>
        <output id="calc-out" for="amount" aria-live="polite">${calcText(d, 1000000)}</output>
      </div>
    </section>
  </aside>`;

  const input = document.getElementById("amount"), out = document.getElementById("calc-out");
  input.addEventListener("input", () => {
    const v = Number(input.value.replace(/[^\d]/g, ""));
    input.value = v ? v.toLocaleString("ko-KR") : "";
    out.innerHTML = calcText(d, v);
  });
  drawChart(d);
}

function drawChart(d) {
  if (!window.LightweightCharts) {
    document.getElementById("chart").innerHTML = `<p class="muted">차트를 불러오지 못했어요. 인터넷 연결을 확인해 주세요.</p>`;
    return;
  }
  const css = getComputedStyle(document.documentElement);
  const c = name => css.getPropertyValue(name).trim();
  const opts = {
    autoSize: true,
    layout: { background: { color: "transparent" }, textColor: c("--muted"), fontFamily: getComputedStyle(document.body).fontFamily },
    grid: { vertLines: { visible: false }, horzLines: { color: c("--line") } },
    rightPriceScale: { borderVisible: false, minimumWidth: 80 }, timeScale: { borderVisible: false },
    localization: { priceFormatter: v => Math.round(v).toLocaleString("ko-KR") },
  };
  const line = key => d.rows.map((r, i) => ({ time: r.date, value: d.series[key][i] })).filter(p => p.value !== null);
  const main = LightweightCharts.createChart(document.getElementById("chart"), opts);
  const candles = main.addCandlestickSeries({
    upColor: c("--up"), downColor: c("--down"), borderVisible: false, wickUpColor: c("--up"), wickDownColor: c("--down"),
  });
  candles.setData(d.rows.map(r => ({ time: r.date, open: r.open, high: r.high, low: r.low, close: r.close })));
  const lines = [
    [d.zone_high, c("--brand"), 2, "매수 상단"], [d.zone_low, c("--brand"), 2, "매수 하단"],
    [d.target, c("--brand"), 0, "목표가"], [d.stop, c("--avoid"), 2, "손절가"],
  ];
  lines.forEach(([price, color, lineStyle, title]) => candles.createPriceLine({ price, color, lineStyle, lineWidth: 1, title }));
  main.addLineSeries({ color: "#e0a100", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }).setData(line("ma20"));
  main.addLineSeries({ color: "#8e5cc7", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }).setData(line("ma60"));
  const vol = main.addHistogramSeries({ priceScaleId: "", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
  vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  vol.setData(d.rows.map(r => ({ time: r.date, value: r.volume, color: (r.close >= r.open ? c("--up") : c("--down")) + "40" })));

  const sub = LightweightCharts.createChart(document.getElementById("rsi"), { ...opts, layout: { ...opts.layout, attributionLogo: false }, timeScale: { visible: false } });
  const rs = sub.addLineSeries({ color: c("--ink"), lineWidth: 1, priceLineVisible: false });
  rs.setData(line("rsi"));
  rs.createPriceLine({ price: 70, color: c("--up"), lineStyle: 2, lineWidth: 1 });
  rs.createPriceLine({ price: 30, color: c("--down"), lineStyle: 2, lineWidth: 1 });
  main.timeScale().subscribeVisibleLogicalRangeChange(r => r && sub.timeScale().setVisibleLogicalRange(r));

  const show = n => main.timeScale().setVisibleLogicalRange({ from: d.rows.length - n, to: d.rows.length + 3 });
  show(63);
  document.getElementById("range").addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b) return;
    document.querySelectorAll("#range button").forEach(x => x.setAttribute("aria-pressed", x === b));
    show(+b.dataset.n);
  });
}

fetch(`/api/stock/${encodeURIComponent(code)}`)
  .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail)))
  .then(render)
  .catch(msg => {
    el.innerHTML = `<main class="main"><section class="card"><b>종목을 불러오지 못했어요.</b><p class="none">${esc(typeof msg === "string" ? msg : "인터넷 연결을 확인한 뒤 새로고침해 주세요.")}</p></section></main>`;
  });
