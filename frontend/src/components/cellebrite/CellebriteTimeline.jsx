import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, Phone, MessageSquare, MapPin, Mail, ChevronDown, Filter } from 'lucide-react';
import { cellebriteAPI } from '../../services/api';

const EVENT_CONFIG = {
  call: { icon: Phone, color: 'text-green-600', bg: 'bg-green-50', border: 'border-green-200', label: 'Call' },
  message: { icon: MessageSquare, color: 'text-purple-600', bg: 'bg-purple-50', border: 'border-purple-200', label: 'Message' },
  location: { icon: MapPin, color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200', label: 'Location' },
  email: { icon: Mail, color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200', label: 'Email' },
};

// Assign a color to each device
const DEVICE_COLORS = ['#059669', '#3b82f6', '#8b5cf6', '#f59e0b', '#ec4899', '#06b6d4'];

/**
 * Multi-device event timeline.
 */
export default function CellebriteTimeline({ caseId, reports }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [selectedTypes, setSelectedTypes] = useState(new Set(['call', 'message', 'location', 'email']));
  const [selectedDevices, setSelectedDevices] = useState(new Set(reports.map(r => r.report_key)));
  const [showFilters, setShowFilters] = useState(false);

  const deviceColorMap = React.useMemo(() => {
    const map = {};
    reports.forEach((r, i) => {
      map[r.report_key] = DEVICE_COLORS[i % DEVICE_COLORS.length];
    });
    return map;
  }, [reports]);

  const deviceNameMap = React.useMemo(() => {
    const map = {};
    reports.forEach(r => {
      map[r.report_key] = r.device_model || r.report_key;
    });
    return map;
  }, [reports]);

  const fetchEvents = useCallback(async (newOffset = 0, append = false) => {
    if (!caseId) return;
    if (newOffset === 0) setLoading(true);
    else setLoadingMore(true);

    try {
      const reportKeys = [...selectedDevices];
      const eventTypes = [...selectedTypes];
      const data = await cellebriteAPI.getTimeline(caseId, reportKeys.length < reports.length ? reportKeys : null, {
        eventTypes: eventTypes.length < 4 ? eventTypes : undefined,
        limit: 200,
        offset: newOffset,
      });

      const newEvents = data.events || [];
      if (append) {
        setEvents(prev => [...prev, ...newEvents]);
      } else {
        setEvents(newEvents);
      }
      setHasMore(newEvents.length >= 200);
      setOffset(newOffset + newEvents.length);
    } catch (err) {
      console.error('Failed to load timeline:', err);
      if (!append) setEvents([]);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [caseId, selectedDevices, selectedTypes, reports.length]);

  useEffect(() => {
    fetchEvents(0, false);
  }, [fetchEvents]);

  const toggleType = (type) => {
    setSelectedTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const toggleDevice = (key) => {
    setSelectedDevices(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const formatTimestamp = (ts) => {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      return d.toLocaleString(undefined, {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    } catch {
      return ts;
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-light-400" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Filter bar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-light-200 bg-light-50 flex-shrink-0">
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-1 px-2 py-1 text-xs rounded border transition-colors ${
            showFilters ? 'bg-emerald-50 border-emerald-300 text-emerald-700' : 'bg-white border-light-300 text-light-600 hover:bg-light-100'
          }`}
        >
          <Filter className="w-3 h-3" />
          Filters
          <ChevronDown className={`w-3 h-3 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
        </button>
        <span className="text-xs text-light-500">
          {events.length} events loaded
        </span>
      </div>

      {showFilters && (
        <div className="px-4 py-3 border-b border-light-200 bg-light-50 space-y-3 flex-shrink-0">
          {/* Event types */}
          <div>
            <div className="text-xs font-medium text-light-600 mb-1.5">Event Types</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(EVENT_CONFIG).map(([type, config]) => {
                const Icon = config.icon;
                const active = selectedTypes.has(type);
                return (
                  <button
                    key={type}
                    onClick={() => toggleType(type)}
                    className={`flex items-center gap-1 px-2 py-1 text-xs rounded border transition-colors ${
                      active ? `${config.bg} ${config.border} ${config.color}` : 'bg-white border-light-300 text-light-400'
                    }`}
                  >
                    <Icon className="w-3 h-3" />
                    {config.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Devices */}
          {reports.length > 1 && (
            <div>
              <div className="text-xs font-medium text-light-600 mb-1.5">Devices</div>
              <div className="flex flex-wrap gap-2">
                {reports.map(r => {
                  const active = selectedDevices.has(r.report_key);
                  const color = deviceColorMap[r.report_key];
                  return (
                    <button
                      key={r.report_key}
                      onClick={() => toggleDevice(r.report_key)}
                      className={`flex items-center gap-1 px-2 py-1 text-xs rounded border transition-colors ${
                        active ? 'bg-white border-light-400 text-owl-blue-900' : 'bg-light-100 border-light-200 text-light-400'
                      }`}
                    >
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: active ? color : '#d1d5db' }}
                      />
                      {r.device_model || r.report_key}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Timeline events */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {events.length === 0 ? (
          <div className="flex items-center justify-center h-full text-light-500 text-sm">
            No events match the current filters
          </div>
        ) : (
          <div className="px-4 py-3 space-y-1">
            {events.map((event, idx) => {
              const config = EVENT_CONFIG[event.event_type] || EVENT_CONFIG.message;
              const Icon = config.icon;
              const deviceColor = deviceColorMap[event.report_key] || '#6b7280';
              const deviceName = deviceNameMap[event.report_key] || '';

              return (
                <div key={`${event.node_key}-${idx}`} className="flex items-start gap-3 py-2 border-b border-light-100 last:border-0">
                  {/* Time column */}
                  <div className="w-36 flex-shrink-0 text-right">
                    <div className="text-xs text-light-500">{formatTimestamp(event.timestamp)}</div>
                  </div>

                  {/* Device indicator */}
                  <div className="flex flex-col items-center flex-shrink-0 pt-0.5">
                    <span
                      className="w-2.5 h-2.5 rounded-full border-2 border-white shadow-sm"
                      style={{ backgroundColor: deviceColor }}
                      title={deviceName}
                    />
                  </div>

                  {/* Event icon */}
                  <div className={`w-6 h-6 rounded flex items-center justify-center flex-shrink-0 ${config.bg}`}>
                    <Icon className={`w-3.5 h-3.5 ${config.color}`} />
                  </div>

                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-owl-blue-900 truncate">
                      {event.summary || config.label}
                    </div>
                    {reports.length > 1 && (
                      <div className="text-[10px] text-light-400 mt-0.5">{deviceName}</div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Load more */}
            {hasMore && (
              <div className="pt-4 text-center">
                <button
                  onClick={() => fetchEvents(offset, true)}
                  disabled={loadingMore}
                  className="px-4 py-2 text-xs text-emerald-600 hover:bg-emerald-50 rounded border border-emerald-200 transition-colors disabled:opacity-50"
                >
                  {loadingMore ? (
                    <span className="flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Loading...
                    </span>
                  ) : (
                    'Load more events'
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
