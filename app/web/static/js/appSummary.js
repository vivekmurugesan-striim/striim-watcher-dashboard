// Applications tab: status-mix chips, searchable/filterable app table, row-click hand-off to
// the History & Trends tab (via a "select-app" custom event main.js listens for).
const AppSummary = (() => {
  let lastApps = [];
  // See nodeHealth.js's loadStatus/loadTrend comment for why this guard exists — the
  // Applications-tab lookback selector, auto-refresh, and "Refresh now" can all trigger a new
  // load() before a previous one resolves.
  let loadSeq = 0;

  function statusDotClass(bucket) {
    const key = (bucket || "").toUpperCase();
    if (key === "UP") return "rag-green";
    if (key === "DOWN") return "rag-red";
    return "rag-amber";
  }

  function renderStatusMix(counts) {
    const container = document.getElementById("status-mix");
    container.innerHTML = "";
    for (const { appStatus, count } of counts.by_status) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = `${appStatus}: ${count}`;
      container.appendChild(chip);
    }
    const total = document.createElement("span");
    total.className = "chip";
    total.textContent = `Total: ${counts.total}`;
    container.appendChild(total);
  }

  function populateStatusFilter(apps) {
    const select = document.getElementById("app-status-filter");
    const current = select.value;
    const statuses = Array.from(new Set(apps.map((a) => a.appStatus))).sort();
    select.innerHTML = '<option value="">All statuses</option>';
    for (const s of statuses) {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      select.appendChild(opt);
    }
    select.value = current;
  }

  // sourceTypes/targetTypes are comma-joined when an app has more than one distinct type
  // (see get_app_status_summary.sql) — split those apart so each individual type is its own
  // filter option, rather than offering "MSJet, Oracle" as one unsplittable choice.
  function splitTypes(value) {
    return value ? value.split(",").map((t) => t.trim()).filter(Boolean) : [];
  }

  function populateTypeFilter(apps, field, selectId, allLabel) {
    const select = document.getElementById(selectId);
    const current = select.value;
    const types = new Set();
    for (const a of apps) {
      for (const t of splitTypes(a[field])) types.add(t);
    }
    const sorted = Array.from(types).sort();
    select.innerHTML = `<option value="">${allLabel}</option>`;
    for (const t of sorted) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      select.appendChild(opt);
    }
    if (sorted.includes(current)) select.value = current;
  }

  function renderTable() {
    const search = document.getElementById("app-search").value.trim().toLowerCase();
    const statusFilter = document.getElementById("app-status-filter").value;
    const sourceTypeFilter = document.getElementById("app-source-type-filter").value;
    const targetTypeFilter = document.getElementById("app-target-type-filter").value;

    const filtered = lastApps.filter((a) => {
      // appName can be null in real data (same nullability as nodeName — see schemas.py); a
      // row with no identity can't support the click-to-drill-down-by-name interaction below.
      if (!a.appName) return false;
      if (search && !a.appName.toLowerCase().includes(search)) return false;
      if (statusFilter && a.appStatus !== statusFilter) return false;
      if (sourceTypeFilter && !splitTypes(a.sourceTypes).includes(sourceTypeFilter)) return false;
      if (targetTypeFilter && !splitTypes(a.targetTypes).includes(targetTypeFilter)) return false;
      return true;
    });

    const tbody = document.querySelector("#app-table tbody");
    tbody.innerHTML = "";
    for (const a of filtered) {
      const backpressure = a.isBackpressured ? "Yes" : "No";
      const recovery = a.isRecoveryEnabled ? "Yes" : "No";
      const lastActivity = a.latestActivity ? new Date(a.latestActivity).toLocaleString() : "—";
      const tr = document.createElement("tr");
      tr.dataset.appName = a.appName;
      tr.innerHTML = `
        <td>${a.appName}</td>
        <td><span class="rag-dot ${statusDotClass(a.status_bucket)}"></span>${a.appStatus}</td>
        <td>${a.sourceTypes ?? "—"}</td>
        <td>${a.targetTypes ?? "—"}</td>
        <td>${backpressure}</td>
        <td>${a.checkpointStatus ?? "—"}</td>
        <td>${recovery}</td>
        <td>${a.totalInput ?? "—"}</td>
        <td>${a.totalOutput ?? "—"}</td>
        <td>${lastActivity}</td>
      `;
      tr.addEventListener("click", () => {
        window.dispatchEvent(new CustomEvent("select-app", { detail: { appName: a.appName } }));
      });
      tbody.appendChild(tr);
    }
  }

  function wireFilters() {
    document.getElementById("app-search").addEventListener("input", renderTable);
    document.getElementById("app-status-filter").addEventListener("change", renderTable);
    document.getElementById("app-source-type-filter").addEventListener("change", renderTable);
    document.getElementById("app-target-type-filter").addEventListener("change", renderTable);
  }

  async function load(daysBack) {
    const seq = ++loadSeq;
    try {
      const data = await Api.appSummary(daysBack);
      if (seq !== loadSeq) return; // superseded by a newer call — discard this response
      lastApps = data.apps;
      renderStatusMix(data.counts);
      populateStatusFilter(data.apps);
      populateTypeFilter(data.apps, "sourceTypes", "app-source-type-filter", "All source types");
      populateTypeFilter(data.apps, "targetTypes", "app-target-type-filter", "All target types");
      renderTable();
    } catch (err) {
      if (seq !== loadSeq) return;
      console.error("App summary load failed:", err);
      lastApps = [];
      Ui.showError("status-mix", "Couldn't load application summary — see console.");
      document.querySelector("#app-table tbody").innerHTML =
        '<tr><td colspan="10" class="error-text">Couldn\'t load application summary — see console.</td></tr>';
    }
  }

  function appNames() {
    return lastApps.map((a) => a.appName).filter(Boolean);
  }

  return { load, wireFilters, appNames };
})();
