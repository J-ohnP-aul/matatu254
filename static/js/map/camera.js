/**
 * Follow Camera Controller
 * Manages map camera: position binding, zoom-by-speed, heading rotation, recenter
 */

import { smoothstep } from './interpolator.js';

export class CameraController {
  constructor(map, options = {}) {
    this.map = map;
    this.marker = options.marker || null;
    
    // Camera mode: 'follow' | 'free' | 'recentering'
    this.mode = 'follow';
    
    // Follow parameters
    this.followOptions = {
      zoomBySpeed: options.zoomBySpeed ?? true,
      headingUp: options.headingUp ?? true,
      minZoom: options.minZoom ?? 10,
      maxZoom: options.maxZoom ?? 19,
      baseZoom: options.baseZoom ?? 17,
      tilt: options.tilt ?? false, // Leaflet doesn't support tilt natively
      smoothPan: options.smoothPan ?? true,
      panDuration: options.panDuration ?? 500,
      zoomDuration: options.zoomDuration ?? 300,
    };
    
    // Recenter button
    this.recenterButton = null;
    this.recenterThreshold = options.recenterThreshold ?? 50; // pixels
    this.recenterDelay = options.recenterDelay ?? 2000; // ms
    
    // State
    this.lastMarkerPos = null;
    this.lastUserInteraction = 0;
    this.userDragged = false;
    this.recenterTimer = null;
    this.targetZoom = null;
    this.targetBearing = null;
    
    // Bind events
    this._bindMapEvents();
    this._createRecenterButton();
  }

  _bindMapEvents() {
    // Detect user interaction
    const events = ['dragstart', 'drag', 'zoomstart', 'zoomend', 'movestart', 'moveend'];
    
    this.map.on('movestart', (e) => {
      if (e.type === 'movestart' && e.hard) {
        // Hard movement = user interaction
        this._onUserInteraction();
      }
    });
    
    this.map.on('dragstart', () => this._onUserInteraction());
    this.map.on('zoomstart', () => this._onUserInteraction());
    
    // Map moveend - check if we should auto-recenter
    this.map.on('moveend', () => {
      if (this.mode === 'free') {
        this._scheduleRecenter();
      }
    });
    
    // Listen for marker position updates
    if (this.marker) {
      this.marker.on('move', () => {
        if (this.mode === 'follow') {
          this._updateCameraForMarker();
        }
      });
    }
  }

  _createRecenterButton() {
    // Create recenter button element
    this.recenterButton = L.Control.extend({
      options: { position: 'bottomright' },
      onAdd: (map) => {
        const btn = L.DomUtil.create('button', 'recenter-btn leaflet-bar leaflet-control');
        btn.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>';
        btn.title = 'Recenter on vehicle';
        btn.style.cssText = `
          background: white; border: none; border-radius: 50%; width: 40px; height: 40px;
          display: flex; align-items: center; justify-content: center; cursor: pointer;
          box-shadow: 0 2px 8px rgba(0,0,0,0.2); opacity: 0; transform: scale(0.8);
          transition: opacity 0.2s, transform 0.2s;
        `;
        btn.onclick = () => this.recenter();
        
        L.DomEvent.disableClickPropagation(btn);
        L.DomEvent.disableScrollPropagation(btn);
        return btn;
      }
    });
    
    this.recenterControl = new this.recenterButton();
    this.recenterControl.addTo(this.map);
    this._updateRecenterButtonVisibility();
  }

  _updateRecenterButtonVisibility() {
    if (!this.recenterControl || !this.recenterControl._container) return;
    
    const btn = this.recenterControl._container;
    if (this.mode === 'free') {
      btn.style.opacity = '1';
      btn.style.transform = 'scale(1)';
    } else {
      btn.style.opacity = '0';
      btn.style.transform = 'scale(0.8)';
    }
  }

  _onUserInteraction() {
    this.lastUserInteraction = Date.now();
    this.userDragged = true;
    
    if (this.mode === 'follow') {
      this.setMode('free');
    }
    
    this._clearRecenterTimer();
    this._scheduleRecenter();
  }

  _scheduleRecenter() {
    this._clearRecenterTimer();
    this.recenterTimer = setTimeout(() => {
      if (this.mode === 'free' && this._shouldAutoRecenter()) {
        this.recenter();
      }
    }, this.recenterDelay);
  }

  _clearRecenterTimer() {
    if (this.recenterTimer) {
      clearTimeout(this.recenterTimer);
      this.recenterTimer = null;
    }
  }

  _shouldAutoRecenter() {
    if (!this.marker || !this.marker.getLatLng) return false;
    
    const markerPos = this.marker.getLatLng();
    const containerPoint = this.map.latLngToContainerPoint(markerPos);
    const centerPoint = this.map.getSize().divideBy(2);
    
    const distance = containerPoint.distanceTo(centerPoint);
    return distance > this.recenterThreshold;
  }

  /**
   * Set camera mode
   */
  setMode(mode) {
    if (this.mode === mode) return;
    
    const prevMode = this.mode;
    this.mode = mode;
    this._updateRecenterButtonVisibility();
    
    if (mode === 'follow') {
      this.userDragged = false;
      this._clearRecenterTimer();
      this._updateCameraForMarker(true); // Immediate snap
    }
    
    this.onModeChange?.(mode, prevMode);
  }

  /**
   * Recenter camera on marker with animation
   */
  recenter() {
    if (this.mode === 'follow') return;
    
    this.setMode('recentering');
    
    if (!this.marker || !this.marker.getLatLng) {
      this.setMode('follow');
      return;
    }
    
    const markerLatLng = this.marker.getLatLng();
    const targetZoom = this.targetZoom ?? this.map.getZoom();
    const targetBearing = this.targetBearing ?? 0;
    
    // Animate camera to marker
    this.map.flyTo(markerLatLng, targetZoom, {
      animate: true,
      duration: this.followOptions.panDuration / 1000,
      easeLinearity: 0.25,
      noMoveStart: true
    });
    
    // If heading-up, animate rotation
    if (this.followOptions.headingUp && this.map.setBearing) {
      this.map.setBearing(targetBearing, { animate: true, duration: this.followOptions.panDuration / 1000 });
    }
    
    // Wait for animation to complete
    setTimeout(() => {
      this.setMode('follow');
    }, this.followOptions.panDuration);
  }

  /**
   * Update camera for marker position (called in follow mode)
   */
  _updateCameraForMarker(immediate = false) {
    if (!this.marker || !this.marker.getLatLng) return;
    
    const markerLatLng = this.marker.getLatLng();
    const speed = this.marker.speed || 0; // km/h
    const bearing = this.marker.bearing || 0;
    
    // Update target zoom based on speed
    if (this.followOptions.zoomBySpeed) {
      this.targetZoom = this._calculateZoomForSpeed(speed);
    }
    
    // Update target bearing for heading-up
    if (this.followOptions.headingUp) {
      this.targetBearing = bearing;
    }
    
    if (immediate) {
      this.map.setView(markerLatLng, this.targetZoom, { animate: false });
      if (this.followOptions.headingUp && this.map.setBearing) {
        this.map.setBearing(this.targetBearing, { animate: false });
      }
    } else {
      // Smooth pan
      this.map.panTo(markerLatLng, {
        animate: this.followOptions.smoothPan,
        duration: this.followOptions.panDuration / 1000,
        easeLinearity: 0.25,
        noMoveStart: true
      });
      
      // Smooth zoom
      if (Math.abs(this.map.getZoom() - this.targetZoom) > 0.1) {
        this.map.animateZoom(this.targetZoom, {
          center: markerLatLng,
          duration: this.followOptions.zoomDuration / 1000
        });
      }
      
      // Smooth bearing rotation
      if (this.followOptions.headingUp && this.map.setBearing) {
        this.map.setBearing(this.targetBearing, {
          animate: true,
          duration: this.followOptions.panDuration / 1000
        });
      }
    }
  }

  /**
   * Calculate zoom level based on speed
   * Google Maps-like zoom curve
   */
  _calculateZoomForSpeed(speedKmh) {
    const { minZoom, maxZoom, baseZoom } = this.followOptions;
    
    if (speedKmh <= 5) return baseZoom;
    
    // Logarithmic zoom reduction
    // At 5 km/h: baseZoom
    // At 100 km/h: baseZoom - 5
    const zoomReduction = Math.log2(speedKmh / 5) * 2.5;
    const zoom = baseZoom - zoomReduction;
    
    return Math.max(minZoom, Math.min(maxZoom, zoom));
  }

  /**
   * Update marker reference
   */
  setMarker(marker) {
    this.marker = marker;
  }

  /**
   * Get current mode
   */
  getMode() {
    return this.mode;
  }

  /**
   * Check if in follow mode
   */
  isFollowing() {
    return this.mode === 'follow';
  }

  /**
   * Cleanup
   */
  destroy() {
    this._clearRecenterTimer();
    this.map.off('movestart');
    this.map.off('dragstart');
    this.map.off('zoomstart');
    this.map.off('moveend');
    if (this.recenterControl) {
      this.recenterControl.remove();
    }
  }
}

/**
 * Leaflet map extension for bearing/rotation support
 * Requires leaflet-rotatedmarker or similar plugin
 */
export function enableMapRotation(map) {
  if (map.setBearing) return; // Already enabled
  
  // Add setBearing method using CSS transform on map pane
  map.setBearing = function(bearing, options = {}) {
    const mapPane = this.getPane('mapPane');
    if (!mapPane) return;
    
    const duration = options.animate ? (options.duration || 0.5) : 0;
    mapPane.style.transition = duration > 0 ? `transform ${duration}s ease-out` : 'none';
    mapPane.style.transform = `rotate(${bearing}deg)`;
    mapPane.style.transformOrigin = 'center center';
    
    this._bearing = bearing;
    
    // Update rotated markers
    this.eachLayer((layer) => {
      if (layer.setRotationAngle) {
        layer.setRotationAngle(bearing);
      } else if (layer.setRotationOrigin) {
        layer.setRotationOrigin('center center');
      }
    });
    
    return this;
  };
  
  map.getBearing = function() {
    return this._bearing || 0;
  };
}