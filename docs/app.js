(() => {
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (x, d = 0) => (x * 100).toFixed(d) + "%";
  const inr = (v) => {
    const a = Math.abs(v), s = v < 0 ? "−" : "";
    if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)} Cr`;
    if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(1)} L`;
    return `${s}₹${Math.round(a).toLocaleString("en-IN")}`;
  };
  const SHORT = {
    "Create Requisition": "PR", "Approve Requisition": "Approve PR", "Second-Level Approval": "2nd approval",
    "Create Purchase Order": "PO", "Send PO to Vendor": "Send PO", "Change Purchase Order": "Change PO",
    "Receive Goods": "Goods", "Receive Invoice": "Invoice", "Three-Way Match": "Match",
    "Resolve Price Mismatch": "Mismatch", "Approve Payment": "Approve pay", "Pay Invoice": "Pay",
  };
  const REWORK = new Set(["Change Purchase Order", "Resolve Price Mismatch", "Second-Level Approval"]);

  function chartDefaults() {
    Chart.defaults.color = css("--muted");
    Chart.defaults.borderColor = css("--border");
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.plugins.legend.labels.boxWidth = 12;
  }

  fetch("data/dashboard.json").then((r) => r.json()).then(render).catch((e) => {
    $("meta").textContent = "Failed to load dashboard data: " + e.message;
  });

  function render(d) {
    chartDefaults();
    const k = d.kpis, m = d.meta, c = d.conformance;
    $("meta").textContent = `${m.process} · ${m.cases.toLocaleString("en-IN")} cases · ${m.events.toLocaleString("en-IN")} events · ${m.from} to ${m.to} · SLA ${m.sla_days} days`;
    $("kpis").innerHTML = [
      [k.median_cycle_days + " d", "Median cycle time", `P90 ${k.p90_cycle_days} d`],
      [pct(k.sla_breach_rate), "Cases breaching SLA", `> ${m.sla_days} days end-to-end`],
      [pct(c.happy_path_rate), "Follow the happy path", `${k.variants} distinct variants`],
      [pct(k.rework_rate), "Cases with rework", `${pct(k.price_mismatch_rate)} price mismatches`],
    ].map(([v, l, s]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div><div class="s">${s}</div></div>`).join("");

    drawMap(d.process_map);
    drawBottlenecks(d.bottlenecks);
    drawHistogram(d.cycle_histogram, m.sla_days);
    drawVariants(d.variants);
    drawConformance(c);
    drawSegments(d.segments);
    drawModel(d.model);
    drawValue(d.value);
  }

  // ---------- process map ----------
  function drawMap(pm) {
    const svg = $("map");
    const NS = "http://www.w3.org/2000/svg";
    const W = 100, H = 46, X0 = -20, DX = 126, Y0 = 50, DY = 100;
    const pos = {};
    for (const [a, [col, row]] of Object.entries(pm.layout)) {
      const c = a.startsWith("●") ? 0.3 : a.startsWith("■") ? 9.7 : col; // pull start/end in
      pos[a] = { x: X0 + c * DX, y: Y0 + row * DY };
    }
    const width = X0 + 10 * DX - 20, height = Y0 + 2 * DY + 50;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const counts = Object.fromEntries(pm.activities.map((a) => [a.activity, a.events]));
    const edges = pm.edges.filter((e) => pos[e.source] && pos[e.target]);
    const maxC = Math.max(...edges.map((e) => e.count));
    const heat = (h) => (h < 24 ? "--heat-0" : h < 72 ? "--heat-1" : "--heat-2");

    let defs = "<defs>";
    for (const h of ["--heat-0", "--heat-1", "--heat-2", "--muted"]) {
      defs += `<marker id="ar${h}" viewBox="0 0 10 10" refX="9" refY="5" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${css(h)}"/></marker>`;
    }
    defs += "</defs>";

    const isTerm = (a) => a.startsWith("●") || a.startsWith("■");
    function border(p, toward, term) {
      // point on the node border in the direction of `toward`
      const dx = toward.x - p.x, dy = toward.y - p.y;
      if (term) { const L = Math.hypot(dx, dy) || 1; return { x: p.x + (dx / L) * 9, y: p.y + (dy / L) * 9 }; }
      const sx = dx ? (W / 2) / Math.abs(dx) : Infinity, sy = dy ? (H / 2) / Math.abs(dy) : Infinity;
      const s = Math.min(sx, sy);
      return { x: p.x + dx * s, y: p.y + dy * s };
    }

    let paths = "", labels = "";
    edges.sort((a, b) => a.count - b.count).forEach((e) => {
      const a = pos[e.source], b = pos[e.target];
      const span = Math.hypot(b.x - a.x, b.y - a.y);
      const adjacent = a.y === b.y && Math.abs(b.x - a.x) <= DX + 1;
      const back = b.x < a.x || (b.x === a.x && b.y < a.y);
      let bend = adjacent && !back ? 0 : Math.max(22, Math.min(70, span * 0.28)) * (back ? 1 : -1);
      if (a.y !== b.y && !back) bend = 0;
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      const nx = -(b.y - a.y) / (span || 1), ny = (b.x - a.x) / (span || 1);
      const cp = { x: mx + nx * bend, y: my + ny * bend };
      const p0 = border(a, bend ? cp : b, isTerm(e.source));
      const p1 = border(b, bend ? cp : a, isTerm(e.target));
      const h = isTerm(e.source) || isTerm(e.target) ? "--muted" : heat(e.median_wait_h);
      const w = (isTerm(e.source) || isTerm(e.target)) ? 1.5 : 1 + 6 * Math.sqrt(e.count / maxC);
      const days = (e.median_wait_h / 24).toFixed(1);
      paths += `<path class="e" d="M${p0.x},${p0.y} Q${cp.x},${cp.y} ${p1.x},${p1.y}" stroke="${css(h)}" stroke-width="${w.toFixed(1)}" marker-end="url(#ar${h})"><title>${esc(e.source)} → ${esc(e.target)}\n${e.count} cases · median wait ${days} d · P90 ${(e.p90_wait_h / 24).toFixed(1)} d</title></path>`;
      if (h !== "--muted" && e.count >= maxC * 0.04) {
        const lx = 0.25 * p0.x + 0.5 * cp.x + 0.25 * p1.x, ly = 0.25 * p0.y + 0.5 * cp.y + 0.25 * p1.y;
        const vertical = Math.abs(a.x - b.x) < 1;
        const ox = vertical ? (back ? 18 : -18) : 0, oy = vertical ? 3 : bend ? (bend < 0 ? -4 : 12) : -7;
        labels += `<text class="el" x="${lx + ox}" y="${ly + oy}" text-anchor="middle">${days}d</text>`;
      }
    });

    let nodes = "";
    for (const [a, p] of Object.entries(pos)) {
      if (isTerm(a)) {
        nodes += `<g class="n term"><circle cx="${p.x}" cy="${p.y}" r="8"/><text x="${p.x}" y="${p.y + 24}" text-anchor="middle" class="cnt">${a.startsWith("●") ? "start" : "end"}</text></g>`;
        continue;
      }
      const words = a.split(" ");
      const mid = Math.ceil(words.length / 2);
      const lines = words.length >= 2 ? [words.slice(0, mid).join(" "), words.slice(mid).join(" ")] : [a];
      nodes += `<g class="n${REWORK.has(a) ? " rework" : ""}"><rect x="${p.x - W / 2}" y="${p.y - H / 2}" width="${W}" height="${H}" rx="7"/>` +
        lines.map((l, i) => `<text x="${p.x}" y="${p.y - (lines.length - 1) * 6 + i * 12 - 3}" text-anchor="middle">${esc(l)}</text>`).join("") +
        `<text class="cnt" x="${p.x}" y="${p.y + (lines.length > 1 ? 16 : 13)}" text-anchor="middle">${(counts[a] || 0).toLocaleString("en-IN")}</text><title>${esc(a)}: ${counts[a]} events</title></g>`;
    }
    svg.innerHTML = defs + paths + nodes + labels;
  }

  // ---------- charts ----------
  function drawBottlenecks(b) {
    new Chart($("bottlenecks"), {
      type: "bar",
      data: {
        labels: b.map((e) => `${SHORT[e.source] || e.source} → ${SHORT[e.target] || e.target}`),
        datasets: [{ data: b.map((e) => Math.round(e.total_wait_days)), backgroundColor: b.map((e) => css(e.median_wait_h < 24 ? "--heat-0" : e.median_wait_h < 72 ? "--heat-1" : "--heat-2")), borderRadius: 4 }],
      },
      options: {
        indexAxis: "y", plugins: { legend: { display: false },
          tooltip: { callbacks: { afterLabel: (ctx) => `median wait ${(b[ctx.dataIndex].median_wait_h / 24).toFixed(1)} d × ${b[ctx.dataIndex].count} cases` } } },
        scales: { x: { title: { display: true, text: "case-days of waiting" } }, y: { grid: { display: false } } },
      },
    });
  }

  function drawHistogram(h, sla) {
    const parse = (s) => s.replace(/[[\])]/g, "").split(",").map(Number);
    const labels = h.map((r) => { const [a, b] = parse(r.bin); return b > 1e6 ? `${a}+` : `${a}–${b}`; });
    new Chart($("histogram"), {
      type: "bar",
      data: { labels, datasets: [{ data: h.map((r) => r.cases), backgroundColor: h.map((r) => (parse(r.bin)[0] >= sla ? css("--heat-2") : css("--accent"))), borderRadius: 3, categoryPercentage: 1, barPercentage: 0.92 }] },
      options: {
        plugins: { legend: { display: false }, tooltip: { callbacks: { title: (i) => `${i[0].label} days` } } },
        scales: { x: { title: { display: true, text: `cycle time (days) · red = beyond ${sla}-day SLA` }, grid: { display: false } }, y: { title: { display: true, text: "cases" } } },
      },
    });
  }

  function drawVariants(v) {
    const max = Math.max(...v.map((r) => r.share));
    $("variants").querySelector("tbody").innerHTML = v.slice(0, 8).map((r) => `<tr>
      <td><div class="path">${r.variant.split(" → ").map((a) => `<span class="${REWORK.has(a) ? "rw" : ""}">${esc(SHORT[a] || a)}</span>`).join("")}</div></td>
      <td><div class="share"><i style="width:${(r.share / max) * 48}px"></i>${pct(r.share, 1)}</div></td>
      <td class="num">${r.median_cycle_days.toFixed(1)}</td><td class="num">${pct(r.breach_rate)}</td></tr>`).join("");
  }

  function drawConformance(c) {
    const rows = [
      ["Exact happy path", c.happy_path_rate, "trace identical to the reference model"],
      ["Order fitness", c.order_fitness, "reference steps occur in the right order"],
      ["Rework loops", c.rework_loop_rate, "an activity repeats (PO resend, re-match)"],
      ["Invoice before goods", c.invoice_before_goods_rate, "breaks the receive-then-bill control"],
      ["Second-level approval", c.extra_approval_rate, "requisitions above ₹5 L"],
    ];
    $("conformance").innerHTML = rows.map(([l, v, h]) => `<div class="row"><div><span>${l}</span><b>${pct(v, 1)}</b></div><div class="track"><i style="width:${v * 100}%"></i></div><div class="hint">${h}</div></div>`).join("");
  }

  function drawSegments(segs) {
    const keys = ["vendor", "channel", "region", "category"];
    let chart;
    function show(key) {
      const rows = segs[key];
      $("segTabs").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.k === key));
      const data = {
        labels: rows.map((r) => r[key]),
        datasets: [
          { type: "bar", label: "Median cycle (days)", data: rows.map((r) => r.median_cycle_days), backgroundColor: css("--accent"), borderRadius: 4, yAxisID: "y" },
          { type: "line", label: "SLA breach rate", data: rows.map((r) => r.breach_rate * 100), borderColor: css("--heat-2"), backgroundColor: css("--heat-2"), yAxisID: "y1", tension: 0.25, pointRadius: 4 },
          { type: "line", label: "Price mismatch rate", data: rows.map((r) => r.mismatch_rate * 100), borderColor: css("--heat-1"), backgroundColor: css("--heat-1"), yAxisID: "y1", borderDash: [5, 4], tension: 0.25, pointRadius: 3 },
        ],
      };
      if (chart) { chart.data = data; chart.update(); return; }
      chart = new Chart($("segments"), {
        data,
        options: {
          interaction: { mode: "index", intersect: false },
          scales: {
            y: { title: { display: true, text: "median days" }, beginAtZero: true },
            y1: { position: "right", title: { display: true, text: "%" }, beginAtZero: true, grid: { drawOnChartArea: false }, ticks: { callback: (v) => v + "%" } },
            x: { grid: { display: false } },
          },
          plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y.toFixed(1)}${c.datasetIndex ? "%" : " d"}` } } },
        },
      });
    }
    $("segTabs").innerHTML = keys.map((k) => `<button data-k="${k}" aria-pressed="false">${k[0].toUpperCase() + k.slice(1)}</button>`).join("");
    $("segTabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) show(b.dataset.k); });
    show("vendor");
  }

  function drawModel(m) {
    $("models").querySelector("tbody").innerHTML = Object.entries(m.models).map(([name, r]) =>
      `<tr><td>${esc(name)}${name === m.best ? ' <span class="badge ok">selected</span>' : ""}</td><td class="num">${r.roc_auc}</td><td class="num">${r.avg_precision}</td><td class="num">${r.precision}</td><td class="num">${r.recall}</td></tr>`).join("");
    $("capture").innerHTML = `Reviewing the <b>top 20%</b> of new requisitions by predicted risk would catch <b>${pct(m.top20_breach_capture)}</b> of eventual SLA breaches, versus 20% for random checks. Base breach rate: ${pct(m.base_rate)} · ${m.train_rows} train / ${m.test_rows} test cases.`;
    const imp = m.importances.filter((r) => r.importance > 0);
    new Chart($("importance"), {
      type: "bar",
      data: { labels: imp.map((r) => r.feature.replace("_", " ")), datasets: [{ data: imp.map((r) => r.importance), backgroundColor: css("--accent"), borderRadius: 4 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: "mean drop in ROC-AUC when shuffled" } }, y: { grid: { display: false } } } },
    });
  }

  // ---------- value model (port of pov_platform/value.py) ----------
  function businessCase(d, a, adoption, levers) {
    const n = a.annual_cases;
    const hours = {
      catalog_first: n * d.manual_share * adoption.catalog_first * (a.manual_touch_minutes - a.catalog_touch_minutes) / 60,
      price_sync: n * d.mismatch_rate * adoption.price_sync * a.mismatch_rework_hours,
      touchless_match: n * d.matches_per_case * adoption.touchless_match * a.match_minutes / 60,
      early_payment: 0,
    };
    const savings = Object.fromEntries(Object.entries(hours).map(([k, h]) => [k, h * a.hourly_cost]));
    savings.early_payment = n * d.spend_per_case * d.late_for_discount_spend_share * adoption.early_payment * a.early_pay_discount;
    const annual = Object.values(savings).reduce((x, y) => x + y, 0);
    const build = Object.entries(levers).reduce((x, [key, l]) => x + (adoption[key] > 0 ? l.build_cost : 0), 0);
    const net = annual - a.run_cost_annual;
    const npv = -build + [1, 2, 3].reduce((x, y) => x + net / (1 + a.discount_rate) ** y, 0);
    return { hours, savings, annual, net, build, npv, payback: net > 0 ? (build / net) * 12 : null, fte: Object.values(hours).reduce((x, y) => x + y, 0) / 1800 };
  }

  function drawValue(v) {
    const a = { ...v.baseline.assumptions };
    const levers = v.levers_meta;
    const adoption = Object.fromEntries(Object.entries(levers).map(([k, l]) => [k, l.adoption]));
    const sliders = [
      ["Volume & cost"],
      ["annual_cases", "Requisitions per year", 5000, 100000, 1000, (x) => x.toLocaleString("en-IN"), a],
      ["hourly_cost", "Loaded cost per hour", 300, 2000, 50, (x) => "₹" + x.toLocaleString("en-IN"), a],
      ["Lever adoption"],
      ...Object.entries(levers).map(([k, l]) => [k, l.name, 0, 1, 0.05, (x) => pct(x), adoption]),
    ];
    $("sliders").innerHTML = sliders.map((s) => s.length === 1 ? `<div class="slider-group">${s[0]}</div>` :
      `<div class="slider"><label for="v-${s[0]}">${esc(s[1])}<output id="vo-${s[0]}"></output></label><input type="range" id="v-${s[0]}" min="${s[2]}" max="${s[3]}" step="${s[4]}" value="${s[6][s[0]]}"></div>`).join("") +
      `<p class="muted" style="font-size:.82rem;margin-bottom:0">Measured from log: ${pct(v.drivers.manual_share)} manual requisitions, ${pct(v.drivers.mismatch_rate, 1)} price mismatches, ${v.drivers.matches_per_case.toFixed(2)} matches per case, ${pct(v.drivers.late_for_discount_spend_share)} of spend paid too late for a ${pct(a.early_pay_discount, 1)} discount. A lever's build cost is dropped at 0% adoption.</p>`;

    const chart = new Chart($("levers"), {
      type: "bar",
      data: { labels: Object.values(levers).map((l) => l.name), datasets: [{ data: [], backgroundColor: css("--accent"), borderRadius: 4 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => inr(c.parsed.x * 1e5) } } }, scales: { x: { beginAtZero: true }, y: { grid: { display: false } } } },
    });

    function update() {
      sliders.filter((s) => s.length > 1).forEach(([k, , , , , f, obj]) => { obj[k] = +$("v-" + k).value; $("vo-" + k).textContent = f(obj[k]); });
      const r = businessCase(v.drivers, a, adoption, levers);
      $("valueKpis").innerHTML = [
        [inr(r.annual), "Gross annual saving"],
        [inr(r.net), "Net of run cost"],
        [r.payback ? r.payback.toFixed(1) + " mo" : "n/a", "Payback period"],
        [inr(r.npv), "3-year NPV @ 10%"],
        [r.fte.toFixed(1), "FTE capacity released"],
        [inr(r.build), "One-off build cost"],
      ].map(([val, l]) => `<div class="kpi"><div class="v">${val}</div><div class="l">${l}</div></div>`).join("");
      chart.data.datasets[0].data = Object.keys(levers).map((k) => r.savings[k] / 1e5);
      chart.update("none");
    }
    $("sliders").addEventListener("input", update);
    update();
  }
})();
