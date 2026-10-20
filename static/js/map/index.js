/**
 * Matatu254 Live Vehicle Tracking Map
 * Main entry point - integrates all map components
 * 
 * Google Maps-like navigation feel using Leaflet
 */

import { GPSFilter, KalmanFilter2D } from './gps-filter.js';
import { PositionInterpolator, smoothstep } from './interpolator.js';
import { BearingSmoother, TurnAnticipation, calculateBearing, calculateSpeed } from './bearing.js';
import { projectToPolyline, decodePolyline, distanceAlongPolyline, remainingDistanceAlongPolyline, getPolylineBearing, findNearestStage } from './map-matcher.js';
import { CameraController, enableMapRotation } from './camera.js';
import { ETACalculator, formatDuration, formatDistance } from './eta.js';
import { ModeController, CameraMode } from './modes.js';
import { VehicleMarker, DestinationMarker, StageMarkers, RoutePolyline } from './markers.js';

export class LiveTrackingMap {
  constructor(containerId, options = {}) {
    this.containerId = containerId;
    this.options = {
      // Map options
      center: options.center || [-1.2921, 36.8219], // Nairobi default
      zoom: options.zoom || 13,
      // OSMF's tile policy requires the canonical, non-subdomain endpoint.
      tileLayer: options.tileLayer || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      attribution: options.attribution || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      
      // Tracking options
      journeyId: options.journeyId || null,
      tripId: options.tripId || null,
      apiBase: options.apiBase || '',
      routeDataUrl: options.routeDataUrl || null,
      latestPositionUrl: options.latestPositionUrl || null,
      locationStreamUrl: options.locationStreamUrl || null,
      
      // Behavior options
      gpsFilterAlpha: options.gpsFilterAlpha ?? 0.3,
      interpolationDuration: options.interpolationDuration ?? 1000,
      lowSpeedThreshold: options.lowSpeedThreshold ?? 5,
      recenterThreshold: options.recenterThreshold ?? 50,
      autoRecenterDelay: options.autoRecenterDelay ?? 2000,
      
      // Callbacks
      onError: options.onError || (() => {}),
      onETAUpdate: options.onETAUpdate || (() => {}),
      onStageChange: options.onStageChange || (() => {}),
      onModeChange: options.onModeChange || (() => {})
    };
    
    // Core components
    this.map = null;
    this.gpsFilter = null;
    this.interpolator = null;
    this.bearingSmoother = null;
    this.turnAnticipation = null;
    this.camera = null;
    this.etaCalculator = null;
    this.modeController = null;
    this.vehicleMarker = null;
    this.destinationMarker = null;
    this.stageMarkers = null;
    this.routePolyline = null;
    
    // State
    this.routeData = null;
    this.lastGPSFix = null;
    this.animationId = null;
    this.pollingInterval = null;
    this.lastPositionTimestamp = null;
    this.sseConnection = null;
    this.running = false;
    
    // Performance
    this.lastFrameTime = 0;
    this.frameCount = 0;
  }

  /**
   * Initialize the map and all components
   */
  async init() {
    // Enable map rotation support
    enableMapRotation(L.Map.prototype);
    
    // Create map
    this.map = L.map(this.containerId, {
      center: this.options.center,
      zoom: this.options.zoom,
      zoomControl: true,
      attributionControl: true,
      rotate: true // Enable rotation
    });
    
    // Add tile layer
    L.tileLayer(this.options.tileLayer, {
      attribution: this.options.attribution,
      maxZoom: 19
    }).addTo(this.map);
    
    // Initialize components
    this._initComponents();
    
    // Load route data
    await this._loadRouteData();
    
    // Start tracking
    this.start();
    
    return this;
  }

  _initComponents() {
    // GPS Filter
    this.gpsFilter = new GPSFilter({ alpha: this.options.gpsFilterAlpha });
    
    // Position Interpolator
    this.interpolator = new PositionInterpolator({
      duration: this.options.interpolationDuration,
      easing: smoothstep,
      onUpdate: (pos) => this._onInterpolatedPosition(pos),
      onComplete: (pos) => this._onInterpolationComplete(pos)
    });
    
    // Bearing Smoother
    this.bearingSmoother = new BearingSmoother({
      lowSpeedThreshold: this.options.lowSpeedThreshold,
      lowSpeedHysteresis: this.options.lowSpeedThreshold + 2
    });
    
    // Turn Anticipation
    this.turnAnticipation = new TurnAnticipation({
      anticipationDistance: 50,
      blendDuration: 2000
    });
    
    // Markers
    this.vehicleMarker = new VehicleMarker(this.map);
    this.stageMarkers = new StageMarkers(this.map);
    
    // Camera Controller
    this.camera = new CameraController(this.map, {
      marker: this.vehicleMarker.marker,
      zoomBySpeed: true,
      headingUp: true,
      minZoom: 10,
      maxZoom: 19,
      baseZoom: 17,
      smoothPan: true,
      panDuration: 500,
      recenterThreshold: this.options.recenterThreshold
    });
    
    // ETA Calculator
    this.etaCalculator = new ETACalculator({
      calculationInterval: 5000,
      fullRecalcInterval: 30000,
      onUpdate: (eta) => this._onETAUpdate(eta)
    });
    
    // Mode Controller
    this.modeController = new ModeController({
      dragThreshold: this.options.recenterThreshold,
      autoRecenterDelay: this.options.autoRecenterDelay,
      recenterDistanceThreshold: 100,
      onModeChange: (mode, prev) => this._onModeChange(mode, prev),
      onRecenterRequested: () => this._onRecenterRequested(),
      getVehiclePosition: () => this.vehicleMarker.getPosition(),
      getMapCenter: () => this.map.getCenter(),
      getMapZoom: () => this.map.getZoom(),
      panTo: (latlng, zoom) => this.map.flyTo(latlng, zoom)
    });
    
    // Wire camera mode to mode controller
    this.camera.onModeChange = (mode) => this.modeController.setMode(mode);
    
    // Set up map event listeners for mode controller
    this.map.on('dragstart', () => this.modeController.onUserDrag());
    this.map.on('zoomstart', () => this.modeController.onUserZoom());
  }

  async _loadRouteData() {
    const url = this.options.routeDataUrl || (this.options.journeyId
      ? `${this.options.apiBase}/journeys/session/${this.options.journeyId}/route-data/`
      : null);
    if (!url) {
      console.warn('No route data URL configured; showing the base map without a route');
      return;
    }
    
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to load route');
      
      this.routeData = await response.json();
      this._applyRouteData(this.routeData);
    } catch (error) {
      console.error('Route load failed:', error);
      // The map and tile layer are already initialized. A route failure should
      // leave them visible rather than trying to decode fabricated geometry.
    }
  }

  _useMockData() {
    // Kept for callers that explicitly request a mock, but no route geometry
    // is safer than a placeholder string that the polyline decoder can't read.
    this.routeData = { polyline: null, stages: [], destinationStage: null };
    this._applyRouteData(this.routeData);
  }

  _applyRouteData(data) {
    if (!data) return;
    
    const hasPolyline = typeof data.polyline === 'string' && data.polyline.length > 0;
    const polylineCoords = hasPolyline ? decodePolyline(data.polyline) : [];
    
    // Set route on ETA calculator
    this.etaCalculator.setRoute(polylineCoords, data.stages || [], data.destinationStage);
    
    // Set route on camera for zoom calculations
    // Draw route polyline
    if (hasPolyline && polylineCoords.length >= 2) {
      this.routePolyline = new RoutePolyline(this.map);
      this.routePolyline.setPolyline(data.polyline);
    }
    
    // Add stage markers
    if (Array.isArray(data.stages)) {
      data.stages.forEach(stage => {
        this.stageMarkers.addStage(stage, 'upcoming');
      });
    }
    
    // Add destination marker
    if (data.destinationStage) {
      this.destinationMarker = new DestinationMarker(this.map);
      this.destinationMarker.setPosition(
        data.destinationStage.latitude,
        data.destinationStage.longitude,
        data.destinationStage.name
      );
    }
    
    // Keep the route and its named stages in view after the first GPS fix.
    // Without a route line (for example, when OSRM is unavailable), stage
    // coordinates still provide a useful overview for both dashboards.
    let hasRouteOverview = false;
    if (this.routePolyline) {
      this.routePolyline.fitBounds();
      hasRouteOverview = true;
    } else {
      const stageBounds = (data.stages || [])
        .filter(stage => Number.isFinite(Number(stage.latitude)) &&
          Number.isFinite(Number(stage.longitude)) &&
          stage.latitude !== null && stage.longitude !== null)
        .map(stage => [Number(stage.latitude), Number(stage.longitude)]);
      if (stageBounds.length >= 2) {
        this.map.fitBounds(stageBounds, { padding: [32, 32], maxZoom: 15 });
        hasRouteOverview = true;
      }
    }

    // Start with route context. The recenter button switches back to live
    // vehicle follow when the user wants a navigation close-up.
    if (hasRouteOverview) this.modeController.setMode('free');
  }

  /**
   * Start live tracking
   */
  start() {
    if (this.running) return;
    this.running = true;
    
    // Start animation loop
    this._animate();
    
    // Start GPS updates (SSE or polling)
    this._startGPSUpdates();
    
    // Start mode controller tick
    this.modeTickInterval = setInterval(() => this.modeController.tick(), 1000);
  }

  /**
   * Stop live tracking
   */
  stop() {
    this.running = false;
    
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
    
    if (this.pollingInterval) {
      clearTimeout(this.pollingInterval);
      this.pollingInterval = null;
    }
    if (this._pollResume) {
      window.removeEventListener('online', this._pollResume);
      document.removeEventListener('visibilitychange', this._pollResume);
      this._pollResume = null;
    }
    
    if (this.sseConnection) {
      this.sseConnection.close();
      this.sseConnection = null;
    }
    
    if (this.modeTickInterval) {
      clearInterval(this.modeTickInterval);
    }
  }

  _animate() {
    if (!this.running) return;
    
    this.animationId = requestAnimationFrame(() => this._animate());
  }

  _onInterpolatedPosition(pos) {
    // Update vehicle marker
    const bearingResult = this.bearingSmoother.getBearing();
    const anticipated = this.turnAnticipation.getAnticipatedBearing(
      bearingResult, 
      this._distanceToNextManeuver()
    );
    
    this.vehicleMarker.updatePosition(pos, anticipated.bearing);
    this.vehicleMarker.setBearingSuppressed(this.bearingSmoother.isSuppressed());
    
    // Update camera (if following)
    if (this.modeController.isFollowing()) {
      this.vehicleMarker.marker.speed = this.bearingSmoother.lastSpeed;
      this.vehicleMarker.marker.bearing = anticipated.bearing;
    }
  }

  _onInterpolationComplete(pos) {
    // Interpolation complete, marker at target
  }

  _onETAUpdate(eta) {
    this.options.onETAUpdate(eta);
  }

  _onModeChange(mode, prevMode) {
    this.camera.setMode(mode);
    this.options.onModeChange(mode, prevMode);
  }

  _onRecenterRequested() {
    this.camera.recenter();
    // Wait for recenter to complete
    setTimeout(() => {
      this.modeController.onRecenterComplete();
    }, 600);
  }

  /**
   * Process incoming GPS fix
   */
  processGPSFix(gpsData) {
    if (gpsData?.latitude == null || gpsData?.longitude == null ||
        gpsData.latitude === '' || gpsData.longitude === '') return;
    const latitude = Number(gpsData.latitude);
    const longitude = Number(gpsData.longitude);
    const { bearing, speed, accuracy, timestamp } = gpsData || {};
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
        latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
      console.warn('Ignoring invalid GPS coordinates', gpsData?.latitude, gpsData?.longitude);
      return;
    }

    const parsedFixTime = timestamp ? new Date(timestamp).getTime() : Date.now();
    const fixTime = Number.isFinite(parsedFixTime) ? parsedFixTime : Date.now();
    
    // 1. Filter GPS noise
    const filtered = this.gpsFilter.update(latitude, longitude, fixTime);
    if (!Number.isFinite(filtered.lat) || !Number.isFinite(filtered.lon)) return;
    
    // 2. Calculate speed/bearing if not provided
    let calculatedSpeed = speed;
    let calculatedBearing = bearing;
    
    if (this.lastGPSFix && (calculatedSpeed == null || calculatedBearing == null)) {
      const dt = fixTime - this.lastGPSFix.timestamp;
      if (dt > 0) {
        if (calculatedSpeed == null) {
          calculatedSpeed = calculateSpeed(
            this.lastGPSFix.lat, this.lastGPSFix.lon,
            filtered.lat, filtered.lon, dt
          );
        }
        if (calculatedBearing == null) {
          calculatedBearing = calculateBearing(
            this.lastGPSFix.lat, this.lastGPSFix.lon,
            filtered.lat, filtered.lon
          );
        }
      }
    }
    
    this.lastGPSFix = { ...filtered, timestamp: fixTime, speed: calculatedSpeed, bearing: calculatedBearing };
    
    // 3. Map match to route
    if (this.routeData && this.routeData.polyline) {
      const polylineCoords = decodePolyline(this.routeData.polyline);
      const projected = projectToPolyline(filtered.lat, filtered.lon, polylineCoords);
      
      // 4. Update bearing smoother
      if (calculatedBearing != null) {
        const bearingResult = this.bearingSmoother.update(calculatedBearing, calculatedSpeed || 0);
        
        // 5. Check for upcoming turns
        const polylineBearing = getPolylineBearing(polylineCoords, projected);
        if (Math.abs(bearingResult.bearing - polylineBearing) > 30) {
          // Potential turn ahead
          this.turnAnticipation.setManeuver({
            bearing: polylineBearing,
            distance: 50,
            type: 'turn'
          });
        } else {
          this.turnAnticipation.clearManeuver();
        }
      }
      
      // 6. Start interpolation to map-matched position
      const currentPos = this.vehicleMarker.getPosition();
      if (currentPos) {
        this.interpolator.updateTarget(
          { lat: projected.lat, lon: projected.lon },
          this.options.interpolationDuration
        );
      } else {
        // First position
        this.interpolator.interpolateTo(
          { lat: projected.lat, lon: projected.lon },
          { lat: projected.lat, lon: projected.lon },
          0
        );
      }
      
      // 7. Update ETA
      this.etaCalculator.update(
        { lat: projected.lat, lon: projected.lon, speed: calculatedSpeed },
        projected
      );
      
      // 8. Check stage proximity
      if (this.routeData.stages) {
        const nearestStage = findNearestStage(projected.lat, projected.lon, this.routeData.stages);
        if (nearestStage && nearestStage.distance < 20) {
          this._onStageReached(nearestStage);
        }
      }
      
      // Notify mode controller
      this.modeController.onVehicleUpdate();
    }
  }

  _distanceToNextManeuver() {
    // Simplified - would use routing data in production
    return 100;
  }

  _onStageReached(stage) {
    this.stageMarkers.updateStageStatus(stage.id, 'complete');
    this.options.onStageChange(stage, 'complete');
    
    // Update next stage
    const nextStage = this.routeData.stages.find(s => 
      s.sequenceOrder === stage.sequenceOrder + 1
    );
    if (nextStage) {
      this.stageMarkers.updateStageStatus(nextStage.id, 'current');
      this.options.onStageChange(nextStage, 'current');
    }
  }

  _startGPSUpdates() {
    // Try SSE first, fallback to polling
    // Passenger tracking uses the readable position endpoint. The SSE endpoint
    // is restricted to the assigned operator/conductor and returns 403 here.
    this._startPolling();
  }

  _startSSE() {
    const url = this.options.locationStreamUrl || `${this.options.apiBase}/trips/${this.options.tripId}/location-stream/`;
    
    try {
      this.sseConnection = new EventSource(url);
      
      this.sseConnection.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'ping') {
          this.processGPSFix(data);
        }
      };
      
      this.sseConnection.onerror = () => {
        console.warn('SSE failed, falling back to polling');
        this.sseConnection.close();
        this._startPolling();
      };
    } catch (e) {
      this._startPolling();
    }
  }

  _startPolling() {
    if (this.pollingInterval || !this.options.tripId) return;
    const poll = async () => {
      this.pollingInterval = null;
      if (!this.running || document.hidden || !navigator.onLine) return;
      try {
        const url = this.options.latestPositionUrl || `${this.options.apiBase}/trips/${this.options.tripId}/latest-position/`;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10000);
        const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
        clearTimeout(timeout);
        if (response.ok) {
          const data = await response.json();
          if (data.timestamp && data.timestamp !== this.lastPositionTimestamp) {
            this.lastPositionTimestamp = data.timestamp;
            this.processGPSFix(data);
          }
        }
      } catch (e) { /* Keep the last good position visible and retry. */ }
      if (this.running && !document.hidden) this.pollingInterval = setTimeout(poll, 3000);
    };
    const resume = () => {
      if (this.running && !document.hidden && navigator.onLine && !this.pollingInterval) poll();
    };
    this._pollResume = resume;
    window.addEventListener('online', resume);
    document.addEventListener('visibilitychange', resume);
    resume();
  }

  /**
   * Manual recenter trigger (for button)
   */
  recenter() {
    this.modeController.onRecenterButton();
  }

  /**
   * Get current ETA info
   */
  getETA() {
    return this.etaCalculator.getRemaining();
  }

  /**
   * Get current mode
   */
  getMode() {
    return this.modeController.getMode();
  }

  /**
   * Destroy map and cleanup
   */
  destroy() {
    this.stop();
    
    this.vehicleMarker?.remove();
    this.destinationMarker?.remove();
    this.stageMarkers?.clear();
    this.routePolyline?.remove();
    this.camera?.destroy();
    this.modeController?.destroy();
    
    if (this.map) {
      this.map.remove();
      this.map = null;
    }
  }
}

/**
 * Factory function for easy initialization
 */
export async function createLiveTrackingMap(containerId, options) {
  const map = new LiveTrackingMap(containerId, options);
  await map.init();
  return map;
}

// Export all components for advanced usage
export {
  GPSFilter,
  KalmanFilter2D,
  PositionInterpolator,
  smoothstep,
  BearingSmoother,
  TurnAnticipation,
  CameraController,
  ETACalculator,
  ModeController,
  CameraMode,
  VehicleMarker,
  DestinationMarker,
  StageMarkers,
  RoutePolyline,
  decodePolyline,
  formatDuration,
  formatDistance
};
