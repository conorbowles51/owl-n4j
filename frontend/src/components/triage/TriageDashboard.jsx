import React, { useState, useEffect, useCallback } from 'react';
import {
  Play, Loader2, CheckCircle2, AlertCircle, BarChart3, Clock,
  Users, ShieldAlert, FileWarning, FolderTree, PieChart,
  Shield, Database, FileText, HardDrive,
} from 'lucide-react';
import { triageAPI } from '../../services/api';

// ── Helpers ─────────────────────────────────────────────────────────

function formatSize(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

const CATEGORY_COLORS = {
  documents: '#3b82f6', images: '#8b5cf6', video: '#ec4899',
  audio: '#f59e0b', archives: '#6b7280', executables: '#ef4444',
  databases: '#10b981', emails: '#06b6d4', web: '#f97316',
  system: '#9ca3af', other: '#d1d5db',
};

const CLASSIFICATION_COLORS = {
  known_good: '#10b981', known_bad: '#ef4444',
  suspicious: '#f59e0b', custom_match: '#8b5cf6', unknown: '#9ca3af',
};

const TABS = [
  { key: 'overview', label: 'Overview', icon: BarChart3 },
  { key: 'categories', label: 'File Types', icon: PieChart },
  { key: 'classification', label: 'Classification', icon: Shield },
  { key: 'timeline', label: 'Timeline', icon: Clock },
  { key: 'users', label: 'Users', icon: Users },
  { key: 'artifacts', label: 'Artifacts', icon: FileText },
  { key: 'mismatches', label: 'Mismatches', icon: FileWarning },
];

// ── Overview Tab ────────────────────────────────────────────────────

function OverviewTab({ profile }) {
  if (!profile) return null;
  const cls = profile.classification || {};
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Total Files" value={(profile.total_files || 0).toLocaleString()} icon={HardDrive} />
        <StatCard label="Total Size" value={formatSize(profile.total_size)} icon={Database} />
        <StatCard label="OS Detected" value={profile.os_detected || '?'} icon={FolderTree} />
        <StatCard label="User Accounts" value={(cls.user_accounts || []).length} icon={Users} />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <MiniStat label="Known Good" value={cls.known_good || 0} color={CLASSIFICATION_COLORS.known_good} />
        <MiniStat label="Known Bad" value={cls.known_bad || 0} color={CLASSIFICATION_COLORS.known_bad} />
        <MiniStat label="Suspicious" value={cls.suspicious || 0} color={CLASSIFICATION_COLORS.suspicious} />
        <MiniStat label="Custom Match" value={cls.custom_match || 0} color={CLASSIFICATION_COLORS.custom_match} />
        <MiniStat label="Unknown" value={cls.unknown || 0} color={CLASSIFICATION_COLORS.unknown} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-light-200 p-4">
          <h4 className="text-sm font-medium text-light-700 mb-3">File Categories</h4>
          <HorizontalBarChart items={(profile.by_category || []).map(c => ({ label: c.category, value: c.count, color: CATEGORY_COLORS[c.category] || '#d1d5db' }))} />
        </div>
        <div className="bg-white rounded-xl border border-light-200 p-4">
          <h4 className="text-sm font-medium text-light-700 mb-3">High-Value Artifacts</h4>
          {(profile.high_value_artifacts || []).length === 0 ? (
            <p className="text-sm text-light-400">No high-value artifacts detected</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {(profile.high_value_artifacts || []).slice(0, 8).map((a, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span className="text-light-700">{a.name}</span>
                  <span className="text-light-500 bg-light-50 px-2 py-0.5 rounded">{a.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Categories Tab ──────────────────────────────────────────────────

function CategoriesTab({ profile }) {
  const categories = profile?.by_category || [];
  if (categories.length === 0) return <EmptyState message="No category data available" />;
  return (
    <div className="space-y-4">
      {categories.map((cat) => (
        <div key={cat.category} className="bg-white rounded-xl border border-light-200 p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: CATEGORY_COLORS[cat.category] || '#d1d5db' }} />
              <span className="font-medium text-owl-blue-900 capitalize">{cat.category}</span>
            </div>
            <div className="text-sm text-light-500">
              {cat.count.toLocaleString()} files ({formatSize(cat.total_size)})
            </div>
          </div>
          {cat.top_extensions && cat.top_extensions.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {cat.top_extensions.map(ext => (
                <span key={ext} className="px-2 py-0.5 bg-light-100 text-light-600 rounded text-xs font-mono">
                  {ext || '(none)'}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Classification Tab ──────────────────────────────────────────────

function ClassificationTab({ profile }) {
  const cls = profile?.classification || {};
  const items = [
    { label: 'Known Good (NSRL)', value: cls.known_good || 0, color: CLASSIFICATION_COLORS.known_good },
    { label: 'Known Bad', value: cls.known_bad || 0, color: CLASSIFICATION_COLORS.known_bad },
    { label: 'Suspicious', value: cls.suspicious || 0, color: CLASSIFICATION_COLORS.suspicious },
    { label: 'Custom Match', value: cls.custom_match || 0, color: CLASSIFICATION_COLORS.custom_match },
    { label: 'Unknown', value: cls.unknown || 0, color: CLASSIFICATION_COLORS.unknown },
  ];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <StatCard label="Total Classified" value={(cls.total_classified || 0).toLocaleString()} icon={Shield} />
        <StatCard label="System Files" value={(cls.system_files || 0).toLocaleString()} icon={FolderTree} />
        <StatCard label="User Files" value={(cls.user_files || 0).toLocaleString()} icon={Users} />
      </div>
      <div className="bg-white rounded-xl border border-light-200 p-4">
        <h4 className="text-sm font-medium text-light-700 mb-3">Hash Classification</h4>
        <HorizontalBarChart items={items} />
      </div>
    </div>
  );
}

// ── Timeline Tab ────────────────────────────────────────────────────

function TimelineTab({ caseId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    triageAPI.getTimeline(caseId).then(r => setData(r.timeline || [])).catch(() => {});
  }, [caseId]);

  if (!data) return <Loader2 className="w-6 h-6 animate-spin text-owl-blue-500 mx-auto mt-8" />;
  if (data.length === 0) return <EmptyState message="No timeline data available" />;

  const maxCount = Math.max(...data.map(d => d.count));

  return (
    <div className="bg-white rounded-xl border border-light-200 p-4">
      <h4 className="text-sm font-medium text-light-700 mb-4">File Modification Activity</h4>
      <div className="space-y-1 max-h-96 overflow-y-auto">
        {data.map((item) => (
          <div key={item.month} className="flex items-center gap-3 text-sm">
            <span className="w-20 text-light-500 text-xs font-mono flex-shrink-0">{item.month}</span>
            <div className="flex-1 h-5 bg-light-50 rounded overflow-hidden">
              <div
                className="h-full bg-owl-blue-400 rounded"
                style={{ width: `${(item.count / maxCount) * 100}%` }}
              />
            </div>
            <span className="w-20 text-right text-light-500 text-xs flex-shrink-0">
              {item.count.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Users Tab ───────────────────────────────────────────────────────

function UsersTab({ profile }) {
  const users = profile?.user_profiles || [];
  if (users.length === 0) return <EmptyState message="No user profiles detected" />;

  return (
    <div className="space-y-4">
      {users.map((user) => (
        <div key={user.account} className="bg-white rounded-xl border border-light-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-owl-blue-500" />
              <span className="font-medium text-owl-blue-900">{user.account}</span>
            </div>
            <span className="text-sm text-light-500">
              {user.file_count.toLocaleString()} files ({formatSize(user.total_size)})
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {(user.categories || []).map(cat => (
              <span key={cat} className="px-2 py-0.5 bg-light-100 text-light-600 rounded text-xs capitalize">
                {cat}
              </span>
            ))}
          </div>
          {user.earliest_modified && user.latest_modified && (
            <p className="text-xs text-light-400">
              Activity: {user.earliest_modified?.slice(0, 10)} to {user.latest_modified?.slice(0, 10)}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Artifacts Tab ───────────────────────────────────────────────────

function ArtifactsTab({ caseId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    triageAPI.getArtifacts(caseId).then(r => setData(r.artifacts || [])).catch(() => {});
  }, [caseId]);

  if (!data) return <Loader2 className="w-6 h-6 animate-spin text-owl-blue-500 mx-auto mt-8" />;
  if (data.length === 0) return <EmptyState message="No high-value artifacts detected" />;

  const priorityColors = { 1: 'bg-red-100 text-red-700', 2: 'bg-amber-100 text-amber-700', 3: 'bg-blue-100 text-blue-700' };

  return (
    <div className="space-y-4">
      {data.map((art, i) => (
        <div key={i} className="bg-white rounded-xl border border-light-200 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${priorityColors[art.priority] || priorityColors[3]}`}>
                P{art.priority}
              </span>
              <span className="font-medium text-owl-blue-900">{art.name}</span>
            </div>
            <span className="text-sm text-light-500">{art.count} found</span>
          </div>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {(art.files || []).map((f, j) => (
              <div key={j} className="flex items-center gap-2 text-xs text-light-600 font-mono">
                <FileText className="w-3 h-3 flex-shrink-0" />
                <span className="truncate">{f.path}</span>
                <span className="text-light-400 flex-shrink-0">{formatSize(f.size)}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Mismatches Tab ──────────────────────────────────────────────────

function MismatchesTab({ caseId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    triageAPI.getMismatches(caseId).then(r => setData(r.mismatches || [])).catch(() => {});
  }, [caseId]);

  if (!data) return <Loader2 className="w-6 h-6 animate-spin text-owl-blue-500 mx-auto mt-8" />;
  if (data.length === 0) return <EmptyState message="No extension mismatches detected" />;

  return (
    <div className="bg-white rounded-xl border border-light-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-light-50 text-left">
          <tr>
            <th className="px-4 py-2 text-light-600 font-medium">File</th>
            <th className="px-4 py-2 text-light-600 font-medium">Extension</th>
            <th className="px-4 py-2 text-light-600 font-medium">Actual Type</th>
            <th className="px-4 py-2 text-light-600 font-medium text-right">Size</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-light-100">
          {data.map((m, i) => (
            <tr key={i} className="hover:bg-light-50">
              <td className="px-4 py-2 font-mono text-xs text-light-700 truncate max-w-xs">{m.name}</td>
              <td className="px-4 py-2 font-mono text-xs text-red-600">{m.extension}</td>
              <td className="px-4 py-2 text-xs text-light-600">{m.mime_type}</td>
              <td className="px-4 py-2 text-xs text-light-500 text-right">{formatSize(m.size)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Shared components ───────────────────────────────────────────────

function StatCard({ label, value, icon: Icon }) {
  return (
    <div className="bg-white rounded-xl border border-light-200 p-4 text-center">
      {Icon && <Icon className="w-5 h-5 text-owl-blue-400 mx-auto mb-1" />}
      <p className="text-2xl font-bold text-owl-blue-900">{value}</p>
      <p className="text-xs text-light-500">{label}</p>
    </div>
  );
}

function MiniStat({ label, value, color }) {
  return (
    <div className="bg-white rounded-lg border border-light-200 p-3 flex items-center gap-2">
      <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
      <div>
        <p className="text-sm font-semibold text-owl-blue-900">{value.toLocaleString()}</p>
        <p className="text-xs text-light-500">{label}</p>
      </div>
    </div>
  );
}

function HorizontalBarChart({ items }) {
  const maxVal = Math.max(...items.map(i => i.value), 1);
  return (
    <div className="space-y-2">
      {items.filter(i => i.value > 0).map((item) => (
        <div key={item.label} className="flex items-center gap-3 text-sm">
          <span className="w-28 text-light-600 truncate text-xs capitalize">{item.label}</span>
          <div className="flex-1 h-4 bg-light-50 rounded overflow-hidden">
            <div
              className="h-full rounded"
              style={{ width: `${(item.value / maxVal) * 100}%`, backgroundColor: item.color || '#3b82f6' }}
            />
          </div>
          <span className="w-16 text-right text-light-500 text-xs">{item.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ message }) {
  return (
    <div className="text-center py-12 text-light-400">
      <p className="text-sm">{message}</p>
    </div>
  );
}

// ── Main Dashboard ──────────────────────────────────────────────────

export default function TriageDashboard({ caseId, triageCase, stage, onRefresh }) {
  const [profile, setProfile] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [generating, setGenerating] = useState(false);

  const isRunning = stage?.status === 'running';
  const isCompleted = stage?.status === 'completed';
  const isFailed = stage?.status === 'failed';
  const isPending = stage?.status === 'pending';

  const loadProfile = useCallback(async () => {
    try {
      const data = await triageAPI.getProfile(caseId);
      if (data && !data.message) setProfile(data);
    } catch (err) {
      console.error('Failed to load profile:', err);
    }
  }, [caseId]);

  useEffect(() => {
    if (isCompleted) loadProfile();
  }, [isCompleted, loadProfile]);

  // Poll while generating
  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(loadProfile, 3000);
    return () => clearInterval(interval);
  }, [isRunning, loadProfile]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      await triageAPI.generateProfile(caseId);
      onRefresh();
    } catch (err) {
      alert(`Error generating profile: ${err.message}`);
    } finally {
      setGenerating(false);
    }
  };

  // Check prerequisites
  const scanComplete = triageCase?.stages?.some(s => s.type === 'scan' && s.status === 'completed');

  if (isPending || isFailed || isRunning) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="bg-white rounded-xl border border-light-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              {isRunning ? (
                <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
              ) : isFailed ? (
                <AlertCircle className="w-6 h-6 text-red-500" />
              ) : (
                <BarChart3 className="w-6 h-6 text-light-400" />
              )}
              <div>
                <h3 className="text-lg font-semibold text-owl-blue-900">
                  {isRunning ? 'Generating Profile...' : isFailed ? 'Profile Generation Failed' : 'Triage Dashboard'}
                </h3>
                <p className="text-sm text-light-500">
                  {isPending && !scanComplete
                    ? 'Complete the scan stage first'
                    : isRunning
                    ? 'Aggregating statistics and detecting artifacts...'
                    : isPending
                    ? 'Generate a comprehensive triage profile'
                    : ''}
                </p>
              </div>
            </div>
            {isPending && scanComplete && (
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 transition-colors"
              >
                {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Generate Profile
              </button>
            )}
            {isFailed && (
              <button
                onClick={handleGenerate}
                disabled={generating}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 transition-colors"
              >
                {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Retry
              </button>
            )}
          </div>
          {isFailed && stage?.error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-sm text-red-700">{stage.error}</p>
            </div>
          )}
          {isRunning && (
            <div className="h-2 bg-light-100 rounded-full overflow-hidden">
              <div className="h-full bg-owl-blue-500 rounded-full animate-pulse" style={{ width: '100%' }} />
            </div>
          )}
        </div>
      </div>
    );
  }

  // Profile complete - show tabbed dashboard
  return (
    <div className="p-6 max-w-5xl mx-auto space-y-4">
      {/* Tabs */}
      <div className="flex items-center gap-1 bg-white rounded-lg border border-light-200 p-1 overflow-x-auto">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors flex-shrink-0 ${
                activeTab === tab.key
                  ? 'bg-owl-blue-600 text-white'
                  : 'text-light-600 hover:bg-light-100'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      {activeTab === 'overview' && <OverviewTab profile={profile} />}
      {activeTab === 'categories' && <CategoriesTab profile={profile} />}
      {activeTab === 'classification' && <ClassificationTab profile={profile} />}
      {activeTab === 'timeline' && <TimelineTab caseId={caseId} />}
      {activeTab === 'users' && <UsersTab profile={profile} />}
      {activeTab === 'artifacts' && <ArtifactsTab caseId={caseId} />}
      {activeTab === 'mismatches' && <MismatchesTab caseId={caseId} />}
    </div>
  );
}
