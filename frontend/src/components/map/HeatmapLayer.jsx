import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';

/**
 * HeatmapLayer Component
 *
 * Renders a heatmap overlay on the Leaflet map showing density of entities.
 * Uses leaflet.heat for performant WebGL-based heatmap rendering.
 *
 * @param {Array} locations - Array of location objects with latitude, longitude
 * @param {string} weightBy - How to weight points: 'count' | 'connections' | 'uniform'
 * @param {number} radius - Radius of each point's influence (default: 25)
 * @param {number} blur - Amount of blur to apply (default: 15)
 * @param {number} maxIntensity - Maximum intensity value (default: 1.0)
 * @param {number} minOpacity - Minimum opacity of the heatmap (default: 0.3)
 */
export default function HeatmapLayer({
  locations = [],
  weightBy = 'uniform',
  radius = 25,
  blur = 15,
  maxIntensity = 1.0,
  minOpacity = 0.3,
  gradient = null,
}) {
  const map = useMap();
  const heatLayerRef = useRef(null);

  useEffect(() => {
    if (!locations || locations.length === 0) {
      // Remove existing layer if no locations
      if (heatLayerRef.current) {
        map.removeLayer(heatLayerRef.current);
        heatLayerRef.current = null;
      }
      return;
    }

    // Calculate weights based on weightBy parameter
    const getWeight = (loc) => {
      switch (weightBy) {
        case 'connections':
          // Weight by number of connections (normalized)
          const connCount = loc.connections?.length || 0;
          return Math.min(1, 0.3 + connCount * 0.1);
        case 'count':
          // All points have equal weight, density comes from clustering
          return 0.5;
        case 'uniform':
        default:
          return 0.5;
      }
    };

    // Convert locations to heatmap points [lat, lng, intensity]
    const heatPoints = locations.map((loc) => [
      loc.latitude,
      loc.longitude,
      getWeight(loc),
    ]);

    // Default gradient (blue -> cyan -> green -> yellow -> red)
    const defaultGradient = {
      0.0: '#3b82f6', // blue
      0.25: '#06b6d4', // cyan
      0.5: '#22c55e', // green
      0.75: '#eab308', // yellow
      1.0: '#ef4444', // red
    };

    // Create or update the heat layer
    if (heatLayerRef.current) {
      // Update existing layer
      heatLayerRef.current.setLatLngs(heatPoints);
      heatLayerRef.current.setOptions({
        radius,
        blur,
        max: maxIntensity,
        minOpacity,
        gradient: gradient || defaultGradient,
      });
    } else {
      // Create new layer
      heatLayerRef.current = L.heatLayer(heatPoints, {
        radius,
        blur,
        max: maxIntensity,
        minOpacity,
        gradient: gradient || defaultGradient,
      });
      heatLayerRef.current.addTo(map);
    }

    // Cleanup on unmount
    return () => {
      if (heatLayerRef.current) {
        map.removeLayer(heatLayerRef.current);
        heatLayerRef.current = null;
      }
    };
  }, [locations, weightBy, radius, blur, maxIntensity, minOpacity, gradient, map]);

  // This component doesn't render any DOM elements directly
  return null;
}
