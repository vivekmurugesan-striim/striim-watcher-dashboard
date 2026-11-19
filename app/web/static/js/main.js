// Orchestrator: tab switching, top-bar wiring, auto-refresh, and the one cross-tab hand-off
// (Applications row click -> History & Trends tab, pre-filtered to that app).
(() => {
  const appEl = document.getElementById("app");
  const nodeTrendDaysBack = parseInt(appEl.dataset.nodeTrendDaysBack, 10);
  const appHistoryDefaultDays = parseInt(appEl.dataset.appHistoryDefaultDays, 10);
  const autoRefreshSeconds = parseInt(appEl.dataset.autoRefreshSeconds, 10);

  let activeTab = "node-health";
  let refreshTimer = null;

  function setActiveTab(tab) {
    activeTab = tab;
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === `tab-${tab}`);
    });
  }

  function setLastUpdated() {
    document.getElementById("last-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }

  function selectValue(id, fallback) {
    const el = document.getElementById(id);
    const val = parseInt(el.value, 10);
    return Number.isFinite(val) ? val : fallback;
  }

  // Re-reads AppSummary's current app list into the History tab's picker. Called after any
  // load that could have changed which apps exist in the response (initial load, or the
  // Applications tab's own lookback range changing) — not after every History-tab-local
  // change, which only needs AppHistory.loadHistoryFor.
  async function repopulateHistoryAppOptions() {
    const names = AppSummary.appNames();
    const select = document.getElementById("history-app-select");
    const selected = AppHistory.populateAppSelect(names, select.value);
    const daysBack = selectValue("history-range", appHistoryDefaultDays);
    await AppHistory.loadHistoryFor(selected, daysBack);
  }

  async function refreshAll() {
    // Node Health and Applications are independent panels, each handling its own fetch
    // errors internally (see nodeHealth.js/appSummary.js) — allSettled here is belt-and-
    // braces, not load-bearing, but means one panel throwing something *unexpected* still
    // can't stop the other from refreshing.
    await Promise.allSettled([
      NodeHealth.load(selectValue("node-range", nodeTrendDaysBack)),
      AppSummary.load(selectValue("apps-range", nodeTrendDaysBack)),
    ]);
    await repopulateHistoryAppOptions();
    setLastUpdated();
  }

  function scheduleAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    const enabled = document.getElementById("auto-refresh-toggle").checked;
    if (enabled && autoRefreshSeconds > 0) {
      refreshTimer = setInterval(refreshAll, autoRefreshSeconds * 1000);
    }
  }

  function wireTopbar() {
    document.getElementById("cluster-name-badge").textContent = appEl.dataset.clusterName;
    document.getElementById("refresh-now").addEventListener("click", refreshAll);
    document.getElementById("auto-refresh-toggle").addEventListener("change", scheduleAutoRefresh);
  }

  function wireTabs() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
    });
  }

  function initLookbackSelects() {
    document.getElementById("node-range").value = String(nodeTrendDaysBack);
    document.getElementById("apps-range").value = String(nodeTrendDaysBack);
    document.getElementById("node-range").addEventListener("change", (e) => {
      NodeHealth.load(parseInt(e.target.value, 10)).then(setLastUpdated);
    });
    document.getElementById("apps-range").addEventListener("change", (e) => {
      AppSummary.load(parseInt(e.target.value, 10))
        .then(repopulateHistoryAppOptions)
        .then(setLastUpdated);
    });
  }

  function wireHistoryControls() {
    document.getElementById("history-app-select").addEventListener("change", (e) => {
      const daysBack = selectValue("history-range", appHistoryDefaultDays);
      AppHistory.loadHistoryFor(e.target.value, daysBack);
    });
    document.getElementById("history-range").addEventListener("change", (e) => {
      const select = document.getElementById("history-app-select");
      AppHistory.loadHistoryFor(select.value, parseInt(e.target.value, 10));
    });
  }

  function wireAppSelectHandoff() {
    window.addEventListener("select-app", (e) => {
      const select = document.getElementById("history-app-select");
      select.value = e.detail.appName;
      const daysBack = selectValue("history-range", appHistoryDefaultDays);
      AppHistory.loadHistoryFor(e.detail.appName, daysBack);
      setActiveTab("history");
    });
  }

  wireTopbar();
  wireTabs();
  initLookbackSelects();
  AppSummary.wireFilters();
  wireHistoryControls();
  wireAppSelectHandoff();
  refreshAll();
  scheduleAutoRefresh();
})();
