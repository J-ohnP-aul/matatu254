/**
 * Transport factory — selects the appropriate LocationTransport based on
 * the server-side LOCATION_TRANSPORT setting.
 *
 * Modes:
 * - 'polling'  → PollingTransport only
 * - 'websocket' → WebSocketTransport only
 * - 'auto'     → AutoTransport (WebSocket with polling fallback)
 */

import { PollingTransport } from './polling-transport.js';
import { WebSocketTransport } from './websocket-transport.js';
import { AutoTransport } from './auto-transport.js';

/**
 * Create a transport instance for the given mode.
 *
 * @param {string} mode - 'polling', 'websocket', or 'auto'
 * @param {object} options - shared options passed to the transport
 * @returns {PollingTransport|WebSocketTransport|AutoTransport}
 */
export function createTransport(mode, options = {}) {
  const normalizedMode = (mode || 'polling').toLowerCase().trim();

  switch (normalizedMode) {
    case 'websocket':
      return new WebSocketTransport(options);

    case 'auto':
      return new AutoTransport(options);

    case 'polling':
    default:
      return new PollingTransport(options);
  }
}

export { PollingTransport, WebSocketTransport, AutoTransport };
