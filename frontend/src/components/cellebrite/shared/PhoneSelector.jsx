import React, { useState, useRef, useEffect } from 'react';
import { Smartphone, Check, ChevronsUpDown, Filter } from 'lucide-react';

import { usePhoneReports } from '../../../context/PhoneReportsContext';

/**
 * Shared phone selector mounted at the top of every Cellebrite tab.
 *
 * Reads its data from PhoneReportsContext so the selection is global
 * (changes in Comms apply to Events, Timeline, Files, etc.) and persists
 * across page refreshes via localStorage.
 *
 * Each chip carries the phone's persistent palette colour and short
 * label ("P1", "P2", …) so investigators can match a chip to rows on
 * any Cellebrite surface without reading text.
 *
 * Right-click (or long-press) on a chip → "Show only this phone" via
 * the context-menu shortcut. A dedicated "Solo" button is also exposed.
 */
export default function PhoneSelector({ compact = false, label = 'Phones' }) {
  const ctx = usePhoneReports();

  // Provider missing or no Cellebrite reports — render nothing.
  if (!ctx || !ctx.hasReports) return null;
  // Single phone: there is no filtering to do — render nothing.
  if (!ctx.hasMultiple) return null;

  const {
    reports,
    selectedReportKeys,
    allSelected,
    noneSelected,
    toggleReport,
    selectAll,
    clear,
    selectOnly,
    getIdentity,
  } = ctx;

  return (
    <div
      className={`flex items-center gap-2 px-4 ${compact ? 'py-1.5' : 'py-2'} border-b border-light-200 bg-light-50 flex-shrink-0 overflow-x-auto`}
      data-testid="phone-selector"
    >
      <div className="flex items-center gap-1.5 text-xs text-light-600 flex-shrink-0">
        <Filter className="w-3.5 h-3.5" />
        <span className="font-medium">{label}:</span>
      </div>

      {/* All / None toggle */}
      <button
        onClick={allSelected ? clear : selectAll}
        className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors flex-shrink-0 ${
          allSelected
            ? 'bg-light-800 border-light-800 text-white'
            : noneSelected
            ? 'bg-light-100 border-light-300 text-light-600 hover:bg-light-200'
            : 'bg-white border-light-400 text-light-700 hover:bg-light-100'
        }`}
        title={allSelected ? 'Deselect all phones' : 'Select all phones'}
      >
        {allSelected ? <Check className="w-3 h-3" /> : <ChevronsUpDown className="w-3 h-3" />}
        All ({reports.length})
      </button>

      {reports.map((r) => {
        const active = selectedReportKeys.has(r.report_key);
        const identity = getIdentity(r);
        const totalComms =
          (r.stats?.calls || 0) +
          (r.stats?.messages || 0) +
          (r.stats?.emails || 0);

        // Active chip: filled with the phone's colour at 100% on the swatch
        // + a soft tinted background, plus a coloured border.
        // Inactive chip: white background with the swatch still showing,
        // muted border. Always visible so the colour mapping is learnable.
        const activeStyles = active
          ? {
              backgroundColor: hexWithAlpha(identity.hex, 0.12),
              borderColor: identity.hex,
              color: identity.hex,
            }
          : undefined;

        return (
          <ChipWithSolo
            key={r.report_key}
            active={active}
            label={(
              <>
                <span
                  className="inline-block rounded-sm px-1.5 py-0.5 font-mono font-bold text-[10px] leading-none"
                  style={{
                    backgroundColor: identity.hex,
                    color: '#fff',
                  }}
                >
                  {identity.short}
                </span>
                <Smartphone className="w-3 h-3 opacity-70" />
                <span className="truncate max-w-[180px]">
                  {r.device_model || 'Unknown device'}
                  {r.phone_owner_name ? ` · ${r.phone_owner_name}` : ''}
                </span>
                {active && <Check className="w-3 h-3 opacity-70" />}
              </>
            )}
            tooltip={`${identity.long}${totalComms ? ` · ${totalComms.toLocaleString()} comms` : ''}\nClick: toggle · Right-click: show only this phone`}
            activeStyle={activeStyles}
            onToggle={() => toggleReport(r.report_key)}
            onSolo={() => selectOnly(r.report_key)}
          />
        );
      })}

      {noneSelected && (
        <span className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-1 rounded-full flex-shrink-0">
          No phones selected — choose at least one to see data
        </span>
      )}
    </div>
  );
}

/**
 * Internal chip component. Wraps the click + right-click ("solo") behaviour
 * so the parent stays declarative.
 */
function ChipWithSolo({ active, label, tooltip, activeStyle, onToggle, onSolo }) {
  const buttonRef = useRef(null);
  // Long-press detection for touch devices: 500ms hold = solo.
  const longPressTimerRef = useRef(null);
  const longPressFiredRef = useRef(false);

  const handleMouseDown = () => {
    longPressFiredRef.current = false;
    longPressTimerRef.current = setTimeout(() => {
      longPressFiredRef.current = true;
      onSolo();
    }, 500);
  };
  const handleMouseUp = () => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  };

  useEffect(() => () => {
    if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current);
  }, []);

  return (
    <button
      ref={buttonRef}
      onClick={(e) => {
        // Suppress click after a long-press solo so the chip doesn't toggle off.
        if (longPressFiredRef.current) {
          longPressFiredRef.current = false;
          e.preventDefault();
          return;
        }
        onToggle();
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        onSolo();
      }}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onTouchStart={handleMouseDown}
      onTouchEnd={handleMouseUp}
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors flex-shrink-0 ${
        active
          ? ''
          : 'bg-white border-light-300 text-light-600 hover:bg-light-100'
      }`}
      style={active ? activeStyle : undefined}
      title={tooltip}
    >
      {label}
    </button>
  );
}

/**
 * Convert a #RRGGBB hex to rgba() with the given alpha.
 * Used for the soft tinted background on the active chip — keeps
 * the chip readable while still carrying the phone's colour.
 */
function hexWithAlpha(hex, alpha) {
  if (!hex || hex.length !== 7) return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
