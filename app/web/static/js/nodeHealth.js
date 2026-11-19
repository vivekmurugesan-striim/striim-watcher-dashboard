// Node Health tab: summary stat tiles, node detail table, CPU + memory trend charts.
//
// Chart.js note: deliberately using a plain "category" x-axis with pre-formatted hour labels
// rather than a "time" scale — a time scale needs a date-adapter library (chartjs-adapter-*)
// as an extra CDN dependency/version to pin, which isn't worth it for two hourly line charts.
const NodeHealth = (() => {
  let cpuChart = null;
  let memoryChart = null;

  function ragBadgeClass(rag) {
    const key = (rag || "").toLowerCase();
    if (key === "red") return "badge-red";
    if (key === "amber") return "badge-amber";
    if (key === "green") return "badge-green";
    return "badge-grey";
  }

  function statusDotClass(status) {
    const key = (status || "").toUpperCase();
    if (key === "UP") return "rag-green";
    if (key === "DOWN") return "rag-red";
    return "rag-amber";
  }

  function statTile(label, value) {
    const div = document.createElement("div");
    div.className = "stat";
    div.innerHTML = `<div class="stat-label">${label}</div><div class="stat-value">${value}</div>`;
    return div;
  }

  function renderSummaryStats(clusters) {
    const container = document.getElementById("node-summary-stats");
    container.innerHTML = "";

    if (clusters.length === 0) {
      container.innerHTML = '<p class="muted">No node data reporting in this window.</p>';
      return;
    }

    const c = clusters[0];
    container.appendChild(statTile("Total nodes", c.total_nodes));
    container.appendChild(statTile("Nodes up", `${c.nodes_up} / ${c.total_nodes}`));

    const statusDiv = document.createElement("div");
    statusDiv.className = "stat";
    statusDiv.innerHTML = `<div class="stat-label">Status</div><div class="stat-value"><span class="badge ${ragBadgeClass(c.RAG_status)}">${c.RAG_status}</span></div>`;
    container.appendChild(statusDiv);
  }

  function renderNodeTable(nodes) {
    const tbody = document.querySelector("#node-table tbody");
    tbody.innerHTML = "";

    for (const n of nodes) {
      const lastSeen = n.last_seen_batchdate ? new Date(n.last_seen_batchdate).toLocaleString() : "—";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${n.nodeName ?? "—"}</td>
        <td><span class="rag-dot ${statusDotClass(n.status)}"></span>${n.status}</td>
        <td>${n.cpurate != null ? n.cpurate + "%" : "—"}</td>
        <td>${n.freemem ?? "—"}</td>
        <td>${n.striimversion ?? "—"}</td>
        <td>${n.uptime ?? "—"}</td>
        <td>${lastSeen}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function formatHourLabel(iso) {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: "numeric", day: "numeric", hour: "2-digit" });
  }

  const PALETTE = ["#2563a8", "#1c8a56", "#b3760e", "#c4392b", "#7b5ea8", "#1897a6"];

  // Shared by the CPU and memory charts — both are "one line per node, hourly" against the
  // same trend payload, differing only in which numeric field feeds the line and the y-axis
  // label. Returns the Chart.js instance so the caller can destroy it on the next load/error.
  function renderLineChart(canvasId, points, valueKey, yAxisLabel) {
    // A node with no nodeName (seen in real Vivek-dataset data — see schemas.py's docstring)
    // can't be plotted as its own identifiable line; drop those points here rather than
    // showing a confusing "null"-labeled series.
    const named = points.filter((p) => p.nodeName);
    const byNode = {};
    const hourSet = new Set();
    for (const p of named) {
      hourSet.add(p.hour);
      if (!byNode[p.nodeName]) byNode[p.nodeName] = {};
      byNode[p.nodeName][p.hour] = p[valueKey];
    }
    const hours = Array.from(hourSet).sort();
    const labels = hours.map(formatHourLabel);

    const datasets = Object.entries(byNode).map(([nodeName, byHour], i) => ({
      label: nodeName,
      data: hours.map((h) => (h in byHour ? byHour[h] : null)),
      borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: "transparent",
      spanGaps: true,
      tension: 0.25,
      pointRadius: hours.length <= 3 ? 4 : 2,
    }));

    return new Chart(document.getElementById(canvasId), {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: "#57697a", maxRotation: 0, autoSkip: true }, grid: { color: "#e4eaf0" } },
          y: {
            title: { display: true, text: yAxisLabel, color: "#57697a" },
            ticks: { color: "#57697a" },
            grid: { color: "#e4eaf0" },
          },
        },
        plugins: { legend: { labels: { color: "#152230" } } },
      },
    });
  }

  function renderSparseDataHint(points) {
    const hint = document.getElementById("node-trend-sparse-hint");
    const distinctHours = new Set(points.filter((p) => p.nodeName).map((p) => p.hour)).size;
    if (distinctHours > 0 && distinctHours <= 2) {
      hint.innerHTML =
        '<p class="hint">Only ' + distinctHours + ' hour(s) of data in this window — the cluster likely ' +
        "had a polling gap. The charts below are accurate, just sparse; widen Lookback to see a fuller trend.</p>";
    } else {
      hint.innerHTML = "";
    }
  }

  // Status and trend come from two independent BigQuery functions (one of them newer than
  // the other) — load and render each on its own, so a failure in one (e.g. not deployed yet)
  // can't blank out a panel whose own data loaded fine.
  //
  // Sequence guards (statusSeq/trendSeq): the lookback selector, "Refresh now", and
  // auto-refresh can all trigger a new loadStatus/loadTrend call before a previous one has
  // resolved — e.g. the page's initial 7-day load is still in flight when the user switches
  // the selector to 30 days. Without this, whichever response happens to resolve LAST wins
  // the DOM regardless of which request was actually issued last, so a slow, now-stale
  // response can silently overwrite the correct one already on screen. Each function bumps
  // its own counter at call time and only renders if it's still the most recent call when its
  // response comes back.
  let statusSeq = 0;
  let trendSeq = 0;

  async function loadStatus(daysBack) {
    const seq = ++statusSeq;
    try {
      const statusData = await Api.nodeStatus(daysBack);
      if (seq !== statusSeq) return; // superseded by a newer call — discard this response
      renderSummaryStats(statusData.clusters);
      renderNodeTable(statusData.nodes);
    } catch (err) {
      if (seq !== statusSeq) return;
      console.error("Node status load failed:", err);
      Ui.showError("node-summary-stats", "Couldn't load node status — see console.");
      document.querySelector("#node-table tbody").innerHTML =
        '<tr><td colspan="7" class="error-text">Couldn\'t load node status — see console.</td></tr>';
    }
  }

  async function loadTrend(daysBack) {
    const seq = ++trendSeq;
    try {
      const trendData = await Api.nodeTrend(daysBack);
      if (seq !== trendSeq) return;

      document.getElementById("node-trend-chart-error").innerHTML = "";
      document.getElementById("node-memory-chart-error").innerHTML = "";
      document.getElementById("node-trend-range").textContent = `(last ${trendData.days_back}d, hourly)`;
      renderSparseDataHint(trendData.points);

      if (cpuChart) cpuChart.destroy();
      if (memoryChart) memoryChart.destroy();
      cpuChart = renderLineChart("node-trend-chart", trendData.points, "avg_cpurate", "CPU % (per core)");
      memoryChart = renderLineChart("node-memory-chart", trendData.points, "avg_freemem_gb", "Free memory (GB)");
    } catch (err) {
      if (seq !== trendSeq) return;
      console.error("Node trend load failed:", err);
      if (cpuChart) { cpuChart.destroy(); cpuChart = null; }
      if (memoryChart) { memoryChart.destroy(); memoryChart = null; }
      document.getElementById("node-trend-range").textContent = "";
      document.getElementById("node-trend-sparse-hint").innerHTML = "";
      Ui.showError("node-trend-chart-error", "Couldn't load the CPU trend — see console.");
      Ui.showError("node-memory-chart-error", "Couldn't load the memory trend — see console.");
    }
  }

  async function load(daysBack) {
    // Deliberately not Promise.all — see loadStatus/loadTrend comment above.
    await Promise.allSettled([loadStatus(daysBack), loadTrend(daysBack)]);
  }

  return { load };
})();
