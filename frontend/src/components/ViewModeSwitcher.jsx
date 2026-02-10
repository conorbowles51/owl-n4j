import React from 'react';
import { Network, Calendar, MapPin, Table2 } from 'lucide-react';

/**
 * View Mode Switcher Component
 *
 * Allows switching between Graph, Timeline, Map, and Table views
 */
export default function ViewModeSwitcher({
  mode,
  onModeChange,
  hasTimelineData = false,
  hasMapData = false,
}) {
  const modes = [
    {
      id: 'graph',
      label: 'Graph',
      icon: Network,
      alwaysAvailable: true,
      hasData: true,
    },
    {
      id: 'timeline',
      label: 'Timeline',
      icon: Calendar,
      alwaysAvailable: true,
      hasData: hasTimelineData,
    },
    {
      id: 'map',
      label: 'Map',
      icon: MapPin,
      alwaysAvailable: true,
      hasData: hasMapData,
    },
    {
      id: 'table',
      label: 'Table',
      icon: Table2,
      alwaysAvailable: true,
      hasData: true,
    },
  ];

  return (
    <div className="flex items-center gap-1 bg-light-50 rounded-lg p-1 border border-light-200">
      {modes.map((modeOption) => {
        const Icon = modeOption.icon;
        const isActive = mode === modeOption.id;
        const hasData = modeOption.hasData;

        return (
          <button
            key={modeOption.id}
            onClick={() => onModeChange(modeOption.id)}
            className={`
              flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all
              ${isActive
                ? 'bg-white text-owl-blue-600 shadow-sm'
                : hasData
                  ? 'text-light-700 hover:text-owl-blue-600 hover:bg-light-50'
                  : 'text-light-500 hover:text-owl-blue-600 hover:bg-light-50'
              }
            `}
            title={
              !hasData && modeOption.id !== 'graph'
                ? `Switch to ${modeOption.label} view (no data available)`
                : `Switch to ${modeOption.label} view`
            }
          >
            <Icon className="w-4 h-4" />
            <span>{modeOption.label}</span>
            {!hasData && modeOption.id !== 'graph' && (
              <span className="text-xs opacity-60">(no data)</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
