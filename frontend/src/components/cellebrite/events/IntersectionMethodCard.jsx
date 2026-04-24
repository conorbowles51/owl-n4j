import React, { useState } from 'react';
import { Play, ChevronDown, ChevronRight, Loader2, MapPin, Users, Phone, Wifi, Radio } from 'lucide-react';
import { cellebriteEventsAPI } from '../../../services/api';

const METHOD_META = {
  spatial: {
    label: 'Spatial co-presence',
    icon: MapPin,
    description: 'Devices within X metres of each other within Y seconds',
    defaults: { max_distance_m: 250, max_time_delta_s: 600 },
    fields: [
      { key: 'max_distance_m', label: 'Max distance (m)', min: 10, max: 5000, step: 10 },
      { key: 'max_time_delta_s', label: 'Max time delta (s)', min: 30, max: 7200, step: 30 },
    ],
  },
  cell_tower: {
    label: 'Shared cell tower',
    icon: Radio,
    description: 'Devices registered to the same tower within the window',
    defaults: { max_time_delta_s: 900 },
    fields: [{ key: 'max_time_delta_s', label: 'Max time delta (s)', min: 60, max: 7200, step: 60 }],
  },
  wifi: {
    label: 'Shared WiFi',
    icon: Wifi,
    description: 'Devices associated with the same network in the window',
    defaults: { max_time_delta_s: 1800 },
    fields: [{ key: 'max_time_delta_s', label: 'Max time delta (s)', min: 60, max: 14400, step: 60 }],
  },
  comm_hub: {
    label: 'Communication hub',
    icon: Phone,
    description: 'Multiple devices talking to the same 3rd party in a window',
    defaults: { time_window_s: 3600, min_devices: 2 },
    fields: [
      { key: 'time_window_s', label: 'Time window (s)', min: 60, max: 86400, step: 60 },
      { key: 'min_devices', label: 'Min devices', min: 2, max: 10, step: 1 },
    ],
  },
  convoy: {
    label: 'Convoy',
    icon: Users,
    description: 'Sustained co-location across multiple samples',
    defaults: { max_distance_m: 500, min_duration_s: 1800, min_samples: 5 },
    fields: [
      { key: 'max_distance_m', label: 'Max distance (m)', min: 10, max: 5000, step: 10 },
      { key: 'min_duration_s', label: 'Min duration (s)', min: 300, max: 86400, step: 300 },
      { key: 'min_samples', label: 'Min samples', min: 2, max: 50, step: 1 },
    ],
  },
};

export default function IntersectionMethodCard({
  method,
  result,               // { matches, params_used, reason } | null if never run
  caseId,
  reportKeys,
  startDate,
  endDate,
  onResult,             // (method, result) => void
  onJumpToMatch,        // (match) => void
}) {
  const meta = METHOD_META[method];
  const [expanded, setExpanded] = useState(false);
  const [params, setParams] = useState(meta.defaults);
  const [running, setRunning] = useState(false);

  if (!meta) return null;
  const Icon = meta.icon;

  const run = async () => {
    setRunning(true);
    try {
      const res = await cellebriteEventsAPI.runIntersections(caseId, {
        methods: [method],
        reportKeys,
        startDate,
        endDate,
        params: { [method]: params },
      });
      const r = (res.results || [])[0];
      onResult(method, r || { method, matches: [], params_used: params });
    } catch (e) {
      onResult(method, { method, matches: [], params_used: params, reason: e.message });
    } finally {
      setRunning(false);
    }
  };

  const matches = result?.matches || [];
  const hasRun = !!result;

  return (
    <div className="border border-light-200 rounded bg-white">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-light-50"
      >
        {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <Icon className="w-4 h-4 text-light-600" />
        <span className="text-sm font-medium text-owl-blue-900 flex-1 text-left">
          {meta.label}
        </span>
        {hasRun && (
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded ${
              matches.length > 0 ? 'bg-emerald-100 text-emerald-800' : 'bg-light-100 text-light-600'
            }`}
          >
            {matches.length} match{matches.length === 1 ? '' : 'es'}
          </span>
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          <div className="text-[11px] text-light-600">{meta.description}</div>

          {/* Param inputs */}
          <div className="space-y-1.5">
            {meta.fields.map((f) => (
              <label key={f.key} className="block text-[11px] text-light-700">
                <div className="flex justify-between">
                  <span>{f.label}</span>
                  <span className="font-mono tabular-nums text-light-500">
                    {params[f.key]}
                  </span>
                </div>
                <input
                  type="range"
                  min={f.min}
                  max={f.max}
                  step={f.step}
                  value={params[f.key]}
                  onChange={(e) =>
                    setParams({ ...params, [f.key]: Number(e.target.value) })
                  }
                  className="w-full"
                />
              </label>
            ))}
          </div>

          <button
            onClick={run}
            disabled={running}
            className="flex items-center gap-1 px-3 py-1.5 bg-owl-blue-600 hover:bg-owl-blue-700 disabled:opacity-50 text-white text-xs rounded"
          >
            {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
            {running ? 'Running…' : 'Run check'}
          </button>

          {result?.reason && (
            <div className="text-[11px] text-amber-700 italic">{result.reason}</div>
          )}

          {hasRun && matches.length > 0 && (
            <div className="border-t border-light-100 pt-2 max-h-[240px] overflow-y-auto space-y-1">
              {matches.map((m) => (
                <button
                  key={m.id}
                  onClick={() => onJumpToMatch?.(m)}
                  className="w-full text-left p-2 border border-light-200 rounded hover:bg-owl-blue-50 text-[11px]"
                >
                  <div className="font-medium text-owl-blue-900 truncate">{m.summary}</div>
                  <div className="text-light-500 flex gap-2">
                    <span>{new Date(m.start_time).toLocaleString()}</span>
                    <span>·</span>
                    <span>{m.devices.length} device{m.devices.length === 1 ? '' : 's'}</span>
                    {m.score != null && (
                      <>
                        <span>·</span>
                        <span>score {(m.score * 100).toFixed(0)}%</span>
                      </>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}

          {hasRun && matches.length === 0 && !result.reason && (
            <div className="text-[11px] text-light-500 italic">No matches for current params.</div>
          )}
        </div>
      )}
    </div>
  );
}
