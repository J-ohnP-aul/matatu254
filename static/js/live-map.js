/**
 * Live Map — public fleet radar for Matatu254.
 *
 * Data sources (all real, nothing simulated):
 * - Routes/stages/geometry: embedded server-side JSON (routes-data).
 * - Vehicles: polling /trips/live/ (the same ActiveTrip cache the journey
 *   screens read). Markers glide between fixes (ease-out interpolation),
 *   update in place per trip_id, and never claim movement the backend
 *   doesn't back: stale vehicles are greyed and labeled.
 */
import { decodePolyline } from './map/map-matcher.js';

(() => {
  const screen = document.getElementById('live-map-screen');
  const container = document.getElementById('live-map');
  if (!screen || !container || !window.L) return;

  const vehiclesUrl = screen.dataset.vehiclesUrl;
  const routes = JSON.parse(document.getElementById('routes-data').textContent);
  const statusEl = document.getElementById('map-live-status');
  const sheet = document.getElementById('map-sheet');
  const sheetBody = document.getElementById('map-sheet-body');

  const POLL_MS = 4000;
  const GLIDE_MS = 3200;          // marker interpolation window between polls
  const STAGE_APPROACH_M = 2000;  // "approaching" radius for stage sheets

  /* ── Map setup ─────────────────────────────────────────────────────── */
  const map = L.map(container, {
    zoomControl: false,
    attributionControl: true,
    center: [-1.2921, 36.8219],
    zoom: 12,
  });
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.control.scale({ imperial: false }).addTo(map);

  const tileOptions = { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 };
  const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', tileOptions).addTo(map);
  let fallbackTiles = false;
  tiles.on('tileerror', () => {
    if (fallbackTiles) return;
    fallbackTiles = true;
    map.removeLayer(tiles);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', tileOptions).addTo(map);
  });

  /* ── Route layers (dim, never hide) ────────────────────────────────── */
  const routeLayers = new Map();   // route_id -> {line, group, color}
  const stageIndex = new Map();    // stage_id -> {stage, routes[]}
  const vehicleMarkers = new Map(); // trip_id -> marker (used by redrawRoutes)
  let activeRouteId = 'all';
  let selectedTripId = null;
  let latestVehicles = [];

  // Route colors come from tokens.css so the palette is themed in one place.
  const routePalette = [1, 2, 3, 4, 5, 6].map((n) =>
    getComputedStyle(document.documentElement).getPropertyValue(`--route-color-${n}`).trim(),
  );

  function styleFor(index) {
    return routePalette[index % routePalette.length];
  }

  routes.forEach((route, index) => {
    const color = styleFor(index);
    const group = L.layerGroup();
    const coords = route.geometry
      ? decodePolyline(route.geometry)
      : route.stages.map((s) => [s.latitude, s.longitude]);
    const line = coords.length >= 2
      ? L.polyline(coords, { color, weight: 5, opacity: 0.85 })
      : null;
    route.stages.forEach((stage) => {
      const marker = L.circleMarker([stage.latitude, stage.longitude], {
        radius: 6,
        color: '#FFFFFF',
        weight: 2.5,
        fillColor: color,
        fillOpacity: 1,
      });
      marker.bindTooltip(stage.name, { direction: 'top', offset: [0, -6] });
      marker.on('click', () => showStageSheet(stage, route));
      group.addLayer(marker);
      const entry = stageIndex.get(stage.id) || { stage, routes: [] };
      entry.routes.push(route);
      stageIndex.set(stage.id, entry);
    });
    routeLayers.set(route.id, { line, group, color });
    if (line) line.on('click', () => selectRoute(route.id));
  });

  function routeIsActive(routeId) {
    return activeRouteId === 'all' || String(routeId) === String(activeRouteId);
  }

  function redrawRoutes() {
    routeLayers.forEach(({ line, group }, id) => {
      const active = routeIsActive(id);
      // Dim unrelated corridors instead of removing them — context matters.
      if (line) {
        line.setStyle({ opacity: active ? 0.85 : 0.12 });
        if (!map.hasLayer(line)) line.addTo(map);
      }
      group.eachLayer((marker) => {
        marker.setStyle({ opacity: active ? 1 : 0.15, fillOpacity: active ? 1 : 0.15 });
      });
      if (!map.hasLayer(group)) group.addTo(map);
    });
    // Vehicles on dimmed routes fade too.
    vehicleMarkers.forEach((marker) => {
      const v = marker._data;
      if (v) marker.getElement()?.classList.toggle('is-dimmed', !routeIsActive(v.route_id));
    });
  }

  function fitRoutes() {
    const points = [];
    routeLayers.forEach(({ line, group }, id) => {
      if (!routeIsActive(id)) return;
      if (line) points.push(...line.getLatLngs());
      group.eachLayer((layer) => {
        if (layer.getLatLng) points.push(layer.getLatLng());
      });
    });
    if (points.length >= 2) {
      map.fitBounds(L.latLngBounds(points).pad(0.15));
    } else {
      map.setView([-1.2921, 36.8219], 12);
    }
  }

  redrawRoutes();
  fitRoutes();

  /* ── Route chips ───────────────────────────────────────────────────── */
  const chips = [...document.querySelectorAll('.map-chip')];
  chips.forEach((chip) => {
    chip.addEventListener('click', () => selectRoute(chip.dataset.routeId));
  });

  function selectRoute(routeId) {
    activeRouteId = routeId;
    chips.forEach((chip) => {
      chip.classList.toggle('is-active', String(chip.dataset.routeId) === String(routeId));
    });
    redrawRoutes();
    fitRoutes();
  }

  /* ── Vehicle markers: plate chip + live pulse, gliding fixes ───────── */

  function vehicleIcon(v, selected) {
    const stale = Boolean(v.is_stale);
    const plate = (v.registration || '').toUpperCase();
    return L.divIcon({
      className: '',
      html: `<div class="matatu-marker${stale ? ' is-stale' : ''}${selected ? ' is-selected' : ''}">
               <span class="matatu-plate">${plate}</span>
               <span class="matatu-tile" aria-hidden="true">
                 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1h1.5a1.5 1.5 0 0 1 1.5 1.5V14a2 2 0 0 1-2 2h-.5"/><path d="M4 6v10a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V6"/><path d="M17 9h2"/><circle cx="7.5" cy="18.5" r="1.5"/><circle cx="15.5" cy="18.5" r="1.5"/></svg>
                 <i class="matatu-pulse"></i>
               </span>
             </div>`,
      iconSize: [44, 58],
      iconAnchor: [22, 46],
    });
  }

  function glide(marker, from, to, ms) {
    if (marker._glideRaf) cancelAnimationFrame(marker._glideRaf);
    if (from[0] === to[0] && from[1] === to[1]) return;
    const start = performance.now();
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    const frame = (now) => {
      const t = Math.min(1, (now - start) / ms);
      marker.setLatLng([
        from[0] + (to[0] - from[0]) * ease(t),
        from[1] + (to[1] - from[1]) * ease(t),
      ]);
      if (t < 1) marker._glideRaf = requestAnimationFrame(frame);
    };
    marker._glideRaf = requestAnimationFrame(frame);
  }

  function upsertVehicle(v) {
    let marker = vehicleMarkers.get(v.trip_id);
    const wasSelected = selectedTripId === v.trip_id;
    if (!marker) {
      marker = L.marker([v.latitude, v.longitude], { icon: vehicleIcon(v, wasSelected), zIndexOffset: 500 });
      marker.on('click', () => {
        selectedTripId = v.trip_id;
        upsertVehicle(marker._data || v);
        showVehicleSheet(v);
      });
      marker.addTo(map);
      vehicleMarkers.set(v.trip_id, marker);
      marker.getElement()?.classList.toggle('is-dimmed', !routeIsActive(v.route_id));
    } else {
      const from = marker.getLatLng();
      glide(marker, [from.lat, from.lng], [v.latitude, v.longitude], GLIDE_MS);
      marker.setIcon(vehicleIcon(v, wasSelected));
      marker.setZIndexOffset(wasSelected ? 900 : 500);
      marker.getElement()?.classList.toggle('is-dimmed', !routeIsActive(v.route_id));
    }
    marker._data = v;
    if (wasSelected) showVehicleSheet(v);
  }

  function removeMissing(liveIds) {
    vehicleMarkers.forEach((marker, tripId) => {
      if (!liveIds.has(tripId)) {
        map.removeLayer(marker);
        vehicleMarkers.delete(tripId);
        if (selectedTripId === tripId) {
          selectedTripId = null;
          sheet.hidden = true;
        }
      }
    });
  }

  function freshnessText(v) {
    if (v.last_ping_at === null) return 'No GPS yet';
    const age = v.gps_age_seconds ?? 0;
    if (v.is_stale) return `Last update ${Math.round(age / 60)} min ago`;
    return age <= 5 ? 'Live · updated just now' : `Live · updated ${age}s ago`;
  }

  function showVehicleSheet(v) {
    sheetBody.innerHTML = `
      <div class="sheet-title-row">
        <span class="matatu-tile is-inline${v.is_stale ? ' is-stale' : ''}" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1h1.5a1.5 1.5 0 0 1 1.5 1.5V14a2 2 0 0 1-2 2h-.5"/><path d="M4 6v10a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V6"/><path d="M17 9h2"/><circle cx="7.5" cy="18.5" r="1.5"/><circle cx="15.5" cy="18.5" r="1.5"/></svg>
        </span>
        <div><strong>${v.registration}</strong><small>${v.route_name}</small></div>
      </div>
      <dl class="sheet-facts">
        <div><dt>Status</dt><dd>${freshnessText(v)}${v.is_stale ? ' · delayed' : ''}</dd></div>
        <div><dt>Position</dt><dd>${v.latitude.toFixed(5)}, ${v.longitude.toFixed(5)}</dd></div>
      </dl>
      <button type="button" class="btn btn-secondary btn-sm sheet-action" data-highlight-route="${v.route_id}">Highlight route ${v.route_name}</button>`;
    sheet.hidden = false;
    sheetBody.querySelector('[data-highlight-route]')?.addEventListener('click', (event) => {
      selectRoute(event.currentTarget.dataset.highlightRoute);
    });
  }

  function showStageSheet(stage, route) {
    const serving = (stageIndex.get(stage.id)?.routes || []).map((r) => r.name).join(' · ');
    const haversine = (a, b) => {
      const toRad = (d) => (d * Math.PI) / 180;
      const dLat = toRad(b.latitude - a.latitude);
      const dLon = toRad(b.longitude - a.longitude);
      const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.latitude)) * Math.cos(toRad(b.latitude)) * Math.sin(dLon / 2) ** 2;
      return 6371000 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
    };
    const approaching = latestVehicles.filter((v) =>
      stageIndex.get(stage.id)?.routes.some((r) => String(r.id) === String(v.route_id))
      && haversine(v, stage) <= STAGE_APPROACH_M,
    );
    sheetBody.innerHTML = `
      <div class="sheet-title-row">
        <span class="stage-dot" aria-hidden="true"></span>
        <div><strong>${stage.name}</strong><small>Stage ${stage.sequenceOrder} · ${route.name}</small></div>
      </div>
      <dl class="sheet-facts">
        <div><dt>Routes serving</dt><dd>${serving || route.name}</dd></div>
        <div><dt>Matatus nearby</dt><dd>${approaching.length ? approaching.map((v) => v.registration).join(', ') : 'None within 2 km'}</dd></div>
      </dl>
      <button type="button" class="btn btn-secondary btn-sm sheet-action" data-open-route="${route.id}">Open ${route.name}</button>`;
    sheet.hidden = false;
    sheetBody.querySelector('[data-open-route]')?.addEventListener('click', (event) => {
      selectRoute(event.currentTarget.dataset.openRoute);
    });
  }

  document.getElementById('map-sheet-close').addEventListener('click', () => {
    sheet.hidden = true;
    selectedTripId = null;
  });

  /* ── Sheet swipe-to-dismiss ────────────────────────────────────────── */
  let touchStartY = null;
  sheet.addEventListener('touchstart', (event) => {
    touchStartY = event.touches[0].clientY;
  }, { passive: true });
  sheet.addEventListener('touchmove', (event) => {
    if (touchStartY === null) return;
    const dy = event.touches[0].clientY - touchStartY;
    if (dy > 0) sheet.style.transform = `translateY(${dy}px)`;
  }, { passive: true });
  sheet.addEventListener('touchend', (event) => {
    if (touchStartY === null) return;
    const dy = event.changedTouches[0].clientY - touchStartY;
    sheet.style.transform = '';
    if (dy > 80) {
      sheet.hidden = true;
      selectedTripId = null;
    }
    touchStartY = null;
  });

  /* ── Recenter on the commuter ──────────────────────────────────────── */
  document.getElementById('recenter-btn')?.addEventListener('click', () => {
    if (!('geolocation' in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        if (window.__userDot) map.removeLayer(window.__userDot);
        window.__userDot = L.circleMarker([latitude, longitude], {
          radius: 7, color: '#FFFFFF', weight: 3, fillColor: '#1769E8', fillOpacity: 1,
        }).addTo(map).bindTooltip('You are here', { direction: 'top' });
        map.flyTo([latitude, longitude], 15, { duration: 0.8 });
      },
      () => {},
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 30000 },
    );
  });

  /* ── Polling ───────────────────────────────────────────────────────── */
  let timer = null;
  let controller = null;
  let busy = false;

  async function poll() {
    if (busy || document.hidden || !navigator.onLine) return;
    busy = true;
    controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(vehiclesUrl, {
        cache: 'no-store',
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      latestVehicles = data.vehicles || [];
      const liveIds = new Set();
      for (const vehicle of latestVehicles) {
        liveIds.add(vehicle.trip_id);
        upsertVehicle(vehicle);
      }
      removeMissing(liveIds);
      const moving = latestVehicles.filter((v) => !v.is_stale).length;
      statusEl.textContent = moving > 0
        ? `${moving} matatu${moving === 1 ? '' : 's'} on the move`
        : 'Waiting for live vehicle updates';
      statusEl.classList.remove('is-stale');
    } catch (_) {
      statusEl.textContent = 'Live updates paused · showing the last known positions';
      statusEl.classList.add('is-stale');
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

  /* ── Deep links: /map/?route=<id> or /map/?stage=<id> ──────────────── */
  const params = new URLSearchParams(location.search);
  const stageParam = params.get('stage');
  const routeParam = params.get('route');
  if (stageParam) {
    const entry = stageIndex.get(Number(stageParam));
    if (entry) {
      selectRoute(entry.routes[0]?.id ?? 'all');
      map.setView([entry.stage.latitude, entry.stage.longitude], 15);
      const openWhenReady = setInterval(() => {
        if (latestVehicles.length) {
          showStageSheet(entry.stage, entry.routes[0]);
          clearInterval(openWhenReady);
        }
      }, 800);
      setTimeout(() => clearInterval(openWhenReady), 8000);
    }
  } else if (routeParam) {
    selectRoute(routeParam);
  }
})();
