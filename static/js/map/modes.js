/**
 * Camera Mode State Machine
 * Manages Free / Follow / Recenter transitions
 */

export const CameraMode = {
  FREE: 'free',
  FOLLOW: 'follow',
  RECENTERING: 'recentering'
};

export class ModeController {
  constructor(options = {}) {
    this.mode = CameraMode.FOLLOW;
    this.previousMode = null;
    
    // Thresholds
    this.dragThreshold = options.dragThreshold ?? 50; // pixels
    this.autoRecenterDelay = options.autoRecenterDelay ?? 2000; // ms
    this.recenterDistanceThreshold = options.recenterDistanceThreshold ?? 100; // meters
    
    // State
    this.lastUserInteraction = 0;
    this.userDragged = false;
    this.autoRecenterTimer = null;
    this.vehicleMovedSinceInteraction = false;
    
    // Callbacks
    this.onModeChange = options.onModeChange || (() => {});
    this.onRecenterRequested = options.onRecenterRequested || (() => {});
    this.getVehiclePosition = options.getVehiclePosition || (() => null);
    this.getMapCenter = options.getMapCenter || (() => null);
    this.getMapZoom = options.getMapZoom || (() => 0);
    this.panTo = options.panTo || (() => {});
    
    // Hysteresis
    this.hysteresisTimer = null;
  }

  /**
   * Handle user drag/pan interaction
   */
  onUserDrag(distance = 0) {
    const now = Date.now();
    this.lastUserInteraction = now;
    this.userDragged = true;
    this.vehicleMovedSinceInteraction = false;
    
    if (this.mode === CameraMode.FOLLOW && distance > this.dragThreshold) {
      this._transitionTo(CameraMode.FREE);
    }
    
    this._scheduleAutoRecenter();
  }

  /**
   * Handle user zoom interaction
   */
  onUserZoom() {
    const now = Date.now();
    this.lastUserInteraction = now;
    this.userDragged = true;
    
    if (this.mode === CameraMode.FOLLOW) {
      this._transitionTo(CameraMode.FREE);
    }
    
    this._scheduleAutoRecenter();
  }

  /**
   * Handle recenter button click
   */
  onRecenterButton() {
    this._requestRecenter();
  }

  /**
   * Called when vehicle position updates
   */
  onVehicleUpdate() {
    this.vehicleMovedSinceInteraction = true;
  }

  /**
   * Called periodically to check auto-recenter conditions
   */
  tick() {
    if (this.mode !== CameraMode.FREE) return;
    // An initial route overview is also represented by FREE mode. Only start
    // automatic recentering after the user has interacted with the map.
    if (!this.lastUserInteraction) return;
    
    const now = Date.now();
    const timeSinceInteraction = now - this.lastUserInteraction;
    
    // Check if we should auto-recenter
    if (timeSinceInteraction >= this.autoRecenterDelay) {
      if (this._shouldAutoRecenter()) {
        this._requestRecenter();
      }
    }
  }

  _shouldAutoRecenter() {
    // Don't auto-recenter if user is actively dragging
    if (this.userDragged && Date.now() - this.lastUserInteraction < 500) {
      return false;
    }
    
    // Check if vehicle has moved significantly from map center
    const vehiclePos = this.getVehiclePosition();
    const mapCenter = this.getMapCenter();
    
    if (!vehiclePos || !mapCenter) return false;
    
    const distance = haversineDistance(
      vehiclePos.lat, vehiclePos.lon,
      mapCenter.lat, mapCenter.lng
    );
    
    return distance > this.recenterDistanceThreshold;
  }

  _scheduleAutoRecenter() {
    if (this.autoRecenterTimer) {
      clearTimeout(this.autoRecenterTimer);
    }
    
    this.autoRecenterTimer = setTimeout(() => {
      if (this.mode === CameraMode.FREE && this._shouldAutoRecenter()) {
        this._requestRecenter();
      }
    }, this.autoRecenterDelay);
  }

  _requestRecenter() {
    this._transitionTo(CameraMode.RECENTERING);
    this.onRecenterRequested();
  }

  /**
   * Called when recenter animation completes
   */
  onRecenterComplete() {
    this._transitionTo(CameraMode.FOLLOW);
    this.userDragged = false;
    this.vehicleMovedSinceInteraction = false;
  }

  _transitionTo(newMode) {
    if (this.mode === newMode) return;
    
    this.previousMode = this.mode;
    this.mode = newMode;
    
    // Clear auto-recenter timer when leaving FREE mode
    if (this.previousMode === CameraMode.FREE) {
      if (this.autoRecenterTimer) {
        clearTimeout(this.autoRecenterTimer);
        this.autoRecenterTimer = null;
      }
    }
    
    this.onModeChange(newMode, this.previousMode);
  }

  /**
   * Force mode change (external)
   */
  setMode(mode) {
    if (Object.values(CameraMode).includes(mode)) {
      this._transitionTo(mode);
    }
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
    return this.mode === CameraMode.FOLLOW;
  }

  /**
   * Check if in free mode
   */
  isFree() {
    return this.mode === CameraMode.FREE;
  }

  /**
   * Check if recentering
   */
  isRecentering() {
    return this.mode === CameraMode.RECENTERING;
  }

  /**
   * Get time since last user interaction
   */
  getTimeSinceInteraction() {
    return Date.now() - this.lastUserInteraction;
  }

  /**
   * Reset controller
   */
  reset() {
    this.mode = CameraMode.FOLLOW;
    this.previousMode = null;
    this.lastUserInteraction = 0;
    this.userDragged = false;
    this.vehicleMovedSinceInteraction = false;
    
    if (this.autoRecenterTimer) {
      clearTimeout(this.autoRecenterTimer);
      this.autoRecenterTimer = null;
    }
  }

  destroy() {
    if (this.autoRecenterTimer) {
      clearTimeout(this.autoRecenterTimer);
    }
    if (this.hysteresisTimer) {
      clearTimeout(this.hysteresisTimer);
    }
  }
}

/**
 * Haversine distance for mode controller
 */
function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon/2)**2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function toRad(deg) { return deg * Math.PI / 180; }

/**
 * Hook for React-like usage (if using a framework)
 */
export function useModeController(options) {
  const controller = new ModeController(options);
  
  // Auto-tick
  let tickInterval = setInterval(() => controller.tick(), 1000);
  
  return {
    controller,
    destroy: () => {
      clearInterval(tickInterval);
      controller.destroy();
    }
  };
}
