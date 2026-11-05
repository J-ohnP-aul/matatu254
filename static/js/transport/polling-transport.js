/**
 * PollingTransport — polls the latest-position HTTP endpoint at a fixed interval.
 *
 * Emits normalized events so map / UI code is transport-agnostic.
 */

export class PollingTransport {
  constructor(options = {}) {
    this.tripId = options.tripId;
    this.apiBase = options.apiBase || '';
    this.latestPositionUrl = options.latestPositionUrl || null;
    this.interval = options.interval || 3000;

    this._listeners = {};
    this._timer = null;
    this._running = false;
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
    this._emit('connected', { transport: 'polling' });
    this._poll();
  }

  stop() {
    this._running = false;
    if (this._timer) {
      clearTimeout(this._timer);
      this._timer = null;
    }
    this._emit('disconnected', { transport: 'polling' });
  }

  // -- Polling loop -----------------------------------------------------------

  _poll() {
    if (!this._running || document.hidden || !navigator.onLine) {
      this._scheduleNext();
      return;
    }

    const url =
      this.latestPositionUrl ||
      `${this.apiBase}/trips/${this.tripId}/latest-position/`;

    fetch(url, { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        // Deduplicate: only forward when the timestamp changes
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
      })
      .catch(() => {
        // Silently retry — the next poll will pick it up.
      })
      .finally(() => {
        this._scheduleNext();
      });
  }

  _scheduleNext() {
    if (this._timer) clearTimeout(this._timer);
    if (this._running && !document.hidden) {
      this._timer = setTimeout(() => this._poll(), this.interval);
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
