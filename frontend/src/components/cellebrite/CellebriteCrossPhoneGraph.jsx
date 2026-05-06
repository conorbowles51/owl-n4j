import React, { useState, useEffect, useCallback, useRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Loader2, Search, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import { cellebriteAPI } from '../../services/api';
import { usePhoneReports } from '../../context/PhoneReportsContext';
import PhoneIdentityChip from './shared/PhoneIdentityChip';

const NODE_COLORS = {
  PhoneReport: '#059669',  // emerald-600 (fallback when no phone identity)
  Person: '#3b82f6',       // blue-500
  PersonShared: '#f59e0b', // amber-500
};

/**
 * Cross-phone graph visualization showing shared contacts across devices.
 */
export default function CellebriteCrossPhoneGraph({ caseId }) {
  const phoneCtx = usePhoneReports();

  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [hoveredNode, setHoveredNode] = useState(null);
  const fgRef = useRef();
  const containerRef = useRef();

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);

    cellebriteAPI.getCrossPhoneGraph(caseId).then(data => {
      if (!cancelled) {
        setGraphData(data || { nodes: [], links: [] });
        setLoading(false);
      }
    }).catch(() => {
      if (!cancelled) {
        setGraphData({ nodes: [], links: [] });
        setLoading(false);
      }
    });

    return () => { cancelled = true; };
  }, [caseId]);

  const filteredData = React.useMemo(() => {
    if (!searchTerm.trim()) return graphData;

    const term = searchTerm.toLowerCase();
    const matchingNodeIds = new Set(
      graphData.nodes
        .filter(n => (n.name || '').toLowerCase().includes(term) || (n.phone || '').includes(term))
        .map(n => n.id)
    );

    // Include linked nodes
    graphData.links.forEach(l => {
      const srcId = typeof l.source === 'object' ? l.source.id : l.source;
      const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
      if (matchingNodeIds.has(srcId)) matchingNodeIds.add(tgtId);
      if (matchingNodeIds.has(tgtId)) matchingNodeIds.add(srcId);
    });

    return {
      nodes: graphData.nodes.filter(n => matchingNodeIds.has(n.id)),
      links: graphData.links.filter(l => {
        const srcId = typeof l.source === 'object' ? l.source.id : l.source;
        const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
        return matchingNodeIds.has(srcId) && matchingNodeIds.has(tgtId);
      }),
    };
  }, [graphData, searchTerm]);

  const paintNode = useCallback((node, ctx, globalScale) => {
    const isReport = node.type === 'PhoneReport';
    const isShared = node.shared;

    // Phone identity colour: a PhoneReport node IS a phone, so it uses
    // its own report_key. A Person node carries one (or more) report_keys
    // depending on whether they appear on one or multiple phones.
    const phoneKey = node.report_key || node.cellebrite_report_key;
    const phoneIdentity = phoneCtx && phoneKey
      ? phoneCtx.getIdentityByKey(phoneKey)
      : null;

    // PhoneReport: fill with the phone's persistent palette colour so it
    // matches every chip / stripe / map ring elsewhere in the app.
    // Person: keep the existing semantic colours (default vs shared) but
    // add a coloured ring in the phone's identity colour to show which
    // phone owns the contact.
    const fillColor = isReport && phoneIdentity
      ? phoneIdentity.hex
      : isReport
      ? NODE_COLORS.PhoneReport
      : isShared
      ? NODE_COLORS.PersonShared
      : NODE_COLORS.Person;

    const r = isReport ? 8 : 4 + Math.min(node.comm_count || 0, 10) * 0.3;

    // Phone identity ring on Person nodes (non-report). Drawn first so
    // the node fill sits inside it.
    if (!isReport && phoneIdentity) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI);
      ctx.fillStyle = phoneIdentity.hex;
      ctx.fill();
    }

    // Draw node
    ctx.beginPath();
    if (isReport) {
      const size = r * 2;
      ctx.roundRect(node.x - r, node.y - r, size, size, 3);
    } else {
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    }
    ctx.fillStyle = fillColor;
    ctx.fill();

    if (isShared) {
      ctx.strokeStyle = '#d97706';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    // Label
    const fontSize = isReport ? 11 / globalScale : 9 / globalScale;
    ctx.font = `${isReport ? 'bold ' : ''}${fontSize}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#334155';
    let label = (node.name || '').substring(0, 20);
    if (isReport && phoneIdentity) {
      label = `${phoneIdentity.short} · ${label}`;
    }
    ctx.fillText(label, node.x, node.y + r + 2 / globalScale);
  }, [phoneCtx]);

  const handleZoomIn = () => fgRef.current?.zoom(fgRef.current.zoom() * 1.5, 300);
  const handleZoomOut = () => fgRef.current?.zoom(fgRef.current.zoom() / 1.5, 300);
  const handleFit = () => fgRef.current?.zoomToFit(400, 40);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-light-400" />
      </div>
    );
  }

  if (graphData.nodes.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-light-500 text-sm">
        No cross-phone data available
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col" ref={containerRef}>
      {/* Controls */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-light-400" />
          <input
            type="text"
            placeholder="Search contacts..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs border border-light-300 rounded bg-white focus:outline-none focus:ring-1 focus:ring-emerald-400"
          />
        </div>
        <button onClick={handleZoomIn} className="p-1.5 hover:bg-light-200 rounded" title="Zoom in">
          <ZoomIn className="w-4 h-4 text-light-600" />
        </button>
        <button onClick={handleZoomOut} className="p-1.5 hover:bg-light-200 rounded" title="Zoom out">
          <ZoomOut className="w-4 h-4 text-light-600" />
        </button>
        <button onClick={handleFit} className="p-1.5 hover:bg-light-200 rounded" title="Fit to view">
          <Maximize2 className="w-4 h-4 text-light-600" />
        </button>
        <div className="text-xs text-light-500 ml-2">
          {filteredData.nodes.length} nodes, {filteredData.links.length} links
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-1.5 border-b border-light-100 text-xs text-light-600 flex-shrink-0 flex-wrap">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full" style={{ backgroundColor: NODE_COLORS.Person }} />
          Contact
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full border-2 border-amber-500" style={{ backgroundColor: NODE_COLORS.PersonShared }} />
          Shared Contact
        </span>
        {phoneCtx?.hasMultiple && (
          <>
            <span className="h-4 w-px bg-light-300" />
            <span className="text-light-500 font-medium">Phones:</span>
            {phoneCtx.reports.map((r) => (
              <PhoneIdentityChip
                key={r.report_key}
                reportKey={r.report_key}
                variant="default"
              />
            ))}
          </>
        )}
      </div>

      {/* Graph */}
      <div className="flex-1 min-h-0">
        <ForceGraph2D
          ref={fgRef}
          graphData={filteredData}
          nodeCanvasObject={paintNode}
          nodePointerAreaPaint={(node, color, ctx) => {
            const r = node.type === 'PhoneReport' ? 8 : 6;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
            ctx.fill();
          }}
          linkColor={() => '#e2e8f0'}
          linkWidth={l => l.count ? Math.min(l.count / 5, 3) : 0.5}
          linkDirectionalArrowLength={0}
          onNodeHover={setHoveredNode}
          warmupTicks={50}
          cooldownTicks={100}
          d3AlphaDecay={0.05}
          d3VelocityDecay={0.3}
        />
      </div>

      {/* Hover tooltip */}
      {hoveredNode && (
        <div className="absolute bottom-4 left-4 bg-white border border-light-300 rounded-lg shadow-lg p-3 text-xs max-w-xs pointer-events-none z-10">
          <div className="font-semibold text-owl-blue-900 flex items-center gap-1.5 flex-wrap">
            <span>{hoveredNode.name}</span>
            {hoveredNode.type === 'PhoneReport' && hoveredNode.report_key && (
              <PhoneIdentityChip reportKey={hoveredNode.report_key} variant="dense" />
            )}
          </div>
          {hoveredNode.type === 'PhoneReport' && hoveredNode.phone_owner && (
            <div className="text-light-600 mt-0.5">Owner: {hoveredNode.phone_owner}</div>
          )}
          {hoveredNode.phone && (
            <div className="text-light-600 mt-0.5">Phone: {hoveredNode.phone}</div>
          )}
          {hoveredNode.device_count > 1 && (
            <div className="text-amber-600 font-medium mt-0.5">
              Appears on {hoveredNode.device_count} devices
            </div>
          )}
          {hoveredNode.comm_count > 0 && (
            <div className="text-light-500 mt-0.5">{hoveredNode.comm_count} communications</div>
          )}
          {/* Person nodes can be linked to one or several phones — show
              every phone they appear on as a chip strip. */}
          {hoveredNode.type !== 'PhoneReport' && (
            (() => {
              const keys = Array.isArray(hoveredNode.report_keys)
                ? hoveredNode.report_keys
                : (hoveredNode.report_key ? [hoveredNode.report_key] : []);
              if (keys.length === 0) return null;
              return (
                <div className="mt-1 flex items-center gap-1 flex-wrap">
                  <span className="text-light-500">On:</span>
                  {keys.map((rk) => (
                    <PhoneIdentityChip key={rk} reportKey={rk} variant="dense" />
                  ))}
                </div>
              );
            })()
          )}
        </div>
      )}
    </div>
  );
}
