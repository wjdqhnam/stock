const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const won = v => Math.round(v).toLocaleString("ko-KR") + "원";
const pct = v => (v > 0 ? "+" : "") + v.toFixed(v % 1 ? 1 : 0) + "%";
const tone = v => (v > 0 ? "up" : v < 0 ? "down" : "");
const day = d => `${+d.slice(5, 7)}월 ${+d.slice(8, 10)}일`;
const LABEL = { buy: "사볼 만해요", wait: "기다려요", avoid: "쉬어가요" };
const AV_COLORS = ["#3b6fd8", "#d9534f", "#2e9c6a", "#8a5cc7", "#e08a1e", "#1f8fa3", "#c44f8a", "#5b6b7c"];

// 로고 대신 이름 첫 글자 아이콘, 색은 종목코드로 고정
function avatar(s, lg) {
  const color = AV_COLORS[[...s.code].reduce((a, c) => a + c.charCodeAt(0), 0) % AV_COLORS.length];
  return `<span class="av${lg ? " lg" : ""}" style="background:${color}" aria-hidden="true">${esc(s.name[0])}</span>`;
}

function change(s) {
  const sign = s.change_amt > 0 ? "+" : s.change_amt < 0 ? "−" : "";
  return `<span class="${tone(s.change_amt)}">${sign}${Math.abs(s.change_amt).toLocaleString("ko-KR")}원 (${Math.abs(s.change).toFixed(1)}%)</span>`;
}

function verdict(s) {
  return `<span class="verdict v-${s.verdict}">${LABEL[s.verdict]}</span>`;
}

function ladder(s, big) {
  const lo = Math.min(s.stop, s.close), hi = Math.max(s.target, s.close);
  const pad = (hi - lo) * 0.06, min = lo - pad, max = hi + pad;
  const p = v => (v - min) / (max - min) * 100;
  const zw = Math.max(0.8, p(s.zone_high) - p(s.zone_low));
  return `<div class="ladder${big ? " big" : ""}" role="img" aria-label="손절가 ${won(s.stop)}, 매수 구간 ${won(s.zone_low)}에서 ${won(s.zone_high)}, 현재가 ${won(s.close)}, 목표가 ${won(s.target)}">
    <div class="track"></div><div class="loss" style="width:${p(s.stop)}%"></div>
    <div class="zone" style="left:${p(s.zone_low)}%;width:${zw}%"></div>
    <div class="goal" style="left:${p(s.target)}%"></div><div class="now" style="left:${p(s.close)}%"></div></div>`;
}

function ladderNums(s) {
  return `<div class="ladder-nums">
    <div>손절가<b>${won(s.stop)}</b></div>
    <div>매수 구간<b>${s.zone_low.toLocaleString("ko-KR")}~${won(s.zone_high)}</b></div>
    <div>목표가<b>${won(s.target)}</b></div></div>`;
}

function outcomeBar(s) {
  return `<div class="outcome" role="img" aria-label="목표가 도달 ${s.win}%, 손절 ${s.loss}%, 기한 만료 ${s.timeout}%">
    <span class="o-win" style="flex:${s.win}"></span><span class="o-loss" style="flex:${s.loss}"></span><span class="o-time" style="flex:${s.timeout}"></span></div>
    <div class="o-legend"><span><i style="background:var(--brand)"></i>목표 도달 ${s.win}%</span>
    <span><i style="background:var(--avoid);opacity:.35"></i>손절 ${s.loss}%</span><span><i style="background:var(--line)"></i>기한 만료 ${s.timeout}%</span></div>`;
}

let allStocks = null;
function getStocks() {
  allStocks ??= fetch("/api/stocks").then(async r => {
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "시세를 불러오지 못했어요.");
    return r.json();
  });
  return allStocks;
}

function setupSearch() {
  const input = document.getElementById("q"), box = document.getElementById("q-list");
  let hits = [];
  input.addEventListener("focus", () => getStocks().catch(() => {}), { once: true });
  input.addEventListener("input", async () => {
    const q = input.value.trim().toLowerCase();
    if (!q) { box.hidden = true; return; }
    const { stocks } = await getStocks();
    hits = stocks.filter(s => s.name.toLowerCase().includes(q) || s.code.startsWith(q)).slice(0, 6);
    box.innerHTML = hits.length
      ? hits.map(s => `<li><a href="/stock/${s.code}">${avatar(s)}${esc(s.name)}<small>${verdict(s)}</small></a></li>`).join("")
      : `<li><a>찾는 종목이 없어요</a></li>`;
    box.hidden = false;
  });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && hits[0]) location.href = `/stock/${hits[0].code}`;
    if (e.key === "Escape") box.hidden = true;
  });
  document.addEventListener("click", e => { if (!e.target.closest(".search")) box.hidden = true; });
}
setupSearch();
