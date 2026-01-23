import React from 'react';
import { Network, Calendar, MapPin } from 'lucide-react';

/**
 * View Mode Switcher Component
 * 
 * Allows switching between Graph, Timeline, and Map views
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
    },
    {
      id: 'timeline',
      label: 'Timeline',
      icon: Calendar,
      alwaysAvailable: false,
      available: hasTimelineData,
    },
    {
      id: 'map',
      label: 'Map',
      icon: MapPin,
      alwaysAvailable: false,
      available: hasMapData,
    },
  ];

  return (
    <div className="flex items-center gap-1 bg-light-100 rounded-lg p-1 border border-light-200">
      {modes.map((modeOption) => {
        const Icon = modeOption.icon;
        const isAvailable = modeOption.alwaysAvailable || modeOption.available;
        const isActive = mode === modeOption.id;

        return (
          <button
            key={modeOption.id}
            onClick={() => isAvailable && onModeChange(modeOption.id)}
            disabled={!isAvailable}
            className={`
              flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all
              ${isActive
                ? 'bg-white text-owl-blue-600 shadow-sm'
                : isAvailable
                  ? 'text-light-700 hover:text-owl-blue-600 hover:bg-light-50'
                  : 'text-light-400 cursor-not-allowed opacity-50'
              }
            `}
            title={
              !isAvailable
                ? `No ${modeOption.label.toLowerCase()} data available`
                : `Switch to ${modeOption.label} view`
            }
          >
            <Icon className="w-4 h-4" />
            <span>{modeOption.label}</span>
          </button>
        );
      })}
    </div>
  );
}
