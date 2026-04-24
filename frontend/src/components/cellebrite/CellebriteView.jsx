import React, { useState, useEffect } from 'react';
import {
  Smartphone, Network, Clock, Users, MessageSquare, MapPin, FolderTree, Loader2,
} from 'lucide-react';
import { cellebriteAPI } from '../../services/api';
import CellebriteOverview from './CellebriteOverview';
import CellebriteCrossPhoneGraph from './CellebriteCrossPhoneGraph';
import CellebriteTimeline from './CellebriteTimeline';
import CellebriteCommunicationView from './CellebriteCommunicationView';
import CellebriteCommsCenter from './CellebriteCommsCenter';
import CellebriteEventCenter from './CellebriteEventCenter';
import CellebriteFilesExplorer from './CellebriteFilesExplorer';

const TABS = [
  { key: 'overview', label: 'Overview', icon: Smartphone },
  { key: 'comms', label: 'Comms Center', icon: MessageSquare },
  { key: 'events', label: 'Location & Events', icon: MapPin },
  { key: 'files', label: 'Files', icon: FolderTree },
  { key: 'graph', label: 'Cross-Phone Graph', icon: Network },
  { key: 'timeline', label: 'Timeline', icon: Clock },
  { key: 'communications', label: 'Communications', icon: Users },
];

/**
 * Main Cellebrite Multi-Phone View container.
 * Renders a tab bar and the active tab's content.
 */
export default function CellebriteView({ caseId }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    setLoading(true);
    cellebriteAPI.getReports(caseId).then(data => {
      if (!cancelled) {
        setReports(data.reports || []);
        setLoading(false);
      }
    }).catch(() => {
      if (!cancelled) {
        setReports([]);
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [caseId]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-light-400" />
      </div>
    );
  }

  if (reports.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-8">
        <Smartphone className="w-12 h-12 text-light-300 mb-4" />
        <h3 className="text-lg font-semibold text-owl-blue-900 mb-2">No Phone Reports</h3>
        <p className="text-sm text-light-600 max-w-md">
          No phone reports have been ingested yet. Upload a Cellebrite UFED report folder
          through the evidence panel and process it to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tab Bar */}
      <div className="flex items-center border-b border-light-200 bg-light-50 px-4 flex-shrink-0">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === key
                ? 'border-emerald-500 text-emerald-700'
                : 'border-transparent text-light-600 hover:text-owl-blue-900 hover:border-light-300'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
        <div className="flex-1" />
        <span className="text-xs text-light-500">
          {reports.length} device{reports.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tab Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === 'overview' && (
          <CellebriteOverview caseId={caseId} reports={reports} />
        )}
        {activeTab === 'comms' && (
          <CellebriteCommsCenter caseId={caseId} reports={reports} />
        )}
        {activeTab === 'events' && (
          <CellebriteEventCenter caseId={caseId} reports={reports} />
        )}
        {activeTab === 'files' && (
          <CellebriteFilesExplorer caseId={caseId} reports={reports} />
        )}
        {activeTab === 'graph' && (
          <CellebriteCrossPhoneGraph caseId={caseId} />
        )}
        {activeTab === 'timeline' && (
          <CellebriteTimeline caseId={caseId} reports={reports} />
        )}
        {activeTab === 'communications' && (
          <CellebriteCommunicationView caseId={caseId} />
        )}
      </div>
    </div>
  );
}
