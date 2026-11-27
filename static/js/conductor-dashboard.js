(() => {
  const root = document.getElementById('crew-dashboard-data');
  if (!root) return;
  const status = document.getElementById('crew-refresh-status');
  const gpsStatus = document.getElementById('crew-gps-status');
  let controller = null;

  async function refreshCounts() {
    if (document.hidden) return;
    controller?.abort();
    controller = new AbortController();
    try {
      const response = await fetch(root.dataset.trackingUrl, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Crew count request failed: ${response.status}`);
      const data = await response.json();
      const total = document.getElementById('crew-total-count');
      const nextTotal = String(data.total_passengers);
      if (total.textContent !== nextTotal) {
        total.textContent = nextTotal;
        total.classList.remove('is-changed');
        requestAnimationFrame(() => total.classList.add('is-changed'));
      }
      const stageRows = Array.from(root.querySelectorAll('[data-stage-order]'));
      let occupiedStages = 0;
      stageRows.forEach((row) => {
        const order = row.dataset.stageOrder;
        const count = row.querySelector('[data-stage-count]');
        const numericCount = Number(data.alighting_counts[order] || 0);
        const nextCount = String(numericCount);
        const unit = row.querySelector('[data-stage-unit]');
        if (numericCount > 0) occupiedStages += 1;
        row.classList.toggle('is-empty', numericCount === 0);
        if (unit) unit.textContent = numericCount === 1 ? 'passenger' : 'passengers';
        if (count.textContent !== nextCount) {
          count.textContent = nextCount;
          count.classList.remove('is-changed');
          requestAnimationFrame(() => count.classList.add('is-changed'));
        }
      });
      const occupied = document.getElementById('crew-occupied-stage-count');
      if (occupied) occupied.textContent = String(occupiedStages);
      const arrived = document.getElementById('crew-arrived-count');
      if (arrived) arrived.textContent = String(data.arrived_passengers || 0);
      const gpsCopy = document.getElementById('crew-gps-copy');
      if (gpsStatus && gpsCopy) {
        const age = data.gps_age_seconds;
        gpsStatus.classList.toggle('is-stale', Boolean(data.gps_stale));
        gpsStatus.classList.toggle('is-live', age !== null && !data.gps_stale);
        gpsStatus.classList.toggle('is-waiting', age === null);
        const freshness = age === null
          ? 'Waiting for the first vehicle location update'
          : data.gps_stale
            ? `Vehicle location delayed · last update ${Math.floor(age / 60)} min ago`
            : `Vehicle location live · updated ${age < 60 ? 'just now' : `${Math.floor(age / 60)} min ago`}`;
        gpsCopy.textContent = freshness;
      }
      if (status) status.textContent = 'Live trip data · updated just now';
    } catch (error) {
      if (error.name === 'AbortError') return;
      if (status) status.textContent = 'Live updates paused · showing the last received counts';
    }
  }
  refreshCounts();
  const timer = window.setInterval(refreshCounts, 10000);
  document.addEventListener('visibilitychange', refreshCounts);
  window.addEventListener('pagehide', () => {
    window.clearInterval(timer);
    controller?.abort();
  }, { once: true });
})();
