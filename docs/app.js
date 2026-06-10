/* ClusPot — interactive site (multi-system: Home / Mono / Bi / HEA) */

/* Theme B — 미소디/CCEL brand palette on a steel-navy sci-fi ground.
   Surfaces keep green slightly above red to avoid a purplish indigo cast.
   Keep these in sync with the :root tokens in styles.css. */
const PALETTE = {
  bg:       "#060d18",
  panel:    "#0c1426",
  card:     "#142036",
  cardHi:   "#1d2c48",
  orange:   "#FA901E",
  navy:     "#3d4f7a",
  text:     "#ECEEF8",
  subtext:  "#93a0bc",
  grid:     "#16213c",
  border:   "#283a5a",
};
/* best→worst model gradient: CCEL orange → SNU gold → beige → silver →
   gray → brightened SNU blue (visible on the dark ground). */
const GRADIENT = ["#FA901E", "#C5A86F", "#DCDAB2", "#B5B6B6", "#888888", "#3d4f7a"];
/* heatmap low→high (navy→orange) using the same brand anchors */
const HEAT     = ["#3d4f7a", "#888888", "#B5B6B6", "#DCDAB2", "#C5A86F", "#FA901E"];
const SYSTEM_COLORS = { mono: "#FA901E", bi: "#B5B6B6", hea: "#C5A86F" };

let DATA = null;
let METRIC_BY_KEY = {};

const STATE = {
  page: pageFromHash(),
  mono: {
    lb_dataset: "total",
    cmp_metric: "E_form_MAE", cmp_dataset: "total",
    par_metric: "E_form_MAE", par_xmetric: "Time_med", par_dataset: "total",
    fwt_dataset: "total",
    pt_metric: "E_form_MAE", pt_model: null, pt_dataset: "total",
    pt_type: "normal", pt_selected: null,
    mdl: null,
    lb_sort: { key: "AFwT", asc: false },
  },
  bi: {
    lb_dataset: "total",
    cmp_metric: "E_form_MAE", cmp_dataset: "total",
    par_metric: "E_form_MAE", par_xmetric: "Time_med", par_dataset: "total",
    fwt_dataset: "total",
    pt_metric: "E_form_MAE", pt_model: null, pt_dataset: "bimetallic",
    pt_a: null, pt_b: null,
    mdl: null,
    lb_sort: { key: "AFwT", asc: false },
  },
  home: { lb_sort: { key: "AFwT", asc: false } },
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

  const mono = DATA.systems.mono;
  const bi   = DATA.systems.bi;
  // Mono heatmap leads the page — open it on the most accurate model
  // (lowest E_form MAE) so the "even the best model struggles on the
  // refractory TMs" story is visible on first load, not alphabetical Allegro.
  if (mono) {
    STATE.mono.mdl = mono.models[0];
    STATE.mono.pt_model = bestModelByMetric(mono, "E_form_MAE", true) || mono.models[0];
  }
  if (bi)   STATE.bi.pt_model    = STATE.bi.mdl = bi.models[0];

  initMetaBar();
  initRouter();

  initHomePage();
  if (mono) initSystemPage("mono", mono);
  if (bi)   initSystemPage("bi",   bi);

  showPage(STATE.page);
}

// ════════════════════════════════════════════════════════════════════════════
//  Helpers
// ════════════════════════════════════════════════════════════════════════════
function metricLabel(m, withUnit = true) {
  if (!m) return "";
  const t = m.target;
  const u = m.unit;
  if (t) return withUnit && u ? `${m.label} (${t}, ${u})` : `${m.label} (${t})`;
  return withUnit && u ? `${m.label} (${u})` : m.label;
}
function fmt(v, d = 4) {
  if (v == null || !isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a !== 0 && (a < 0.001 || a >= 100000)) return v.toExponential(2);
  return v.toFixed(d);
}
function fmtSmall(v) {
  if (v == null) return "";
  const a = Math.abs(v);
  if (a >= 100) return v.toFixed(0);
  if (a >= 10)  return v.toFixed(1);
  if (a >= 1)   return v.toFixed(2);
  return v.toFixed(3);
}
function fmtInt(v) {
  if (v == null || !isFinite(v)) return "—";
  return Math.round(v).toLocaleString();
}
function rankIdx(values, lowerBetter) {
  const idx = values.map((v, i) => [i, v]).filter(([, v]) => v != null && isFinite(v));
  idx.sort((a, b) => lowerBetter ? a[1] - b[1] : b[1] - a[1]);
  return idx.map(([i]) => i);
}
// Best model in a system by a summary metric on the "total" dataset.
function bestModelByMetric(sys, key, lowerBetter = true) {
  let best = null, bestV = null;
  (sys.models || []).forEach(m => {
    const v = sys.summary?.[m]?.["total"]?.[key];
    if (v == null || !isFinite(v)) return;
    if (bestV == null || (lowerBetter ? v < bestV : v > bestV)) { bestV = v; best = m; }
  });
  return best;
}
function modelColor(rank, total) {
  if (total <= 1) return GRADIENT[0];
  return interpStops(GRADIENT, rank / (total - 1));
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
  const r  = Math.round(ah[0] + (bh[0] - ah[0]) * f);
  const g  = Math.round(ah[1] + (bh[1] - ah[1]) * f);
  const bl = Math.round(ah[2] + (bh[2] - ah[2]) * f);
  return `rgb(${r}, ${g}, ${bl})`;
}
function parseHex(s) {
  if (s.startsWith("rgb")) return s.match(/\d+/g).slice(0, 3).map(Number);
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
    legend: { font: { color: PALETTE.text, size: 11 }, bgcolor: "rgba(20,32,54,0.85)", bordercolor: PALETTE.border, borderwidth: 1 },
    hoverlabel: { bgcolor: PALETTE.cardHi, bordercolor: PALETTE.orange, font: { color: PALETTE.text, family: "JetBrains Mono, monospace", size: 12 } },
  }, extra);
}
// Capture a whole <section> (title + controls + chart) as a PNG so the
// exported image matches what the user sees, instead of just the bare
// Plotly canvas. Used both as the modebar camera-button click handler and
// from standalone download buttons (e.g. on the periodic heatmap, which
// has no Plotly modebar of its own).
function captureSectionAsPng(section, fallbackPlotly) {
  if (!section) return;
  const titleEl = section.querySelector("h2");
  const filename = (titleEl?.textContent.trim().toLowerCase()
    .replace(/[()]/g, "")
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9_-]/g, "") || "cluspot") + ".png";

  if (typeof html2canvas !== "function") {
    if (fallbackPlotly) Plotly.downloadImage(fallbackPlotly, { format: "png", filename, width: 1600, height: 900 });
    return;
  }

  // Hide transient hover-only UI (Plotly modebars, our floating camera
  // button) so they don't end up in the captured image.
  const hiders = section.querySelectorAll(".modebar-container, .modebar, .dl-camera, .lb-sticky-scroll");
  const prevVis = [];
  hiders.forEach(b => { prevVis.push(b.style.visibility); b.style.visibility = "hidden"; });

  // Tables inside .lb-wrap scroll horizontally on screen. For the capture
  // we want the *whole* table — temporarily release the scroll, expand
  // the wrap and the enclosing panel/section to the table's natural width,
  // snapshot, then restore.
  const restore = [];
  const scrollers = section.querySelectorAll(".lb-wrap");
  let needsExpand = false;
  scrollers.forEach(s => {
    if (s.scrollWidth > s.clientWidth + 1) {
      needsExpand = true;
      restore.push({ el: s, prop: "overflowX", val: s.style.overflowX });
      restore.push({ el: s, prop: "width",     val: s.style.width });
      s.style.overflowX = "visible";
      s.style.width = s.scrollWidth + "px";
    }
  });
  if (needsExpand) {
    [section, section.querySelector(".chart-panel"), section.querySelector(".panel")]
      .filter(Boolean)
      .forEach(el => {
        restore.push({ el, prop: "maxWidth", val: el.style.maxWidth });
        restore.push({ el, prop: "width",    val: el.style.width });
        el.style.maxWidth = "none";
        el.style.width = "max-content";
      });
  }

  html2canvas(section, {
    backgroundColor: "#0c1426",
    scale: 2,
    logging: false,
    useCORS: true,
    windowWidth: Math.max(document.documentElement.scrollWidth, section.scrollWidth + 80),
  }).then(canvas => {
    const link = document.createElement("a");
    link.download = filename;
    link.href = canvas.toDataURL("image/png");
    link.click();
  }).catch(err => {
    console.warn("html2canvas capture failed", err);
    if (fallbackPlotly) Plotly.downloadImage(fallbackPlotly, { format: "png", filename, width: 1600, height: 900 });
  }).finally(() => {
    hiders.forEach((b, i) => { b.style.visibility = prevVis[i] || ""; });
    restore.forEach(r => { r.el.style[r.prop] = r.val; });
  });
}

function downloadSectionAsPng(gd) {
  const section = gd.closest("section[id]") || gd.closest(".chart-panel") || gd.closest(".panel") || gd.parentElement;
  captureSectionAsPng(section, gd);
}

// Standalone download buttons (used on sections without a Plotly modebar,
// e.g. the periodic heatmap which is plain HTML/CSS grid).
document.addEventListener("click", e => {
  const btn = e.target.closest("[data-dl-section]");
  if (!btn) return;
  e.preventDefault();
  captureSectionAsPng(btn.closest("section[id]"));
});

// Key-findings cards jump to the supporting view: a page name navigates
// (hash router scrolls to top → that page's lead chart), a "#id" scrolls to
// that section on the current page.
function jumpTo(dest) {
  if (!dest) return;
  if (dest.startsWith("#")) {
    const el = document.querySelector(dest);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    location.hash = dest;
  }
}
document.addEventListener("click", e => {
  const card = e.target.closest(".finding-card[data-jump]");
  if (card) jumpTo(card.dataset.jump);
});
document.addEventListener("keydown", e => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const card = e.target.closest?.(".finding-card[data-jump]");
  if (card) { e.preventDefault(); jumpTo(card.dataset.jump); }
});

const PLOTLY_CFG = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "zoomIn2d", "zoomOut2d", "toImage"],
  modeBarButtonsToAdd: [{
    name: "Download plot as PNG (with title & controls)",
    icon: Plotly.Icons.camera,
    click: downloadSectionAsPng,
  }],
};

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
function metricValsFor(sysData, metricKey, dataset) {
  return sysData.models.map(m => sysData.summary[m]?.[dataset]?.[metricKey] ?? null);
}

// ════════════════════════════════════════════════════════════════════════════
//  Routing
// ════════════════════════════════════════════════════════════════════════════
function pageFromHash() {
  const h = (location.hash || "#home").replace("#", "").split("/")[0];
  return ["home", "mono", "bi", "hea", "reference"].includes(h) ? h : "home";
}
function initRouter() {
  document.querySelectorAll(".nav a").forEach(a => {
    a.addEventListener("click", e => {
      e.preventDefault();
      const target = a.dataset.page;
      if (target === STATE.page) return;
      location.hash = target;
    });
  });
  window.addEventListener("hashchange", () => {
    const p = pageFromHash();
    if (p !== STATE.page) showPage(p);
  });
}
function showPage(name) {
  STATE.page = name;
  document.querySelectorAll(".page").forEach(p => p.classList.toggle("page--active", p.id === `page-${name}`));
  document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("active", a.dataset.page === name));
  // Plotly needs a resize after the container becomes visible
  setTimeout(() => {
    document.querySelectorAll(`#page-${name} .plot`).forEach(el => {
      if (el && el._fullData) Plotly.Plots.resize(el);
    });
    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  }, 0);
}

function initMetaBar() {
  const dt = DATA.meta.generated_at?.replace("T", " ").replace(/\+.*$/, "").slice(0, 16) || "—";
  const right = document.querySelector("#meta-right");
  const m = DATA.systems.mono;
  const b = DATA.systems.bi;
  const totalModels = (m?.n_models || 0) + (b?.n_models || 0);
  if (right) {
    right.innerHTML =
      `<b>Mono</b> ${m?.n_models ?? 0} models · <b>Bi</b> ${b?.n_models ?? 0} models<br>` +
      `${dt} UTC`;
  }
  const foot = document.querySelector("#foot-right");
  if (foot) foot.textContent = `data.json · ${DATA.meta.generated_at?.slice(0, 10) || ""}`;
}

// ════════════════════════════════════════════════════════════════════════════
//  HOME PAGE
// ════════════════════════════════════════════════════════════════════════════
function initHomePage() {
  const m = DATA.systems.mono;
  const b = DATA.systems.bi;

  // hero stats — combined view (best AFwT computed from aggregated global rows)
  const monoEl  = m?.active_elements?.length || 0;
  const biPairs = b?.active_pairs?.length || 0;
  const allModels = new Set([...(m?.models || []), ...(b?.models || [])]);

  let bestAFwT = 0;
  allModels.forEach(mn => {
    const agg = aggregateGlobalRow(mn);
    if (agg && agg.AFwT != null && isFinite(agg.AFwT) && agg.AFwT > bestAFwT) bestAFwT = agg.AFwT;
  });

  const stats = [
    { v: allModels.size,             k: "MLIPs benchmarked" },
    { v: monoEl,                     k: "Mono elements" },
    { v: biPairs,                    k: "Bi pairs" },
    { v: `${bestAFwT.toFixed(1)}%`,  k: "Best AFwT (aggregated)" },
  ];
  document.querySelector("#hero-stats").innerHTML =
    stats.map(s => `<div class="stat"><div class="v">${s.v}</div><div class="k">${s.k}</div></div>`).join("");

  // home-mono badge update
  if (m) document.getElementById("home-mono-badge").textContent = `●  ${m.n_models} models · ${monoEl} elements`;
  if (b) document.getElementById("home-bi-badge").textContent   = `●  ${b.n_models} models · ${biPairs} pairs`;

  renderHomeLeaderboard();
}

// Metrics shown in the global leaderboard (Home page).
const HOME_LB_KEYS = ["AFwT", "E_form_MAE", "E_form_RMSE", "Force_MAE", "Anomaly_pct", "Time_med"];

// Metric weighting policy when aggregating across systems.
//   wNormal: weight by N_normal           — use for accuracy on the "normal" subset
//   wAll:    weight by N_normal + N_anomaly — use for rates / time spanning all samples
const METRIC_WEIGHT = {
  E_form_MAE: "wNormal", E_form_RMSE: "wNormal",
  E_form_R2: "wNormal", E_form_Pearson: "wNormal", E_form_Spearman: "wNormal",
  Force_MAE: "wNormal", Force_RMSE: "wNormal",
  Force_R2: "wNormal", Force_Pearson: "wNormal", Force_Spearman: "wNormal", Force_cosine: "wNormal",
  AFwT: "wAll", Anomaly_pct: "wAll",
  Time_med: "wAll", Time_mean: "wAll",
};
// RMSE-style metrics combine via weighted root-mean-square instead of weighted mean.
const RMS_METRICS = new Set(["E_form_RMSE", "Force_RMSE"]);

function aggregateGlobalRow(modelName) {
  const rows = [];
  ["mono", "bi"].forEach(sk => {
    const sys = DATA.systems[sk];
    if (!sys) return;
    const s = sys.summary[modelName]?.["total"];
    if (!s) return;
    rows.push({ system: sk, label: sys.label, ...s });
  });
  if (!rows.length) return null;

  const wNormal = rows.map(r => r.N_normal || 0);
  const wAll    = rows.map(r => (r.N_normal || 0) + (r.N_anomaly || 0));
  const weights = { wNormal, wAll };

  const wmean = (key, w) => {
    let num = 0, den = 0;
    rows.forEach((r, i) => {
      const v = r[key];
      if (v == null || !isFinite(v) || w[i] === 0) return;
      num += v * w[i]; den += w[i];
    });
    return den > 0 ? num / den : null;
  };
  const wrms = (key, w) => {
    let num = 0, den = 0;
    rows.forEach((r, i) => {
      const v = r[key];
      if (v == null || !isFinite(v) || w[i] === 0) return;
      num += v * v * w[i]; den += w[i];
    });
    return den > 0 ? Math.sqrt(num / den) : null;
  };

  const out = {
    systems:   rows.map(r => r.system),
    sysLabels: rows.map(r => r.label),
    N_normal:  rows.reduce((a, r) => a + (r.N_normal  || 0), 0),
    N_anomaly: rows.reduce((a, r) => a + (r.N_anomaly || 0), 0),
  };
  Object.keys(METRIC_WEIGHT).forEach(k => {
    const w = weights[METRIC_WEIGHT[k]];
    out[k] = RMS_METRICS.has(k) ? wrms(k, w) : wmean(k, w);
  });
  return out;
}

function renderHomeLeaderboard() {
  const tbl = document.querySelector("#home-lb-table");
  const sortKey = STATE.home.lb_sort.key;
  const sortAsc = STATE.home.lb_sort.asc;
  const sortMeta = METRIC_BY_KEY[sortKey];

  // unique model list across all systems
  const modelSet = new Set();
  ["mono", "bi"].forEach(sk => {
    const sys = DATA.systems[sk];
    if (!sys) return;
    sys.models.forEach(m => modelSet.add(m));
  });

  const rows = Array.from(modelSet)
    .map(m => {
      const agg = aggregateGlobalRow(m);
      return agg ? { model: m, ...agg } : null;
    })
    .filter(Boolean);

  // header — # · Model · metrics · N
  let thead = `<tr>
    <th data-k="rank">#</th>
    <th class="sticky-l" data-k="model">Model</th>`;
  HOME_LB_KEYS.forEach(k => {
    const m = METRIC_BY_KEY[k];
    const arrow = sortKey === k ? `<span class="arrow">${sortAsc ? "▲" : "▼"}</span>` : "";
    thead += `<th data-k="${k}">${metricLabel(m)}${arrow}</th>`;
  });
  thead += `<th data-k="N">N samples</th>`;
  thead += `</tr>`;
  tbl.querySelector("thead").innerHTML = thead;

  // best per metric (across all aggregated rows)
  const bestIdx = {};
  HOME_LB_KEYS.forEach(k => {
    const m = METRIC_BY_KEY[k];
    const ranked = rows.map((r, i) => [i, r[k]]).filter(([, v]) => v != null);
    if (ranked.length) {
      ranked.sort((a, b) => m.lower_better ? a[1] - b[1] : b[1] - a[1]);
      bestIdx[k] = ranked[0][0];
    }
  });

  // sort rows by chosen metric
  const order = rows.map((r, i) => [i, r[sortKey]])
    .sort((a, b) => {
      if (a[1] == null) return 1;
      if (b[1] == null) return -1;
      const cmp = a[1] - b[1];
      const wantAsc = sortAsc !== undefined ? sortAsc : sortMeta?.lower_better;
      return wantAsc ? cmp : -cmp;
    })
    .map(([i]) => i);

  let body = "";
  order.forEach((i, rk) => {
    const r = rows[i];
    let row = `<tr>
      <td class="rank">${rk + 1}</td>
      <td class="name">${r.model}</td>`;
    HOME_LB_KEYS.forEach(k => {
      const v = r[k];
      const cls = bestIdx[k] === i ? "best" : "";
      row += `<td class="${cls}">${fmt(v, 4)}</td>`;
    });
    row += `<td class="n-cell">${fmtInt((r.N_normal || 0) + (r.N_anomaly || 0))}</td>`;
    row += `</tr>`;
    body += row;
  });
  tbl.querySelector("tbody").innerHTML = body;

  // header click → sort (skip non-metric columns)
  tbl.querySelectorAll("thead th").forEach(th => {
    const k = th.dataset.k;
    if (!METRIC_BY_KEY[k]) return;
    th.addEventListener("click", () => {
      if (STATE.home.lb_sort.key === k) STATE.home.lb_sort.asc = !STATE.home.lb_sort.asc;
      else STATE.home.lb_sort = { key: k, asc: METRIC_BY_KEY[k]?.lower_better ?? false };
      renderHomeLeaderboard();
    }, { once: true });
  });

  syncStickyScroll();
}

// Floating horizontal scrollbar for the Home leaderboard. A proxy bar
// (.lb-sticky-scroll) sticks to the viewport bottom while the section is on
// screen; we mirror its scroll position to/from the real .lb-wrap so you can
// pan the wide table left/right without scrolling down to its bottom edge.
let _stickyScrollWired = false;
function syncStickyScroll() {
  const wrap = document.querySelector("#home-leaderboard .lb-wrap");
  const bar = document.querySelector("#home-leaderboard .lb-sticky-scroll");
  if (!wrap || !bar) return;
  const track = bar.querySelector(".lb-sticky-track");

  const refresh = () => {
    const overflow = wrap.scrollWidth - wrap.clientWidth > 1;
    bar.style.display = overflow ? "block" : "none";
    if (!overflow) return;
    bar.style.width = wrap.clientWidth + "px";
    track.style.width = wrap.scrollWidth + "px";
    bar.scrollLeft = wrap.scrollLeft;
  };

  if (!_stickyScrollWired) {
    let lock = false;
    bar.addEventListener("scroll", () => {
      if (lock) return;
      lock = true; wrap.scrollLeft = bar.scrollLeft; lock = false;
    });
    wrap.addEventListener("scroll", () => {
      if (lock) return;
      lock = true; bar.scrollLeft = wrap.scrollLeft; lock = false;
    });
    window.addEventListener("resize", refresh);
    _stickyScrollWired = true;
  }
  refresh();
}

// ════════════════════════════════════════════════════════════════════════════
//  Per-System page initializer (mono + bi share most sub-sections)
// ════════════════════════════════════════════════════════════════════════════
function initSystemPage(prefix, sys) {
  initCompare(prefix, sys);
  initPareto(prefix, sys);
  initFwt(prefix, sys);
  if (sys.kind === "single") {
    initPeriodic(prefix, sys);
  } else if (sys.kind === "pair") {
    initBiPeriodic(prefix, sys);
  }
}

// ─── 1. Per-system leaderboard (bar chart, metric-selectable) ──────────────
function initCompare(prefix, sys) {
  const sel = document.querySelector(`#${prefix}-cmp-metric`);
  fillMetricSelect(sel, m => m.group !== "efficiency" || m.key === "Time_med");
  sel.value = STATE[prefix].cmp_metric;
  sel.addEventListener("change", () => { STATE[prefix].cmp_metric = sel.value; renderCompare(prefix, sys); });

  makeSeg(document.querySelector(`#${prefix}-cmp-ds-seg`),
    sys.datasets.map(d => ({ value: d, label: d })),
    STATE[prefix].cmp_dataset, v => { STATE[prefix].cmp_dataset = v; renderCompare(prefix, sys); });

  renderCompare(prefix, sys);
}
function renderCompare(prefix, sys) {
  const m = METRIC_BY_KEY[STATE[prefix].cmp_metric];
  const ds = STATE[prefix].cmp_dataset;
  const vals = metricValsFor(sys, m.key, ds);
  const order = rankIdx(vals, m.lower_better);
  const names   = order.map(i => sys.models[i]);
  const series  = order.map(i => vals[i]);
  const samples = order.map(i => {
    const s = sys.summary[sys.models[i]]?.[ds];
    return (s?.N_normal || 0) + (s?.N_anomaly || 0);
  });
  const colors = order.map((_, k) => modelColor(k, order.length));

  const trace = {
    type: "bar", orientation: "h",
    x: series, y: names,
    marker: { color: colors, line: { color: PALETTE.border, width: 0.5 } },
    text: series.map((v, k) => `${fmt(v, 4)}  ·  n=${fmtInt(samples[k])}`),
    textposition: "outside",
    textfont: { color: PALETTE.text, family: "JetBrains Mono", size: 11 },
    customdata: samples,
    hovertemplate: "<b>%{y}</b><br>" + metricLabel(m) + ": %{x:.4f}<br>N samples: %{customdata:,}<extra></extra>",
    cliponaxis: false,
  };
  const layout = plotlyLayout({
    height: Math.max(380, 30 * names.length + 120),
    margin: { l: 200, r: 140, t: 30, b: 60 },
    yaxis: { autorange: "reversed", gridcolor: PALETTE.bg, color: PALETTE.text, tickfont: { color: PALETTE.text, size: 11 } },
    xaxis: { title: metricLabel(m), gridcolor: PALETTE.grid, zerolinecolor: PALETTE.border, color: PALETTE.subtext },
    showlegend: false,
  });
  Plotly.react(`${prefix}-cmp-plot`, [trace], layout, PLOTLY_CFG);
}

// ─── 3. Pareto (per-system) ────────────────────────────────────────────────
function initPareto(prefix, sys) {
  const sel = document.querySelector(`#${prefix}-par-metric`);
  fillMetricSelect(sel, m => m.group !== "efficiency");
  sel.value = STATE[prefix].par_metric;
  sel.addEventListener("change", () => { STATE[prefix].par_metric = sel.value; renderPareto(prefix, sys); });

  document.querySelector(`#${prefix}-par-xmetric`).addEventListener("change", e => {
    STATE[prefix].par_xmetric = e.target.value; renderPareto(prefix, sys);
  });
  makeSeg(document.querySelector(`#${prefix}-par-ds-seg`),
    sys.datasets.map(d => ({ value: d, label: d })),
    STATE[prefix].par_dataset, v => { STATE[prefix].par_dataset = v; renderPareto(prefix, sys); });
  renderPareto(prefix, sys);
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
function renderPareto(prefix, sys) {
  const m = METRIC_BY_KEY[STATE[prefix].par_metric];
  const xKey = STATE[prefix].par_xmetric;
  const ds = STATE[prefix].par_dataset;
  const xs = metricValsFor(sys, xKey, ds);
  const ys = metricValsFor(sys, m.key, ds);

  const valid = sys.models.map((_, i) => xs[i] != null && ys[i] != null);
  const mask  = paretoMask(xs, ys, m.lower_better);

  const tracePareto = {
    type: "scatter", mode: "markers", name: "Pareto-optimal",
    x: sys.models.map((_, i) => mask[i] ? xs[i] : null),
    y: sys.models.map((_, i) => mask[i] ? ys[i] : null),
    text: sys.models,
    marker: { color: PALETTE.orange, size: 16, line: { color: "white", width: 1.5 } },
    hovertemplate: "<b>%{text}</b><br>x=%{x:.4f}<br>y=%{y:.4f}<extra>★ Pareto</extra>",
  };
  const traceOther = {
    type: "scatter", mode: "markers", name: "Dominated",
    x: sys.models.map((_, i) => (!mask[i] && valid[i]) ? xs[i] : null),
    y: sys.models.map((_, i) => (!mask[i] && valid[i]) ? ys[i] : null),
    text: sys.models,
    marker: { color: "#6a6fb0", size: 11, line: { color: PALETTE.border, width: 1 } },
    hovertemplate: "<b>%{text}</b><br>x=%{x:.4f}<br>y=%{y:.4f}<extra></extra>",
  };
  const front = sys.models.map((_, i) => mask[i] ? [xs[i], ys[i]] : null).filter(Boolean).sort((a, b) => a[0] - b[0]);
  const traceLine = {
    type: "scatter", mode: "lines", name: "Frontier",
    x: front.map(p => p[0]), y: front.map(p => p[1]),
    line: { color: PALETTE.orange, width: 2, dash: "dash" },
    hoverinfo: "skip", showlegend: false,
  };
  const traceLabels = {
    type: "scatter", mode: "text",
    x: sys.models.map((_, i) => valid[i] ? xs[i] : null),
    y: sys.models.map((_, i) => valid[i] ? ys[i] : null),
    text: sys.models.map((n, i) => valid[i] ? n : ""),
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
  Plotly.react(`${prefix}-par-plot`, [traceLine, traceOther, tracePareto, traceLabels], layout, PLOTLY_CFG);
}

// ─── 4. FwT (per-system) ───────────────────────────────────────────────────
function initFwt(prefix, sys) {
  makeSeg(document.querySelector(`#${prefix}-fwt-ds-seg`),
    sys.datasets.map(d => ({ value: d, label: d })),
    STATE[prefix].fwt_dataset, v => { STATE[prefix].fwt_dataset = v; renderFwt(prefix, sys); });
  renderFwt(prefix, sys);
}
function renderFwt(prefix, sys) {
  const ds = STATE[prefix].fwt_dataset;
  const afwt = metricValsFor(sys, "AFwT", ds);
  const order = rankIdx(afwt, false);
  const traces = [];
  order.forEach((i, k) => {
    const m = sys.models[i];
    const pts = sys.fwt[m]?.[ds] || [];
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
    legend: { x: 1.02, y: 1, font: { size: 11, color: PALETTE.text }, bgcolor: "rgba(20,32,54,0.9)", bordercolor: PALETTE.border, borderwidth: 1 },
    margin: { l: 70, r: 280, t: 30, b: 60 },
  });
  Plotly.react(`${prefix}-fwt-plot`, traces, layout, PLOTLY_CFG);
}

// ─── 5a. Periodic table — MONO (single click) ──────────────────────────────
function initPeriodic(prefix, sys) {
  const grid = document.querySelector(`#${prefix}-pt-grid`);
  grid.innerHTML = "";
  ELEMENTS.forEach(el => {
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.style.gridRow = el.row;
    cell.style.gridColumn = el.col;
    cell.dataset.sym = el.sym;
    cell.innerHTML = `<span class="z">${el.z}</span><span class="sym">${el.sym}</span><span class="v"></span>`;
    cell.addEventListener("mouseenter", () => onMonoCellHover(prefix, sys, cell, el));
    cell.addEventListener("mouseleave", hideTip);
    cell.addEventListener("mousemove", moveTip);
    cell.addEventListener("click", () => onMonoCellClick(prefix, sys, el));
    grid.appendChild(cell);
  });

  const sel = document.querySelector(`#${prefix}-pt-metric`);
  fillMetricSelect(sel, m => ["energy", "force"].includes(m.group));
  sel.value = STATE[prefix].pt_metric;
  sel.addEventListener("change", () => { STATE[prefix].pt_metric = sel.value; renderMonoPeriodic(prefix, sys); });

  const mSel = document.querySelector(`#${prefix}-pt-model`);
  mSel.innerHTML = sys.models.map(m => `<option>${m}</option>`).join("");
  mSel.value = STATE[prefix].pt_model;
  mSel.addEventListener("change", () => { STATE[prefix].pt_model = mSel.value; renderMonoPeriodic(prefix, sys); });

  makeSeg(document.querySelector(`#${prefix}-pt-ds-seg`),
    sys.datasets.map(d => ({ value: d, label: d })),
    STATE[prefix].pt_dataset, v => { STATE[prefix].pt_dataset = v; renderMonoPeriodic(prefix, sys); });

  document.querySelectorAll(`#${prefix}-pt-type-seg button`).forEach(b => {
    b.addEventListener("click", () => {
      document.querySelectorAll(`#${prefix}-pt-type-seg button`).forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      STATE[prefix].pt_type = b.dataset.v;
      renderMonoPeriodic(prefix, sys);
    });
  });

  renderMonoPeriodic(prefix, sys);
}
function elementValue(sys, model, dataset, type, sym, metricKey) {
  return sys.elements?.[model]?.[dataset]?.[sym]?.[type]?.[metricKey] ?? null;
}
function renderMonoPeriodic(prefix, sys) {
  const m = METRIC_BY_KEY[STATE[prefix].pt_metric];
  const model = STATE[prefix].pt_model;
  const ds = STATE[prefix].pt_dataset;
  const type = STATE[prefix].pt_type;
  const stops = m.lower_better ? [...HEAT].reverse() : HEAT;

  const vals = {};
  ELEMENTS.forEach(el => {
    const v = elementValue(sys, model, ds, type, el.sym, m.key);
    if (v != null && isFinite(v)) vals[el.sym] = v;
  });
  const arr = Object.values(vals);
  const vmin = arr.length ? Math.min(...arr) : 0;
  const vmax = arr.length ? Math.max(...arr) : 1;
  const span = vmax - vmin || 1e-9;

  document.querySelectorAll(`#${prefix}-pt-grid .cell`).forEach(cell => {
    const sym = cell.dataset.sym;
    const v = vals[sym];
    cell.classList.toggle("active", v != null);
    cell.classList.toggle("selected", sym === STATE[prefix].pt_selected);
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
      cell.querySelector(".z").style.color = lum > 0.55 ? "rgba(0,0,0,0.55)" : "rgba(255,255,255,0.6)";
      vSpan.textContent = fmtSmall(v);
      vSpan.style.color = fg;
    }
  });

  document.querySelector(`#${prefix}-pt-min`).textContent = arr.length ? fmt(vmin, 3) : "—";
  document.querySelector(`#${prefix}-pt-max`).textContent = arr.length ? fmt(vmax, 3) : "—";
  const legend = document.querySelector(`#${prefix}-pt-legend`);
  legend.classList.toggle("reverse", m.lower_better);

  if (STATE[prefix].pt_selected) {
    renderMonoPeriodicSide(prefix, sys, STATE[prefix].pt_selected);
  } else {
    renderModelSummarySide(`#${prefix}-pt-side`, sys, STATE[prefix].pt_model, STATE[prefix].pt_dataset);
  }
}
function onMonoCellHover(prefix, sys, cell, el) {
  const m = METRIC_BY_KEY[STATE[prefix].pt_metric];
  const v = elementValue(sys, STATE[prefix].pt_model, STATE[prefix].pt_dataset, STATE[prefix].pt_type, el.sym, m.key);
  const slot = sys.elements?.[STATE[prefix].pt_model]?.[STATE[prefix].pt_dataset]?.[el.sym]?.[STATE[prefix].pt_type];
  const n = slot?.N_samples;
  TIP.innerHTML = `<b style="color:${PALETTE.orange}">${el.sym}</b> ${el.name}<br>${metricLabel(m)}: ${v != null ? fmt(v, 4) : "no data"}${n != null ? `<br>N=${fmtInt(n)}` : ""}`;
  TIP.classList.add("show");
}
function onMonoCellClick(prefix, sys, el) {
  if (!el.sym) return;
  const hasAny = sys.models.some(m =>
    sys.elements?.[m]?.[STATE[prefix].pt_dataset]?.[el.sym]?.[STATE[prefix].pt_type] != null
  );
  if (!hasAny) return;
  STATE[prefix].pt_selected = el.sym;
  renderMonoPeriodic(prefix, sys);
  renderMonoPeriodicSide(prefix, sys, el.sym);
}
function renderMonoPeriodicSide(prefix, sys, sym) {
  const el = ELEMENTS.find(e => e.sym === sym);
  if (!el) return;
  const m = METRIC_BY_KEY[STATE[prefix].pt_metric];
  const ds = STATE[prefix].pt_dataset;
  const type = STATE[prefix].pt_type;

  const rows = sys.models.map(mn => {
    const slot = sys.elements?.[mn]?.[ds]?.[sym]?.[type];
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
    html += `<div class="breakdown"><h4>Models · sorted best→worst</h4>`;
    valid.forEach((r, k) => {
      const pct = max > 0 ? Math.abs(r.v) / max * 100 : 0;
      const color = modelColor(k, valid.length);
      html += `
        <div class="row">
          <span class="name" title="${r.model}">${k + 1}. ${r.model}</span>
          <div class="bar"><span style="width:${pct.toFixed(1)}%; background: linear-gradient(90deg, ${color}, ${color} 60%, transparent);"></span></div>
          <span class="v">${fmt(r.v, 4)}</span>
        </div>`;
    });
    html += `</div>`;
  }
  document.querySelector(`#${prefix}-pt-side`).innerHTML = html;
}

// ─── Bi-system pair lookups (used by the two-click periodic table) ────────
function pairValueAcross(sys, dataset, pairKey, metricKey, type = "normal") {
  return sys.models.map(m => {
    const slot = sys.pairs?.[m]?.[dataset]?.[pairKey]?.[type];
    return { model: m, v: slot?.[metricKey] ?? null, n: slot?.N_samples ?? null };
  });
}
function pairValueForModel(sys, model, dataset, pairKey, metricKey, type = "normal") {
  return sys.pairs?.[model]?.[dataset]?.[pairKey]?.[type]?.[metricKey] ?? null;
}

// ─── Two-click periodic table — BI ─────────────────────────────────────────
function initBiPeriodic(prefix, sys) {
  const grid = document.querySelector(`#${prefix}-pt-grid`);
  grid.innerHTML = "";
  ELEMENTS.forEach(el => {
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.style.gridRow = el.row;
    cell.style.gridColumn = el.col;
    cell.dataset.sym = el.sym;
    cell.innerHTML = `<span class="z">${el.z}</span><span class="sym">${el.sym}</span><span class="v"></span>`;
    cell.addEventListener("mouseenter", () => onBiCellHover(prefix, sys, cell, el));
    cell.addEventListener("mouseleave", hideTip);
    cell.addEventListener("mousemove", moveTip);
    cell.addEventListener("click", () => onBiCellClick(prefix, sys, el));
    grid.appendChild(cell);
  });

  const sel = document.querySelector(`#${prefix}-pt-metric`);
  fillMetricSelect(sel, m => ["energy", "force"].includes(m.group));
  sel.value = STATE[prefix].pt_metric;
  sel.addEventListener("change", () => { STATE[prefix].pt_metric = sel.value; renderBiPeriodic(prefix, sys); });

  const mSel = document.querySelector(`#${prefix}-pt-model`);
  mSel.innerHTML = sys.models.map(m => `<option>${m}</option>`).join("");
  mSel.value = STATE[prefix].pt_model;
  mSel.addEventListener("change", () => { STATE[prefix].pt_model = mSel.value; renderBiPeriodic(prefix, sys); });

  makeSeg(document.querySelector(`#${prefix}-pt-ds-seg`),
    sys.datasets.map(d => ({ value: d, label: d })),
    STATE[prefix].pt_dataset, v => { STATE[prefix].pt_dataset = v; renderBiPeriodic(prefix, sys); });

  document.querySelector(`#${prefix}-pt-reset`).addEventListener("click", () => {
    STATE[prefix].pt_a = null;
    STATE[prefix].pt_b = null;
    renderBiPeriodic(prefix, sys);
  });

  renderBiPeriodic(prefix, sys);
}

function biPartnersOf(sys, sym) {
  const set = new Set();
  sys.active_pairs.forEach(pk => {
    const [a, b] = pk.split("-");
    if (a === sym) set.add(b);
    else if (b === sym) set.add(a);
  });
  return set;
}

function renderBiPeriodic(prefix, sys) {
  const m = METRIC_BY_KEY[STATE[prefix].pt_metric];
  const model = STATE[prefix].pt_model;
  const ds = STATE[prefix].pt_dataset;
  const a = STATE[prefix].pt_a;
  const b = STATE[prefix].pt_b;
  const stops = m.lower_better ? [...HEAT].reverse() : HEAT;

  const activeSet = new Set(sys.active_elements);
  const partners = a ? biPartnersOf(sys, a) : null;

  // values: if A is picked, color all (A, X) pairs; otherwise just mark active
  const vals = {};
  if (a) {
    partners.forEach(p => {
      const pk = [a, p].sort().join("-");
      const v = pairValueForModel(sys, model, ds, pk, m.key, "normal");
      if (v != null && isFinite(v)) vals[p] = v;
    });
  }
  const arr = Object.values(vals);
  const vmin = arr.length ? Math.min(...arr) : 0;
  const vmax = arr.length ? Math.max(...arr) : 1;
  const span = vmax - vmin || 1e-9;

  document.querySelectorAll(`#${prefix}-pt-grid .cell`).forEach(cell => {
    const sym = cell.dataset.sym;
    const inActive = activeSet.has(sym);
    const v = vals[sym];
    cell.classList.toggle("active", inActive);
    cell.classList.toggle("dim", a ? !(sym === a || partners.has(sym)) : !inActive);
    cell.classList.toggle("eligible", a && partners.has(sym) && sym !== a);
    cell.classList.toggle("first-pick", sym === a);
    cell.classList.toggle("selected", sym === b);

    const vSpan = cell.querySelector(".v");
    const zSpan = cell.querySelector(".z");

    if (!a) {
      // idle state — neutral active styling
      if (inActive) {
        cell.style.background = PALETTE.cardHi;
        cell.style.color = PALETTE.text;
        cell.style.borderColor = PALETTE.borderHi || "#324666";
        cell.style.opacity = "1";
        zSpan.style.color = PALETTE.subtext;
      } else {
        cell.style.background = PALETTE.card;
        cell.style.color = PALETTE.subtext;
        cell.style.borderColor = PALETTE.border;
        cell.style.opacity = "0.35";
        zSpan.style.color = PALETTE.subtext;
      }
      vSpan.textContent = "";
    } else if (sym === a) {
      // first pick — orange highlight
      cell.style.background = PALETTE.orange;
      cell.style.color = "#ffffff";
      cell.style.opacity = "1";
      zSpan.style.color = "rgba(255,255,255,0.7)";
      vSpan.textContent = "";
    } else if (v == null) {
      cell.style.background = PALETTE.card;
      cell.style.color = PALETTE.subtext;
      cell.style.borderColor = PALETTE.border;
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
      zSpan.style.color = lum > 0.55 ? "rgba(0,0,0,0.55)" : "rgba(255,255,255,0.6)";
      vSpan.textContent = fmtSmall(v);
      vSpan.style.color = fg;
    }
  });

  document.querySelector(`#${prefix}-pt-min`).textContent = arr.length ? fmt(vmin, 3) : "—";
  document.querySelector(`#${prefix}-pt-max`).textContent = arr.length ? fmt(vmax, 3) : "—";
  document.querySelector(`#${prefix}-pt-legend`).classList.toggle("reverse", m.lower_better);

  // status line
  const status = document.querySelector(`#${prefix}-pt-status`);
  if (!a) {
    status.innerHTML = `Click any active element to start. <span style="color:${PALETTE.subtext}">→ pair partners will be highlighted</span>`;
  } else if (a && !b) {
    status.innerHTML = `<span class="pick">A = ${a}</span> · pick a partner element (highlighted with dashed orange outline).`;
  } else {
    status.innerHTML = `<span class="pick">Pair = ${a}–${b}</span>`;
  }

  // side panel
  if (a && b) {
    renderBiPairSide(prefix, sys, [a, b].sort().join("-"));
  } else if (a) {
    document.querySelector(`#${prefix}-pt-side`).innerHTML = `
      <h3>${a}</h3>
      <div class="el-name">First pick · ${ELEMENTS.find(e => e.sym === a)?.name || ""}</div>
      <div class="empty-note">Pick a partner element to see the pair detail.</div>`;
  } else {
    document.querySelector(`#${prefix}-pt-side`).innerHTML = `
      <div class="empty-note">Pick two elements above to see their pair's metrics across all models.</div>`;
  }
}

function onBiCellHover(prefix, sys, cell, el) {
  const m = METRIC_BY_KEY[STATE[prefix].pt_metric];
  const a = STATE[prefix].pt_a;
  const activeSet = new Set(sys.active_elements);
  if (!activeSet.has(el.sym)) {
    TIP.innerHTML = `<b>${el.sym}</b> ${el.name}<br><span style="color:${PALETTE.subtext}">no bimetallic data</span>`;
    TIP.classList.add("show");
    return;
  }
  if (!a) {
    const partnerCount = biPartnersOf(sys, el.sym).size;
    TIP.innerHTML = `<b style="color:${PALETTE.orange}">${el.sym}</b> ${el.name}<br>${partnerCount} partner${partnerCount === 1 ? "" : "s"} available`;
  } else if (el.sym === a) {
    TIP.innerHTML = `<b style="color:${PALETTE.orange}">${el.sym}</b> ${el.name}<br>first pick — click again to reset`;
  } else {
    const partners = biPartnersOf(sys, a);
    if (!partners.has(el.sym)) {
      TIP.innerHTML = `<b>${el.sym}</b> ${el.name}<br><span style="color:${PALETTE.subtext}">not a partner of ${a}</span>`;
    } else {
      const pk = [a, el.sym].sort().join("-");
      const v = pairValueForModel(sys, STATE[prefix].pt_model, STATE[prefix].pt_dataset, pk, m.key, "normal");
      TIP.innerHTML = `<b style="color:${PALETTE.orange}">${a}–${el.sym}</b><br>${metricLabel(m)}: ${v != null ? fmt(v, 4) : "no data"}`;
    }
  }
  TIP.classList.add("show");
}
function onBiCellClick(prefix, sys, el) {
  const activeSet = new Set(sys.active_elements);
  if (!activeSet.has(el.sym)) return;
  const a = STATE[prefix].pt_a;
  if (!a) {
    STATE[prefix].pt_a = el.sym;
    STATE[prefix].pt_b = null;
  } else if (el.sym === a) {
    // click first-pick again → reset
    STATE[prefix].pt_a = null;
    STATE[prefix].pt_b = null;
  } else {
    const partners = biPartnersOf(sys, a);
    if (!partners.has(el.sym)) return;       // not a valid partner
    STATE[prefix].pt_b = el.sym;
  }
  renderBiPeriodic(prefix, sys);
}
function renderBiPairSide(prefix, sys, pairKey) {
  const m = METRIC_BY_KEY[STATE[prefix].pt_metric];
  const ds = STATE[prefix].pt_dataset;
  const rows = pairValueAcross(sys, ds, pairKey, m.key, "normal");
  const valid = rows.filter(r => r.v != null && isFinite(r.v));
  valid.sort((a, b) => m.lower_better ? a.v - b.v : b.v - a.v);
  const samples = valid.length ? valid[0].n : null;
  const [a, b] = pairKey.split("-");

  let html = `
    <h3>${a}–${b}</h3>
    <div class="el-name">Bimetallic pair</div>
    <div class="meta-row"><span class="k">Metric</span><span class="v">${metricLabel(m)}</span></div>
    <div class="meta-row"><span class="k">Dataset</span><span class="v">${ds}</span></div>
    <div class="meta-row"><span class="k">N samples</span><span class="v">${samples != null ? fmtInt(samples) : "—"}</span></div>
  `;
  if (valid.length === 0) {
    html += `<div class="empty-note">No model has data for ${pairKey}.</div>`;
  } else {
    const max = Math.max(...valid.map(r => Math.abs(r.v)));
    html += `<div class="breakdown"><h4>Models · sorted best→worst</h4>`;
    valid.forEach((r, k) => {
      const pct = max > 0 ? Math.abs(r.v) / max * 100 : 0;
      const color = modelColor(k, valid.length);
      html += `
        <div class="row">
          <span class="name" title="${r.model}">${k + 1}. ${r.model}</span>
          <div class="bar"><span style="width:${pct.toFixed(1)}%; background: linear-gradient(90deg, ${color}, ${color} 60%, transparent);"></span></div>
          <span class="v">${fmt(r.v, 4)}</span>
        </div>`;
    });
    html += `</div>`;
  }
  document.querySelector(`#${prefix}-pt-side`).innerHTML = html;
}

// ─── tooltip (shared) ──────────────────────────────────────────────────────
const TIP = document.querySelector("#cell-tip");
function moveTip(e) {
  TIP.style.left = (e.clientX + 14) + "px";
  TIP.style.top  = (e.clientY + 14) + "px";
}
function hideTip() { TIP.classList.remove("show"); }

// ─── Per-model summary (used as the heatmap side-panel default state) ─────
//   When no element/cell is clicked, the side panel shows the currently-
//   selected model's headline stats — replaces the dropped Per-Model Detail
//   section while keeping the info one click away.
function renderModelSummarySide(containerSel, sys, modelName, dataset) {
  const container = document.querySelector(containerSel);
  if (!container) return;
  if (!modelName) {
    container.innerHTML = `<div class="empty-note">Pick a model above to see its headline stats.</div>`;
    return;
  }
  const s = sys.summary[modelName]?.[dataset] || sys.summary[modelName]?.["total"] || {};
  const dsLabel = sys.summary[modelName]?.[dataset] ? dataset : "total";
  const stats = [
    { k: "AFwT (%)",                v: fmt(s.AFwT, 2) },
    { k: "MAE (E_form, eV/atom)",   v: fmt(s.E_form_MAE, 4) },
    { k: "MAE (Force, eV/Å)",       v: fmt(s.Force_MAE, 4) },
    { k: "Anomaly rate (%)",        v: fmt(s.Anomaly_pct, 2) },
    { k: "R² (E_form)",             v: fmt(s.E_form_R2, 3) },
    { k: "Cosine (Force)",          v: fmt(s.Force_cosine, 3) },
    { k: "Time / step (s, median)", v: fmt(s.Time_med, 4) },
    { k: "N samples",               v: fmtInt((s.N_normal || 0) + (s.N_anomaly || 0)) },
  ];
  container.innerHTML = `
    <h3>${modelName}</h3>
    <div class="el-name">Dataset · ${dsLabel}</div>
    <div class="mdl-stats compact">
      ${stats.map(b => `<div class="b"><div class="k">${b.k}</div><div class="v">${b.v}</div></div>`).join("")}
    </div>
    <div class="empty-note" style="margin-top:14px">Click a cell on the heatmap to compare this metric across all models.</div>
  `;
}
