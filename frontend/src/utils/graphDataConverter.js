/**
 * Utility functions to convert graph data to timeline and map formats
 */

/**
 * Convert graph nodes to timeline events
 * Filters nodes that have date properties and converts them to timeline event format
 */
export function convertGraphNodesToTimelineEvents(nodes, links = []) {
  const events = [];
  
  nodes.forEach(node => {
    // Check for various date properties
    const date = node.date || node.timestamp || node.created_at || node.occurred_at;
    
    if (date) {
      // Parse date
      const eventDate = new Date(date);
      if (!isNaN(eventDate.getTime())) {
        events.push({
          key: node.key,
          id: node.id || node.key,
          name: node.name || node.title || 'Untitled Event',
          type: node.type || 'Event',
          date: date,
          time: node.time || null,
          description: node.summary || node.description || '',
          // Include relationships for timeline visualization
          relationships: links
            .filter(link => {
              const sourceKey = typeof link.source === 'object' ? link.source?.key : link.source;
              const targetKey = typeof link.target === 'object' ? link.target?.key : link.target;
              return sourceKey === node.key || targetKey === node.key;
            })
            .map(link => {
              const sourceKey = typeof link.source === 'object' ? link.source?.key : link.source;
              const targetKey = typeof link.target === 'object' ? link.target?.key : link.target;
              return {
                type: link.type || link.relationship || 'RELATED_TO',
                target: sourceKey === node.key ? targetKey : sourceKey,
              };
            }),
        });
      }
    }
  });
  
  return events;
}

/**
 * Convert graph nodes to map locations
 * Filters nodes that have latitude and longitude properties
 */
export function convertGraphNodesToMapLocations(nodes, links = []) {
  const locations = [];
  
  nodes.forEach(node => {
    // Check for geographic coordinates
    const latitude = node.latitude || node.lat;
    const longitude = node.longitude || node.lng || node.lon;
    
    if (latitude != null && longitude != null && 
        !isNaN(parseFloat(latitude)) && !isNaN(parseFloat(longitude))) {
      locations.push({
        key: node.key,
        id: node.id || node.key,
        name: node.name || 'Unnamed Location',
        type: node.type || 'Location',
        latitude: parseFloat(latitude),
        longitude: parseFloat(longitude),
        summary: node.summary || '',
        // Include relationships for map visualization
        connections: links
          .filter(link => {
            const sourceKey = typeof link.source === 'object' ? link.source?.key : link.source;
            const targetKey = typeof link.target === 'object' ? link.target?.key : link.target;
            return sourceKey === node.key || targetKey === node.key;
          })
          .map(link => {
            const sourceKey = typeof link.source === 'object' ? link.source?.key : link.source;
            const targetKey = typeof link.target === 'object' ? link.target?.key : link.target;
            const connectedKey = sourceKey === node.key ? targetKey : sourceKey;
            const connectedNode = nodes.find(n => n.key === connectedKey);
            return {
              key: connectedKey,
              name: connectedNode?.name || connectedKey,
              type: link.type || link.relationship || 'RELATED_TO',
              latitude: connectedNode?.latitude || connectedNode?.lat,
              longitude: connectedNode?.longitude || connectedNode?.lng || connectedNode?.lon,
            };
          })
          .filter(conn => conn.latitude != null && conn.longitude != null),
      });
    }
  });
  
  return locations;
}

/**
 * Check if graph data has timeline data (nodes with dates)
 */
export function hasTimelineData(nodes) {
  return nodes.some(node => {
    const date = node.date || node.timestamp || node.created_at || node.occurred_at;
    if (date) {
      const eventDate = new Date(date);
      return !isNaN(eventDate.getTime());
    }
    return false;
  });
}

/**
 * Check if graph data has map data (nodes with coordinates)
 */
export function hasMapData(nodes) {
  return nodes.some(node => {
    const latitude = node.latitude || node.lat;
    const longitude = node.longitude || node.lng || node.lon;
    return latitude != null && longitude != null && 
           !isNaN(parseFloat(latitude)) && !isNaN(parseFloat(longitude));
  });
}
