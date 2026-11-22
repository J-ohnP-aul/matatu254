/**
 * Stage board — feeds real /trips/live/ data into the home board cards.
 * Same freshness contract as the live map: a vehicle is "live" only when
 * the backend says it isn't stale; otherwise we show the honest age.
 */
(() => {
  const board = document.getElementById('stage-board');
  const updated = document.getElementById('board-updated');
  if (!board) return;

  const POLL_MS = 6000;
  let timer = null;
  let controller = null;
  let busy = false;

  function ageText(seconds) {
    if (seconds === null || seconds === undefined) return null;
    if (seconds <= 5) return 'moving now';
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
    return `${Math.round(seconds / 3600)}h ago`;
  }

  function applyVehicles(vehicles) {
    const byRoute = new Map();
    for (const v of vehicles || []) {
      byRoute.set(String(v.route_id), v);
    }
    board.querySelectorAll('[data-board-live]').forEach((pill) => {
      const routeId = pill.dataset.boardLive;
      const text = pill.querySelector('[data-board-live-text]');
      const vehicle = byRoute.get(routeId);
      if (!text) return;
      pill.classList.remove('is-loading');
      if (vehicle && !vehicle.is_stale) {
        // Green pill: only when the backend says the vehicle is live.
        pill.classList.remove('is-quiet');
        text.textContent = `Live · ${ageText(vehicle.gps_age_seconds)}`;
      } else if (vehicle) {
        pill.classList.add('is-quiet');
        text.textContent = `On route · last seen ${ageText(vehicle.gps_age_seconds)}`;
      } else {
        pill.classList.add('is-quiet');
        text.textContent = 'No live data';
      }
    });
    if (updated) updated.textContent = 'board updated just now';
  }

  async function poll() {
    if (busy || document.hidden || !navigator.onLine) return;
    busy = true;
    controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(board.dataset.liveUrl, {
        cache: 'no-store',
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      applyVehicles((await response.json()).vehicles);
    } catch (_) {
      if (updated) updated.textContent = 'live data unavailable · showing saved routes';
    } finally {
      clearTimeout(timeout);
      controller = null;
      busy = false;
    }
  }

  function schedule() {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(async () => {
      await poll();
      schedule();
    }, POLL_MS);
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && navigator.onLine) poll();
  });
  window.addEventListener('online', () => poll());
  window.addEventListener('pagehide', () => {
    if (timer) window.clearTimeout(timer);
    if (controller) controller.abort();
  }, { once: true });

  poll();
  schedule();
})();
