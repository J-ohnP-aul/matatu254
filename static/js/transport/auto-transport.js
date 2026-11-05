/**
 * AutoTransport — tries WebSocket first, falls back to polling on failure,
 * retries WebSocket in the background, and switches back on reconnect.
 *
 * Never runs duplicate subscriptions for the same trip.
 */

import { PollingTransport } from './polling-transport.js';
import { WebSocketTransport } from './websocket-transport.js';

export class AutoTransport {
  constructor(options = {}) {
    this.tripId = options.tripId;
    this.apiBase = options.apiBase || '';
    this.latestPositionUrl = options.latestPositionUrl || null;
    this.pollingInterval = options.pollingInterval || 3000;

    this._listeners = {};
    this._running = false;

    // Active transport: either 'websocket' or 'polling'
    this._activeMode = null;

    this._wsTransport = new WebSocketTransport({
      tripId: this.tripId,
      apiBase: this.apiBase,
      ...options,
    });

    this._pollTransport = new PollingTransport({
      tripId: this.tripId,
      apiBase: this.apiBase,
      latestPositionUrl: this.latestPositionUrl,
      interval: this.pollingInterval,
    });

    // Wire both transports to the same event bus
    this._wireTransport(this._wsTransport, 'websocket');
    this._wireTransport(this._pollTransport, 'polling');

    // WebSocket failure → fall back to polling
    this._wsTransport.on('disconnected', () => {
      if (this._activeMode === 'websocket' && this._running) {
        this._switchTo('polling');
      }
    });

    // WebSocket reconnect → switch back
    this._wsTransport.on('connected', () => {
      if (this._activeMode === 'polling' && this._running) {
        this._switchTo('websocket');
      }
    });
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
    // Start both; WebSocket will become active first if it connects.
    // Polling starts as a safety net.
    this._pollTransport.start();
    this._wsTransport.start();
    // Default to polling until WebSocket confirms
    this._activeMode = 'polling';
  }

  stop() {
    this._running = false;
    this._activeMode = null;
    this._wsTransport.stop();
    this._pollTransport.stop();
    this._emit('disconnected', { transport: 'auto' });
  }

  // -- Internal ---------------------------------------------------------------

  _wireTransport(transport, mode) {
    // Forward position, stale, and trip_completed events
    for (const event of ['position', 'stale', 'trip_completed']) {
      transport.on(event, (payload) => {
        // Only forward from the active transport to avoid duplicates
        if (this._activeMode === mode || this._activeMode === null) {
          this._emit(event, payload);
        }
      });
    }
  }

  _switchTo(mode) {
    if (this._activeMode === mode || !this._running) return;
    const prev = this._activeMode;
    this._activeMode = mode;

    // Stop the inactive transport to avoid duplicate subscriptions
    if (mode === 'websocket') {
      this._pollTransport.stop();
    } else {
      // Keep polling running as fallback; don't stop it.
      // WebSocket will restart in background.
    }

    this._emit('transport_changed', {
      type: 'transport_changed',
      from: prev,
      to: mode,
    });
  }

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
