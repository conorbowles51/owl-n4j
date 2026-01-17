/**
 * Geographic utility functions for map-based analysis
 */

/**
 * Calculate the haversine distance between two points on Earth
 * @param {number} lat1 - Latitude of first point
 * @param {number} lon1 - Longitude of first point
 * @param {number} lat2 - Latitude of second point
 * @param {number} lon2 - Longitude of second point
 * @returns {number} Distance in kilometers
 */
export function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371; // Earth's radius in kilometers
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);

  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2);

  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * Convert degrees to radians
 * @param {number} deg - Degrees
 * @returns {number} Radians
 */
function toRad(deg) {
  return deg * (Math.PI / 180);
}

/**
 * Find all entities within a radius of a center point
 * @param {{lat: number, lng: number}} center - Center point
 * @param {number} radiusKm - Radius in kilometers
 * @param {Array} entities - Array of entities with latitude/longitude
 * @returns {Array} Entities within the radius with their distances
 */
export function findEntitiesWithinRadius(center, radiusKm, entities) {
  return entities
    .map(entity => {
      const distance = haversineDistance(
        center.lat,
        center.lng,
        entity.latitude,
        entity.longitude
      );
      return { ...entity, distance };
    })
    .filter(entity => entity.distance <= radiusKm)
    .sort((a, b) => a.distance - b.distance);
}

/**
 * Calculate bounding box for a center point and radius
 * @param {{lat: number, lng: number}} center - Center point
 * @param {number} radiusKm - Radius in kilometers
 * @returns {{north: number, south: number, east: number, west: number}}
 */
export function calculateBoundingBox(center, radiusKm) {
  const R = 6371; // Earth's radius in km
  const lat = toRad(center.lat);

  // Latitude: 1 degree = ~111 km
  const latDelta = radiusKm / 111;

  // Longitude: depends on latitude
  const lonDelta = radiusKm / (111 * Math.cos(lat));

  return {
    north: center.lat + latDelta,
    south: center.lat - latDelta,
    east: center.lng + lonDelta,
    west: center.lng - lonDelta,
  };
}

/**
 * Find the geographic center (centroid) of a set of points
 * @param {Array} points - Array of objects with latitude/longitude
 * @returns {{lat: number, lng: number}} Geographic center
 */
export function findGeographicCenter(points) {
  if (!points || points.length === 0) return null;

  const sum = points.reduce(
    (acc, p) => ({
      lat: acc.lat + p.latitude,
      lng: acc.lng + p.longitude,
    }),
    { lat: 0, lng: 0 }
  );

  return {
    lat: sum.lat / points.length,
    lng: sum.lng / points.length,
  };
}

/**
 * Calculate distances between selected entities
 * @param {Array} entities - Array of entities with latitude/longitude
 * @returns {Array} Array of distance pairs
 */
export function calculatePairwiseDistances(entities) {
  const distances = [];

  for (let i = 0; i < entities.length; i++) {
    for (let j = i + 1; j < entities.length; j++) {
      const distance = haversineDistance(
        entities[i].latitude,
        entities[i].longitude,
        entities[j].latitude,
        entities[j].longitude
      );
      distances.push({
        from: entities[i],
        to: entities[j],
        distance,
      });
    }
  }

  return distances.sort((a, b) => a.distance - b.distance);
}

/**
 * Format distance for display
 * @param {number} distanceKm - Distance in kilometers
 * @returns {string} Formatted distance string
 */
export function formatDistance(distanceKm) {
  if (distanceKm < 1) {
    return `${Math.round(distanceKm * 1000)} m`;
  } else if (distanceKm < 10) {
    return `${distanceKm.toFixed(1)} km`;
  } else {
    return `${Math.round(distanceKm)} km`;
  }
}

/**
 * Grid-based clustering for hotspot detection
 * @param {Array} entities - Array of entities with latitude/longitude
 * @param {number} gridSizeKm - Size of grid cells in kilometers
 * @returns {Array} Array of grid cells with entity counts
 */
export function gridCluster(entities, gridSizeKm = 10) {
  if (!entities || entities.length === 0) return [];

  // Find bounds
  const lats = entities.map(e => e.latitude);
  const lngs = entities.map(e => e.longitude);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);

  // Calculate grid cell size in degrees (approximate)
  const latStep = gridSizeKm / 111;
  const lngStep = gridSizeKm / (111 * Math.cos(toRad((minLat + maxLat) / 2)));

  // Create grid
  const grid = {};

  entities.forEach(entity => {
    const cellLat = Math.floor((entity.latitude - minLat) / latStep);
    const cellLng = Math.floor((entity.longitude - minLng) / lngStep);
    const key = `${cellLat},${cellLng}`;

    if (!grid[key]) {
      grid[key] = {
        key,
        cellLat,
        cellLng,
        centerLat: minLat + (cellLat + 0.5) * latStep,
        centerLng: minLng + (cellLng + 0.5) * lngStep,
        entities: [],
        count: 0,
      };
    }

    grid[key].entities.push(entity);
    grid[key].count++;
  });

  // Convert to array and sort by count
  return Object.values(grid)
    .filter(cell => cell.count > 0)
    .sort((a, b) => b.count - a.count);
}

/**
 * Calculate total path distance for a sequence of points
 * @param {Array} points - Array of points with latitude/longitude
 * @returns {number} Total distance in kilometers
 */
export function calculatePathDistance(points) {
  if (!points || points.length < 2) return 0;

  let total = 0;
  for (let i = 0; i < points.length - 1; i++) {
    total += haversineDistance(
      points[i].latitude,
      points[i].longitude,
      points[i + 1].latitude,
      points[i + 1].longitude
    );
  }
  return total;
}

/**
 * Sort points by date to create a chronological path
 * @param {Array} points - Array of points with latitude/longitude and date
 * @returns {Array} Points sorted by date
 */
export function sortByDate(points) {
  return [...points].sort((a, b) => {
    const dateA = a.date ? new Date(a.date) : new Date(0);
    const dateB = b.date ? new Date(b.date) : new Date(0);
    return dateA - dateB;
  });
}
