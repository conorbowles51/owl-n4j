import React from 'react';
import { X, User, Building2, Wallet, MapPin, FileText, ArrowRight, ArrowLeft } from 'lucide-react';

/**
 * Icon mapping for entity types
 */
const TYPE_ICONS = {
  Person: User,
  Company: Building2,
  Account: Wallet,
  Location: MapPin,
  Document: FileText,
};

/**
 * Get icon for entity type
 */
function getTypeIcon(type) {
  return TYPE_ICONS[type] || FileText;
}

/**
 * NodeDetails Component
 * 
 * Displays detailed information about a selected node
 */
export default function NodeDetails({ node, onClose, onSelectNode, compact = false }) {
  if (!node) return null;

  const Icon = getTypeIcon(node.type);

  const containerClass = compact 
    ? 'w-full bg-dark-800/50 flex flex-col'
    : 'w-80 bg-dark-800 border-l border-dark-700 h-full flex flex-col';
  const headerPadding = compact ? 'p-3' : 'p-4';
  const iconSize = compact ? 'w-4 h-4' : 'w-5 h-5';
  const titleSize = compact ? 'text-sm font-semibold' : 'font-semibold';
  const contentClass = compact 
    ? 'p-3 space-y-2'
    : 'flex-1 overflow-y-auto p-4 space-y-4';

  return (
    <div className={containerClass}>
      {/* Header */}
      <div className={`${headerPadding} border-b border-dark-700 flex items-start justify-between`}>
        <div className="flex items-start gap-3">
          <div className="p-2 bg-dark-700 rounded-lg">
            <Icon className={`${iconSize} text-dark-300`} />
          </div>
          <div>
            <h2 className={`${titleSize} text-dark-100`}>{node.name}</h2>
            <span className="text-xs text-dark-400 bg-dark-700 px-2 py-0.5 rounded">
              {node.type}
            </span>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 hover:bg-dark-700 rounded transition-colors"
          >
            <X className="w-4 h-4 text-dark-400" />
          </button>
        )}
      </div>

      {/* Content */}
      <div className={contentClass}>
        {/* Key */}
        <div>
          <label className="text-xs font-medium text-dark-400 uppercase tracking-wide">
            Key
          </label>
          <p className="text-sm text-dark-200 font-mono mt-1">{node.key}</p>
        </div>

        {/* Summary */}
        {node.summary && (
          <div>
            <label className="text-xs font-medium text-dark-400 uppercase tracking-wide">
              Summary
            </label>
            <p className="text-sm text-dark-200 mt-1 leading-relaxed">
              {node.summary}
            </p>
          </div>
        )}

        {/* Notes */}
        {node.notes && (
          <div>
            <label className="text-xs font-medium text-dark-400 uppercase tracking-wide">
              Document Notes
            </label>
            <div className="mt-1 text-sm text-dark-300 bg-dark-900 rounded-lg p-3 max-h-48 overflow-y-auto whitespace-pre-wrap font-mono text-xs">
              {node.notes}
            </div>
          </div>
        )}

        {/* Connections */}
        {node.connections && node.connections.length > 0 && (
          <div>
            <label className="text-xs font-medium text-dark-400 uppercase tracking-wide">
              Connections ({node.connections.length})
            </label>
            <div className="mt-2 space-y-2">
              {node.connections.map((conn, idx) => (
                <button
                  key={idx}
                  onClick={() => onSelectNode?.(conn.key)}
                  className="w-full text-left p-2 bg-dark-900 hover:bg-dark-700 rounded-lg transition-colors group"
                >
                  <div className="flex items-center gap-2">
                    {conn.direction === 'outgoing' ? (
                      <ArrowRight className="w-4 h-4 text-dark-500" />
                    ) : (
                      <ArrowLeft className="w-4 h-4 text-dark-500" />
                    )}
                    <span className="text-xs text-dark-400 font-mono">
                      {conn.relationship}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between">
                    <span className="text-sm text-dark-200 group-hover:text-dark-100">
                      {conn.name}
                    </span>
                    <span className="text-xs text-dark-500">
                      {conn.type}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Properties */}
        {node.properties && Object.keys(node.properties).length > 0 && (
          <div>
            <label className="text-xs font-medium text-dark-400 uppercase tracking-wide">
              Properties
            </label>
            <div className="mt-2 space-y-1">
              {Object.entries(node.properties)
                .filter(([key]) => !['id', 'key', 'name', 'summary', 'notes', 'type'].includes(key))
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between text-sm">
                    <span className="text-dark-400">{key}</span>
                    <span className="text-dark-200 font-mono text-xs">
                      {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
