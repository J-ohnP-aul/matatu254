(() => {
  const root = document.getElementById('trip-dashboard');
  if (!root) return;
  const trackingUrl = root.dataset.trackingUrl;
  const passengersUrl = root.dataset.passengersUrl;
  const pingUrl = root.dataset.pingUrl;
  const refreshStatus = document.getElementById('crew-refresh-status');
  const stageRows = [...document.querySelectorAll('.stop-row[data-stage-order]')];
  const stages = [...new Map(stageRows.map((row) => [row.dataset.stageOrder, {
    order: Number(row.dataset.stageOrder),
    name: row.querySelector('.stop-name')?.textContent.trim() || '',
    lat: Number(row.dataset.stageLat),
    lon: Number(row.dataset.stageLon),
  }])).values()].filter((stage) => Number.isFinite(stage.lat) && Number.isFinite(stage.lon));
  const path = document.getElementById('crew-map-path');
  const stageLayer = document.getElementById('crew-map-stages');
  const vehicle = document.getElementById('crew-map-vehicle');
  const svgNs = 'http://www.w3.org/2000/svg';
  let watchId = null;

  function mapCoords(latitude, longitude) {
    if (!stages.length) return null;
    const points = [...stages];
    if (Number.isFinite(latitude) && Number.isFinite(longitude)) points.push({ lat: latitude, lon: longitude });
    const minLat = Math.min(...points.map((item) => item.lat));
    const maxLat = Math.max(...points.map((item) => item.lat));
    const minLon = Math.min(...points.map((item) => item.lon));
    const maxLon = Math.max(...points.map((item) => item.lon));
    const latRange = maxLat - minLat || .001;
    const lonRange = maxLon - minLon || .001;
    const project = (item) => ({
      x: 36 + ((item.lon - minLon) / lonRange) * 528,
      y: 30 + ((maxLat - item.lat) / latRange) * 280,
    });
    return {
      stages: stages.map((stage) => ({ ...stage, ...project(stage) })),
      vehicle: Number.isFinite(latitude) && Number.isFinite(longitude) ? project({ lat: latitude, lon: longitude }) : null,
    };
  }

  function drawMap(latitude = null, longitude = null, currentOrder = null) {
    const mapped = mapCoords(latitude, longitude);
    if (!mapped) return;
    path.setAttribute('points', mapped.stages.map((item) => `${item.x},${item.y}`).join(' '));
    stageLayer.replaceChildren();
    mapped.stages.forEach((item) => {
      const dot = document.createElementNS(svgNs, 'circle');
      dot.setAttribute('cx', item.x);
      dot.setAttribute('cy', item.y);
      dot.setAttribute('r', 8);
      dot.setAttribute('class', `route-map-stage${currentOrder !== null && item.order <= currentOrder ? ' is-complete' : ''}`);
      const label = document.createElementNS(svgNs, 'text');
      label.setAttribute('x', item.x);
      label.setAttribute('y', Math.max(20, item.y - 16));
      label.setAttribute('class', 'route-map-label');
      label.textContent = item.name;
      stageLayer.append(dot, label);
    });
    if (mapped.vehicle) {
      vehicle.setAttribute('cx', mapped.vehicle.x);
      vehicle.setAttribute('cy', mapped.vehicle.y);
      vehicle.hidden = false;
    }
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }
  function distanceText(value) {
    return value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${Math.round(value)} m`;
  }
  function durationText(value) {
    const minutes = Math.max(0, Math.round(value));
    return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60} min` : `${minutes} min`;
  }
  function pulse(node) {
    node.classList.remove('is-changed');
    requestAnimationFrame(() => node.classList.add('is-changed'));
  }
  function updateCounts(data) {
    const total = document.getElementById('onboard-count');
    if (total.textContent !== String(data.total_passengers)) {
      total.textContent = data.total_passengers;
      pulse(total);
    }
    stageRows.forEach((row) => {
      const value = String(data.alighting_counts[row.dataset.stageOrder] || 0);
      row.querySelectorAll('[data-alighting-count]').forEach((count) => {
        if (count.textContent.trim() !== value) {
          count.textContent = value;
          pulse(count);
        }
      });
      const order = Number(row.dataset.stageOrder);
      row.classList.toggle('is-complete', data.current_stage_order !== null && order <= data.current_stage_order);
      row.classList.toggle('is-next', data.next_stage_order !== null && order === data.next_stage_order);
      row.querySelector('.next-stop-badge')?.toggleAttribute('hidden', order !== data.next_stage_order);
    });
  }

  async function refreshTrip() {
    try {
      const response = await fetch(trackingUrl, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      if (!response.ok) throw new Error(`Trip status request failed: ${response.status}`);
      const data = await response.json();
      setText('current-stage', data.current_stage || 'Waiting for GPS');
      setText('next-stage', data.next_stage || 'Destination reached');
      setText('vehicle-latitude', data.vehicle_latitude === null ? '—' : data.vehicle_latitude.toFixed(5));
      setText('vehicle-longitude', data.vehicle_longitude === null ? '—' : data.vehicle_longitude.toFixed(5));
      setText('vehicle-speed', data.speed_kmh === null ? '—' : `${Math.round(data.speed_kmh)} km/h`);
      const progress = Math.min(100, Math.max(0, Math.round(data.progress_percent || 0)));
      setText('progress-percent', `${progress}%`);
      const progressBar = document.getElementById('trip-progress');
      progressBar.setAttribute('aria-valuenow', progress);
      document.getElementById('trip-progress-fill').style.transform = `scaleX(${progress / 100})`;
      const nextDistance = data.next_stage_distance_m;
      setText('next-stage-distance', nextDistance === null ? 'Waiting for GPS' : distanceText(nextDistance));
      setText('next-stage-eta', data.next_stage_duration_minutes === null ? '—' : durationText(data.next_stage_duration_minutes));
      setText('trip-remaining-summary', data.distance_m === null
        ? (data.at_destination ? 'Trip destination reached' : 'Waiting for a GPS position')
        : `${distanceText(data.distance_m)} · about ${durationText(data.duration_minutes)} to ${data.destination}`);
      drawMap(data.vehicle_latitude, data.vehicle_longitude, data.current_stage_order);
      updateCounts(data);

      const alert = document.getElementById('next-stop-alert');
      alert.hidden = !data.next_stage;
      alert.classList.toggle('is-calm', data.next_stage_distance_m === null || data.next_stage_distance_m > 1200);
      const alighting = data.alighting_counts[String(data.next_stage_order)] || 0;
      setText('next-stop-alert-text', `${data.next_stage_distance_m !== null && data.next_stage_distance_m <= 1200 ? 'Approaching' : 'Next stop:'} ${data.next_stage} · ${alighting} alighting${data.next_stage_distance_m !== null ? ` · ${distanceText(data.next_stage_distance_m)}` : ''}`);
      const freshness = document.getElementById('gps-freshness');
      freshness.classList.toggle('is-stale', data.gps_stale);
      freshness.textContent = data.gps_age_seconds === null ? 'Waiting for the first vehicle GPS update'
        : data.gps_stale ? 'Vehicle location delayed · showing the latest position' : 'Vehicle location live';
      refreshStatus.textContent = 'Updated just now';
    } catch (_) {
      refreshStatus.textContent = 'Live counts paused. Showing the last update.';
    }
  }

  async function refreshPassengers() {
    try {
      const response = await fetch(passengersUrl, { headers: { Accept: 'text/html' }, cache: 'no-store' });
      if (!response.ok) throw new Error(`Passenger list request failed: ${response.status}`);
      document.getElementById('passenger-list').innerHTML = await response.text();
    } catch (_) {
      const panel = document.getElementById('passenger-list');
      panel.querySelector('[data-passenger-error]')?.remove();
      const error = document.createElement('p');
      error.className = 'error-state';
      error.dataset.passengerError = '';
      error.textContent = 'Passenger list could not refresh. The last list is still shown.';
      panel.append(error);
    }
  }

  function setGpsState(active, message) {
    document.getElementById('start-tracking-btn').hidden = active;
    document.getElementById('stop-tracking-btn').hidden = !active;
    setText('tracking-status', message);
  }
  function stopTracking() {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null;
    setGpsState(false, 'Location sharing stopped');
  }
  document.getElementById('start-tracking-btn').addEventListener('click', () => {
    if (!navigator.geolocation) return setGpsState(false, 'GPS is unavailable in this browser.');
    if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) return setGpsState(false, 'GPS needs HTTPS or localhost.');
    setGpsState(true, 'Requesting GPS permission…');
    watchId = navigator.geolocation.watchPosition(async (position) => {
      setGpsState(true, 'Location shared · updated just now');
      try {
        const response = await fetch(pingUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            recorded_at: new Date(position.timestamp).toISOString(),
          }),
        });
        if (!response.ok) throw new Error('GPS update rejected');
        refreshTrip();
      } catch (_) { setGpsState(true, 'Could not send location update. Retrying…'); }
    }, (error) => {
      stopTracking();
      setGpsState(false, error.code === error.PERMISSION_DENIED ? 'Location permission was denied.' : 'Could not get a GPS fix.');
    }, { enableHighAccuracy: true, maximumAge: 3000, timeout: 15000 });
  });
  document.getElementById('stop-tracking-btn').addEventListener('click', stopTracking);

  drawMap();
  refreshTrip();
  refreshPassengers();
  const trackingTimer = window.setInterval(refreshTrip, 5000);
  const passengerTimer = window.setInterval(refreshPassengers, 10000);
  window.addEventListener('pagehide', () => {
    window.clearInterval(trackingTimer);
    window.clearInterval(passengerTimer);
    stopTracking();
  }, { once: true });
})();
