# WebSocket Live Location Tracking — Setup Guide

## Overview

This project supports three transport modes for real-time vehicle location updates:

| Mode | Description |
|------|-------------|
| `polling` | HTTP polling (default, works with current WSGI deployment) |
| `websocket` | WebSocket connections for real-time updates |
| `auto` | WebSocket with automatic polling fallback |

## Configuration

Set the `LOCATION_TRANSPORT` environment variable:

```bash
# Default — HTTP polling only (no changes to deployment needed)
export LOCATION_TRANSPORT=polling

# WebSocket only — requires ASGI server
export LOCATION_TRANSPORT=websocket

# WebSocket with polling fallback — recommended for production
export LOCATION_TRANSPORT=auto
```

### Docker / Render.com

Add to your environment variables:

```
LOCATION_TRANSPORT=auto
```

## Deployment Requirements

### Polling Mode (Default)

No changes required. The existing gunicorn WSGI deployment works as-is.

### WebSocket and Auto Modes

WebSocket mode requires an **ASGI server** instead of (or in addition to) the WSGI server.

#### ASGI Server

Install `uvicorn`:

```bash
pip install uvicorn
```

Start the application:

```bash
uvicorn config.asgi:application --host 0.0.0.0 --port $PORT
```

#### Render.com Deployment

1. Add the Redis add-on for the channel layer (required for multi-worker setups).
2. Set `REDIS_URL` environment variable (Render does this automatically when you add the Redis service).
3. Update the start command to use uvicorn:

```yaml
services:
  - type: web
    name: matatu254
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn config.asgi:application --host 0.0.0.0 --port $PORT"
    envVars:
      - key: LOCATION_TRANSPORT
        value: auto
      - key: REDIS_URL
        fromService:
          type: redis
          name: matatu254-redis
          property: connectionString
```

#### Redis Channel Layer

For production multi-worker deployments, configure Redis:

```bash
export REDIS_URL=redis://your-redis-host:6379/0
```

The application automatically detects `REDIS_URL` and switches from the in-memory channel layer to Redis.

For local development, the in-memory channel layer works fine with a single process.

## Security

### Authentication

WebSocket connections use the same Django session cookie as HTTP requests. No additional token-based authentication is added.

### Authorization

- **Publish** (send location updates): Only assigned conductors or matatu owners.
- **Subscribe** (receive location updates): Passengers with an active journey session, conductors, matatu owners, and admins.
- A user cannot gain access to a trip by changing the trip ID in the WebSocket URL.

### Same-Origin

WebSocket connections use the same origin as the HTTP page. Cross-origin WebSocket connections require additional CORS configuration.

## Architecture

```
Conductor Browser → POST /trips/<id>/ping/ → record_ping() → ActiveTrip cache
                                                              ↓
Passenger Browser ← GET /trips/<id>/latest-position/ (initial load)
Passenger Browser ← WS /ws/trips/<id>/ (real-time updates via trip_<id> group)
```

## Troubleshooting

### WebSocket connection fails

1. Verify `LOCATION_TRANSPORT` is set correctly.
2. Check that the ASGI server (uvicorn) is running, not just gunicorn.
3. In the browser console, look for WebSocket upgrade errors.
4. In `auto` mode, the client will fall back to polling automatically.

### Stale location after WebSocket reconnect

The stale threshold (`GPS_STALE_AFTER_SECONDS = 60`) is enforced server-side. A WebSocket connection does not make old GPS data appear live.

### Duplicate updates in auto mode

The `AutoTransport` ensures only one active transport at a time. If you see duplicate position events, check the browser console for transport switch logs.
