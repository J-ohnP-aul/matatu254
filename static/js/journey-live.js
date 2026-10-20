(() => {
  const card = document.getElementById('journey-tracking-card');
  if (!card) return;
  const trackingUrl = card.dataset.trackingUrl;
  const stageRows = [...document.querySelectorAll('#route-stages [data-stage-order]')];
  const mapPath = document.getElementById('route-map-path');
  const mapStages = document.getElementById('route-map-stages');
  const vehicle = document.getElementById('route-map-vehicle');
  const freshness = document.getElementById('gps-freshness');
  const ns = 'http://www.w3.org/2000/svg';
  let lastNotificationId = Number(document.getElementById('destination-alert-text').dataset.notificationId || 0);

  const stagePoints = stageRows.map((row) => ({
    row,
    order: Number(row.dataset.stageOrder),
    name: row.dataset.stageName,
    lat: Number(row.dataset.stageLat),
    lon: Number(row.dataset.stageLon),
  })).filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon));

  function coordinatesFor(vehicleLat, vehicleLon) {
    // Keep the route projection fixed so the map does not zoom/jump as the
    // vehicle moves beyond the stage bounds.
    const points = stagePoints;
    const minLat = Math.min(...points.map((point) => point.lat));
    const maxLat = Math.max(...points.map((point) => point.lat));
    const minLon = Math.min(...points.map((point) => point.lon));
    const maxLon = Math.max(...points.map((point) => point.lon));
    const latRange = maxLat - minLat || .001;
    const lonRange = maxLon - minLon || .001;
    return {
      stagePoints: stagePoints.map((point) => ({
        ...point,
        x: 36 + ((point.lon - minLon) / lonRange) * 528,
        y: 30 + ((maxLat - point.lat) / latRange) * 280,
      })),
      vehicle: Number.isFinite(vehicleLat) && Number.isFinite(vehicleLon) ? {
        x: 36 + ((vehicleLon - minLon) / lonRange) * 528,
        y: 30 + ((maxLat - vehicleLat) / latRange) * 280,
      } : null,
    };
  }

  function drawMap(vehicleLat = null, vehicleLon = null, currentOrder = null) {
    if (!mapPath || !mapStages || stagePoints.length === 0) return;
    const mapped = coordinatesFor(vehicleLat, vehicleLon);
    mapPath.setAttribute('points', mapped.stagePoints.map((point) => `${point.x},${point.y}`).join(' '));
    mapStages.replaceChildren();
    mapped.stagePoints.forEach((point, index) => {
      const dot = document.createElementNS(ns, 'circle');
      dot.setAttribute('cx', point.x);
      dot.setAttribute('cy', point.y);
      dot.setAttribute('r', index === mapped.stagePoints.length - 1 ? 10 : 8);
      dot.setAttribute('class', `route-map-stage${currentOrder !== null && point.order <= currentOrder ? ' is-complete' : ''}${index === mapped.stagePoints.length - 1 ? ' is-destination' : ''}`);
      const label = document.createElementNS(ns, 'text');
      label.setAttribute('x', point.x);
      label.setAttribute('y', Math.max(20, point.y - 18));
      label.setAttribute('class', 'route-map-label');
      label.textContent = point.name;
      mapStages.append(dot, label);
    });
    if (mapped.vehicle) {
      vehicle.setAttribute('cx', mapped.vehicle.x);
      vehicle.setAttribute('cy', mapped.vehicle.y);
      vehicle.hidden = false;
    }
  }

  function updateRoute(currentOrder, nextOrder) {
    stageRows.forEach((row) => {
      const order = Number(row.dataset.stageOrder);
      const current = currentOrder !== null && order === currentOrder;
      const complete = currentOrder !== null && order < currentOrder;
      const next = nextOrder !== null && order === nextOrder;
      row.classList.toggle('is-complete', complete || current);
      row.classList.toggle('is-current', current);
      row.classList.toggle('is-next', next);
      row.querySelector('.route-stop-badge').hidden = !next;
      row.querySelector('.route-stop-icon').classList.toggle('is-complete', complete || current);
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
    freshness.classList.toggle('is-stale', stale);
    freshness.textContent = age === null
      ? 'Waiting for the vehicle’s first GPS update'
      : stale ? `Vehicle location delayed · last update ${formatMinutes(age / 60)} ago` : 'Vehicle location live · updated just now';
  }
  function updateProgress(value) {
    const percent = Math.min(100, Math.max(0, Math.round(value || 0)));
    document.getElementById('progress-percent').textContent = `${percent}%`;
    const progress = document.getElementById('journey-progress');
    progress.setAttribute('aria-valuenow', percent);
    document.getElementById('journey-progress-fill').style.transform = `scaleX(${percent / 100})`;
  }

  const initialPercent = Number(document.getElementById('journey-progress').getAttribute('aria-valuenow')) || 0;
  updateProgress(initialPercent);
  drawMap();

  async function refreshJourney() {
    try {
      const response = await fetch(trackingUrl, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (!response.ok) throw new Error(`Journey tracking request failed: ${response.status}`);
      const data = await response.json();
      const status = document.getElementById('journey-status');
      status.textContent = data.status;
      status.className = `trip-status${data.status === 'Arrived' ? ' badge-success' : data.status === 'Approaching' ? ' badge-warning' : ''}`;
      document.getElementById('current-stage').textContent = data.current_stage || 'Waiting for GPS';
      document.getElementById('next-stage').textContent = data.next_stage || 'At destination';
      updateProgress(data.progress_percent);
      updateRoute(data.current_stage_order, data.next_stage_order);
      drawMap(data.vehicle_latitude, data.vehicle_longitude, data.current_stage_order);
      updateFreshness(data.gps_stale, data.gps_age_seconds);

      const alert = document.getElementById('destination-alert');
      alert.classList.toggle('is-approaching', data.status === 'Approaching');
      const alertText = document.getElementById('destination-alert-text');
      if (data.latest_notification && data.latest_notification.id > lastNotificationId) {
        alertText.textContent = data.latest_notification.message;
        lastNotificationId = data.latest_notification.id;
        alertText.dataset.notificationId = lastNotificationId;
        navigator.vibrate?.(10);
      }
      if (data.distance_m === null) {
        document.getElementById('remaining-distance').textContent = data.at_destination ? '0 m' : 'Waiting for GPS';
        document.getElementById('remaining-eta').textContent = data.at_destination ? 'Arrived' : 'Waiting for GPS';
      } else {
        document.getElementById('remaining-distance').textContent = formatDistance(data.distance_m);
        document.getElementById('remaining-eta').textContent = formatMinutes(data.duration_minutes);
      }
      document.getElementById('end-journey-form').hidden = data.status !== 'Arrived';
      document.getElementById('tracking-refresh-note').hidden = ['Arrived', 'Ended'].includes(data.status);
    } catch (error) {
      freshness.textContent = 'Live updates paused. Showing the latest route information.';
      freshness.classList.add('is-stale');
    }
  }

  let timer = null;
  let refreshing = false;
  async function pollJourney() {
    if (refreshing || document.hidden || !navigator.onLine) return;
    refreshing = true;
    try { await refreshJourney(); } finally { refreshing = false; }
    if (!document.hidden) timer = window.setTimeout(pollJourney, 5000);
  }
  pollJourney();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) window.clearTimeout(timer);
    else pollJourney();
  });
  window.addEventListener('online', pollJourney);
  window.addEventListener('pagehide', () => window.clearTimeout(timer), { once: true });
})();
