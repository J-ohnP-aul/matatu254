---
sessionId: session-261105-191117-1iok
---

# Requirements

### Overview & Goals
Add optional WebSocket live-location tracking for passengers while preserving the existing HTTP polling implementation. The transport mode (polling, websocket, auto) is configurable via environment variable. All location processing — validation, persistence, journey status updates — flows through the existing `record_ping()` service to avoid duplicating business logic.

### Scope

**In Scope:**
- Backend: Django Channels WebSocket consumer for trip location updates
- Backend: Shared location processing service (existing `record_ping()` reused)
- Backend: WebSocket authorization mirroring existing HTTP view rules
- Backend: `LOCATION_TRANSPORT` setting with safe default of `polling`
- Frontend: Transport abstraction (PollingTransport, WebSocketTransport, AutoTransport)
- Frontend: Normalized events for map/UI code (position received, connection opened/lost, location stale, transport changed)
- Frontend: Auto mode with WebSocket → polling fallback and background reconnect
- Configuration documentation for deployment
- Focused tests for all new functionality and regression tests for existing behavior

**Out of Scope:**
- Removing or breaking existing polling
- WebSocket driver uploads (driver continues to use HTTP ping)
- Redis as a hard requirement (configurable, with in-memory channel layer for dev)
- Modifying the conductor-trip.js GPS capture flow
- Committing secrets or local-only config

### User Stories
- As a passenger, I want to receive real-time vehicle location updates so I can track my matatu without waiting for polling intervals.
- As a developer, I want to switch between polling and WebSocket transports via environment config so I can choose the right mode for my deployment.
- As a conductor, I want my existing GPS tracking to continue working unchanged.
- As an admin, I want WebSocket connections to be authorized the same way HTTP endpoints are, so users can't bypass security.

### Functional Requirements
1. **Transport Configuration**: `LOCATION_TRANSPORT` env var supports `polling` (default), `websocket`, and `auto`.
2. **WebSocket Messages**: Support `location.update` (publish), `location.accepted`/`location.rejected` (ack), `trip.completed` (broadcast).
3. **Trip-Specific Groups**: WebSocket connections join `trip_<trip_id>` groups.
4. **Authorization**: Same rules as HTTP views — conductor/owner publishes, authorized passengers subscribe.
5. **Shared Service**: Both HTTP ping and WebSocket consumer call `record_ping()` for all business logic.
6. **Stale Handling**: Existing `GPS_STALE_AFTER_SECONDS` (60s) threshold preserved. WebSocket does not make old GPS appear live.
7. **Initial Position**: Existing `latest-position` HTTP endpoint used for initial load, even with WebSockets.
8. **Auto Mode**: Try WebSocket first, fall back to polling on failure, retry WebSocket in background, switch back on reconnect, no duplicate subscriptions.

### Non-Functional Requirements
- No duplicate polling + WebSocket subscriptions for the same trip in auto mode.
- Existing tests must not be removed or weakened.
- Django Channels with in-memory channel layer for dev; Redis optional for production.
- ASGI-compatible deployment; WSGI continues to work for polling-only mode.


# Technical Design

### Current Implementation

**Driver GPS Flow:**
1. `conductor-trip.js` uses `navigator.geolocation.watchPosition()` → queues fixes in localStorage
2. `flushQueue()` POSTs each fix to `POST /trips/<trip_id>/ping/`
3. `trips/views.py::ping()` authorizes (conductor/owner check), calls `trips/services.py::record_ping()`
4. `record_ping()` validates coords, parses timestamps, prevents out-of-order updates, writes `TripLocationLog`, updates `ActiveTrip` cache, triggers journey status updates

**Passenger Tracking Flow:**
1. `journey-live.js` polls `GET /journeys/session/<id>/tracking-data/` every 3.5s
2. `map/index.js` polls `GET /trips/<trip_id>/latest-position/` every 3s (SSE attempt exists but falls back to polling since SSE is conductor-only)
3. Both read from `ActiveTrip.current_latitude/longitude` cache

**Key Files:**
- `trips/models.py` — `ActiveTrip` with position cache, `GPS_STALE_AFTER_SECONDS = 60`
- `trips/services.py` — `record_ping()` (shared business logic)
- `trips/views.py` — `ping()`, `location_stream()` (SSE, conductor-only), `latest_position()`
- `trips/urls.py` — route definitions
- `tracking/models.py` — `TripLocationLog` history
- `journeys/views.py` — `journey_tracking_data()` (passenger polling endpoint)
- `journeys/services.py` — `update_journey_status()`
- `static/js/journey-live.js` — passenger polling
- `static/js/map/index.js` — map polling/SSE
- `config/settings.py` — Django settings, no Channels/ASGI currently
- `config/asgi.py` — basic ASGI (empty `get_asgi_application()`)
- `render.yaml` — gunicorn WSGI deployment, no Redis

### Key Decisions

1. **Django Channels with In-Memory Channel Layer for Dev**: The project currently uses gunicorn WSGI with no Redis. Django Channels provides the best fit for WebSocket support in Django. The in-memory channel layer (`InMemoryChannelLayer`) works for development and single-process deployments. Redis channel layer is optional for production multi-worker setups.

2. **WebSocket for Passenger Updates Only (Initially)**: The driver continues to use HTTP POST ping. WebSockets are added first for passenger live updates. This minimizes risk and keeps the conductor flow unchanged.

3. **Transport Abstraction in Frontend**: A `LocationTransport` interface with `PollingTransport`, `WebSocketTransport`, and `AutoTransport` implementations. The map and UI code consume normalized events, not transport-specific details.

4. **Authorization via Cookie-Based Session**: WebSocket connections authenticate using the existing Django session cookie, mirroring HTTP view authorization. No token-based auth added.

5. **ASGI Application with WSGI Compatibility**: The ASGI application in `config/asgi.py` will be updated to support both WebSocket and HTTP routes. The existing WSGI deployment continues to work for polling-only mode.

### Proposed Changes

**Backend:**

1. **Add Django Channels dependency** to `requirements.txt` (`channels>=4.0,<5.0`).

2. **Update `config/settings.py`**:
   - Add `channels` to `INSTALLED_APPS`
   - Add `LOCATION_TRANSPORT` setting (default `"polling"`)
   - Add `CHANNEL_LAYERS` config with in-memory layer (Redis configurable via env)
   - Add `ASGI_APPLICATION = 'config.asgi.application'`

3. **Update `config/asgi.py`**: Wrap WSGI app in `ProtocolTypeRouter` with HTTP and WebSocket routes.

4. **Create `trips/consumers.py`**: `TripLocationConsumer` (AsyncJsonWebsocketConsumer) that:
   - Authenticates via session cookie
   - Handles `location.update` messages → calls `record_ping()` via sync-to-async bridge
   - Joins `trip_<trip_id>` group
   - Broadcasts accepted updates to group
   - Sends `location.accepted`/`location.rejected` acks
   - Handles `trip.completed` broadcasts

5. **Create `trips/routing.py`**: WebSocket URL routing (`websocket_urlpatterns`).

6. **Update `config/urls.py`**: Include WebSocket routing.

7. **No changes to `trips/views.py::ping()`**, `trips/services.py::record_ping()`, or `trips/urls.py` existing endpoints — all preserved.

**Frontend:**

8. **Create `static/js/transport/polling-transport.js`**: Wraps existing polling logic, emits normalized events.

9. **Create `static/js/transport/websocket-transport.js`**: WebSocket client, emits normalized events, handles reconnection.

10. **Create `static/js/transport/auto-transport.js`**: Tries WebSocket first, falls back to polling, background reconnect, no duplicate subscriptions.

11. **Create `static/js/transport/index.js`**: Factory that selects transport based on server config.

12. **Update `static/js/journey-live.js`**: Use transport abstraction instead of direct polling. Server exposes `LOCATION_TRANSPORT` via template context or a config endpoint.

13. **Update `static/js/map/index.js`**: Accept transport instance, use normalized events for GPS updates.

**Configuration:**

14. **Create `WEBSOCKET_SETUP.md`**: Documentation for `LOCATION_TRANSPORT` modes, Redis/ASGI deployment requirements.

### Data Models / Contracts

**WebSocket URL**: `ws://<host>/ws/trips/<trip_id>/`

**Client → Server Messages:**
```json
{"type": "location.update", "trip_id": 123, "latitude": -1.286389, "longitude": 36.817223, "accuracy_m": 8.4, "recorded_at": "2026-11-05T12:00:00Z"}
```

**Server → Client Messages:**
```json
{"type": "location.accepted", "trip_id": 123, "latitude": -1.286389, "longitude": 36.817223, "timestamp": "2026-11-05T12:00:00Z", "gps_age_seconds": 2, "is_stale": false}
{"type": "location.rejected", "trip_id": 123, "reason": "Latitude or longitude is outside the valid coordinate range"}
{"type": "trip.completed", "trip_id": 123}
```

**Frontend Transport Interface:**
```javascript
interface LocationTransport {
  start(): void;
  stop(): void;
  on(event: 'position' | 'connected' | 'disconnected' | 'stale' | 'transport_changed', callback);
  // Emits: { type: 'position', latitude, longitude, timestamp, gps_age_seconds, is_stale }
  // Emits: { type: 'connected', transport: 'websocket' | 'polling' }
  // Emits: { type: 'disconnected', transport: 'websocket' | 'polling' }
  // Emits: { type: 'stale', is_stale: true }
  // Emits: { type: 'transport_changed', from: 'websocket', to: 'polling' }
}
```

**Server Setting:**
```python
LOCATION_TRANSPORT = os.environ.get('LOCATION_TRANSPORT', 'polling')  # 'polling' | 'websocket' | 'auto'
```

### File Structure

**New Files:**
- `trips/consumers.py` — WebSocket consumer
- `trips/routing.py` — WebSocket URL routing
- `static/js/transport/polling-transport.js` — Polling transport
- `static/js/transport/websocket-transport.js` — WebSocket transport
- `static/js/transport/auto-transport.js` — Auto transport with fallback
- `static/js/transport/index.js` — Transport factory
- `WEBSOCKET_SETUP.md` — Configuration documentation

**Modified Files:**
- `config/settings.py` — Add Channels, LOCATION_TRANSPORT, CHANNEL_LAYERS
- `config/asgi.py` — ProtocolTypeRouter with WebSocket routes
- `config/urls.py` — Include WebSocket routing
- `requirements.txt` — Add channels dependency
- `static/js/journey-live.js` — Use transport abstraction
- `static/js/map/index.js` — Accept transport instance
- `journeys/views.py` — Expose LOCATION_TRANSPORT in template context (minor)

### Architecture Diagram

```mermaid
graph LR
  A[Conductor Browser] -->|POST /trips/id/ping/| B[HTTP ping view]
  B -->|record_ping()| C[trips/services.py]
  C -->|Update| D[(ActiveTrip cache)]
  C -->|Write| E[(TripLocationLog)]
  C -->|Update| F[(JourneySession)]
  
  G[Passenger Browser] -->|GET latest-position| H[HTTP latest-position view]
  H -->|Read| D
  
  G -->|WS /ws/trips/id/| I[TripLocationConsumer]
  I -->|Broadcast| J[trip_<id> group]
  J -->|location.accepted| G
  
  I -.->|Calls record_ping()| C
```

### Risks

1. **Render.com Deployment**: Render uses gunicorn WSGI. WebSocket requires an ASGI server (e.g., `uvicorn`). The deployment config needs updating for WebSocket mode. Documented in `WEBSOCKET_SETUP.md`. Polling mode continues to work with current setup.

2. **Redis Dependency**: Multi-worker ASGI deployments require Redis for channel layer. In-memory layer works for single-process dev. Made configurable via env.

3. **Session Cookie over WebSocket**: WebSocket upgrade must carry the session cookie. This works for same-origin but may require CORS configuration for cross-origin setups.

4. **Backward Compatibility**: Existing `location_stream()` SSE endpoint is conductor-only and preserved. No changes to existing HTTP endpoints.


# Delivery Steps

### ✓ Step 1: Add Django Channels backend infrastructure
Set up Django Channels with in-memory channel layer, update ASGI config, and add LOCATION_TRANSPORT setting.
- Add `channels>=4.0,<5.0` to `requirements.txt`.
- Update `config/settings.py`: add `channels` to `INSTALLED_APPS`, add `CHANNEL_LAYERS` with in-memory layer (Redis configurable via `REDIS_URL` env), add `LOCATION_TRANSPORT` setting defaulting to `"polling"`.
- Update `config/asgi.py`: wrap existing WSGI app in `ProtocolTypeRouter` with HTTP and WebSocket route placeholders.
- Create `trips/routing.py` with `websocket_urlpatterns` for `ws/trips/<trip_id>/`.
- Update `config/urls.py` to include WebSocket routing via `ProtocolTypeRouter`.
- Verify Django checks pass with new Channels config.

### ✓ Step 2: Implement WebSocket consumer with shared service
Create the WebSocket consumer that authenticates users, processes location updates via the existing `record_ping()` service, and broadcasts to trip groups.
- Create `trips/consumers.py` with `TripLocationConsumer` (AsyncJsonWebsocketConsumer).
- Implement session-based authentication (mirror HTTP view authorization: conductor/owner for publish, passenger/conductor/admin for subscribe).
- Handle `location.update` → call `record_ping()` via `async_to_sync` → broadcast `location.accepted` to `trip_<trip_id>` group on success, `location.rejected` on failure.
- Handle `trip.completed` broadcasts.
- Enforce trip-level authorization: user must have access to the specific trip (not just any trip).
- Ensure stale GPS handling matches existing `GPS_STALE_AFTER_SECONDS` threshold.
- Update `trips/routing.py` to wire the consumer.

### ✓ Step 3: Create frontend transport abstraction
Build the JavaScript transport layer with PollingTransport, WebSocketTransport, and AutoTransport implementations.
- Create `static/js/transport/polling-transport.js`: wraps existing polling logic (fetch `latest-position` every 3s), emits normalized events (`position`, `connected`, `disconnected`, `stale`).
- Create `static/js/transport/websocket-transport.js`: WebSocket client connecting to `ws/trips/<id>/`, emits normalized events, handles reconnection with backoff.
- Create `static/js/transport/auto-transport.js`: tries WebSocket first, falls back to polling on failure, retries WebSocket in background, switches back on reconnect, prevents duplicate subscriptions.
- Create `static/js/transport/index.js`: factory that selects transport based on `LOCATION_TRANSPORT` config (passed from template context).
- Ensure all transports emit the same event shape so map/UI code is transport-agnostic.

### ✓ Step 4: Integrate transport into journey-live and map
Wire the transport abstraction into the passenger tracking UI and map components.
- Update `static/js/journey-live.js`: replace direct polling with transport abstraction. Read `LOCATION_TRANSPORT` from template data attribute. Use normalized events to update UI (freshness, position, stale state).
- Update `static/js/map/index.js`: accept optional transport instance in constructor options. Use transport events instead of internal polling when transport is provided. Preserve existing `_startPolling` as the default when no transport is passed.
- Update `journeys/views.py::journey_detail` to pass `LOCATION_TRANSPORT` to template context.
- Ensure the initial position still loads via `latest-position` HTTP endpoint.
- Verify conductor-trip.js is unchanged.

### ✓ Step 5: Add configuration documentation
Document the WebSocket setup, deployment requirements, and configuration options.
- Create `WEBSOCKET_SETUP.md` with:
  - `LOCATION_TRANSPORT` modes (polling, websocket, auto) and how to set via env.
  - Redis channel layer configuration for production.
  - ASGI server requirements (uvicorn) vs current WSGI (gunicorn).
  - Render.com deployment notes (ASGI start command, Redis add-on).
  - Security notes (session cookie auth, trip-level authorization).
  - No secrets or local-only config committed.

### ✓ Step 6: Write focused tests for all requirements
Add comprehensive tests for WebSocket functionality and regression tests for existing behavior.
- Create/update `trips/tests.py` with:
  - HTTP ping still works (regression).
  - Invalid coordinates rejected.
  - Out-of-order timestamps don't rewind position.
  - Location history recorded in TripLocationLog.
  - Latest-position endpoint still works.
  - WebSocket: unauthorized user cannot publish locations.
  - WebSocket: unauthorized user cannot subscribe to trip.
  - WebSocket: authorized user can connect to correct trip group.
  - WebSocket: valid location update uses shared service.
  - WebSocket: accepted updates broadcast to group.
  - WebSocket: rejected updates not broadcast.
  - Stale GPS status correct over WebSocket.
- Create tests for transport configuration (polling, websocket, auto mode selection).
- Use `channels.testing.WebsocketCommunicator` for WebSocket tests.
- Run full Django test suite and checks.
- Verify no existing tests are broken.