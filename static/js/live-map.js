/**
 * Live Map — public fleet map for Matatu254.
 *
 * Data sources (all real, nothing simulated):
 * - Routes/stages/geometry: embedded server-side JSON (routes-data).
 * - Vehicles: polling /trips/live/ (same ActiveTrip cache the journey
 *   screens read). Markers are updated in place per trip_id; polling
 *   pauses when the tab is hidden and aborts in-flight requests.
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
  const STALE_AFTER_S = 60;

  /* ── Map setup ─────────────────────────────────────────────────────── */
  const map = L.map(container, {
    zoomControl: false,
    attributionControl: true,
    center: [-1.2921, 36.8219], // Nairobi default; fitRoutes() refines it
    zoom: 7,
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

  /* ── Route layers ──────────────────────────────────────────────────── */
  const routeLayers = new Map();   // route_id -> {line, stageGroup}
  const stageIndex = new Map();    // stage_id -> {stage, routes[]}
  let activeRouteId = 'all';

  // Route colors come from tokens.css so the palette is themed in one place.
  const routePalette = getComputedStyle(document.documentElement)
    .getPropertyValue('--route-color-1')
    ? [1, 2, 3, 4, 5, 6].map((n) =>
        getComputedStyle(document.documentElement)
          .getPropertyValue(`--route-color-${n}`)
          .trim(),
      )
    : ['#1769E8', '#10B981', '#7C5CD6', '#F59E0B', '#E11D74', '#0EA5E9'];

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

  function layersForSelection() {
    if (activeRouteId === 'all') return [...routeLayers.values()];
    return [routeLayers.get(Number(activeRouteId))].filter(Boolean);
  }

  function redrawRoutes() {
    routeLayers.forEach(({ line, group }) => {
      map.removeLayer(group);
      if (line) map.removeLayer(line);
    });
    layersForSelection().forEach(({ line, group }) => {
      group.addTo(map);
      if (line) line.addTo(map);
    });
  }

  function fitRoutes() {
    const points = [];
    layersForSelection().forEach(({ group, line }) => {
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

  /* ── Vehicle markers ───────────────────────────────────────────────── */
  const vehicleMarkers = new Map(); // trip_id -> marker
  let selectedTripId = null;

  function vehicleIcon(stale) {
    return L.divIcon({
      className: '',
      html: `<div class="vehicle-dot${stale ? ' is-stale' : ''}" aria-hidden="true">
               <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1h1.5a1.5 1.5 0 0 1 1.5 1.5V14a2 2 0 0 1-2 2h-.5"/><path d="M4 6v10a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V6"/><path d="M17 9h2"/><circle cx="7.5" cy="18.5" r="1.5"/><circle cx="15.5" cy="18.5" r="1.5"/></svg>
             </div>`,
      iconSize: [38, 38],
      iconAnchor: [19, 19],
    });
  }

  function upsertVehicle(v) {
    let marker = vehicleMarkers.get(v.trip_id);
    const stale = Boolean(v.is_stale);
    if (!marker) {
      marker = L.marker([v.latitude, v.longitude], { icon: vehicleIcon(stale), zIndexOffset: 500 });
      marker.on('click', () => {
        selectedTripId = v.trip_id;
        showVehicleSheet(v);
      });
      marker.addTo(map);
      vehicleMarkers.set(v.trip_id, marker);
    } else {
      marker.setLatLng([v.latitude, v.longitude]);
      marker.setIcon(vehicleIcon(stale));
    }
    marker._data = v;
    if (selectedTripId === v.trip_id) showVehicleSheet(v);
  }

  function removeMissing(liveIds) {
    vehicleMarkers.forEach((marker, tripId) => {
      if (!liveIds.has(tripId)) {
        map.removeLayer(marker);
        vehicleMarkers.delete(tripId);
      }
    });
  }

  function freshnessText(v) {
    if (v.last_ping_at === null) return 'No GPS yet';
    const age = v.gps_age_seconds ?? 0;
    if (v.is_stale) return `Last update ${Math.round(age / 60)} min ago`;
    return age <= 5 ? 'Updated just now' : `Updated ${age}s ago`;
  }

  function showVehicleSheet(v) {
    sheetBody.innerHTML = `
      <div class="sheet-title-row">
        <span class="vehicle-dot is-inline" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1h1.5a1.5 1.5 0 0 1 1.5 1.5V14a2 2 0 0 1-2 2h-.5"/><path d="M4 6v10a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V6"/><path d="M17 9h2"/><circle cx="7.5" cy="18.5" r="1.5"/><circle cx="15.5" cy="18.5" r="1.5"/></svg></span>
        <div><strong>${v.registration}</strong><small>${v.route_name}</small></div>
      </div>
      <dl class="sheet-facts">
        <div><dt>Position</dt><dd>${v.latitude.toFixed(5)}, ${v.longitude.toFixed(5)}</dd></div>
        <div><dt>Freshness</dt><dd>${freshnessText(v)}${v.is_stale ? ' · delayed' : ''}</dd></div>
      </dl>`;
    sheet.hidden = false;
  }

  function showStageSheet(stage, route) {
    const serving = (stageIndex.get(stage.id)?.routes || []).map((r) => r.name).join(' · ');
    sheetBody.innerHTML = `
      <div class="sheet-title-row">
        <span class="stage-dot" aria-hidden="true"></span>
        <div><strong>${stage.name}</strong><small>Stage ${stage.sequenceOrder} · ${route.name}</small></div>
      </div>
      <dl class="sheet-facts">
        <div><dt>Routes serving</dt><dd>${serving || route.name}</dd></div>
        <div><dt>Position</dt><dd>${stage.latitude.toFixed(5)}, ${stage.longitude.toFixed(5)}</dd></div>
      </dl>`;
    sheet.hidden = false;
  }

  document.getElementById('map-sheet-close').addEventListener('click', () => {
    sheet.hidden = true;
    selectedTripId = null;
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
      const liveIds = new Set();
      for (const vehicle of data.vehicles || []) {
        liveIds.add(vehicle.trip_id);
        upsertVehicle(vehicle);
      }
      removeMissing(liveIds);
      const moving = (data.vehicles || []).filter((v) => !v.is_stale).length;
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

  function resume() {
    if (!document.hidden && navigator.onLine) poll();
  }

  document.addEventListener('visibilitychange', resume);
  window.addEventListener('online', resume);
  window.addEventListener('pagehide', () => {
    if (timer) window.clearTimeout(timer);
    if (controller) controller.abort();
  }, { once: true });

  poll();
  schedule();
})();
