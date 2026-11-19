// History & Trends tab: app picker, uptime stat tiles (app + cluster), and a colored
// status-timeline strip (one bar per polled hour, colored by that hour's appStatus).
const AppHistory = (() => {
  let timelineChart = null;
  // See nodeHealth.js's loadStatus/loadTrend comment for why these guards exist — switching
  // the selected app, the date range, or a hand-off from the Applications tab can all trigger
  // a new load before a previous one (for a different app/range) has resolved.
  let uptimeSeq = 0;
  let timelineSeq = 0;

  const STATUS_COLOR = {
    RUNNING: "#1c8a56",
    HALT: "#c4392b",
    CRASH: "#c4392b",
    STOPPED: "#c4392b",
    CREATED: "#b3760e",
    DEPLOYED: "#b3760e",
  };

  function colorFor(status) {
    return STATUS_COLOR[(status || "").toUpperCase()] || "#74828f";
  }

  function populateAppSelect(appNames, preferred) {
    const select = document.getElementById("history-app-select");
    const current = preferred || select.value;
    select.innerHTML = "";
    for (const name of appNames) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    }
    if (current && appNames.includes(current)) {
      select.value = current;
    }
    return select.value;
  }

  function statTile(label, value) {
    const div = document.createElement("div");
    div.className = "stat";
    div.innerHTML = `<div class="stat-label">${label}</div><div class="stat-value">${value}</div>`;
    return div;
  }

  function fmtMinutes(mins) {
    if (mins == null) return "—";
    const h = Math.floor(mins / 60);
    const m = Math.round(mins % 60);
    return `${h}h ${m}m`;
  }

  async function renderUptimeStats(appName, daysBack) {
    const seq = ++uptimeSeq;
    const container = document.getElementById("uptime-stat");
    container.innerHTML = "";

    try {
      const [appUptime, clusterUptime] = await Promise.all([
        Api.appUptime(appName, daysBack),
        Api.clusterUptime(daysBack),
      ]);
      if (seq !== uptimeSeq) return; // superseded by a newer call — discard this response

      const appPct = appUptime && appUptime.uptime_pct != null ? appUptime.uptime_pct.toFixed(1) + "%" : "—";
      container.appendChild(statTile(`App uptime (${daysBack}d)`, appPct));
      container.appendChild(
        statTile(
          "Up / Down",
          appUptime ? `${fmtMinutes(appUptime.up_minutes)} / ${fmtMinutes(appUptime.down_minutes)}` : "—"
        )
      );

      const clusterRow = clusterUptime.clusters[0];
      const clusterPct = clusterRow && clusterRow.uptime_pct != null ? clusterRow.uptime_pct.toFixed(1) + "%" : "—";
      container.appendChild(statTile(`Cluster uptime (${daysBack}d)`, clusterPct));
    } catch (err) {
      if (seq !== uptimeSeq) return;
      console.error("Uptime stats load failed:", err);
      container.innerHTML = '<p class="error-text">Couldn\'t load uptime stats — see console.</p>';
    }
  }

  function formatHourLabel(iso) {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: "numeric", day: "numeric", hour: "2-digit" });
  }

  function renderTimeline(points) {
    const sorted = [...points].sort((a, b) => new Date(a.hour) - new Date(b.hour));
    const labels = sorted.map((p) => formatHourLabel(p.hour));
    const colors = sorted.map((p) => colorFor(p.appStatus));
    const statuses = sorted.map((p) => p.appStatus);

    document.getElementById("status-timeline-chart-error").innerHTML = "";
    const ctx = document.getElementById("status-timeline-chart");
    if (timelineChart) timelineChart.destroy();
    timelineChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Status",
            data: labels.map(() => 1),
            backgroundColor: colors,
            borderWidth: 0,
            categoryPercentage: 1.0,
            barPercentage: 1.0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: "#57697a", maxRotation: 0, autoSkip: true }, grid: { display: false } },
          y: { display: false, max: 1 },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => statuses[ctx.dataIndex],
            },
          },
        },
      },
    });
  }

  async function loadTimeline(appName, daysBack) {
    const seq = ++timelineSeq;
    try {
      const historyData = await Api.appHistory(appName, daysBack);
      if (seq !== timelineSeq) return; // superseded by a newer call — discard this response
      renderTimeline(historyData.points);
    } catch (err) {
      if (seq !== timelineSeq) return;
      console.error("Status history load failed:", err);
      if (timelineChart) {
        timelineChart.destroy();
        timelineChart = null;
      }
      Ui.showError("status-timeline-chart-error", "Couldn't load the status timeline — see console.");
    }
  }

  async function loadHistoryFor(appName, daysBack) {
    if (!appName) return;
    // Independent of each other on purpose — see renderUptimeStats'/loadTimeline's own
    // try/catch: one failing (e.g. a BigQuery function not deployed yet) shouldn't blank the
    // other half of this tab.
    await Promise.allSettled([renderUptimeStats(appName, daysBack), loadTimeline(appName, daysBack)]);
  }

  return { populateAppSelect, loadHistoryFor };
})();
