import { createLiveTrackingMap } from './map/index.js';
import { createTransport } from './transport/index.js';

(async () => {
  const card = document.getElementById('journey-tracking-card');
  if (!card) return;

  const trackingUrl = card.dataset.trackingUrl;
  const routeDataUrl = card.dataset.routeDataUrl;
  const latestPositionUrl = card.dataset.latestPositionUrl;
  const tripId = card.dataset.tripId;
  const journeyId = card.dataset.journeyId;
  const locationTransport = card.dataset.locationTransport || 'polling';
  const stageRows = [...document.querySelectorAll('#route-stages [data-stage-order]')];
  const freshness = document.getElementById('gps-freshness');
  let lastNotificationId = Number(document.getElementById('destination-alert-text')?.dataset.notificationId || 0);

  function updateRoute(currentOrder, nextOrder) {
    stageRows.forEach((row) => {
      const order = Number(row.dataset.stageOrder);
      const current = currentOrder !== null && order === currentOrder;
      const complete = currentOrder !== null && order < currentOrder;
      const next = nextOrder !== null && order === nextOrder;
      row.classList.toggle('is-complete', complete || current);
      row.classList.toggle('is-current', current);
      row.classList.toggle('is-next', next);
      const badge = row.querySelector('.route-stop-badge');
      if (badge) badge.hidden = !next;
      const icon = row.querySelector('.route-stop-icon');
      if (icon) icon.classList.toggle('is-complete', complete || current);
    });
  }

  function formatDistance(meters) {
    return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${Math.round(meters)} m`;
  }
  function formatMinutes(value) {
    const minutes = Math.max(0, Math.round(value));
    return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60} min` : `${minutes} min`;
  }
  function updateFreshness(stale, age) {
    if (!freshness) return;
    freshness.classList.toggle('is-stale', stale);
    freshness.textContent = age === null
      ? 'Waiting for the vehicle’s first GPS update'
      : stale ? `Vehicle location delayed · last update ${formatMinutes(age / 60)} ago` : 'Vehicle location live · updated just now';
  }
  function updateProgress(value) {
    const percent = Math.min(100, Math.max(0, Math.round(value || 0)));
    const percentEl = document.getElementById('progress-percent');
    if (percentEl) percentEl.textContent = `${percent}%`;
    const progress = document.getElementById('journey-progress');
    if (progress) progress.setAttribute('aria-valuenow', percent);
    const fill = document.getElementById('journey-progress-fill');
    if (fill) fill.style.transform = `scaleX(${percent / 100})`;
  }

  const initialPercent = Number(document.getElementById('journey-progress')?.getAttribute('aria-valuenow')) || 0;
  updateProgress(initialPercent);

  // Initialize interactive LiveTrackingMap
  let liveMap = null;
  try {
    liveMap = await createLiveTrackingMap('map', {
      tripId,
      journeyId,
      routeDataUrl,
      latestPositionUrl,
      locationTransport,
      interpolationDuration: 3000,
      lowSpeedThreshold: 3,
      onETAUpdate: (eta) => {
        if (!eta) return;
        if (eta.formattedDistance) {
          const distEl = document.getElementById('remaining-distance');
          if (distEl && distEl.textContent !== 'Waiting for GPS') {
            distEl.textContent = eta.formattedDistance;
          }
        }
        if (eta.formattedDuration) {
          const etaEl = document.getElementById('remaining-eta');
          if (etaEl && etaEl.textContent !== 'Waiting for GPS') {
            etaEl.textContent = eta.formattedDuration;
          }
        }
      },
      onStageChange: (stage, status) => {
        if (status === 'complete' || status === 'current') {
          updateRoute(stage.sequenceOrder || stage.sequence_order, (stage.sequenceOrder || stage.sequence_order) + 1);
        }
      }
    });
  } catch (err) {
    console.error('Failed to initialize live map:', err);
  }

  async function refreshJourney() {
    try {
      const response = await fetch(trackingUrl, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (!response.ok) throw new Error(`Journey tracking request failed: ${response.status}`);
      const data = await response.json();
      const status = document.getElementById('journey-status');
      if (status) {
        status.textContent = data.status;
        status.className = `trip-status${data.status === 'Arrived' ? ' badge-success' : data.status === 'Approaching' ? ' badge-warning' : ''}`;
      }
      const curStage = document.getElementById('current-stage');
      if (curStage) curStage.textContent = data.current_stage || 'Waiting for GPS';
      const nxtStage = document.getElementById('next-stage');
      if (nxtStage) nxtStage.textContent = data.next_stage || 'At destination';
      updateProgress(data.progress_percent);
      updateRoute(data.current_stage_order, data.next_stage_order);
      updateFreshness(data.gps_stale, data.gps_age_seconds);

      // Feed GPS fix directly to live map for continuous smooth navigation
      if (liveMap && Number.isFinite(data.vehicle_latitude) && Number.isFinite(data.vehicle_longitude)) {
        liveMap.processGPSFix({
          latitude: data.vehicle_latitude,
          longitude: data.vehicle_longitude,
          timestamp: data.last_ping_at,
          speed: data.speed_kmh
        });
      }

      const alert = document.getElementById('destination-alert');
      if (alert) alert.classList.toggle('is-approaching', data.status === 'Approaching');
      const alertText = document.getElementById('destination-alert-text');
      if (alertText && data.latest_notification && data.latest_notification.id > lastNotificationId) {
        alertText.textContent = data.latest_notification.message;
        lastNotificationId = data.latest_notification.id;
        alertText.dataset.notificationId = lastNotificationId;
        navigator.vibrate?.(10);
      }
      if (data.distance_m === null) {
        const distEl = document.getElementById('remaining-distance');
        if (distEl) distEl.textContent = data.at_destination ? '0 m' : 'Waiting for GPS';
        const etaEl = document.getElementById('remaining-eta');
        if (etaEl) etaEl.textContent = data.at_destination ? 'Arrived' : 'Waiting for GPS';
      } else {
        const distEl = document.getElementById('remaining-distance');
        if (distEl) distEl.textContent = formatDistance(data.distance_m);
        const etaEl = document.getElementById('remaining-eta');
        if (etaEl) etaEl.textContent = formatMinutes(data.duration_minutes);
      }
      const endForm = document.getElementById('end-journey-form');
      if (endForm) endForm.hidden = data.status !== 'Arrived';
      const refNote = document.getElementById('tracking-refresh-note');
      if (refNote) refNote.hidden = ['Arrived', 'Ended'].includes(data.status);
    } catch (error) {
      if (freshness) {
        freshness.textContent = 'Live updates paused. Showing the latest route information.';
        freshness.classList.add('is-stale');
      }
    }
  }

  let timer = null;
  let refreshing = false;
  async function pollJourney() {
    if (refreshing || document.hidden || !navigator.onLine) return;
    refreshing = true;
    try { await refreshJourney(); } finally { refreshing = false; }
    if (!document.hidden) timer = window.setTimeout(pollJourney, 3500);
  }
  pollJourney();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) window.clearTimeout(timer);
    else pollJourney();
  });
  window.addEventListener('online', pollJourney);
  window.addEventListener('pagehide', () => {
    window.clearTimeout(timer);
    liveMap?.destroy();
  }, { once: true });
})();
