// Small shared helper so one panel's fetch failure shows an inline message in just that
// panel's container, rather than the caller needing to decide how to blank it out — used by
// every panel module below instead of letting an unhandled rejection blank the whole page.
const Ui = {
  showError(containerId, message) {
    const el = document.getElementById(containerId);
    if (el) el.innerHTML = `<p class="error-text">${message}</p>`;
  },
};

// Thin fetch wrapper over the backend's /api/* routes — one function per endpoint, no caching
// here (the backend already caches at the BigQuery-call layer).
const Api = (() => {
  async function getJSON(path) {
    const res = await fetch(path);
    if (!res.ok) {
      throw new Error(`${path} -> HTTP ${res.status}`);
    }
    return res.json();
  }

  return {
    clusters: () => getJSON("/api/meta/clusters"),
    health: () => getJSON("/api/meta/health"),

    nodeStatus: (daysBack) => getJSON(`/api/nodes/status?days_back=${daysBack}`),
    nodeTrend: (daysBack) => getJSON(`/api/nodes/trend?days_back=${daysBack}`),

    appSummary: (daysBack) => getJSON(`/api/apps/summary?days_back=${daysBack}`),
    appHistory: (appName, daysBack) =>
      getJSON(`/api/apps/${encodeURIComponent(appName)}/history?days_back=${daysBack}`),
    appUptime: (appName, daysBack) =>
      getJSON(`/api/apps/${encodeURIComponent(appName)}/uptime?days_back=${daysBack}`),

    clusterUptime: (daysBack) => getJSON(`/api/cluster/uptime?days_back=${daysBack}`),
  };
})();
