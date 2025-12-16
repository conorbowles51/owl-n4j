
import { Minus, ZoomIn, ZoomOut } from "lucide-react";


/**
 * Zoom Controls Component
 */
export function ZoomControls({ zoomLevel, onZoomChange }) {
  return (
    <div className="flex items-center gap-2 bg-light-100 rounded-lg px-2 py-1">
      <button
        onClick={() => onZoomChange(Math.max(0.5, zoomLevel - 0.5))}
        className="p-1 hover:bg-light-200 rounded transition-colors"
        title="Zoom out"
        disabled={zoomLevel <= 0.5}
      >
        <ZoomOut className="w-4 h-4 text-light-600" />
      </button>
      
      <div className="flex items-center gap-1">
        <Minus className="w-3 h-3 text-light-400" />
        <input
          type="range"
          min="0.5"
          max="5"
          step="0.5"
          value={zoomLevel}
          onChange={(e) => onZoomChange(parseFloat(e.target.value))}
          className="w-20 h-1 bg-light-300 rounded-lg appearance-none cursor-pointer"
        />
        <Minus className="w-3 h-3 text-light-400" />
      </div>
      
      <button
        onClick={() => onZoomChange(Math.min(5, zoomLevel + 0.5))}
        className="p-1 hover:bg-light-200 rounded transition-colors"
        title="Zoom in"
        disabled={zoomLevel >= 5}
      >
        <ZoomIn className="w-4 h-4 text-light-600" />
      </button>
      
      <span className="text-xs text-light-600 ml-1 min-w-[40px]">
        {zoomLevel}x
      </span>
    </div>
  );
}