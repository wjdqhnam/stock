const ORDER = { buy: 0, wait: 1, avoid: 2 };
const PAGE = 50;
const state = { f: "all", sector: "all", market: "all", sort: "rec", limit: PAGE };
let stocks = [];

function renderToday(data) {
  const n = { buy: 0, wait: 0, avoid: 0 };
  stocks.forEach(s => n[s.verdict]++);
  const up = stocks.filter(s => s.change_amt > 0).length, down = stocks.filter(s => s.change_amt < 0).length;
  document.getElementById("asof").textContent = `${day(data.date)} 장 마감 기준 · 코스피·코스닥 ${stocks.length.toLocaleString("ko-KR")}개`;
  document.getElementById("headline").textContent = n.buy ? `오늘 사볼 만한 주식 ${n.buy}개` : "오늘은 사볼 만한 주식이 없어요";
  document.getElementById("stat").innerHTML = `<span>오른 종목 <b class="up">${up}</b></span><span>내린 종목 <b class="down">${down}</b></span>`;
  document.querySelectorAll("#tabs button").forEach(b => {
    const k = b.dataset.f;
    b.innerHTML = `${k === "all" ? "전체" : LABEL[k]} <small>${(k === "all" ? stocks.length : n[k]).toLocaleString("ko-KR")}</small>`;
  });
}

function renderPicks() {
  const picks = stocks.filter(s => s.verdict === "buy")
    .sort((a, b) => b.score - a.score || b.turnover - a.turnover).slice(0, 4);
  const el = document.getElementById("pick-list");
  if (!picks.length) {
    el.outerHTML = `<p class="none">오늘은 조건에 맞는 종목이 없어요. 시장 전체가 쉬어가는 날엔 사지 않는 것도 전략이에요. 아래 '기다려요' 종목의 매수 구간을 미리 봐두세요.</p>`;
    return;
  }
  el.innerHTML = picks.map(s => `
    <a class="pick" href="/stock/${s.code}">
      <div class="pick-top">${avatar(s)}<div><b>${esc(s.name)}</b><span>${won(s.close)} ${change(s)}</span></div></div>
      <p>${esc(s.headline)}</p>
      <div>${ladder(s)}${ladderNums(s)}</div>
    </a>`).join("");
}

function renderList() {
  const rows = stocks.filter(s => (state.f === "all" || s.verdict === state.f) && (state.sector === "all" || s.sector === state.sector)
    && (state.market === "all" || s.market === state.market));
  const sorts = {
    rec: (a, b) => ORDER[a.verdict] - ORDER[b.verdict] || b.score - a.score || b.turnover - a.turnover,
    risk: (a, b) => a.risk_pct - b.risk_pct,
    up: (a, b) => b.change - a.change,
    down: (a, b) => a.change - b.change,
  };
  rows.sort(sorts[state.sort]);
  const more = document.getElementById("more"), left = rows.length - state.limit;
  more.hidden = left <= 0;
  more.textContent = `더 보기 (${left.toLocaleString("ko-KR")}개 남음)`;
  document.getElementById("list").innerHTML = rows.length ? rows.slice(0, state.limit).map(s => `
    <a class="row" href="/stock/${s.code}">
      <div class="nm">${avatar(s)}<div><b>${esc(s.name)}</b><small>${s.market} · ${esc(s.sector)}${s.alert ? `<span class="flag ${s.alert}">공시 주의</span>` : ""}${s.beginner ? "" : `<span class="flag mid">초보 주의</span>`}</small></div></div>
      <div class="px"><b>${won(s.close)}</b><small>${change(s)}</small></div>
      <div class="num"><small>살 가격</small>${s.zone_low.toLocaleString("ko-KR")}~${won(s.zone_high)}</div>
      <div class="num"><small>목표가</small>${won(s.target)} <span class="up">${pct(s.target_pct)}</span></div>
      <div class="v">${verdict(s)}</div>
    </a>`).join("") : `<div class="empty-row">이 조건에 맞는 종목이 없어요. 업종이나 판정을 바꿔 보세요.</div>`;
}

function renderRecord(bt) {
  if (!bt || !bt.signal.n) return;
  const s = bt.signal, v = bt.by_verdict, base = bt.baseline;
  document.getElementById("record").hidden = false;
  document.getElementById("record-period").textContent = `${bt.start.slice(0, 4)}.${bt.start.slice(5, 7)} ~ ${bt.end.slice(0, 4)}.${bt.end.slice(5, 7)}`;
  document.getElementById("record-big").textContent = `'사볼 만해요'를 따랐다면 10번 중 ${+(s.win / 10).toFixed(1)}번 목표가 도달`;
  document.getElementById("record-bar").innerHTML = outcomeBar(s);
  document.getElementById("record-nums").innerHTML = `
    <li><span>거래당 평균 수익</span><b class="${tone(s.avg_ret)}">${pct(s.avg_ret)}</b></li>
    <li><span>평균 보유 기간</span><b>${Math.round(s.avg_days)}거래일</b></li>
    <li><span>계산한 거래 수</span><b>${s.n.toLocaleString("ko-KR")}번</b></li>`;
  const rows = [["사볼 만해요", v.buy], ["기다려요", v.wait], ["쉬어가요", v.avoid], ["아무 날이나", base]];
  document.getElementById("record-table").innerHTML = `<tr><th>그날 샀다면</th><th>목표 도달</th><th>평균 수익</th></tr>` +
    rows.map(([k, x]) => `<tr><td>${k}</td><td>${x.win}%</td><td class="${tone(x.avg_ret)}">${pct(x.avg_ret)}</td></tr>`).join("");
  const notes = ["목표 수익이 손실의 두 배라 10번 중 3.4번만 맞아도 본전이에요."];
  if (v.avoid.avg_ret < base.avg_ret) notes.push(`'쉬어가요'일 때 샀다면 평균 ${pct(v.avoid.avg_ret)}로 가장 나빴어요.`);
  notes.push(v.buy.avg_ret > v.wait.avg_ret * 1.5
    ? `'사볼 만해요'일 때 산 평균 수익(${pct(v.buy.avg_ret)})이 '기다려요'(${pct(v.wait.avg_ret)})보다 높았어요.`
    : "'사볼 만해요'와 '기다려요'는 결과 차이가 크지 않았어요.");
  notes.push(`수수료·세금 ${bt.rules.cost}%를 뺀 결과예요. 지금 남아 있는 대형주만으로 계산해서 실제보다 좋게 나왔을 수 있어요.`);
  document.getElementById("record-notes").innerHTML = notes.map(n => `<li>${esc(n)}</li>`).join("");
}

document.getElementById("tabs").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  state.f = b.dataset.f;
  state.limit = PAGE;
  document.querySelectorAll("#tabs button").forEach(x => x.setAttribute("aria-pressed", x === b));
  renderList();
});
document.getElementById("sector").addEventListener("change", e => { state.sector = e.target.value; state.limit = PAGE; renderList(); });
document.getElementById("market").addEventListener("change", e => { state.market = e.target.value; state.limit = PAGE; renderList(); });
document.getElementById("more").addEventListener("click", () => { state.limit += PAGE * 2; renderList(); });
document.getElementById("sort").addEventListener("change", e => { state.sort = e.target.value; state.limit = PAGE; renderList(); });

getStocks().then(data => {
  stocks = data.stocks;
  const sectors = [...new Set(stocks.map(s => s.sector))].sort((a, b) => a.localeCompare(b, "ko"));
  document.getElementById("sector").innerHTML += sectors.map(s => `<option>${esc(s)}</option>`).join("");
  renderToday(data);
  renderPicks();
  renderList();
  renderRecord(data.backtest);
}).catch(e => {
  document.getElementById("asof").textContent = "아직 보여드릴 시세가 없어요";
  document.getElementById("headline").textContent = e.message;
  document.getElementById("list").innerHTML = `<div class="empty-row">시세를 불러오지 못했어요.</div>`;
  document.getElementById("pick-list").innerHTML = "";
});
