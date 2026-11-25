(() => {
  const root = document.getElementById('passenger-management-data');
  if (!root) return;

  const list = document.getElementById('passenger-management-list');
  const status = document.getElementById('passenger-refresh-status');
  const total = document.getElementById('passenger-total-count');
  let controller = null;

  async function refreshPassengers() {
    if (document.hidden) return;
    controller?.abort();
    controller = new AbortController();

    try {
      const response = await fetch(root.dataset.passengersUrl, {
        headers: { Accept: 'text/html' },
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Passenger request failed: ${response.status}`);
      const markup = await response.text();
      const previousOpenStages = new Set(
        Array.from(list.querySelectorAll('[data-passenger-stage][open]'))
          .map((stage) => stage.dataset.passengerStage),
      );
      list.innerHTML = markup;
      list.querySelectorAll('[data-passenger-stage]').forEach((stage) => {
        stage.open = previousOpenStages.has(stage.dataset.passengerStage);
      });
      const refreshedTotal = list.querySelector('.passenger-list-panel > .section-heading .badge');
      if (refreshedTotal) {
        total.textContent = refreshedTotal.textContent.trim().split(' ')[0];
      }
      status.textContent = 'Live passenger list · updated just now';
    } catch (error) {
      if (error.name === 'AbortError') return;
      status.textContent = 'Passenger list could not refresh. The last update is still shown.';
    }
  }

  refreshPassengers();
  const timer = window.setInterval(refreshPassengers, 10000);
  document.addEventListener('visibilitychange', refreshPassengers);
  window.addEventListener('pagehide', () => {
    window.clearInterval(timer);
    controller?.abort();
  }, { once: true });
})();
