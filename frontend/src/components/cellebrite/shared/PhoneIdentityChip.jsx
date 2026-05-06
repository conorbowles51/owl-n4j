import React from 'react';
import { Smartphone } from 'lucide-react';

import { usePhoneReports } from '../../../context/PhoneReportsContext';
import { getPhoneIdentityByKey } from '../../../utils/phoneIdentity';

/**
 * Inline chip that identifies which phone a row, message, marker, or
 * graph node belongs to.
 *
 * Variants:
 *  - "dense"   — just the swatch + short label (e.g. [● P1]). Use in
 *                tight columns and dense lists.
 *  - "default" — swatch + short label + device model (P1 · iPhone 12).
 *  - "full"    — swatch + short label + device + owner.
 *
 * Falls back to a hash-derived colour and "P?" label when the
 * PhoneReportsContext is missing or the report_key is unknown — that
 * way the chip still renders sensibly in places like the main MapView
 * popup where the provider may not be in scope.
 */
export default function PhoneIdentityChip({
  reportKey,
  variant = 'default',
  className = '',
  showIcon = false,
}) {
  const ctx = usePhoneReports();
  const reports = ctx ? ctx.reports : [];
  const identity = ctx
    ? ctx.getIdentityByKey(reportKey)
    : getPhoneIdentityByKey(reportKey, reports);

  if (!reportKey) return null;

  const showModel = variant === 'default' || variant === 'full';
  const showOwner = variant === 'full' && identity.owner;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[11px] font-medium ${className}`}
      style={{
        borderColor: identity.hex,
        color: identity.hex,
        backgroundColor: 'transparent',
      }}
      title={identity.long}
    >
      <span
        className="inline-block rounded-sm px-1 py-0.5 font-mono font-bold text-[10px] leading-none text-white"
        style={{ backgroundColor: identity.hex }}
      >
        {identity.short}
      </span>
      {showIcon && <Smartphone className="w-3 h-3 opacity-70" />}
      {showModel && (
        <span className="truncate max-w-[160px]">
          {identity.model || 'Unknown device'}
          {showOwner ? ` · ${identity.owner}` : ''}
        </span>
      )}
    </span>
  );
}

/**
 * 4-pixel left accent stripe colour helper. Returns an inline `style`
 * object suitable for spreading on a row/list-item.
 *
 * Usage:
 *   <li style={{ ...phoneAccentStripe(reportKey, ctx) }}>...
 */
export function phoneAccentStripe(reportKey, ctx) {
  if (!reportKey) return {};
  const identity = ctx
    ? ctx.getIdentityByKey(reportKey)
    : getPhoneIdentityByKey(reportKey, []);
  return {
    borderLeftWidth: '4px',
    borderLeftStyle: 'solid',
    borderLeftColor: identity.hex,
  };
}
