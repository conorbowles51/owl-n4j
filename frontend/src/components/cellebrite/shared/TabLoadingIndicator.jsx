import React, { useEffect, useState } from 'react';

/**
 * TabLoadingIndicator
 *
 * Determinate progress UI for slow Cellebrite tabs (Comms, Timeline,
 * Location & Events). The parent fetches data in stages and updates
 * `progress` (0..100) and `stage` (a short label) as each stage
 * completes — the bar fills accordingly so the user can see real
 * movement and tell the difference between "still working" and
 * "frozen / crashed".
 *
 * Reassurance copy appears on a delay so users know the long load is
 * still in-flight when no stages have completed in a while.
 */
export default function TabLoadingIndicator({
  label = 'Loading…',
  progress = 0,
  stage = '',
}) {
  const [reassureLevel, setReassureLevel] = useState(0);

  // Reset reassurance counter whenever progress moves — if the bar is
  // ticking forward there's no need to reassure the user.
  useEffect(() => {
    setReassureLevel(0);
    const t1 = setTimeout(() => setReassureLevel(1), 5000);
    const t2 = setTimeout(() => setReassureLevel(2), 15000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [progress]);

  const clamped = Math.max(0, Math.min(100, progress));

  return (
    <div className="flex flex-col items-center justify-center h-full px-6 gap-3">
      <div className="w-72 h-2 bg-light-100 rounded overflow-hidden">
        <div
          className="h-full bg-emerald-500 rounded transition-all duration-200 ease-out"
          style={{ width: `${clamped}%` }}
        />
      </div>
      <div className="flex items-center gap-2 text-sm text-light-700">
        <span>{label}</span>
        <span className="text-light-400">·</span>
        <span className="tabular-nums text-light-500">{Math.round(clamped)}%</span>
      </div>
      {stage && (
        <div className="text-xs text-light-500">{stage}</div>
      )}
      {reassureLevel >= 1 && (
        <div className="text-xs text-light-500 max-w-xs text-center">
          Still working — large cases can take a moment on first load.
        </div>
      )}
      {reassureLevel >= 2 && (
        <div className="text-xs text-light-500 max-w-xs text-center">
          Working on it… very large datasets may take up to a minute.
        </div>
      )}
    </div>
  );
}
