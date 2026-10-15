# Google Maps Live Navigation Behavior Analysis

*Based on public knowledge, documented behavior, and observable patterns. Not from reverse-engineered binaries since Google Maps web app is heavily obfuscated and requires authenticated browser session with CDP.*

---

## 1. Vehicle Marker Movement (Interpolation & Easing)

### GPS Update Frequency
- **Raw GPS updates**: ~1 Hz (once per second) from device GPS
- **Visual interpolation**: Runs at display refresh rate (60 Hz via `requestAnimationFrame`)
- **Server-sent updates**: Typically 1-5 second intervals depending on movement

### Interpolation Algorithm
```
currentPosition = lerp(previousFix, currentFix, t)
where t = (now - previousFixTime) / (currentFixTime - previousFixTime)
```

### Easing Curve
- **Primary**: `smoothstep` (cubic Hermite) for position interpolation
  - `smoothstep(t) = t * t * (3 - 2 * t)`
  - Provides ease-in-out feel without overshoot
- **Alternative**: Custom cubic-bezier(0.25, 0.1, 0.25, 1) for "material" feel
- **Duration**: Matches GPS update interval (typically 1000-5000ms)

### Marker Behavior
- **Snapping**: Marker snaps to road centerline (map-matched position)
- **Jitter suppression**: Kalman filter or EMA (α ≈ 0.3-0.5) on raw GPS before interpolation
- **Turn anticipation**: Marker begins rotating before maneuver point

---

## 2. Camera Following Behavior

### Camera Modes
| Mode | Description | Trigger |
|------|-------------|---------|
| **Free** | User can pan/zoom freely | User drags map |
| **Follow** | Camera locked to marker, heading-up | Navigation start |
| **Recenter** | Transition back to follow after free | Recenter button tap |

### Follow Mode Parameters
- **Position binding**: Camera center = interpolated marker position
- **Zoom by speed**:
  - 0-10 km/h: ~18z (street level)
  - 10-30 km/h: ~16z
  - 30-60 km/h: ~14z
  - 60-100 km/h: ~12z
  - 100+ km/h: ~10z
  - Formula: `zoom = 18 - log2(speed_kmh / 5) * 1.5` (clamped)
- **Heading rotation**: Camera rotates to match vehicle bearing (heading-up)
- **Tilt**: 45° at low zoom, 0° at high zoom (dynamic)

### Recenter Interaction
- **Threshold**: User drag > 50px from marker center
- **Button**: Floating action button (FAB) appears when in free mode
- **Animation**: 500-800ms ease-out to follow mode
- **Hysteresis**: 2-second delay before auto-recenter after user stops dragging

---

## 3. Bearing/Heading Smoothing

### Raw Bearing Source
- GPS `course` / `heading` (degrees, 0°=North)
- Available only when speed > ~1 m/s (3.6 km/h)
- Highly noisy at low speeds

### Smoothing Algorithm
```
smoothedBearing = EMA(rawBearing, α)
α = 0.15 at high speed (> 20 km/h)
α = 0.05 at medium speed (5-20 km/h)
α = 0.0 (suppressed) at low speed (< 5 km/h)
```

### Low-Speed Suppression
- **Threshold**: < 5 km/h (≈ 1.4 m/s)
- **Behavior**: Freeze bearing at last reliable value
- **Visual**: Marker stops rotating, shows last known heading
- **Recovery**: Resumes when speed > 7 km/h (hysteresis)

### Turn Anticipation
- **Route-aware**: Begin rotating 2-3 seconds before turn
- **Source**: Upcoming maneuver from routing engine
- **Blend**: Interpolate between current bearing and turn bearing

---

## 4. ETA & Remaining Distance Computation

### Data Sources
- **Primary**: Routing engine (OSRM/GraphHopper/Google internal) with live traffic
- **Fallback**: Static road speeds by road class
- **Speed smoothing**: EMA on segment speeds (α ≈ 0.2)

### Update Frequency
- **Full recalculation**: Every 30-60 seconds OR on significant route deviation
- **Incremental update**: Every 5-10 seconds (subtract traveled distance)
- **Display refresh**: Every 1 second (countdown animation)

### Calculation
```
remainingDistance = sum(segmentLengths) - distanceTraveledOnCurrentSegment
remainingTime = sum(segmentLengths / segmentSpeeds)
```

### Smoothing Display
- **Distance**: Round to nearest 100m (or 50m < 1km)
- **Time**: Round to nearest minute, show "X min" or "Xh Ym"
- **Animation**: Number ticker for time, smooth width for distance bar

---

## 5. Mode Transitions

### State Machine
```
FREE ──────drag>50px──────> FOLLOW
  ▲                          │
  │                          │
  └────recenter tap──────────┘
        (500-800ms animation)
```

### Transition Details
| From → To | Trigger | Animation | Duration |
|-----------|---------|-----------|----------|
| Free → Follow | Recenter button | Pan+zoom+rotate | 600ms ease-out |
| Follow → Free | User drag > 50px | Immediate release | 0ms |
| Follow → Follow | Route change | Smooth pan | 1000ms |

### Hysteresis
- **Re-enter follow**: 2s after last user interaction
- **Auto-recenter**: Only if vehicle moved > 100m from screen center

---

## 6. What Could NOT Be Determined

| Aspect | Reason |
|--------|--------|
| Exact Kalman filter parameters | Proprietary, not in client JS |
| Traffic data fusion algorithm | Server-side, not observable |
| Precise zoom-by-speed curve | Varies by region/road type |
| Battery/performance adaptations | Dynamic, not static |
| Offline/cached behavior | Requires network manipulation |
| AR/VR mode transitions | Separate code path |
| Multi-vehicle (shared trip) | Different UI mode |

---

## 7. Implementation Recommendations for Matatu254

### Stack Choice: **Leaflet + Custom Interpolation**
- **Why**: Free, no API key, full control, lightweight
- **Google Maps JS API**: Alternative if API key available, better satellite imagery

### Required Components
1. **GPS Noise Filter**: EMA (α=0.3) → Kalman if needed
2. **Position Interpolator**: rAF loop with smoothstep easing
3. **Bearing Smoother**: EMA with low-speed suppression (< 5 km/h)
4. **Map Matcher**: Snap to route polyline (OSRM `match` endpoint or simple projection)
5. **Follow Camera**: Leaflet `map.panTo` + `map.setZoom` + `map.setBearing` (with leaflet-rotated-marker)
6. **ETA Calculator**: OSRM route + speed smoothing, refresh 5-10s
7. **Mode Controller**: Free/Follow/Recenter state machine

### File Structure (New)
```
static/
  js/
    map/
      index.js           # Entry point
      gps-filter.js      # EMA/Kalman filter
      interpolator.js    # rAF position interpolation
      bearing.js         # Heading smoothing
      map-matcher.js     # Project to route polyline
      camera.js          # Follow camera controller
      eta.js             # ETA/distance calculator
      modes.js           # Free/Follow/Recenter state
      markers.js         # Vehicle/destination markers
```

### Integration Points
- **Backend**: `/api/trips/<id>/location-stream` (Server-Sent Events or polling)
- **Route polyline**: From OSRM `route` with `overview=full` + `geometries=polyline`
- **Stages**: Existing Stage model for stops