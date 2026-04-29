/* ClusPot — interactive site */

const PALETTE = {
  bg:       "#080c14",
  panel:    "#0d1525",
  card:     "#131e30",
  cardHi:   "#1a2740",
  orange:   "#FF6B35",
  navy:     "#1A3A6E",
  text:     "#E8EAF0",
  subtext:  "#7A8FAA",
  grid:     "#192840",
  border:   "#253550",
};
// Orange → navy gradient (best → worst)
const GRADIENT = ["#FF6B35", "#FF9560", "#D4A870", "#7A9EC8", "#3266AA", "#1A3A6E"];
// Heatmap stops (low → high). Lower-is-better metrics use the reversed array.
const HEAT = ["#1A3A6E", "#2A5CA8", "#5888C0", "#B8A060", "#E87840", "#FF6B35"];

let DATA = null;            // entire data.json
let METRIC_BY_KEY = {};     // key → metric meta

const STATE = {
  lb_dataset:   "total",
  cmp_metric:   "E_form_MAE",
  cmp_dataset:  "total",
  par_metric:   "E_form_MAE",
  par_xmetric:  "Time_med",
  par_dataset:  "total",
  fwt_dataset:  "total",
  pt_metric:    "E_form_MAE",
  pt_model:     null,
  pt_dataset:   "total",
  pt_type:      "normal",
  pt_selected:  null,
  mdl:          null,
};

// ─── boot ─────────────────────────────────────────────────────────────────
fetch("data.json")
  .then(r => r.json())
  .then(d => { DATA = d; main(); })
  .catch(err => {
    document.querySelector("#hero-stats").innerHTML =
      `<div class="stat" style="grid-column:1/-1"><div class="v">⚠</div><div class="k">data.json failed to load — run python build_data.py</div></div>`;
    console.error(err);
  });

function main() {
  METRIC_BY_KEY = Object.fromEntries(DATA.meta.metrics.map(m => [m.key, m]));
  STATE.pt_model = STATE.mdl = DATA.models[0];

  initSidebarFoot();
  initHeroStats();
  initLeaderboard();
  initCompare();
  initPareto();
  initFwt();
  initPeriodic();
  initModels();
  initNav();
}

// ─── helpers ───────────────────────────────────────────────────────────────
function metricLabel(m, withUnit = true) {
  // "MAE (E_form, eV/atom)" / "R² (Force)" / "AFwT (%)" / "Time / step (median, s)"
  if (!m) return "";
  const t = m.target;
  const u = m.unit;
  if (t) {
    return withUnit && u ? `${m.label} (${t}, ${u})` : `${m.label} (${t})`;
  }
  return withUnit && u ? `${m.label} (${u})` : m.label;
}
function metricShort(m) {
  // For tight contexts (axis labels)
  return metricLabel(m, true);
}

function fmt(v, d = 4) {
  if (v == null || !isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a !== 0 && (a < 0.001 || a >= 100000)) return v.toExponential(2);
  return v.toFixed(d);
}
function fmtInt(v) {
  if (v == null || !isFinite(v)) return "—";
  return Math.round(v).toLocaleString();
}
function metricVals(metricKey, dataset) {
  return DATA.models.map(m => DATA.summary[m]?.[dataset]?.[metricKey] ?? null);
}
function rankIdx(values, lowerBetter) {
  const idx = values.map((v, i) => [i, v]).filter(([, v]) => v != null && isFinite(v));
  idx.sort((a, b) => lowerBetter ? a[1] - b[1] : b[1] - a[1]);
  return idx.map(([i]) => i);
}
function modelColor(rank, total) {
  if (total <= 1) return GRADIENT[0];
  const t = rank / (total - 1);
  return interpStops(GRADIENT, t);
}
function interpStops(stops, t) {
  t = Math.max(0, Math.min(1, t));
  const idx = t * (stops.length - 1);
  const i = Math.floor(idx);
  const f = idx - i;
  if (i >= stops.length - 1) return stops[stops.length - 1];
  return mix(stops[i], stops[i + 1], f);
}
function mix(a, b, f) {
  const ah = parseHex(a), bh = parseHex(b);
  const r = Math.round(ah[0] + (bh[0] - ah[0]) * f);
  const g = Math.round(ah[1] + (bh[1] - ah[1]) * f);
  const bl = Math.round(ah[2] + (bh[2] - ah[2]) * f);
  return `rgb(${r}, ${g}, ${bl})`;
}
function parseHex(s) {
  if (s.startsWith("rgb")) {
    return s.match(/\d+/g).slice(0, 3).map(Number);
  }
  s = s.replace("#", "");
  return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
}
function luminance(rgb) {
  const v = parseHex(rgb);
  return (0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]) / 255;
}
function plotlyLayout(extra = {}) {
  return Object.assign({
    paper_bgcolor: PALETTE.panel,
    plot_bgcolor:  PALETTE.panel,
    font: { color: PALETTE.text, family: "Inter, sans-serif", size: 12.5 },
    margin: { l: 70, r: 30, t: 30, b: 70 },
    xaxis: {
      gridcolor: PALETTE.grid, zerolinecolor: PALETTE.border,
      linecolor: PALETTE.border, tickcolor: PALETTE.border,
      title: { font: { size: 13, color: PALETTE.text } },
    },
    yaxis: {
      gridcolor: PALETTE.grid, zerolinecolor: PALETTE.border,
      linecolor: PALETTE.border, tickcolor: PALETTE.border,
      title: { font: { size: 13, color: PALETTE.text } },
    },
    legend: { font: { color: PALETTE.text, size: 11 }, bgcolor: "rgba(19,30,48,0.8)", bordercolor: PALETTE.border, borderwidth: 1 },
    hoverlabel: { bgcolor: PALETTE.cardHi, bordercolor: PALETTE.orange, font: { color: PALETTE.text, family: "JetBrains Mono, monospace", size: 12 } },
  }, extra);
}
const PLOTLY_CFG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"] };

function makeSeg(container, options, current, onChange) {
  container.innerHTML = "";
  options.forEach(opt => {
    const b = document.createElement("button");
    b.textContent = opt.label;
    b.dataset.v = opt.value;
    if (opt.value === current) b.classList.add("on");
    b.addEventListener("click", () => {
      container.querySelectorAll("button").forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      onChange(opt.value);
    });
    container.appendChild(b);
  });
}

function fillMetricSelect(sel, filter = () => true) {
  sel.innerHTML = "";
  DATA.meta.metrics.filter(filter).forEach(m => {
    const opt = document.createElement("option");
    opt.value = m.key;
    opt.textContent = `${metricLabel(m)}  ${m.lower_better ? "↓" : "↑"}`;
    sel.appendChild(opt);
  });
}

// ─── 0. metadata bar + hero ────────────────────────────────────────────────
function initSidebarFoot() {
  const dt = DATA.meta.generated_at?.replace("T", " ").replace(/\+.*$/, "").slice(0, 16) || "—";
  document.querySelector("#meta-right").innerHTML =
    `<b>${DATA.meta.n_models}</b> models · <b>${DATA.meta.active_elements.length}</b> elements<br>` +
    `${dt} UTC`;
  document.querySelector("#foot-right").textContent =
    `data.json · ${DATA.meta.generated_at?.slice(0, 10) || ""}`;
}

function initHeroStats() {
  const ds = "total";
  const afwt = metricVals("AFwT", ds).filter(v => v != null);
  const mae  = metricVals("E_form_MAE", ds).filter(v => v != null);
  const tmed = metricVals("Time_med", ds).filter(v => v != null);
  const sumN = DATA.models.reduce((s, m) => {
    const r = DATA.summary[m]?.[ds];
    return s + (r?.N_normal || 0) + (r?.N_anomaly || 0);
  }, 0);

  const stats = [
    { v: DATA.meta.n_models,                    k: "MLIPs benchmarked" },
    { v: DATA.meta.active_elements.length,      k: "Elements covered" },
    { v: fmtInt(sumN / DATA.meta.n_models),     k: "Avg samples / model" },
    { v: `${Math.max(...afwt).toFixed(1)}%`,    k: "Best AFwT" },
  ];
  document.querySelector("#hero-stats").innerHTML =
    stats.map(s => `<div class="stat"><div class="v">${s.v}</div><div class="k">${s.k}</div></div>`).join("");
}

// ─── 1. Leaderboard ────────────────────────────────────────────────────────
// labels are derived from metric meta via metricLabel()
const LB_KEYS = [
  "AFwT", "E_form_MAE", "E_form_RMSE", "E_form_R2",
  "Force_MAE", "Force_RMSE", "Force_cosine",
  "Anomaly_pct", "Time_med",
];
let LB_SORT = { key: "AFwT", asc: false };

function initLeaderboard() {
  const seg = document.querySelector("#lb-ds-seg");
  makeSeg(seg, DATA.meta.datasets.map(d => ({ value: d, label: d })), STATE.lb_dataset, v => {
    STATE.lb_dataset = v; renderLeaderboard();
  });
  renderLeaderboard();
}

function renderLeaderboard() {
  const ds = STATE.lb_dataset;
  const tbl = document.querySelector("#lb-table");
  // header
  let thead = `<tr><th class="sticky-l" data-k="model">Model</th><th data-k="rank">#</th>`;
  LB_KEYS.forEach(k => {
    const m = METRIC_BY_KEY[k];
    const arrow = LB_SORT.key === k ? `<span class="arrow">${LB_SORT.asc ? "▲" : "▼"}</span>` : "";
    thead += `<th data-k="${k}">${metricLabel(m)}${arrow}</th>`;
  });
  thead += `</tr>`;
  tbl.querySelector("thead").innerHTML = thead;

  // best per col
  const bestIdx = {};
  LB_KEYS.forEach(k => {
    const m = METRIC_BY_KEY[k];
    const vals = DATA.models.map(mn => DATA.summary[mn]?.[ds]?.[k]);
    const ranked = vals.map((v, i) => [i, v]).filter(([, v]) => v != null);
    if (ranked.length) {
      ranked.sort((a, b) => m.lower_better ? a[1] - b[1] : b[1] - a[1]);
      bestIdx[k] = ranked[0][0];
    }
  });

  // rows: sort by current sort key
  const sortMeta = METRIC_BY_KEY[LB_SORT.key];
  const order = DATA.models.map((mn, i) => [i, DATA.summary[mn]?.[ds]?.[LB_SORT.key]])
    .sort((a, b) => {
      if (a[1] == null) return 1; if (b[1] == null) return -1;
      const cmp = a[1] - b[1];
      const lower = sortMeta?.lower_better;
      const wantAsc = LB_SORT.asc !== undefined ? LB_SORT.asc : lower;
      return wantAsc ? cmp : -cmp;
    })
    .map(([i]) => i);

  let body = "";
  order.forEach((i, rk) => {
    const mn = DATA.models[i];
    let row = `<tr><td class="name">${mn}</td><td class="rank">${rk + 1}</td>`;
    LB_KEYS.forEach(k => {
      const v = DATA.summary[mn]?.[ds]?.[k];
      const cls = bestIdx[k] === i ? "best" : "";
      row += `<td class="${cls}">${fmt(v, 4)}</td>`;
    });
    row += `</tr>`;
    body += row;
  });
  tbl.querySelector("tbody").innerHTML = body;

  // header click → sort
  tbl.querySelectorAll("thead th").forEach(th => {
    const k = th.dataset.k;
    if (k === "model" || k === "rank") return;
    th.addEventListener("click", () => {
      if (LB_SORT.key === k) LB_SORT.asc = !LB_SORT.asc;
      else LB_SORT = { key: k, asc: METRIC_BY_KEY[k]?.lower_better ?? false };
      renderLeaderboard();
    }, { once: true });
  });
}

// ─── 2. Comparison bar ─────────────────────────────────────────────────────
function initCompare() {
  const sel = document.querySelector("#cmp-metric");
  fillMetricSelect(sel, m => m.group !== "efficiency" || m.key === "Time_med");
  sel.value = STATE.cmp_metric;
  sel.addEventListener("change", () => { STATE.cmp_metric = sel.value; renderCompare(); });

  makeSeg(document.querySelector("#cmp-ds-seg"),
    DATA.meta.datasets.map(d => ({ value: d, label: d })),
    STATE.cmp_dataset,
    v => { STATE.cmp_dataset = v; renderCompare(); });
  renderCompare();
}

function renderCompare() {
  const m = METRIC_BY_KEY[STATE.cmp_metric];
  const ds = STATE.cmp_dataset;
  const vals = metricVals(m.key, ds);
  const order = rankIdx(vals, m.lower_better);
  const names  = order.map(i => DATA.models[i]);
  const series = order.map(i => vals[i]);
  const colors = order.map((_, k) => modelColor(k, order.length));

  const trace = {
    type: "bar", orientation: "h",
    x: series, y: names,
    marker: { color: colors, line: { color: PALETTE.border, width: 0.5 } },
    text: series.map(v => fmt(v, 4)),
    textposition: "outside",
    textfont: { color: PALETTE.text, family: "JetBrains Mono", size: 11 },
    hovertemplate: "<b>%{y}</b><br>" + metricLabel(m) + ": %{x:.4f}<extra></extra>",
    cliponaxis: false,
  };
  const layout = plotlyLayout({
    height: Math.max(380, 38 * names.length + 120),
    margin: { l: 170, r: 80, t: 30, b: 60 },
    yaxis: { autorange: "reversed", gridcolor: PALETTE.bg, color: PALETTE.text, tickfont: { color: PALETTE.text, size: 12 } },
    xaxis: { title: metricLabel(m), gridcolor: PALETTE.grid, zerolinecolor: PALETTE.border, color: PALETTE.subtext },
    showlegend: false,
  });
  Plotly.react("cmp-plot", [trace], layout, PLOTLY_CFG);
}

// ─── 3. Pareto ─────────────────────────────────────────────────────────────
function initPareto() {
  const sel = document.querySelector("#par-metric");
  fillMetricSelect(sel, m => m.group !== "efficiency");
  sel.value = STATE.par_metric;
  sel.addEventListener("change", () => { STATE.par_metric = sel.value; renderPareto(); });

  document.querySelector("#par-xmetric").addEventListener("change", e => {
    STATE.par_xmetric = e.target.value; renderPareto();
  });
  makeSeg(document.querySelector("#par-ds-seg"),
    DATA.meta.datasets.map(d => ({ value: d, label: d })),
    STATE.par_dataset,
    v => { STATE.par_dataset = v; renderPareto(); });
  renderPareto();
}

function paretoMask(xs, ys, lowerBetter) {
  const n = xs.length;
  const mask = new Array(n).fill(false);
  for (let i = 0; i < n; i++) {
    if (xs[i] == null || ys[i] == null) continue;
    let dominated = false;
    for (let j = 0; j < n; j++) {
      if (j === i || xs[j] == null || ys[j] == null) continue;
      const xb = xs[j] <= xs[i];
      const yb = lowerBetter ? ys[j] <= ys[i] : ys[j] >= ys[i];
      const xs_ = xs[j] < xs[i];
      const ys_ = lowerBetter ? ys[j] < ys[i] : ys[j] > ys[i];
      if (xb && yb && (xs_ || ys_)) { dominated = true; break; }
    }
    if (!dominated) mask[i] = true;
  }
  return mask;
}

function renderPareto() {
  const m = METRIC_BY_KEY[STATE.par_metric];
  const xKey = STATE.par_xmetric;
  const ds = STATE.par_dataset;
  const xs = metricVals(xKey, ds);
  const ys = metricVals(m.key, ds);

  const valid = DATA.models.map((_, i) => xs[i] != null && ys[i] != null);
  const mask  = paretoMask(xs, ys, m.lower_better);

  const tracePareto = {
    type: "scatter", mode: "markers", name: "Pareto-optimal",
    x: DATA.models.map((_, i) => mask[i] ? xs[i] : null),
    y: DATA.models.map((_, i) => mask[i] ? ys[i] : null),
    text: DATA.models.map(n => n),
    marker: { color: PALETTE.orange, size: 16, line: { color: "white", width: 1.5 } },
    hovertemplate: "<b>%{text}</b><br>x=%{x:.4f}<br>y=%{y:.4f}<extra>★ Pareto</extra>",
  };
  const traceOther = {
    type: "scatter", mode: "markers", name: "Dominated",
    x: DATA.models.map((_, i) => (!mask[i] && valid[i]) ? xs[i] : null),
    y: DATA.models.map((_, i) => (!mask[i] && valid[i]) ? ys[i] : null),
    text: DATA.models.map(n => n),
    marker: { color: "#2A5CAA", size: 11, line: { color: PALETTE.border, width: 1 } },
    hovertemplate: "<b>%{text}</b><br>x=%{x:.4f}<br>y=%{y:.4f}<extra></extra>",
  };

  // pareto frontier line (sorted by x)
  const front = DATA.models.map((_, i) => mask[i] ? [xs[i], ys[i]] : null).filter(Boolean).sort((a, b) => a[0] - b[0]);
  const traceLine = {
    type: "scatter", mode: "lines", name: "Frontier",
    x: front.map(p => p[0]), y: front.map(p => p[1]),
    line: { color: PALETTE.orange, width: 2, dash: "dash" },
    hoverinfo: "skip", showlegend: false,
  };

  // labels
  const traceLabels = {
    type: "scatter", mode: "text",
    x: DATA.models.map((_, i) => valid[i] ? xs[i] : null),
    y: DATA.models.map((_, i) => valid[i] ? ys[i] : null),
    text: DATA.models.map((n, i) => valid[i] ? n : ""),
    textposition: "top center",
    textfont: { color: PALETTE.subtext, size: 10, family: "JetBrains Mono" },
    showlegend: false, hoverinfo: "skip",
  };

  const layout = plotlyLayout({
    height: 600,
    xaxis: { title: metricLabel(METRIC_BY_KEY[xKey]), type: "log", gridcolor: PALETTE.grid, color: PALETTE.text },
    yaxis: { title: metricLabel(m), gridcolor: PALETTE.grid, color: PALETTE.text },
    showlegend: true,
  });
  Plotly.react("par-plot", [traceLine, traceOther, tracePareto, traceLabels], layout, PLOTLY_CFG);
}

// ─── 4. FwT ────────────────────────────────────────────────────────────────
function initFwt() {
  makeSeg(document.querySelector("#fwt-ds-seg"),
    DATA.meta.datasets.map(d => ({ value: d, label: d })),
    STATE.fwt_dataset,
    v => { STATE.fwt_dataset = v; renderFwt(); });
  renderFwt();
}

function renderFwt() {
  const ds = STATE.fwt_dataset;
  const afwt = metricVals("AFwT", ds);
  const order = rankIdx(afwt, false);
  const traces = [];
  order.forEach((i, k) => {
    const m = DATA.models[i];
    const pts = DATA.fwt[m]?.[ds] || [];
    if (!pts.length) return;
    traces.push({
      type: "scatter", mode: "lines+markers",
      x: pts.map(p => p.threshold),
      y: pts.map(p => p.pct),
      name: `${m}  (AFwT=${fmt(afwt[i], 1)}%)`,
      line: { color: modelColor(k, order.length), width: 2.2 },
      marker: { color: modelColor(k, order.length), size: 6 },
      hovertemplate: `<b>${m}</b><br>ε=%{x} eV/Å<br>%{y:.2f}%<extra></extra>`,
    });
  });
  const layout = plotlyLayout({
    height: 580,
    xaxis: { title: "Force threshold ε (eV/Å)", range: [0, 1.05], gridcolor: PALETTE.grid, color: PALETTE.text },
    yaxis: { title: "Forces within threshold (%)", range: [0, 101], gridcolor: PALETTE.grid, color: PALETTE.text },
    legend: { x: 1.02, y: 1, font: { size: 11, color: PALETTE.text }, bgcolor: "rgba(19,30,48,0.9)", bordercolor: PALETTE.border, borderwidth: 1 },
    margin: { l: 70, r: 280, t: 30, b: 60 },
  });
  Plotly.react("fwt-plot", traces, layout, PLOTLY_CFG);
}

// ─── 5. Periodic table ─────────────────────────────────────────────────────
function initPeriodic() {
  const grid = document.querySelector("#pt-grid");
  grid.innerHTML = "";
  // 9 rows visible (rows 1-7 + lanthanide row 8 + actinide row 9 if needed)
  // We use grid-row positions directly. Row 8/9 only render if data present.
  ELEMENTS.forEach(el => {
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.style.gridRow = el.row;
    cell.style.gridColumn = el.col;
    cell.dataset.sym = el.sym;
    cell.innerHTML = `<span class="z">${el.z}</span><span class="sym">${el.sym}</span><span class="v"></span>`;
    cell.addEventListener("mouseenter", () => onCellHover(cell, el));
    cell.addEventListener("mouseleave", hideTip);
    cell.addEventListener("mousemove", moveTip);
    cell.addEventListener("click", () => onCellClick(el));
    grid.appendChild(cell);
  });

  // metric select (per-element only — efficiency excluded)
  const sel = document.querySelector("#pt-metric");
  fillMetricSelect(sel, m => ["energy", "force"].includes(m.group));
  sel.value = STATE.pt_metric;
  sel.addEventListener("change", () => { STATE.pt_metric = sel.value; renderPeriodic(); });

  const mSel = document.querySelector("#pt-model");
  mSel.innerHTML = DATA.models.map(m => `<option>${m}</option>`).join("");
  mSel.value = STATE.pt_model;
  mSel.addEventListener("change", () => { STATE.pt_model = mSel.value; renderPeriodic(); });

  makeSeg(document.querySelector("#pt-ds-seg"),
    DATA.meta.datasets.map(d => ({ value: d, label: d })),
    STATE.pt_dataset,
    v => { STATE.pt_dataset = v; renderPeriodic(); });

  document.querySelectorAll("#pt-type-seg button").forEach(b => {
    b.addEventListener("click", () => {
      document.querySelectorAll("#pt-type-seg button").forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      STATE.pt_type = b.dataset.v;
      renderPeriodic();
    });
  });

  renderPeriodic();
}

function elementValue(model, dataset, type, sym, metricKey) {
  return DATA.elements?.[model]?.[dataset]?.[sym]?.[type]?.[metricKey] ?? null;
}

function renderPeriodic() {
  const m = METRIC_BY_KEY[STATE.pt_metric];
  const model = STATE.pt_model;
  const ds = STATE.pt_dataset;
  const type = STATE.pt_type;
  const stops = m.lower_better ? [...HEAT].reverse() : HEAT;

  // collect values
  const vals = {};
  ELEMENTS.forEach(el => {
    const v = elementValue(model, ds, type, el.sym, m.key);
    if (v != null && isFinite(v)) vals[el.sym] = v;
  });
  const arr = Object.values(vals);
  const vmin = arr.length ? Math.min(...arr) : 0;
  const vmax = arr.length ? Math.max(...arr) : 1;
  const span = vmax - vmin || 1e-9;

  // paint cells
  document.querySelectorAll(".cell").forEach(cell => {
    const sym = cell.dataset.sym;
    const v = vals[sym];
    cell.classList.toggle("active", v != null);
    cell.classList.toggle("selected", sym === STATE.pt_selected);
    const vSpan = cell.querySelector(".v");
    if (v == null) {
      cell.style.background = PALETTE.card;
      cell.style.color = PALETTE.subtext;
      cell.style.borderColor = PALETTE.border;
      cell.style.opacity = "0.35";
      vSpan.textContent = "";
    } else {
      const t = (v - vmin) / span;
      const bg = interpStops(stops, t);
      cell.style.background = bg;
      cell.style.opacity = "1";
      const lum = luminance(bg);
      const fg = lum > 0.55 ? "#0a0d14" : "#ffffff";
      cell.style.color = fg;
      cell.style.borderColor = "rgba(0,0,0,0.25)";
      const sub = cell.querySelector(".z");
      sub.style.color = lum > 0.55 ? "rgba(0,0,0,0.55)" : "rgba(255,255,255,0.6)";
      vSpan.textContent = fmtSmall(v);
      vSpan.style.color = fg;
    }
  });

  // legend
  document.querySelector("#pt-min").textContent = arr.length ? fmt(vmin, 3) : "—";
  document.querySelector("#pt-max").textContent = arr.length ? fmt(vmax, 3) : "—";
  const legend = document.querySelector("#pt-legend");
  legend.classList.toggle("reverse", m.lower_better);

  // ensure side panel reflects current state
  if (STATE.pt_selected) renderPeriodicSide(STATE.pt_selected);
}

function fmtSmall(v) {
  if (v == null) return "";
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  if (a >= 1) return v.toFixed(2);
  return v.toFixed(3);
}

function onCellClick(el) {
  if (!el.sym) return;
  // active check: only allow click if any model has data for this element
  const hasAny = DATA.models.some(m =>
    DATA.elements?.[m]?.[STATE.pt_dataset]?.[el.sym]?.[STATE.pt_type] != null
  );
  if (!hasAny) return;
  STATE.pt_selected = el.sym;
  renderPeriodic();
  renderPeriodicSide(el.sym);
}

function renderPeriodicSide(sym) {
  const el = ELEMENTS.find(e => e.sym === sym);
  if (!el) return;
  const m = METRIC_BY_KEY[STATE.pt_metric];
  const ds = STATE.pt_dataset;
  const type = STATE.pt_type;

  // collect per-model values
  const rows = DATA.models.map(mn => {
    const slot = DATA.elements?.[mn]?.[ds]?.[sym]?.[type];
    return { model: mn, v: slot?.[m.key] ?? null, n: slot?.N_samples ?? null };
  });
  const valid = rows.filter(r => r.v != null && isFinite(r.v));
  valid.sort((a, b) => m.lower_better ? a.v - b.v : b.v - a.v);

  const samples = valid.length ? valid[0].n : null;

  let html = `
    <h3>${sym}</h3>
    <div class="el-name">${el.name} · Z=${el.z}</div>
    <div class="meta-row"><span class="k">Metric</span><span class="v">${metricLabel(m)}</span></div>
    <div class="meta-row"><span class="k">Type</span><span class="v">${type}</span></div>
    <div class="meta-row"><span class="k">Dataset</span><span class="v">${ds}</span></div>
    <div class="meta-row"><span class="k">N samples</span><span class="v">${samples != null ? fmtInt(samples) : "—"}</span></div>
  `;

  if (valid.length === 0) {
    html += `<div class="empty-note">No model has data for ${sym} (${type}).</div>`;
  } else {
    const max = Math.max(...valid.map(r => Math.abs(r.v)));
    html += `<div class="breakdown"><h4>Models · sorted ${m.lower_better ? "best→worst" : "best→worst"}</h4>`;
    valid.forEach((r, k) => {
      const pct = max > 0 ? Math.abs(r.v) / max * 100 : 0;
      const color = modelColor(k, valid.length);
      html += `
        <div class="row">
          <span class="name" title="${r.model}">${k + 1}. ${r.model}</span>
          <span class="v">${fmt(r.v, 4)}</span>
          <div class="bar"><span style="width:${pct.toFixed(1)}%; background: linear-gradient(90deg, ${color}, ${color} 60%, transparent);"></span></div>
        </div>`;
    });
    html += `</div>`;
  }
  document.querySelector("#pt-side").innerHTML = html;
}

// ─── tooltip ───────────────────────────────────────────────────────────────
const TIP = document.querySelector("#cell-tip");
function onCellHover(cell, el) {
  const m = METRIC_BY_KEY[STATE.pt_metric];
  const v = elementValue(STATE.pt_model, STATE.pt_dataset, STATE.pt_type, el.sym, m.key);
  const slot = DATA.elements?.[STATE.pt_model]?.[STATE.pt_dataset]?.[el.sym]?.[STATE.pt_type];
  const n = slot?.N_samples;
  TIP.innerHTML = `<b style="color:${PALETTE.orange}">${el.sym}</b> ${el.name}<br>${metricLabel(m)}: ${v != null ? fmt(v, 4) : "no data"}${n != null ? `<br>N=${fmtInt(n)}` : ""}`;
  TIP.classList.add("show");
}
function moveTip(e) {
  const x = e.clientX + 14;
  const y = e.clientY + 14;
  TIP.style.left = x + "px";
  TIP.style.top  = y + "px";
}
function hideTip() { TIP.classList.remove("show"); }

// ─── 6. Per-Model ──────────────────────────────────────────────────────────
function initModels() {
  const list = document.querySelector("#mdl-list");
  // sort by AFwT desc
  const afwt = metricVals("AFwT", "total");
  const order = rankIdx(afwt, false);
  list.innerHTML = "";
  order.forEach((i, k) => {
    const mn = DATA.models[i];
    const b = document.createElement("button");
    b.dataset.m = mn;
    b.innerHTML = `<span>${mn}</span><span class="rk">#${k + 1}</span>`;
    if (mn === STATE.mdl) b.classList.add("on");
    b.addEventListener("click", () => {
      list.querySelectorAll("button").forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      STATE.mdl = mn;
      renderModelCard();
    });
    list.appendChild(b);
  });
  renderModelCard();
}

function renderModelCard() {
  const mn = STATE.mdl;
  const card = document.querySelector("#mdl-card");
  const s = DATA.summary[mn]?.["total"] || {};

  const stats = [
    { k: "AFwT (%)",                 v: fmt(s.AFwT, 2) },
    { k: "MAE (E_form, eV/atom)",    v: fmt(s.E_form_MAE, 4) },
    { k: "MAE (Force, eV/Å)",        v: fmt(s.Force_MAE, 4) },
    { k: "Anomaly rate (%)",         v: fmt(s.Anomaly_pct, 2) },
    { k: "R² (E_form)",              v: fmt(s.E_form_R2, 3) },
    { k: "Cosine (Force)",           v: fmt(s.Force_cosine, 3) },
    { k: "Time / step (median, s)",  v: fmt(s.Time_med, 4) },
    { k: "N samples",                v: fmtInt((s.N_normal || 0) + (s.N_anomaly || 0)) },
  ];

  card.innerHTML = `
    <div class="mdl-name">${mn}</div>
    <div class="mdl-stats">
      ${stats.map(b => `<div class="b"><div class="k">${b.k}</div><div class="v">${b.v}</div></div>`).join("")}
    </div>
    <div id="mdl-fwt" class="plot" style="min-height:320px"></div>
    <div style="margin-top:24px">
      <h4 style="color:${PALETTE.subtext}; font-size:12px; text-transform:uppercase; letter-spacing:0.6px; margin:0 0 10px;">Per-element MAE (E_form) — top 25 by sample count</h4>
      <div id="mdl-elements" class="plot" style="min-height:660px"></div>
    </div>
  `;

  // mini fwt
  const pts = DATA.fwt[mn]?.["total"] || [];
  if (pts.length) {
    Plotly.react("mdl-fwt",
      [{
        type: "scatter", mode: "lines+markers",
        x: pts.map(p => p.threshold),
        y: pts.map(p => p.pct),
        line: { color: PALETTE.orange, width: 2.5 },
        marker: { color: PALETTE.orange, size: 7 },
        fill: "tozeroy",
        fillcolor: "rgba(255,107,53,0.12)",
        hovertemplate: "ε=%{x}<br>%{y:.2f}%<extra></extra>",
      }],
      plotlyLayout({
        height: 320,
        xaxis: { title: "ε (eV/Å)", range: [0, 1.05], color: PALETTE.text, gridcolor: PALETTE.grid },
        yaxis: { title: "FwT (%)",  range: [0, 101],  color: PALETTE.text, gridcolor: PALETTE.grid },
        showlegend: false,
        margin: { l: 60, r: 30, t: 20, b: 50 },
      }),
      PLOTLY_CFG);
  }

  // per-element top 25 by sample size
  const elemBlock = DATA.elements?.[mn]?.["total"] || {};
  const rows = Object.entries(elemBlock).map(([sym, byType]) => {
    const slot = byType.normal || {};
    return { sym, mae: slot.E_form_MAE, n: slot.N_samples || 0 };
  }).filter(r => r.mae != null && isFinite(r.mae));
  rows.sort((a, b) => b.n - a.n);
  const top = rows.slice(0, 25);

  if (top.length) {
    const order = top.map((_, i) => i).sort((a, b) => top[a].mae - top[b].mae);
    const sorted = order.map(i => top[i]);
    Plotly.react("mdl-elements",
      [{
        type: "bar", orientation: "h",
        x: sorted.map(r => r.mae),
        y: sorted.map(r => r.sym),
        marker: { color: sorted.map((_, k) => modelColor(k, sorted.length)) },
        text: sorted.map(r => `${fmt(r.mae, 3)}  (n=${fmtInt(r.n)})`),
        textposition: "outside",
        textfont: { color: PALETTE.subtext, size: 10 },
        hovertemplate: "<b>%{y}</b><br>MAE (E_form): %{x:.4f} eV/atom<extra></extra>",
        cliponaxis: false,
      }],
      plotlyLayout({
        height: Math.max(640, 24 * sorted.length + 80),
        margin: { l: 50, r: 110, t: 10, b: 50 },
        yaxis: {
          autorange: "reversed", color: PALETTE.text,
          tickmode: "array",
          tickvals: sorted.map(r => r.sym),
          ticktext: sorted.map(r => r.sym),
          tickfont: { color: PALETTE.text, size: 11 },
          automargin: true,
        },
        xaxis: { title: "MAE (E_form, eV/atom)", color: PALETTE.text, gridcolor: PALETTE.grid },
        showlegend: false,
      }),
      PLOTLY_CFG);
  }
}

// ─── 7. Sidebar nav active state ───────────────────────────────────────────
function initNav() {
  const links = document.querySelectorAll(".nav a");
  const sections = [...links].map(a => document.querySelector(a.getAttribute("href")));
  function update() {
    let active = 0;
    const y = window.scrollY + 120;
    sections.forEach((s, i) => { if (s && s.offsetTop <= y) active = i; });
    links.forEach((a, i) => a.classList.toggle("active", i === active));
  }
  window.addEventListener("scroll", update, { passive: true });
  update();
  links.forEach(a => a.addEventListener("click", e => {
    e.preventDefault();
    document.querySelector(a.getAttribute("href")).scrollIntoView({ behavior: "smooth", block: "start" });
  }));
}
