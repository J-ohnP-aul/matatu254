/**
 * ETA Calculator - Computes remaining distance/time along route polyline
 * Uses smoothed speed, refreshes every 5-10 seconds
 */

import { haversineDistance } from './bearing.js';

export class ETACalculator {
  constructor(options = {}) {
    this.routePolyline = options.polyline || [];
    this.stages = options.stages || [];
    this.destinationStage = options.destinationStage || null;
    
    // Speed smoothing
    this.speedAlpha = options.speedAlpha ?? 0.2;
    this.smoothedSpeed = null; // km/h
    this.lastSpeedUpdate = null;
    
    // Segment speeds (from OSRM or defaults)
    this.segmentSpeeds = options.segmentSpeeds || new Map(); // segmentIndex -> km/h
    this.defaultSpeed = options.defaultSpeed ?? 30; // km/h fallback
    
    // Cache
    this.cachedRemaining = null;
    this.lastCalculation = 0;
    this.calculationInterval = options.calculationInterval ?? 5000; // 5s
    this.fullRecalcInterval = options.fullRecalcInterval ?? 30000; // 30s
    
    // Callbacks
    this.onUpdate = options.onUpdate || (() => {});
  }

  /**
   * Set route polyline (decoded array of [lat, lon])
   */
  setRoute(polyline, stages = [], destinationStage = null) {
    this.routePolyline = polyline;
    this.stages = stages;
    this.destinationStage = destinationStage;
    this.cachedRemaining = null;
    this.lastCalculation = 0;
  }

  /**
   * Set segment speeds from OSRM route response
   * @param {Array} legs - OSRM route legs with duration/distance
   */
  setSegmentSpeeds(legs) {
    this.segmentSpeeds.clear();
    legs.forEach((leg, i) => {
      const distanceKm = leg.distance / 1000;
      const durationH = leg.duration / 3600;
      if (distanceKm > 0 && durationH > 0) {
        this.segmentSpeeds.set(i, distanceKm / durationH);
      }
    });
  }

  /**
   * Update with current vehicle position and speed
   * @param {Object} vehiclePos - { lat, lon, speed, bearing }
   * @param {Object} projected - Result from projectToPolyline
   */
  update(vehiclePos, projected) {
    const now = Date.now();
    
    // Update smoothed speed
    if (vehiclePos.speed != null) {
      this._updateSmoothedSpeed(vehiclePos.speed);
    }
    
    // Check if we need to recalculate
    const needsFullRecalc = now - this.lastCalculation > this.fullRecalcInterval;
    const needsIncremental = now - this.lastCalculation > this.calculationInterval;
    
    if (needsFullRecalc || !this.cachedRemaining) {
      this._fullRecalculation(vehiclePos, projected);
    } else if (needsIncremental) {
      this._incrementalUpdate(vehiclePos, projected);
    }
    
    return this.cachedRemaining;
  }

  _updateSmoothedSpeed(rawSpeedKmh) {
    if (this.smoothedSpeed === null) {
      this.smoothedSpeed = rawSpeedKmh;
    } else {
      this.smoothedSpeed = this.smoothedSpeed + this.speedAlpha * (rawSpeedKmh - this.smoothedSpeed);
    }
    this.lastSpeedUpdate = Date.now();
  }

  getSmoothedSpeed() {
    return this.smoothedSpeed ?? this.defaultSpeed;
  }

  _fullRecalculation(vehiclePos, projected) {
    if (!this.routePolyline.length || !projected) {
      this.cachedRemaining = this._emptyResult();
      this.lastCalculation = Date.now();
      this.onUpdate(this.cachedRemaining);
      return;
    }

    // Distance from vehicle to destination along polyline
    const remainingDist = this._calculateRemainingDistance(projected);
    
    // Time estimation using segment speeds
    const remainingTime = this._estimateTime(remainingDist, projected);
    
    // Next stage info
    const nextStage = this._getNextStage(projected);
    
    this.cachedRemaining = {
      distanceM: Math.round(remainingDist),
      distanceKm: remainingDist / 1000,
      durationS: Math.round(remainingTime * 3600),
      durationMinutes: Math.round(remainingTime * 60),
      formattedDistance: this._formatDistance(remainingDist),
      formattedDuration: this._formatDuration(remainingTime * 60),
      nextStage: nextStage,
      progress: this._calculateProgress(projected),
      speed: this.getSmoothedSpeed(),
      timestamp: Date.now()
    };
    
    this.lastCalculation = Date.now();
    this.onUpdate(this.cachedRemaining);
  }

  _incrementalUpdate(vehiclePos, projected) {
    if (!this.cachedRemaining || !projected) return;
    
    // Subtract distance traveled since last calculation
    const speed = this.getSmoothedSpeed(); // km/h
    const timeDelta = (Date.now() - this.lastCalculation) / 3600000; // hours
    const distanceTraveled = speed * timeDelta * 1000; // meters
    
    this.cachedRemaining.distanceM = Math.max(0, this.cachedRemaining.distanceM - distanceTraveled);
    this.cachedRemaining.distanceKm = this.cachedRemaining.distanceM / 1000;
    this.cachedRemaining.durationS = Math.max(0, this.cachedRemaining.durationS - timeDelta * 3600);
    this.cachedRemaining.durationMinutes = Math.round(this.cachedRemaining.durationS / 60);
    this.cachedRemaining.formattedDistance = this._formatDistance(this.cachedRemaining.distanceM);
    this.cachedRemaining.formattedDuration = this._formatDuration(this.cachedRemaining.durationMinutes);
    this.cachedRemaining.speed = speed;
    this.cachedRemaining.timestamp = Date.now();
    
    this.lastCalculation = Date.now();
    this.onUpdate(this.cachedRemaining);
  }

  _calculateRemainingDistance(projected) {
    // Distance from projected point to end of polyline
    let remaining = 0;
    const startIdx = projected.index;
    const startProgress = projected.segmentProgress;
    
    // Partial first segment
    if (startIdx < this.routePolyline.length - 1) {
      const p1 = this.routePolyline[startIdx];
      const p2 = this.routePolyline[startIdx + 1];
      const segmentDist = haversineDistance(p1[0], p1[1], p2[0], p2[1]);
      remaining += segmentDist * (1 - startProgress);
    }
    
    // Full remaining segments
    for (let i = startIdx + 1; i < this.routePolyline.length - 1; i++) {
      const p1 = this.routePolyline[i];
      const p2 = this.routePolyline[i + 1];
      remaining += haversineDistance(p1[0], p1[1], p2[0], p2[1]);
    }
    
    return remaining;
  }

  _estimateTime(remainingDist, projected) {
    // Use segment speeds if available, otherwise default
    let remainingTime = 0;
    const speed = this.getSmoothedSpeed();
    
    // Simple estimation: distance / speed
    // Could be enhanced with per-segment speeds
    remainingTime = (remainingDist / 1000) / speed; // hours
    
    return remainingTime;
  }

  _getNextStage(projected) {
    if (!this.stages.length || !this.destinationStage) return null;
    
    // Find first stage ahead of current position that hasn't been passed
    for (const stage of this.stages) {
      if (stage.sequenceOrder > this.destinationStage.sequenceOrder) continue;
      
      // Check if stage is ahead on the route
      const stageIdx = this._findStageOnPolyline(stage);
      if (stageIdx !== null && stageIdx >= projected.index) {
        return stage;
      }
    }
    
    return null;
  }

  _findStageOnPolyline(stage) {
    // Simple: find closest polyline point to stage
    let minDist = Infinity;
    let closestIdx = null;
    
    for (let i = 0; i < this.routePolyline.length; i++) {
      const dist = haversineDistance(
        this.routePolyline[i][0], this.routePolyline[i][1],
        stage.latitude, stage.longitude
      );
      if (dist < minDist) {
        minDist = dist;
        closestIdx = i;
      }
    }
    
    return minDist < 100 ? closestIdx : null; // Within 100m
  }

  _calculateProgress(projected) {
    const totalDist = this._getTotalRouteDistance();
    if (totalDist === 0) return 0;
    
    const traveled = this._calculateTraveledDistance(projected);
    return Math.min(100, Math.max(0, (traveled / totalDist) * 100));
  }

  _calculateTraveledDistance(projected) {
    let traveled = 0;
    
    for (let i = 0; i < projected.index; i++) {
      const p1 = this.routePolyline[i];
      const p2 = this.routePolyline[i + 1];
      traveled += haversineDistance(p1[0], p1[1], p2[0], p2[1]);
    }
    
    if (projected.index < this.routePolyline.length - 1) {
      const p1 = this.routePolyline[projected.index];
      const p2 = this.routePolyline[projected.index + 1];
      const segmentDist = haversineDistance(p1[0], p1[1], p2[0], p2[1]);
      traveled += segmentDist * projected.segmentProgress;
    }
    
    return traveled;
  }

  _getTotalRouteDistance() {
    let total = 0;
    for (let i = 0; i < this.routePolyline.length - 1; i++) {
      const p1 = this.routePolyline[i];
      const p2 = this.routePolyline[i + 1];
      total += haversineDistance(p1[0], p1[1], p2[0], p2[1]);
    }
    return total;
  }

  _emptyResult() {
    return {
      distanceM: 0,
      distanceKm: 0,
      durationS: 0,
      durationMinutes: 0,
      formattedDistance: '0 m',
      formattedDuration: '0 min',
      nextStage: null,
      progress: 0,
      speed: this.defaultSpeed,
      timestamp: Date.now()
    };
  }

  _formatDistance(meters) {
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(1)} km`;
    }
    return `${Math.round(meters)} m`;
  }

  _formatDuration(minutes) {
    const mins = Math.max(0, Math.round(minutes));
    if (mins >= 60) {
      const hours = Math.floor(mins / 60);
      const remaining = mins % 60;
      return remaining > 0 ? `${hours}h ${remaining}m` : `${hours}h`;
    }
    return `${mins} min`;
  }

  /**
   * Get current cached result
   */
  getRemaining() {
    return this.cachedRemaining || this._emptyResult();
  }

  /**
   * Force full recalculation
   */
  recalculate(vehiclePos, projected) {
    this.lastCalculation = 0;
    return this.update(vehiclePos, projected);
  }
}

/**
 * Format duration for display
 */
export function formatDuration(minutes) {
  const mins = Math.max(0, Math.round(minutes));
  if (mins >= 60) {
    const hours = Math.floor(mins / 60);
    const remaining = mins % 60;
    return remaining > 0 ? `${hours}h ${remaining}m` : `${hours}h`;
  }
  return `${mins} min`;
}

/**
 * Format distance for display
 */
export function formatDistance(meters) {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} km`;
  }
  return `${Math.round(meters)} m`;
}