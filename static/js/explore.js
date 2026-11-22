/**
 * Explore — route/stage search, nearby sorting, and the route-detail map.
 * All data comes from server-embedded JSON built from real Route/Stage rows.
 */

/* ── Explore index: search + nearby ──────────────────────────────────── */
const searchInput = document.getElementById('explore-search');
if (searchInput) {
  const routeCards = [...document.querySelectorAll('#explore-routes [data-search]')];
  const stageItems = [...document.querySelectorAll('#explore-stages [data-search]')];
  const emptyState = document.getElementById('explore-empty');
  const query = () => searchInput.value.trim().toLocaleLowerCase();

  const applyFilter = () => {
    const q = query();
    let visible = 0;
    routeCards.forEach((card) => {
      const show = !q || card.dataset.search.includes(q);
      card.hidden = !show;
      if (show) visible += 1;
    });
    stageItems.forEach((item) => {
      const show = !q || item.dataset.search.includes(q);
      item.hidden = !show;
      if (show) visible += 1;
    });
    if (emptyState) emptyState.hidden = visible > 0;
  };
  searchInput.addEventListener('input', applyFilter);

  // Nearby: sort stages by distance from the user's position (real GPS only).
  const nearbyButton = document.getElementById('nearby-btn');
  const stagesData = document.getElementById('stages-data');
  const haversineM = (lat1, lon1, lat2, lon2) => {
    const toRad = (d) => (d * Math.PI) / 180;
    const R = 6371000;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  };
  nearbyButton?.addEventListener('click', () => {
    if (!('geolocation' in navigator)) {
      nearbyButton.textContent = 'Location is not available in this browser';
      return;
    }
    nearbyButton.disabled = true;
    nearbyButton.textContent = 'Finding your location…';
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        const stages = JSON.parse(stagesData.textContent)
          .map((stage) => ({ ...stage, distanceM: haversineM(latitude, longitude, stage.latitude, stage.longitude) }))
          .sort((a, b) => a.distanceM - b.distanceM)
          .slice(0, 8);
        const list = document.getElementById('explore-stages');
        if (list && stages.length) {
          const template = list.querySelector('.stage-item:not([hidden])');
          list.querySelectorAll('.stage-item').forEach((item) => { item.remove(); });
          stages.forEach((stage) => {
            const row = template
              ? template.cloneNode(true)
              : document.createElement('a');
            row.className = 'stage-item';
            row.dataset.search = `${stage.name} ${stage.routeName}`.toLowerCase();
            row.href = row.href || `/map/?route=${stage.routeId}`;
            const distanceKm = stage.distanceM >= 1000
              ? `${(stage.distanceM / 1000).toFixed(1)} km`
              : `${Math.round(stage.distanceM)} m`;
            row.innerHTML = `<span class="stage-item-dot" aria-hidden="true"></span>
              <span class="action-card-body"><strong>${stage.name}</strong><small>${stage.routeName} · about ${distanceKm} away</small></span>`;
            list.append(row);
          });
        }
        nearbyButton.textContent = 'Sorted by distance from you';
        document.getElementById('explore-stages')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      },
      () => {
        nearbyButton.disabled = false;
        nearbyButton.textContent = 'Allow location to find nearby stages';
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 },
    );
  });
}

/* ── Live vehicle counts on route cards (real /trips/live/ data) ────── */
const liveCountCards = document.querySelectorAll('[data-live-count]');
if (liveCountCards.length) {
  fetch('/trips/live/', { headers: { Accept: 'application/json' }, cache: 'no-store' })
    .then((response) => (response.ok ? response.json() : Promise.reject(new Error('HTTP ' + response.status))))
    .then((data) => {
      const byRoute = new Map();
      for (const vehicle of data.vehicles || []) {
        if (!vehicle.is_stale) {
          byRoute.set(String(vehicle.route_id), (byRoute.get(String(vehicle.route_id)) || 0) + 1);
        }
      }
      liveCountCards.forEach((badge) => {
        const routeId = badge.dataset.liveCount;
        const count = byRoute.get(routeId) || 0;
        const text = badge.querySelector('[data-live-count-text]');
        badge.classList.remove('is-loading');
        if (text) text.textContent = count === 1 ? '1 live' : `${count} live`;
        badge.hidden = count === 0;
      });
    })
    .catch(() => {
      liveCountCards.forEach((badge) => {
        badge.classList.remove('is-loading');
        badge.hidden = true; // skeleton resolves to nothing — no invented counts
      });
    });
}

/* ── Route detail: static route map ─────────────────────────────────── */
const routeMapEl = document.getElementById('route-map');
if (routeMapEl && window.L) {
  const route = JSON.parse(document.getElementById('route-data').textContent);
  const map = L.map(routeMapEl, { zoomControl: false, attributionControl: true, scrollWheelZoom: false });
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  const points = [];
  if (route.geometry && route.geometry.length > 10) {
    const coords = route.geometry
      ? decodeEncodedPolyline(route.geometry)
      : [];
    if (coords.length >= 2) {
      L.polyline(coords, { color: '#1769E8', weight: 5, opacity: 0.85 }).addTo(map);
      points.push(...coords);
    }
  }
  if (!points.length) {
    route.stages.forEach((stage) => points.push([stage.latitude, stage.longitude]));
  }
  route.stages.forEach((stage, index) => {
    L.circleMarker([stage.latitude, stage.longitude], {
      radius: 6, color: '#FFFFFF', weight: 2.5,
      fillColor: index === route.stages.length - 1 ? '#10B981' : '#1769E8', fillOpacity: 1,
    }).addTo(map).bindTooltip(stage.name, { direction: 'top' });
    points.push([stage.latitude, stage.longitude]);
  });
  if (points.length >= 2) map.fitBounds(L.latLngBounds(points).pad(0.15));
  else map.setView([-1.2921, 36.8219], 12);
}

// Minimal Google-encoded polyline decoder (same algorithm as map-matcher.js;
// duplicated here so route-detail can draw geometry without importing the
// full matcher module).
function decodeEncodedPolyline(encoded) {
  let index = 0;
  let lat = 0;
  let lng = 0;
  const coordinates = [];
  while (index < encoded.length) {
    let result = 0;
    let shift = 0;
    let byte;
    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);
    lat += ((result & 1) ? ~(result >> 1) : (result >> 1));
    result = 0;
    shift = 0;
    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);
    lng += ((result & 1) ? ~(result >> 1) : (result >> 1));
    coordinates.push([lat / 1e5, lng / 1e5]);
  }
  return coordinates;
}
