/**
 * GPS Noise Filter - Exponential Moving Average (EMA)
 * Smooths raw GPS coordinates before rendering
 */

export class GPSFilter {
  constructor(options = {}) {
    this.alpha = options.alpha ?? 0.3; // 0.3 = moderate smoothing
    this.filteredLat = null;
    this.filteredLon = null;
    this.initialized = false;
    this.lastTimestamp = null;
  }

  /**
   * Apply EMA filter to new GPS coordinate
   * @param {number} lat - Raw latitude
   * @param {number} lon - Raw longitude
   * @param {number} timestamp - Unix timestamp (ms)
   * @returns {Object} { lat, lon, filtered: boolean }
   */
  update(lat, lon, timestamp = Date.now()) {
    if (!this.initialized) {
      this.filteredLat = lat;
      this.filteredLon = lon;
      this.initialized = true;
      this.lastTimestamp = timestamp;
      return { lat: this.filteredLat, lon: this.filteredLon, filtered: false };
    }

    // Adaptive alpha based on time delta (handles irregular updates)
    const dt = (timestamp - this.lastTimestamp) / 1000; // seconds
    const adaptiveAlpha = 1 - Math.exp(-dt * this.alpha * 2);
    
    this.filteredLat = this.filteredLat + adaptiveAlpha * (lat - this.filteredLat);
    this.filteredLon = this.filteredLon + adaptiveAlpha * (lon - this.filteredLon);
    this.lastTimestamp = timestamp;

    return { lat: this.filteredLat, lon: this.filteredLon, filtered: true };
  }

  /**
   * Get current filtered position
   * @returns {Object|null} { lat, lon } or null if not initialized
   */
  getPosition() {
    if (!this.initialized) return null;
    return { lat: this.filteredLat, lon: this.filteredLon };
  }

  /**
   * Reset filter (e.g., on large position jump)
   */
  reset(lat, lon) {
    this.filteredLat = lat;
    this.filteredLon = lon;
    this.initialized = true;
    this.lastTimestamp = Date.now();
  }

  /**
   * Check if filter has valid position
   */
  hasPosition() {
    return this.initialized;
  }
}

/**
 * Kalman Filter for 2D position (optional upgrade from EMA)
 * Better for high-noise environments
 */
export class KalmanFilter2D {
  constructor(options = {}) {
    // Process noise (how much we expect true position to change)
    this.q = options.processNoise ?? 0.01;
    // Measurement noise (GPS accuracy)
    this.r = options.measurementNoise ?? 10; // meters
    
    // State: [lat, lon, lat_velocity, lon_velocity]
    this.x = [0, 0, 0, 0];
    // Covariance matrix (4x4, stored as flat array)
    this.P = [
      1000, 0, 0, 0,
      0, 1000, 0, 0,
      0, 0, 1000, 0,
      0, 0, 0, 1000
    ];
    
    this.initialized = false;
    this.lastTime = null;
  }

  update(lat, lon, timestamp = Date.now(), accuracy = 10) {
    const dt = this.lastTime ? (timestamp - this.lastTime) / 1000 : 0;
    this.lastTime = timestamp;

    if (!this.initialized) {
      this.x[0] = lat;
      this.x[1] = lon;
      this.initialized = true;
      return { lat: this.x[0], lon: this.x[1] };
    }

    // Prediction step
    // State transition matrix F (constant velocity model)
    const F = [
      1, 0, dt, 0,
      0, 1, 0, dt,
      0, 0, 1, 0,
      0, 0, 0, 1
    ];

    // Predict state: x = F * x
    const xPred = [
      F[0]*this.x[0] + F[1]*this.x[1] + F[2]*this.x[2] + F[3]*this.x[3],
      F[4]*this.x[0] + F[5]*this.x[1] + F[6]*this.x[2] + F[7]*this.x[3],
      F[8]*this.x[0] + F[9]*this.x[1] + F[10]*this.x[2] + F[11]*this.x[3],
      F[12]*this.x[0] + F[13]*this.x[1] + F[14]*this.x[2] + F[15]*this.x[3]
    ];

    // Predict covariance: P = F * P * F^T + Q
    const Q = [
      this.q*dt*dt*dt/3, 0, this.q*dt*dt/2, 0,
      0, this.q*dt*dt*dt/3, 0, this.q*dt*dt/2,
      this.q*dt*dt/2, 0, this.q*dt, 0,
      0, this.q*dt*dt/2, 0, this.q*dt
    ];

    // Simplified: just add process noise to diagonal
    for (let i = 0; i < 4; i++) {
      this.P[i*4 + i] += Q[i*4 + i];
    }

    this.x = xPred;

    // Update step
    // Measurement: z = [lat, lon]
    // Measurement matrix H = [1 0 0 0; 0 1 0 0]
    const z = [lat, lon];
    const R = accuracy * accuracy; // measurement variance

    // Innovation: y = z - H*x
    const y = [z[0] - this.x[0], z[1] - this.x[1]];

    // Innovation covariance: S = H*P*H^T + R
    const S = [
      this.P[0] + R, this.P[1],
      this.P[4], this.P[5] + R
    ];

    // Kalman gain: K = P*H^T*S^-1
    const det = S[0]*S[3] - S[1]*S[2];
    if (det === 0) return { lat: this.x[0], lon: this.x[1] };

    const Sinv = [S[3]/det, -S[1]/det, -S[2]/det, S[0]/det];
    const K = [
      this.P[0]*Sinv[0] + this.P[1]*Sinv[2], this.P[0]*Sinv[1] + this.P[1]*Sinv[3],
      this.P[4]*Sinv[0] + this.P[5]*Sinv[2], this.P[4]*Sinv[1] + this.P[5]*Sinv[3],
      this.P[8]*Sinv[0] + this.P[9]*Sinv[2], this.P[8]*Sinv[1] + this.P[9]*Sinv[3],
      this.P[12]*Sinv[0] + this.P[13]*Sinv[2], this.P[12]*Sinv[1] + this.P[13]*Sinv[3]
    ];

    // Update state: x = x + K*y
    this.x[0] += K[0]*y[0] + K[1]*y[1];
    this.x[1] += K[2]*y[0] + K[3]*y[1];
    this.x[2] += K[4]*y[0] + K[5]*y[1];
    this.x[3] += K[6]*y[0] + K[7]*y[1];

    // Update covariance: P = (I - K*H)*P
    const IminusKH = [
      1-K[0], -K[1], 0, 0,
      -K[2], 1-K[3], 0, 0,
      -K[4], -K[5], 1, 0,
      -K[6], -K[7], 0, 1
    ];

    const Pnew = new Array(16).fill(0);
    for (let i = 0; i < 4; i++) {
      for (let j = 0; j < 4; j++) {
        let sum = 0;
        for (let k = 0; k < 4; k++) {
          sum += IminusKH[i*4+k] * this.P[k*4+j];
        }
        Pnew[i*4+j] = sum;
      }
    }
    this.P = Pnew;

    return { lat: this.x[0], lon: this.x[1] };
  }

  getPosition() {
    if (!this.initialized) return null;
    return { lat: this.x[0], lon: this.x[1] };
  }

  getVelocity() {
    if (!this.initialized) return null;
    return { latVel: this.x[2], lonVel: this.x[3] };
  }

  reset(lat, lon) {
    this.x[0] = lat;
    this.x[1] = lon;
    this.x[2] = 0;
    this.x[3] = 0;
    this.initialized = true;
    this.lastTime = Date.now();
  }
}