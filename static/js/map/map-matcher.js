/**
 * Map Matcher - Project GPS positions onto route polyline
 * Snaps raw GPS to nearest point on the planned route
 */

import { haversineDistance, calculateBearing } from './bearing.js';

/**
 * Decode Google encoded polyline to array of [lat, lon]
 * @param {string} encoded - Encoded polyline string
 * @returns {Array<Array<number>>} Array of [lat, lon] pairs
 */
export function decodePolyline(encoded) {
  const coordinates = [];
  let index = 0;
  let lat = 0;
  let lng = 0;

  while (index < encoded.length) {
    let shift = 0;
    let result = 0;
    let byte;

    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);

    const deltaLat = (result & 1) ? ~(result >> 1) : (result >> 1);
    lat += deltaLat;

    shift = 0;
    result = 0;

    do {
      byte = encoded.charCodeAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);

    const deltaLng = (result & 1) ? ~(result >> 1) : (result >> 1);
    lng += deltaLng;

    coordinates.push([lat / 1e5, lng / 1e5]);
  }

  return coordinates;
}

/**
 * Encode array of [lat, lon] to Google encoded polyline
 * @param {Array<Array<number>>} coordinates - Array of [lat, lon] pairs
 * @returns {string} Encoded polyline string
 */
export function encodePolyline(coordinates) {
  let encoded = '';
  let prevLat = 0;
  let prevLng = 0;

  for (const [lat, lng] of coordinates) {
    const deltaLat = Math.round(lat * 1e5) - prevLat;
    const deltaLng = Math.round(lng * 1e5) - prevLng;
    prevLat += deltaLat;
    prevLng += deltaLng;

    encoded += encodeSignedNumber(deltaLat);
    encoded += encodeSignedNumber(deltaLng);
  }

  return encoded;
}

function encodeSignedNumber(num) {
  let sgnNum = num << 1;
  if (num < 0) sgnNum = ~sgnNum;
  let encoded = '';
  while (sgnNum >= 0x20) {
    encoded += String.fromCharCode((0x20 | (sgnNum & 0x1f)) + 63);
    sgnNum >>= 5;
  }
  encoded += String.fromCharCode(sgnNum + 63);
  return encoded;
}

/**
 * Find nearest point on polyline to a GPS position
 * @param {number} lat - GPS latitude
 * @param {number} lon - GPS longitude
 * @param {Array<Array<number>>} polyline - Array of [lat, lon] points
 * @returns {Object} { lat, lon, index, distance, segmentProgress }
 */
export function projectToPolyline(lat, lon, polyline) {
  if (!polyline || polyline.length < 2) {
    return { lat, lon, index: 0, distance: 0, segmentProgress: 0 };
  }

  let minDistance = Infinity;
  let bestPoint = { lat, lon, index: 0, distance: 0, segmentProgress: 0 };

  for (let i = 0; i < polyline.length - 1; i++) {
    const p1 = polyline[i];
    const p2 = polyline[i + 1];
    
    const result = projectToSegment(lat, lon, p1[0], p1[1], p2[0], p2[1]);
    result.index = i;
    
    if (result.distance < minDistance) {
      minDistance = result.distance;
      bestPoint = result;
    }
  }

  return bestPoint;
}

/**
 * Project point to line segment
 */
function projectToSegment(lat, lon, lat1, lon1, lat2, lon2) {
  // Convert to local Cartesian approximation for projection
  const R = 6371000;
  const latMid = (lat1 + lat2) / 2;
  const cosLatMid = Math.cos(latMid * Math.PI / 180);
  
  const x1 = 0;
  const y1 = 0;
  const x2 = (lon2 - lon1) * cosLatMid * 111320;
  const y2 = (lat2 - lat1) * 111320;
  const px = (lon - lon1) * cosLatMid * 111320;
  const py = (lat - lat1) * 111320;

  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  
  let segmentProgress = 0;
  let projX, projY;

  if (lenSq === 0) {
    projX = x1;
    projY = y1;
  } else {
    const t = Math.max(0, Math.min(1, (px * dx + py * dy) / lenSq));
    segmentProgress = t;
    projX = x1 + t * dx;
    projY = y1 + t * dy;
  }

  const projLat = lat1 + projY / 111320;
  const projLon = lon1 + projX / (cosLatMid * 111320);
  const distance = haversineDistance(lat, lon, projLat, projLon);

  return {
    lat: projLat,
    lon: projLon,
    distance,
    segmentProgress
  };
}

/**
 * Calculate distance along polyline from start to a projected point
 * @param {Array<Array<number>>} polyline - Route polyline
 * @param {Object} projectedPoint - Result from projectToPolyline
 * @returns {number} Distance in meters
 */
export function distanceAlongPolyline(polyline, projectedPoint) {
  let totalDistance = 0;
  
  for (let i = 0; i < projectedPoint.index; i++) {
    totalDistance += haversineDistance(
      polyline[i][0], polyline[i][1],
      polyline[i+1][0], polyline[i+1][1]
    );
  }
  
  // Add partial segment distance
  const p1 = polyline[projectedPoint.index];
  const p2 = polyline[projectedPoint.index + 1];
  const segmentDist = haversineDistance(p1[0], p1[1], p2[0], p2[1]);
  totalDistance += segmentDist * projectedPoint.segmentProgress;
  
  return totalDistance;
}

/**
 * Calculate remaining distance along polyline from projected point to end
 */
export function remainingDistanceAlongPolyline(polyline, projectedPoint) {
  const totalDistance = polylineDistance(polyline);
  const traveled = distanceAlongPolyline(polyline, projectedPoint);
  return Math.max(0, totalDistance - traveled);
}

/**
 * Get total polyline distance
 */
export function polylineDistance(polyline) {
  let total = 0;
  for (let i = 0; i < polyline.length - 1; i++) {
    total += haversineDistance(
      polyline[i][0], polyline[i][1],
      polyline[i+1][0], polyline[i+1][1]
    );
  }
  return total;
}

/**
 * Get bearing at a point on the polyline (forward direction)
 */
export function getPolylineBearing(polyline, projectedPoint) {
  const idx = projectedPoint.index;
  if (idx >= polyline.length - 1) {
    // At or near end, use last segment
    if (polyline.length >= 2) {
      const p1 = polyline[polyline.length - 2];
      const p2 = polyline[polyline.length - 1];
      return calculateBearing(p1[0], p1[1], p2[0], p2[1]);
    }
    return 0;
  }
  
  const p1 = polyline[idx];
  const p2 = polyline[idx + 1];
  return calculateBearing(p1[0], p1[1], p2[0], p2[1]);
}

/**
 * Find closest stage on the route
 */
export function findNearestStage(lat, lon, stages) {
  let nearest = null;
  let minDist = Infinity;
  
  for (const stage of stages) {
    const dist = haversineDistance(lat, lon, stage.latitude, stage.longitude);
    if (dist < minDist) {
      minDist = dist;
      nearest = { ...stage, distance: dist };
    }
  }
  
  return nearest;
}

/**
 * Check if position is near a stage (within radius)
 */
export function isNearStage(lat, lon, stage, radiusM = 20) {
  return haversineDistance(lat, lon, stage.latitude, stage.longitude) <= radiusM;
}