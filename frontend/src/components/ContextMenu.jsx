import React, { useEffect, useRef } from 'react';
import { Eye, Maximize2, X } from 'lucide-react';

/**
 * ContextMenu Component
 * 
 * Right-click menu for node actions
 */
export default function ContextMenu({ 
  node, 
  position, 
  onShowDetails, 
  onExpand, 
  onClose 
}) {
  const menuRef = useRef(null);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  // Close on escape
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  if (!node || !position) return null;

  // Adjust position to stay within viewport
  const adjustedPosition = {
    x: Math.min(position.x, window.innerWidth - 200),
    y: Math.min(position.y, window.innerHeight - 150),
  };

  return (
    <div
      ref={menuRef}
      className="fixed bg-dark-800 border border-dark-600 rounded-lg shadow-xl py-1 z-50 min-w-[160px]"
      style={{
        left: adjustedPosition.x,
        top: adjustedPosition.y,
      }}
    >
      {/* Node name header */}
      <div className="px-3 py-2 border-b border-dark-700">
        <div className="font-medium text-dark-100 text-sm truncate">
          {node.name}
        </div>
        <div className="text-xs text-dark-400">{node.type}</div>
      </div>

      {/* Actions */}
      <div className="py-1">
        <button
          onClick={() => {
            onShowDetails(node);
            onClose();
          }}
          className="w-full px-3 py-2 text-left text-sm text-dark-200 hover:bg-dark-700 flex items-center gap-2 transition-colors"
        >
          <Eye className="w-4 h-4 text-dark-400" />
          Show Details
        </button>
        <button
          onClick={() => {
            onExpand(node);
            onClose();
          }}
          className="w-full px-3 py-2 text-left text-sm text-dark-200 hover:bg-dark-700 flex items-center gap-2 transition-colors"
        >
          <Maximize2 className="w-4 h-4 text-dark-400" />
          Expand Connections
        </button>
      </div>
    </div>
  );
}
