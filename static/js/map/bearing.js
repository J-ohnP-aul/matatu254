/**
 * Bearing/Heading Smoothing with Low-Speed Suppression
 * Handles noisy GPS course data, suppresses rotation below ~5 km/h
 */

const LOW_SPEED_THRESHOLD = 5; // km/h
const LOW_SPEED_HYSTERESIS = 7; // km/h (resume threshold)
const HIGH_SPEED_ALPHA = 0.15;
const MEDIUM_SPEED_ALPHA = 0.05;
const LOW_SPEED_ALPHA = 0; // Suppressed

export class BearingSmoother {
  constructor(options = {}) {
    this.lowSpeedThreshold = options.lowSpeedThreshold ?? LOW_SPEED_THRESHOLD;
    this.lowSpeedHysteresis = options.lowSpeedHysteresis ?? LOW_SPEED_HYSTERESIS;
    this.highSpeedAlpha = options.highSpeedAlpha ?? HIGH_SPEED_ALPHA;
    this.mediumSpeedAlpha = options.mediumSpeedAlpha ?? MEDIUM_SPEED_ALPHA;
    
    this.smoothedBearing = null;
    this.rawBearing = null;
    this.lastSpeed = 0;
    this.suppressed = false;
    this.initialized = false;
  }

  /**
   * Update with new GPS bearing and speed
   * @param {number} rawBearing - GPS course in degrees (0-360, 0=North)
   * @param {number} speedKmh - Speed in km/h
   * @returns {Object} { bearing, suppressed, rawBearing }
   */
  update(rawBearing, speedKmh) {
    this.rawBearing = rawBearing;
    this.lastSpeed = speedKmh;

    // Determine if we should suppress bearing updates
    const wasSuppressed = this.suppressed;
    
    if (speedKmh < this.lowSpeedThreshold) {
      this.suppressed = true;
    } else if (speedKmh > this.lowSpeedHysteresis) {
      this.suppressed = false;
    }
    // In hysteresis zone (5-7 km/h), keep previous state

    if (!this.initialized) {
      this.smoothedBearing = rawBearing;
      this.initialized = true;
      return { bearing: this.smoothedBearing, suppressed: this.suppressed, rawBearing };
    }

    if (this.suppressed) {
      // Return last reliable bearing, don't update
      return { bearing: this.smoothedBearing, suppressed: true, rawBearing };
    }

    // Select alpha based on speed
    let alpha;
    if (speedKmh > 20) {
      alpha = this.highSpeedAlpha;
    } else if (speedKmh > 5) {
      alpha = this.mediumSpeedAlpha;
    } else {
      alpha = LOW_SPEED_ALPHA;
    }

    // Circular EMA: handle 0/360 boundary
    let diff = rawBearing - this.smoothedBearing;
    if (diff > 180) diff -= 360;
    if (diff < -180) diff += 360;

    this.smoothedBearing = (this.smoothedBearing + alpha * diff + 360) % 360;

    return { bearing: this.smoothedBearing, suppressed: false, rawBearing };
  }

  /**
   * Get current smoothed bearing
   */
  getBearing() {
    return this.smoothedBearing;
  }

  /**
   * Check if bearing is currently suppressed
   */
  isSuppressed() {
    return this.suppressed;
  }

  /**
   * Force set bearing (e.g., from route maneuver)
   */
  setBearing(bearing) {
    this.smoothedBearing = bearing % 360;
    this.initialized = true;
  }

  /**
   * Reset smoother
   */
  reset() {
    this.smoothedBearing = null;
    this.rawBearing = null;
    this.lastSpeed = 0;
    this.suppressed = false;
    this.initialized = false;
  }
}

/**
 * Turn Anticipation - blend bearing toward upcoming maneuver
 */
export class TurnAnticipation {
  constructor(options = {}) {
    this.anticipationDistance = options.anticipationDistance ?? 50; // meters before turn
    this.blendDuration = options.blendDuration ?? 2000; // ms to complete blend
    this.currentManeuver = null;
    this.blendStartTime = null;
    this.startBearing = null;
  }

  /**
   * Set upcoming maneuver from routing
   * @param {Object} maneuver - { bearing, distance, type }
   */
  setManeuver(maneuver) {
    this.currentManeuver = maneuver;
    this.blendStartTime = null;
    this.startBearing = null;
  }

  /**
   * Clear maneuver
   */
  clearManeuver() {
    this.currentManeuver = null;
    this.blendStartTime = null;
    this.startBearing = null;
  }

  /**
   * Get anticipated bearing blend
   * @param {number} currentBearing - Current smoothed bearing
   * @param {number} distanceToManeuver - Meters to maneuver point
   * @returns {Object} { bearing, blending }
   */
  getAnticipatedBearing(currentBearing, distanceToManeuver) {
    if (!this.currentManeuver || distanceToManeuver > this.anticipationDistance) {
      return { bearing: currentBearing, blending: false };
    }

    if (this.blendStartTime === null) {
      this.blendStartTime = performance.now();
      this.startBearing = currentBearing;
    }

    const elapsed = performance.now() - this.blendStartTime;
    const progress = Math.min(elapsed / this.blendDuration, 1);
    const easedProgress = smoothstep(progress);

    let diff = this.currentManeuver.bearing - this.startBearing;
    if (diff > 180) diff -= 360;
    if (diff < -180) diff += 360;

    const bearing = (this.startBearing + diff * easedProgress + 360) % 360;

    return { bearing, blending: progress < 1 };
  }
}

/**
 * Smoothstep easing
 */
function smoothstep(t) {
  return t * t * (3 - 2 * t);
}

/**
 * Calculate bearing between two GPS points
 * @returns {number} Bearing in degrees (0-360, 0=North)
 */
export function calculateBearing(lat1, lon1, lat2, lon2) {
  const dLon = toRad(lon2 - lon1);
  const lat1Rad = toRad(lat1);
  const lat2Rad = toRad(lat2);

  const y = Math.sin(dLon) * Math.cos(lat2Rad);
  const x = Math.cos(lat1Rad) * Math.sin(lat2Rad) -
            Math.sin(lat1Rad) * Math.cos(lat2Rad) * Math.cos(dLon);

  let bearing = toDeg(Math.atan2(y, x));
  return (bearing + 360) % 360;
}

function toRad(deg) { return deg * Math.PI / 180; }
function toDeg(rad) { return rad * 180 / Math.PI; }

/**
 * Calculate speed from two GPS positions
 * @returns {number} Speed in km/h
 */
export function calculateSpeed(lat1, lon1, lat2, lon2, timeMs) {
  const distance = haversineDistance(lat1, lon1, lat2, lon2); // meters
  const hours = timeMs / 3600000;
  return hours > 0 ? distance / 1000 / hours : 0;
}

export function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon/2)**2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}