/**
 * Position Interpolator - requestAnimationFrame loop with smoothstep easing
 * Provides smooth marker movement between GPS fixes
 */

export class PositionInterpolator {
  constructor(options = {}) {
    this.duration = options.duration ?? 1000; // ms between fixes
    this.easing = options.easing ?? smoothstep;
    this.onUpdate = options.onUpdate ?? (() => {});
    this.onComplete = options.onComplete ?? (() => {});
    
    this.startPos = null;
    this.endPos = null;
    this.startTime = null;
    this.animationId = null;
    this.running = false;
  }

  /**
   * Start interpolation to new position
   * @param {Object} startPos - { lat, lon }
   * @param {Object} endPos - { lat, lon }
   * @param {number} duration - Override default duration (ms)
   */
  interpolateTo(startPos, endPos, duration) {
    this.startPos = { ...startPos };
    this.endPos = { ...endPos };
    this.duration = duration ?? this.duration;
    this.startTime = performance.now();
    
    if (!this.running) {
      this.running = true;
      this._animate();
    }
  }

  /**
   * Update target position (for continuous updates)
   * Smoothly transitions from current interpolated position to new target
   */
  updateTarget(newEndPos, newDuration) {
    if (!this.running || !this.startPos) {
      this.interpolateTo(this.getCurrentPosition() || newEndPos, newEndPos, newDuration);
      return;
    }

    // Get current interpolated position as new start
    const now = performance.now();
    const elapsed = now - this.startTime;
    const progress = Math.min(elapsed / this.duration, 1);
    const easedProgress = this.easing(progress);
    
    const currentLat = this.startPos.lat + (this.endPos.lat - this.startPos.lat) * easedProgress;
    const currentLon = this.startPos.lon + (this.endPos.lon - this.startPos.lon) * easedProgress;

    this.startPos = { lat: currentLat, lon: currentLon };
    this.endPos = { ...newEndPos };
    this.duration = newDuration ?? this.duration;
    this.startTime = now;
  }

  _animate() {
    if (!this.running) return;

    const now = performance.now();
    const elapsed = now - this.startTime;
    const progress = Math.min(elapsed / this.duration, 1);
    const easedProgress = this.easing(progress);

    const lat = this.startPos.lat + (this.endPos.lat - this.startPos.lat) * easedProgress;
    const lon = this.startPos.lon + (this.endPos.lon - this.startPos.lon) * easedProgress;

    this.onUpdate({ lat, lon, progress: easedProgress, rawProgress: progress });

    if (progress >= 1) {
      this.running = false;
      this.onComplete({ lat: this.endPos.lat, lon: this.endPos.lon });
    } else {
      this.animationId = requestAnimationFrame(() => this._animate());
    }
  }

  /**
   * Get current interpolated position without advancing time
   */
  getCurrentPosition() {
    if (!this.startPos || !this.endPos) return null;
    
    const now = performance.now();
    const elapsed = now - this.startTime;
    const progress = Math.min(elapsed / this.duration, 1);
    const easedProgress = this.easing(progress);

    return {
      lat: this.startPos.lat + (this.endPos.lat - this.startPos.lat) * easedProgress,
      lon: this.startPos.lon + (this.endPos.lon - this.startPos.lon) * easedProgress,
      progress: easedProgress
    };
  }

  stop() {
    this.running = false;
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
  }

  isRunning() {
    return this.running;
  }
}

/**
 * Smoothstep easing function: t * t * (3 - 2 * t)
 * Ease-in-out cubic, no overshoot
 */
export function smoothstep(t) {
  return t * t * (3 - 2 * t);
}

/**
 * Smootherstep: t^3 * (t * (6t - 15) + 10)
 * Even smoother, zero 1st and 2nd derivatives at endpoints
 */
export function smootherstep(t) {
  return t * t * t * (t * (t * 6 - 15) + 10);
}

/**
 * Custom easing for "material" feel: cubic-bezier(0.25, 0.1, 0.25, 1)
 * Approximated with polynomial
 */
export function materialEasing(t) {
  // Approximation of cubic-bezier(0.25, 0.1, 0.25, 1)
  return t * t * (3 - 2 * t) * (1 + 0.1 * (1 - t));
}

/**
 * Linear interpolation (no easing)
 */
export function linear(t) {
  return t;
}

/**
 * Interpolate between two positions with bearing
 * Returns { lat, lon, bearing }
 */
export function interpolateWithBearing(start, end, progress, startBearing, endBearing) {
  const lat = start.lat + (end.lat - start.lat) * progress;
  const lon = start.lon + (end.lon - start.lon) * progress;
  
  // Shortest path bearing interpolation
  let bearingDiff = endBearing - startBearing;
  if (bearingDiff > 180) bearingDiff -= 360;
  if (bearingDiff < -180) bearingDiff += 360;
  
  const bearing = (startBearing + bearingDiff * progress + 360) % 360;
  
  return { lat, lon, bearing };
}