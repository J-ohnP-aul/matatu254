import { createLiveTrackingMap } from './map/index.js';

(() => {
  const root = document.getElementById('trip-dashboard');
  if (!root) return;
  const trackingUrl = root.dataset.trackingUrl;
  const passengersUrl = root.dataset.passengersUrl;
  const pingUrl = root.dataset.pingUrl;
  const routeUrl = root.dataset.routeUrl;
  const refreshStatus = document.getElementById('crew-refresh-status');
  const stageRows = [...document.querySelectorAll('.stop-row[data-stage-order]')];

  let watchId = null;
  let trackingRequested = false;
  let watchRetryTimer = null;
  let uploadRetryTimer = null;
  let uploadRunning = false;
  let wakeLock = null;
  let crewMap = null;

  const queueKey = `matatu254-trip-${root.dataset.tripId}-gps-queue`;
  const readQueue = () => {
    try { return JSON.parse(localStorage.getItem(queueKey) || '[]'); } catch (_) { return []; }
  };
  const writeQueue = (queue) => {
    try { localStorage.setItem(queueKey, JSON.stringify(queue.slice(-120))); } catch (_) {}
  };

  async function acquireWakeLock() {
    if ('wakeLock' in navigator && !wakeLock) {
      try {
        wakeLock = await navigator.wakeLock.request('screen');
        wakeLock.addEventListener('release', () => { wakeLock = null; });
      } catch (_) {
        // Optional feature; browser might deny if battery is critically low
      }
    }
  }

  function releaseWakeLock() {
    if (wakeLock) {
      wakeLock.release().catch(() => {});
      wakeLock = null;
    }
  }

  function queueFix(position) {
    const queue = readQueue();
    const fix = {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      speed: position.coords.speed != null ? position.coords.speed * 3.6 : null,
      bearing: position.coords.heading != null ? position.coords.heading : null,
      recorded_at: new Date(position.timestamp).toISOString()
    };
    queue.push(fix);
    writeQueue(queue);

    // Provide immediate zero-latency feedback on conductor's map
    if (crewMap) {
      crewMap.processGPSFix({
        latitude: fix.latitude,
        longitude: fix.longitude,
        speed: fix.speed,
        bearing: fix.bearing,
        timestamp: fix.recorded_at
      });
    }

    flushQueue();
  }

  async function flushQueue() {
    if (uploadRunning || !navigator.onLine) return;
    uploadRunning = true;
    try {
      let queue = readQueue();
      if (!queue.length) return;

      // Prioritize sending the freshest fix first so the live server position updates immediately
      if (queue.length > 1) {
        const latestFix = queue[queue.length - 1];
        try {
          const resp = await fetch(pingUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(latestFix)
          });
          if (resp.ok) {
            queue.pop();
            writeQueue(queue);
          }
        } catch (_) {}
      }

      // Flush remaining historical fixes
      while (queue.length && navigator.onLine && trackingRequested) {
        const response = await fetch(pingUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(queue[0])
        });
        if (!response.ok) break;
        queue.shift();
        writeQueue(queue);
      }
      if (!queue.length) refreshTrip();
    } catch (_) {
      setGpsState(true, 'Connection interrupted · location will sync automatically');
    } finally {
      uploadRunning = false;
      if (trackingRequested && readQueue().length && uploadRetryTimer === null) {
        uploadRetryTimer = window.setTimeout(() => {
          uploadRetryTimer = null;
          flushQueue();
        }, 4000);
      }
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
    if (total && total.textContent !== String(data.total_passengers)) {
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
      if (progressBar) progressBar.setAttribute('aria-valuenow', progress);
      const fill = document.getElementById('trip-progress-fill');
      if (fill) fill.style.transform = `scaleX(${progress / 100})`;
      const nextDistance = data.next_stage_distance_m;
      setText('next-stage-distance', nextDistance === null ? 'Waiting for GPS' : distanceText(nextDistance));
      setText('next-stage-eta', data.next_stage_duration_minutes === null ? '—' : durationText(data.next_stage_duration_minutes));
      setText('trip-remaining-summary', data.distance_m === null
        ? (data.at_destination ? 'Trip destination reached' : 'Waiting for a GPS position')
        : `${distanceText(data.distance_m)} · about ${durationText(data.duration_minutes)} to ${data.destination}`);

      // Feed GPS fix to map if not already fed locally
      if (crewMap && !watchId && Number.isFinite(data.vehicle_latitude) && Number.isFinite(data.vehicle_longitude)) {
        crewMap.processGPSFix({
          latitude: data.vehicle_latitude,
          longitude: data.vehicle_longitude,
          timestamp: data.last_ping_at,
          speed: data.speed_kmh
        });
      }

      updateCounts(data);

      const alert = document.getElementById('next-stop-alert');
      if (alert) {
        alert.hidden = !data.next_stage;
        alert.classList.toggle('is-calm', data.next_stage_distance_m === null || data.next_stage_distance_m > 1200);
      }
      const alighting = data.alighting_counts[String(data.next_stage_order)] || 0;
      setText('next-stop-alert-text', `${data.next_stage_distance_m !== null && data.next_stage_distance_m <= 1200 ? 'Approaching' : 'Next stop:'} ${data.next_stage} · ${alighting} alighting${data.next_stage_distance_m !== null ? ` · ${distanceText(data.next_stage_distance_m)}` : ''}`);
      const freshness = document.getElementById('gps-freshness');
      if (freshness) {
        freshness.classList.toggle('is-stale', data.gps_stale);
        freshness.textContent = data.gps_age_seconds === null ? 'Waiting for the first vehicle GPS update'
          : data.gps_stale ? 'Vehicle location delayed · showing the latest position' : 'Vehicle location live';
      }
      if (refreshStatus) refreshStatus.textContent = 'Updated just now';
    } catch (_) {
      if (refreshStatus) refreshStatus.textContent = 'Live counts paused. Showing the last update.';
    }
  }

  async function refreshPassengers() {
    try {
      const response = await fetch(passengersUrl, { headers: { Accept: 'text/html' }, cache: 'no-store' });
      if (!response.ok) throw new Error(`Passenger list request failed: ${response.status}`);
      document.getElementById('passenger-list').innerHTML = await response.text();
    } catch (_) {
      const panel = document.getElementById('passenger-list');
      if (panel) {
        panel.querySelector('[data-passenger-error]')?.remove();
        const error = document.createElement('p');
        error.className = 'error-state';
        error.dataset.passengerError = '';
        error.textContent = 'Passenger list could not refresh. The last list is still shown.';
        panel.append(error);
      }
    }
  }

  function setGpsState(active, message) {
    const startBtn = document.getElementById('start-tracking-btn');
    const stopBtn = document.getElementById('stop-tracking-btn');
    if (startBtn) startBtn.hidden = active;
    if (stopBtn) stopBtn.hidden = !active;
    setText('tracking-status', message);
  }

  function stopTracking() {
    trackingRequested = false;
    try { sessionStorage.removeItem(`matatu254-trip-${root.dataset.tripId}-tracking`); } catch (_) {}
    if (watchId !== null) {
      navigator.geolocation.clearWatch(watchId);
      watchId = null;
    }
    if (watchRetryTimer !== null) window.clearTimeout(watchRetryTimer);
    if (uploadRetryTimer !== null) window.clearTimeout(uploadRetryTimer);
    watchRetryTimer = null;
    uploadRetryTimer = null;
    releaseWakeLock();
    setGpsState(false, 'Location sharing stopped');
  }

  function startTracking() {
    if (!navigator.geolocation) return setGpsState(false, 'GPS is unavailable in this browser.');
    if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
      return setGpsState(false, 'GPS needs HTTPS or localhost.');
    }
    if (watchId !== null) return;
    trackingRequested = true;
    try { sessionStorage.setItem(`matatu254-trip-${root.dataset.tripId}-tracking`, 'true'); } catch (_) {}
    setGpsState(true, 'Acquiring GPS fix…');
    acquireWakeLock();

    watchId = navigator.geolocation.watchPosition((position) => {
      setGpsState(true, navigator.onLine ? 'Location shared · updated just now' : 'Offline · saving location to sync');
      queueFix(position);
    }, (error) => {
      if (error.code === error.PERMISSION_DENIED) {
        trackingRequested = false;
        try { sessionStorage.removeItem(`matatu254-trip-${root.dataset.tripId}-tracking`); } catch (_) {}
        if (watchId !== null) {
          navigator.geolocation.clearWatch(watchId);
          watchId = null;
        }
        releaseWakeLock();
        setGpsState(false, 'Location permission was denied.');
        return;
      }
      // For TIMEOUT or POSITION_UNAVAILABLE, keep watch active or cleanly restart
      setGpsState(true, 'GPS signal weak · searching for satellites…');
      if (trackingRequested && watchRetryTimer === null) {
        watchRetryTimer = window.setTimeout(() => {
          watchRetryTimer = null;
          if (trackingRequested && watchId !== null) {
            navigator.geolocation.clearWatch(watchId);
            watchId = null;
            startTracking();
          }
        }, 8000);
      }
    }, { enableHighAccuracy: true, maximumAge: 4000, timeout: 10000 });
  }

  document.getElementById('start-tracking-btn')?.addEventListener('click', startTracking);
  document.getElementById('stop-tracking-btn')?.addEventListener('click', stopTracking);
  window.addEventListener('online', flushQueue);

  // Initialize interactive map for conductor
  (async () => {
    try {
      crewMap = await createLiveTrackingMap('crew-map', {
        tripId: root.dataset.tripId,
        routeDataUrl: routeUrl,
        interpolationDuration: 3000,
        lowSpeedThreshold: 3
      });
    } catch (e) {
      console.warn('Conductor live map initialization failed:', e);
    }
  })();

  refreshTrip();
  refreshPassengers();

  let trackingTimer = null;
  let passengerTimer = null;
  let trackingPollBusy = false;
  let passengerPollBusy = false;

  async function pollTracking() {
    if (trackingPollBusy || document.hidden || !navigator.onLine) return;
    trackingPollBusy = true;
    try { await refreshTrip(); } finally { trackingPollBusy = false; }
    if (!document.hidden) trackingTimer = window.setTimeout(pollTracking, 4000);
  }

  async function pollPassengers() {
    if (passengerPollBusy || document.hidden || !navigator.onLine) return;
    passengerPollBusy = true;
    try { await refreshPassengers(); } finally { passengerPollBusy = false; }
    if (!document.hidden) passengerTimer = window.setTimeout(pollPassengers, 10000);
  }

  pollTracking();
  pollPassengers();

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearTimeout(trackingTimer);
      clearTimeout(passengerTimer);
    } else {
      if (trackingRequested) acquireWakeLock();
      pollTracking();
      pollPassengers();
      flushQueue();
    }
  });

  window.addEventListener('online', () => { pollTracking(); pollPassengers(); });
  window.addEventListener('pagehide', () => {
    window.clearTimeout(trackingTimer);
    window.clearTimeout(passengerTimer);
    releaseWakeLock();
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null;
    crewMap?.destroy();
  }, { once: true });

  function resumeTracking() {
    try {
      if (sessionStorage.getItem(`matatu254-trip-${root.dataset.tripId}-tracking`) === 'true') {
        startTracking();
      }
    } catch (_) {}
  }
  resumeTracking();
  window.addEventListener('pageshow', resumeTracking);
})();
