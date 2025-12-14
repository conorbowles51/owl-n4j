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
    ? 'w-full bg-white/50 flex flex-col'
    : 'w-80 bg-white border-l border-light-200 h-full flex flex-col';
  const headerPadding = compact ? 'p-3' : 'p-4';
  const iconSize = compact ? 'w-4 h-4' : 'w-5 h-5';
  const titleSize = compact ? 'text-sm font-semibold' : 'font-semibold';
  const contentClass = compact 
    ? 'p-3 space-y-2'
    : 'flex-1 overflow-y-auto p-4 space-y-4';

  return (
    <div className={containerClass}>
      {/* Header */}
      <div className={`${headerPadding} border-b border-light-200 flex items-start justify-between`}>
        <div className="flex items-start gap-3">
          <div className="p-2 bg-owl-blue-100 rounded-lg">
            <Icon className={`${iconSize} text-owl-blue-700`} />
          </div>
          <div>
            <h2 className={`${titleSize} text-owl-blue-900`}>{node.name}</h2>
            <span className="text-xs text-light-600 bg-light-100 px-2 py-0.5 rounded">
              {node.type}
            </span>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-4 h-4 text-light-600" />
          </button>
        )}
      </div>

      {/* Content */}
      <div className={contentClass}>
        {/* Key */}
        <div>
          <label className="text-xs font-medium text-light-600 uppercase tracking-wide">
            Key
          </label>
          <p className="text-sm text-light-800 font-mono mt-1">{node.key}</p>
        </div>

        {/* Summary */}
        {node.summary && (
          <div>
            <label className="text-xs font-medium text-light-600 uppercase tracking-wide">
              Summary
            </label>
            <p className="text-sm text-light-800 mt-1 leading-relaxed">
              {node.summary}
            </p>
          </div>
        )}

        {/* Notes */}
        {node.notes && (
          <div>
            <label className="text-xs font-medium text-light-600 uppercase tracking-wide">
              Document Notes
            </label>
            <div className="mt-1 text-sm text-light-700 bg-light-50 rounded-lg p-3 max-h-48 overflow-y-auto whitespace-pre-wrap font-mono text-xs border border-light-200">
              {node.notes}
            </div>
          </div>
        )}

        {/* Connections */}
        {node.connections && node.connections.length > 0 && (
          <div>
            <label className="text-xs font-medium text-light-600 uppercase tracking-wide">
              Connections ({node.connections.length})
            </label>
            <div className="mt-2 space-y-2">
              {node.connections.map((conn, idx) => (
                <button
                  key={idx}
                  onClick={() => onSelectNode?.(conn.key)}
                  className="w-full text-left p-2 bg-light-50 hover:bg-light-100 rounded-lg transition-colors group border border-light-200"
                >
                  <div className="flex items-center gap-2">
                    {conn.direction === 'outgoing' ? (
                      <ArrowRight className="w-4 h-4 text-owl-purple-500" />
                    ) : (
                      <ArrowLeft className="w-4 h-4 text-owl-purple-500" />
                    )}
                    <span className="text-xs text-owl-purple-600 font-mono">
                      {conn.relationship}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center justify-between">
                    <span className="text-sm text-light-800 group-hover:text-owl-blue-900">
                      {conn.name}
                    </span>
                    <span className="text-xs text-light-600">
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
            <label className="text-xs font-medium text-light-600 uppercase tracking-wide">
              Properties
            </label>
            <div className="mt-2 space-y-1">
              {Object.entries(node.properties)
                .filter(([key]) => !['id', 'key', 'name', 'summary', 'notes', 'type'].includes(key))
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between text-sm">
                    <span className="text-light-600">{key}</span>
                    <span className="text-light-800 font-mono text-xs">
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
