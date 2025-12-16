
import { Building2, ChevronDown, ChevronUp, Circle, MapPin, User, Wallet } from "lucide-react";
import { useMemo } from "react";

/**
 * Event types that should NOT appear in the entity dock
 * (these are timeline events, not entities)
 */
const EVENT_TYPES = new Set([
  'Transaction', 'Transfer', 'Payment', 
  'Communication', 'Email', 'PhoneCall', 'Meeting',
  'Event', 'Activity'
]);

/**
 * Get icon for entity type
 */
function getEntityIcon(type) {
  const typeLC = type?.toLowerCase() || '';
  if (typeLC.includes('person') || typeLC.includes('individual')) {
    return User;
  }
  if (typeLC.includes('location') || typeLC.includes('address') || typeLC.includes('place')) {
    return MapPin;
  }
  if (typeLC.includes('org') || typeLC.includes('company') || typeLC.includes('business')) {
    return Building2;
  }
  if (typeLC.includes('account') || typeLC.includes('wallet') || typeLC.includes('bank')) {
    return Wallet;
  }
  return Circle;
}

/**
 * Get color for entity type
 */
function getEntityColor(type) {
  const typeLC = type?.toLowerCase() || '';
  if (typeLC.includes('person') || typeLC.includes('individual')) {
    return '#3b82f6'; // blue
  }
  if (typeLC.includes('location') || typeLC.includes('address') || typeLC.includes('place')) {
    return '#10b981'; // green
  }
  if (typeLC.includes('org') || typeLC.includes('company') || typeLC.includes('business')) {
    return '#8b5cf6'; // purple
  }
  if (typeLC.includes('account') || typeLC.includes('wallet') || typeLC.includes('bank')) {
    return '#f59e0b'; // amber
  }
  return '#6b7280'; // gray
}

/**
 * Entity Dock Component
 * Shows connected non-event entities when events are selected
 */
export function EntityDock({ selectedEvents, onEntityClick, isExpanded, onToggleExpand }) {
  // Extract and group non-event entities from selected events
  const groupedEntities = useMemo(() => {
    const entities = new Map(); // key -> entity with count
    
    selectedEvents.forEach(event => {
      event.connections?.forEach(conn => {
        // Skip if it's an event type (not an entity)
        if (EVENT_TYPES.has(conn.type)) return;
        
        if (!entities.has(conn.key)) {
          entities.set(conn.key, { 
            ...conn, 
            eventCount: 1,
            connectedEventKeys: [event.key]
          });
        } else {
          const existing = entities.get(conn.key);
          existing.eventCount++;
          existing.connectedEventKeys.push(event.key);
        }
      });
    });
    
    // Group by type
    const grouped = {};
    entities.forEach(entity => {
      const type = entity.type || 'Other';
      if (!grouped[type]) {
        grouped[type] = [];
      }
      grouped[type].push(entity);
    });
    
    // Sort entities within each group by event count (most connected first)
    Object.values(grouped).forEach(arr => {
      arr.sort((a, b) => b.eventCount - a.eventCount);
    });
    
    return grouped;
  }, [selectedEvents]);
  
  const entityTypes = Object.keys(groupedEntities).sort();
  const totalEntities = Object.values(groupedEntities).reduce((sum, arr) => sum + arr.length, 0);
  
  // Don't render if no entities or no selected events
  if (selectedEvents.length === 0 || totalEntities === 0) {
    return null;
  }
  
  return (
    <div className="border-t border-light-300 bg-white flex-shrink-0">
      {/* Dock Header */}
      <button
        onClick={onToggleExpand}
        className="w-full px-4 py-2 flex items-center justify-between hover:bg-light-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-light-500" />
          ) : (
            <ChevronUp className="w-4 h-4 text-light-500" />
          )}
          <span className="text-sm font-medium text-owl-blue-900">
            Connected Entities
          </span>
          <span className="text-xs bg-light-100 text-light-600 px-2 py-0.5 rounded-full">
            {totalEntities}
          </span>
        </div>
        <span className="text-xs text-light-500">
          from {selectedEvents.length} selected event{selectedEvents.length !== 1 ? 's' : ''}
        </span>
      </button>
      
      {/* Dock Content */}
      {isExpanded && (
        <div className="px-4 pb-4 overflow-x-auto">
          <div className="flex gap-4">
            {entityTypes.map(type => {
              const entities = groupedEntities[type];
              const Icon = getEntityIcon(type);
              const color = getEntityColor(type);
              
              return (
                <div 
                  key={type}
                  className="flex-shrink-0 min-w-[180px] max-w-[240px]"
                >
                  {/* Type Header */}
                  <div 
                    className="flex items-center gap-2 mb-2 pb-1 border-b"
                    style={{ borderColor: `${color}40` }}
                  >
                    <Icon className="w-4 h-4" style={{ color }} />
                    <span className="text-xs font-semibold uppercase tracking-wide" style={{ color }}>
                      {type}
                    </span>
                    <span className="text-xs text-light-500">
                      ({entities.length})
                    </span>
                  </div>
                  
                  {/* Entity Chips */}
                  <div className="flex flex-col gap-1.5">
                    {entities.map(entity => (
                      <button
                        key={entity.key}
                        onClick={() => onEntityClick(entity)}
                        className="flex items-center gap-2 px-2.5 py-1.5 rounded-md text-left transition-all hover:shadow-sm group"
                        style={{ 
                          backgroundColor: `${color}10`,
                          border: `1px solid ${color}30`
                        }}
                        title={`${entity.name} - Connected to ${entity.eventCount} event${entity.eventCount !== 1 ? 's' : ''}`}
                      >
                        <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color }} />
                        <span className="text-sm text-light-800 truncate flex-1 group-hover:text-owl-blue-700">
                          {entity.name}
                        </span>
                        {entity.eventCount > 1 && (
                          <span 
                            className="text-xs px-1.5 py-0.5 rounded-full flex-shrink-0"
                            style={{ backgroundColor: `${color}20`, color }}
                          >
                            {entity.eventCount}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
