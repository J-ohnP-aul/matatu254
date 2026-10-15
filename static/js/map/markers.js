/**
 * Marker Management
 * Vehicle marker, destination marker, stage markers
 */

import { smoothstep } from './interpolator.js';

export class VehicleMarker {
  constructor(map, options = {}) {
    this.map = map;
    this.marker = null;
    this.options = {
      iconSize: options.iconSize ?? [40, 40],
      iconAnchor: options.iconAnchor ?? [20, 40],
      rotationOrigin: options.rotationOrigin ?? 'center center',
      zIndexOffset: options.zIndexOffset ?? 1000
    };
    
    this.currentPos = null;
    this.targetPos = null;
    this.currentBearing = 0;
    this.targetBearing = 0;
    this.speed = 0;
    this.suppressed = false;
    
    this._createMarker();
  }

  _createMarker() {
    // Create vehicle icon SVG
    const iconHtml = this._createVehicleIcon();
    
    this.marker = L.marker([0, 0], {
      icon: L.divIcon({
        html: iconHtml,
        className: 'vehicle-marker',
        iconSize: this.options.iconSize,
        iconAnchor: this.options.iconAnchor
      }),
      zIndexOffset: this.options.zIndexOffset,
      rotationAngle: 0,
      rotationOrigin: this.options.rotationOrigin
    }).addTo(this.map);
  }

  _createVehicleIcon() {
    return `
      <div class="vehicle-icon" style="transform: rotate(0deg); transition: transform 0.1s linear;">
        <svg width="40" height="40" viewBox="0 0 40 40" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">
          <!-- Vehicle body -->
          <path d="M20 4 L30 16 L30 28 L24 34 L16 34 L10 28 L10 16 Z" 
                fill="#087a45" stroke="#065a32" stroke-width="1.5"/>
          <!-- Roof -->
          <path d="M20 8 L26 16 L14 16 Z" fill="#0a9050"/>
          <!-- Windshield -->
          <path d="M20 10 L24 16 L16 16 Z" fill="#7dd3a0" opacity="0.8"/>
          <!-- Wheels -->
          <circle cx="13" cy="28" r="3" fill="#1a2a20"/>
          <circle cx="27" cy="28" r="3" fill="#1a2a20"/>
          <!-- Direction indicator -->
          <polygon points="20,22 17,27 23,27" fill="#fff" opacity="0.9"/>
        </svg>
      </div>
    `;
  }

  /**
   * Set target position for smooth interpolation
   */
  setTargetPosition(lat, lon, bearing = null, speed = 0) {
    if (!this._isValidPosition(lat, lon)) return;
    this.targetPos = { lat, lon };
    if (bearing !== null) this.targetBearing = bearing;
    this.speed = speed;
    
    if (!this.currentPos) {
      // First position - set immediately
      this.currentPos = { lat, lon };
      this.currentBearing = bearing ?? 0;
      this._updateMarker();
    }
  }

  /**
   * Update marker position (called from animation loop)
   * @param {Object} interpolatedPos - { lat, lon, progress }
   * @param {number} bearing - Smoothed bearing
   */
  updatePosition(interpolatedPos, bearing) {
    if (!interpolatedPos || !this._isValidPosition(interpolatedPos.lat, interpolatedPos.lon)) return;
    this.currentPos = { lat: interpolatedPos.lat, lon: interpolatedPos.lon };
    this.currentBearing = Number.isFinite(Number(bearing)) ? Number(bearing) : this.currentBearing;
    this._updateMarker();
  }

  _isValidPosition(lat, lon) {
    return lat != null && lon != null && lat !== '' && lon !== '' &&
      Number.isFinite(Number(lat)) && Number.isFinite(Number(lon)) &&
      Number(lat) >= -90 && Number(lat) <= 90 &&
      Number(lon) >= -180 && Number(lon) <= 180;
  }

  _updateMarker() {
    if (!this.marker || !this.currentPos ||
        !this._isValidPosition(this.currentPos.lat, this.currentPos.lon)) return;
    
    // Update position
    this.marker.setLatLng([this.currentPos.lat, this.currentPos.lon]);
    
    // Update rotation if supported
    if (this.marker.setRotationAngle) {
      this.marker.setRotationAngle(this.currentBearing);
    } else {
      // Fallback: CSS transform on icon
      const iconEl = this.marker.getElement();
      if (iconEl) {
        const vehicleIcon = iconEl.querySelector('.vehicle-icon');
        if (vehicleIcon) {
          vehicleIcon.style.transform = `rotate(${this.currentBearing}deg)`;
        }
      }
    }
    
    // Update suppressed state visual
    if (this.suppressed) {
      this.marker.getElement()?.classList.add('bearing-suppressed');
    } else {
      this.marker.getElement()?.classList.remove('bearing-suppressed');
    }
  }

  setBearingSuppressed(suppressed) {
    this.suppressed = suppressed;
    this._updateMarker();
  }

  getPosition() {
    return this.currentPos;
  }

  getLatLng() {
    if (!this.currentPos) return null;
    return L.latLng(this.currentPos.lat, this.currentPos.lon);
  }

  getElement() {
    return this.marker?.getElement();
  }

  remove() {
    if (this.marker) {
      this.marker.remove();
      this.marker = null;
    }
  }
}

export class DestinationMarker {
  constructor(map, options = {}) {
    this.map = map;
    this.marker = null;
    this._createMarker(options);
  }

  _createMarker(options) {
    const iconHtml = `
      <div class="destination-marker">
        <svg width="36" height="48" viewBox="0 0 24 32" fill="none" stroke="#087a45" stroke-width="2">
          <path d="M12 2C7.58 2 4 5.58 4 10c0 5.25 7 20 7 20s7-14.75 7-20C20 5.58 16.42 2 12 2z"/>
          <circle cx="12" cy="10" r="3" fill="#087a45"/>
        </svg>
        <span class="destination-label" style="
          position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
          white-space: nowrap; background: #087a45; color: white; padding: 2px 8px;
          border-radius: 4px; font-size: 11px; font-weight: 600; margin-top: 4px;
        ">${options.label || 'Destination'}</span>
      </div>
    `;
    
    this.marker = L.marker([0, 0], {
      icon: L.divIcon({
        html: iconHtml,
        className: 'destination-marker-container',
        iconSize: [36, 48],
        iconAnchor: [18, 48]
      }),
      zIndexOffset: 900
    }).addTo(this.map);
  }

  setPosition(lat, lon, label = null) {
    this.marker.setLatLng([lat, lon]);
    if (label) {
      const el = this.marker.getElement();
      if (el) {
        const labelEl = el.querySelector('.destination-label');
        if (labelEl) labelEl.textContent = label;
      }
    }
  }

  remove() {
    if (this.marker) {
      this.marker.remove();
      this.marker = null;
    }
  }
}

export class StageMarkers {
  constructor(map, options = {}) {
    this.map = map;
    this.markers = new Map(); // stageId -> marker
    this.options = options;
  }

  addStage(stage, status = 'upcoming') {
    const iconHtml = this._createStageIcon(stage, status);
    
    const marker = L.marker([stage.latitude, stage.longitude], {
      icon: L.divIcon({
        html: iconHtml,
        className: `stage-marker stage-${status}`,
        iconSize: [32, 32],
        iconAnchor: [16, 16]
      }),
      zIndexOffset: 800
    }).addTo(this.map);

    const label = document.createElement('span');
    label.textContent = stage.name;
    label.style.cssText = [
      'color:#17251c',
      'font:600 12px/1.25 system-ui,sans-serif',
      'white-space:nowrap'
    ].join(';');
    marker.bindTooltip(label, {
      permanent: true,
      direction: 'right',
      offset: [10, 0],
      opacity: 1,
      className: 'stage-name-tooltip'
    });
    
    this.markers.set(stage.id, marker);
    return marker;
  }

  _createStageIcon(stage, status) {
    const colors = {
      upcoming: { bg: '#fff', border: '#087a45', icon: '#087a45' },
      current: { bg: '#e8f1e9', border: '#a8cdb5', icon: '#087a45' },
      complete: { bg: '#f0f0f0', border: '#d0d0d0', icon: '#718076' },
      next: { bg: '#e8f1e9', border: '#a8cdb5', icon: '#f7b51b' }
    };
    
    const c = colors[status] || colors.upcoming;
    
    return `
      <div class="stage-icon" style="
        width: 32px; height: 32px; border-radius: 50%;
        background: ${c.bg}; border: 3px solid ${c.border};
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
        transition: all 0.3s ease;
      ">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${c.icon}" stroke-width="2.5">
          ${status === 'complete' 
            ? '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/>'
            : '<path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>'
          }
        </svg>
      </div>
    `;
  }

  updateStageStatus(stageId, status) {
    const marker = this.markers.get(stageId);
    if (!marker) return;
    
    const iconHtml = this._createStageIcon({ id: stageId }, status);
    marker.setIcon(L.divIcon({
      html: iconHtml,
      className: `stage-marker stage-${status}`,
      iconSize: [32, 32],
      iconAnchor: [16, 16]
    }));
  }

  removeStage(stageId) {
    const marker = this.markers.get(stageId);
    if (marker) {
      marker.remove();
      this.markers.delete(stageId);
    }
  }

  clear() {
    this.markers.forEach(marker => marker.remove());
    this.markers.clear();
  }
}

export class RoutePolyline {
  constructor(map, options = {}) {
    this.map = map;
    this.polyline = null;
    this.options = {
      color: options.color ?? '#087a45',
      weight: options.weight ?? 4,
      opacity: options.opacity ?? 0.8,
      dashArray: options.dashArray ?? null,
      lineCap: options.lineCap ?? 'round',
      lineJoin: options.lineJoin ?? 'round'
    };
  }

  setPolyline(encodedPolyline) {
    if (this.polyline) {
      this.polyline.remove();
    }
    
    const coords = decodePolyline(encodedPolyline);
    const latLngs = coords.map(([lat, lon]) => L.latLng(lat, lon));
    
    this.polyline = L.polyline(latLngs, this.options).addTo(this.map);
    return this.polyline;
  }

  setProgress(progress) {
    // Progress: 0-1, show completed portion in different style
    // Could use L.PolylineDecorator or split into two polylines
    if (!this.polyline) return;
    
    // Simple approach: just update opacity/color based on progress
    // For true progress, would need to split polyline
  }

  fitBounds(padding = [20, 20]) {
    if (this.polyline) {
      this.map.fitBounds(this.polyline.getBounds(), { padding: L.point(...padding) });
    }
  }

  getBounds() {
    return this.polyline?.getBounds();
  }

  remove() {
    if (this.polyline) {
      this.polyline.remove();
      this.polyline = null;
    }
  }
}

// Re-export decodePolyline from map-matcher
import { decodePolyline } from './map-matcher.js';
export { decodePolyline };
