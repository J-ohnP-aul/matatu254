(() => {
  const root = document.getElementById('crew-dashboard-data');
  if (!root) return;
  const status = document.getElementById('crew-refresh-status');

  async function refreshCounts() {
    try {
      const response = await fetch(root.dataset.trackingUrl, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
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
        const nextCount = String(data.alighting_counts[order] || 0);
        if (Number(nextCount) > 0) occupiedStages += 1;
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
      status.textContent = 'Updated just now';
    } catch (_) {
      status.textContent = 'Live counts paused. Showing the last update.';
    }
  }
  refreshCounts();
  const timer = window.setInterval(refreshCounts, 10000);
  window.addEventListener('pagehide', () => window.clearInterval(timer), { once: true });
})();
