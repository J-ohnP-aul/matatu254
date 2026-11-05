/**
 * WebSocketTransport — connects to the trip WebSocket endpoint for real-time
 * location updates.
 *
 * Emits the same normalized events as PollingTransport so map / UI code is
 * transport-agnostic.
 */

export class WebSocketTransport {
  constructor(options = {}) {
    this.tripId = options.tripId;
    this.apiBase = options.apiBase || '';
    this.reconnectDelay = options.reconnectDelay || 3000;
    this.maxReconnectDelay = options.maxReconnectDelay || 30000;

    this._listeners = {};
    this._ws = null;
    this._running = false;
    this._reconnectTimer = null;
    this._currentDelay = this.reconnectDelay;
    this._lastTimestamp = null;
  }

  // -- Public API -------------------------------------------------------------

  on(event, callback) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(callback);
    return () => {
      this._listeners[event] = this._listeners[event].filter((cb) => cb !== callback);
    };
  }

  start() {
    if (this._running) return;
    this._running = true;
    this._currentDelay = this.reconnectDelay;
    this._connect();
  }

  stop() {
    this._running = false;
    this._clearReconnectTimer();
    if (this._ws) {
      this._ws.onclose = null;
      this._ws.onerror = null;
      this._ws.onmessage = null;
      this._ws.close();
      this._ws = null;
    }
    this._emit('disconnected', { transport: 'websocket' });
  }

  // -- WebSocket lifecycle ----------------------------------------------------

  _connect() {
    if (!this._running) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/trips/${this.tripId}/`;

    try {
      this._ws = new WebSocket(url);
    } catch (_) {
      this._handleClose();
      return;
    }

    this._ws.binaryType = 'blob';

    this._ws.onopen = () => {
      this._currentDelay = this.reconnectDelay;
      this._emit('connected', { transport: 'websocket' });
    };

    this._ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this._handleMessage(data);
      } catch (_) {
        // Ignore malformed messages.
      }
    };

    this._ws.onclose = () => {
      this._ws = null;
      this._handleClose();
    };

    this._ws.onerror = () => {
      // onclose will fire after onerror; handle reconnection there.
    };
  }

  _handleMessage(data) {
    switch (data.type) {
      case 'connected':
        // Server confirms connection; already emitted on open.
        break;

      case 'location.accepted':
        // Deduplicate by timestamp
        if (data.timestamp && data.timestamp !== this._lastTimestamp) {
          this._lastTimestamp = data.timestamp;
          this._emit('position', {
            type: 'position',
            latitude: data.latitude,
            longitude: data.longitude,
            timestamp: data.timestamp,
            gps_age_seconds: data.gps_age_seconds,
            is_stale: data.is_stale,
          });

          if (data.is_stale) {
            this._emit('stale', { type: 'stale', is_stale: true });
          }
        }
        break;

      case 'location.rejected':
        // Server rejected the update — informational.
        break;

      case 'trip.completed':
        this._emit('trip_completed', data);
        break;

      default:
        break;
    }
  }

  _handleClose() {
    this._emit('disconnected', { transport: 'websocket' });
    if (this._running) {
      this._scheduleReconnect();
    }
  }

  _scheduleReconnect() {
    this._clearReconnectTimer();
    this._reconnectTimer = setTimeout(() => {
      if (this._running) this._connect();
    }, this._currentDelay);
    // Exponential backoff
    this._currentDelay = Math.min(this._currentDelay * 2, this.maxReconnectDelay);
  }

  _clearReconnectTimer() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }

  // -- Event helpers ----------------------------------------------------------

  _emit(event, payload) {
    const cbs = this._listeners[event] || [];
    for (const cb of cbs) {
      try {
        cb(payload);
      } catch (_) {
        // Listener error should not break the transport.
      }
    }
  }
}
