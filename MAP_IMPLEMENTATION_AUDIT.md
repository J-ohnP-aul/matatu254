# Matatu254 Map Implementation Audit

## Current State Summary

**NO LIVE MAP EXISTS.** The current `journeys/tracking.html` is a **text-only** tracking view showing:
- Journey progress bar (stage-based %)
- Current/next stage names
- Remaining distance (straight-line Haversine + OSRM segments)
- ETA (based on fixed 25 km/h fallback speed)
- Route stage list with completion status
- GPS freshness indicator
- 5-second polling for updates

**No Google Maps JS API, Leaflet, Mapbox, or any mapping library is loaded.**

---

## Gap Analysis vs. Google Maps Navigation Behavior

| Behavior | Current State | Gap |
|----------|---------------|-----|
| **Live map display** | ❌ None | Need full map implementation |
| **Vehicle marker** | ❌ None | Need marker with interpolation |
| **Marker interpolation** | ❌ None | Need rAF + smoothstep |
| **GPS noise filtering** | ❌ None | Raw GPS used directly |
| **Bearing/heading** | ❌ None | Not computed or displayed |
| **Bearing smoothing** | ❌ None | Need EMA + low-speed suppression |
| **Map matching** | ❌ None | Raw GPS coords, not snapped to route |
| **Follow camera** | ❌ None | Static view, no camera logic |
| **Zoom by speed** | ❌ None | Fixed zoom |
| **Heading-up rotation** | ❌ None | North-up only |
| **Recenter button** | ❌ None | No user interaction handling |
| **Mode transitions** | ❌ None | No Free/Follow/Recenter states |
| **ETA along polyline** | ⚠️ Partial | OSRM segments but straight-line to next stage |
| **ETA refresh rate** | ⚠️ 5s polling | Need 5-10s incremental + 30-60s full |
| **Speed-smoothed ETA** | ❌ Fixed 25 km/h | Need live speed from GPS deltas |

---

## Files That Need Changes

### Backend (Django)

| File | Current Role | Changes Needed |
|------|--------------|----------------|
| `trips/views.py:ping` | Receives GPS pings | Add SSE endpoint for real-time stream |
| `trips/services.py:record_ping` | Stores GPS + updates trip cache | Optionally compute speed/bearing deltas |
| `journeys/views.py:journey_tracking_data` | Returns tracking JSON | Add route polyline, bearing, speed |
| `r_outes/routes_services.py` | OSRM distance/ETA | Add `get_route_polyline()` for full route geometry |
| `core/osrm.py` | OSRM client | Add polyline decoding, match endpoint |

### Frontend (New Files)

| File | Purpose |
|------|---------|
| `static/js/map/index.js` | Main map controller, initialization |
| `static/js/map/gps-filter.js` | EMA/Kalman filter for GPS noise |
| `static/js/map/interpolator.js` | rAF loop with smoothstep easing |
| `static/js/map/bearing.js` | Heading smoothing + low-speed suppression |
| `static/js/map/map-matcher.js` | Project GPS to route polyline |
| `static/js/map/camera.js` | Follow camera (pan/zoom/rotate) |
| `static/js/map/eta.js` | ETA/distance along polyline |
| `static/js/map/modes.js` | Free/Follow/Recenter state machine |
| `static/js/map/markers.js` | Vehicle, destination, stage markers |

### Templates

| File | Changes |
|------|---------|
| `templates/journeys/tracking.html` | Replace text view with map container + keep metrics overlay |
| `templates/base.html` | Add Leaflet/Google Maps CSS/JS includes |

---

## Required Backend API Additions

### 1. Route Polyline Endpoint
```
GET /api/trips/<trip_id>/route-polyline
Response: { polyline: "encoded_polyline", stages: [...] }
```
- Use OSRM `route` with `overview=full&geometries=polyline`
- Include all stages up to destination

### 2. Real-time Location Stream (SSE)
```
GET /api/trips/<trip_id>/location-stream
Event: ping
Data: { lat, lon, bearing, speed, accuracy, timestamp }
```
- Server-Sent Events for <1s latency
- Fallback: 1s polling if SSE not feasible

### 3. Enhanced Tracking Data
```
GET /api/journeys/<journey_id>/tracking-data (existing)
Add: bearing, speed, polyline_progress, map_matched_position
```

---

## Implementation Priority Order

1. **GPS noise filtering** (EMA) - Foundation for everything
2. **requestAnimationFrame interpolation** - Smooth marker motion
3. **Bearing smoothing** - With <5 km/h suppression
4. **Map matching** - Project to route polyline
5. **Follow camera** - Bound to interpolated position
6. **Speed-adaptive zoom** - Zoom by speed formula
7. **Recenter button** - User drag detection + FAB
8. **ETA along polyline** - Smoothed speed, 5-10s refresh

---

## Dependencies to Add

### Option A: Leaflet (Recommended - Free)
```html
<!-- CSS -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<!-- JS -->
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<!-- Plugins -->
<script src="https://unpkg.com/leaflet-rotatedmarker@0.2.0/leaflet.rotatedMarker.js"></script>
<script src="https://unpkg.com/@mapbox/polyline@1.2.1/src/polyline.js"></script>
```

### Option B: Google Maps JS API (If API Key Available)
```html
<script src="https://maps.googleapis.com/maps/api/js?key=YOUR_KEY&libraries=marker"></script>
```
- Better satellite, traffic layer, but requires billing setup

---

## Testing Checklist

After each behavior implementation:
- [ ] `python manage.py test` passes
- [ ] Manual test: Open tracking page, verify no JS errors
- [ ] Simulate GPS pings (via admin or script), verify smooth marker
- [ ] Drag map → recenter button appears → tap → smooth return
- [ ] Low speed (<5 km/h) → marker stops rotating
- [ ] High speed → zoom out, heading-up rotation
- [ ] ETA updates every 5-10s, counts down smoothly