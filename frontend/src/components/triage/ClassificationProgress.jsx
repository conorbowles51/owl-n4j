import React, { useState, useEffect, useCallback } from 'react';
import {
  Play, Loader2, CheckCircle2, AlertCircle,
  Shield, ShieldCheck, ShieldAlert, ShieldQuestion,
  FileSearch, FolderTree, Upload, Database,
} from 'lucide-react';
import { triageAPI } from '../../services/api';

const CLASSIFICATION_COLORS = {
  known_good: '#10b981',
  known_bad: '#ef4444',
  suspicious: '#f59e0b',
  custom_match: '#8b5cf6',
  unknown: '#9ca3af',
};

function ClassificationPieChart({ stats }) {
  const total = (stats.known_good || 0) + (stats.known_bad || 0) +
    (stats.suspicious || 0) + (stats.custom_match || 0) + (stats.unknown || 0);
  if (total === 0) return null;

  const segments = [
    { key: 'known_good', label: 'Known Good (NSRL)', count: stats.known_good || 0, color: CLASSIFICATION_COLORS.known_good },
    { key: 'known_bad', label: 'Known Bad', count: stats.known_bad || 0, color: CLASSIFICATION_COLORS.known_bad },
    { key: 'suspicious', label: 'Suspicious', count: stats.suspicious || 0, color: CLASSIFICATION_COLORS.suspicious },
    { key: 'custom_match', label: 'Custom Match', count: stats.custom_match || 0, color: CLASSIFICATION_COLORS.custom_match },
    { key: 'unknown', label: 'Unknown', count: stats.unknown || 0, color: CLASSIFICATION_COLORS.unknown },
  ].filter(s => s.count > 0);

  // Build SVG donut chart
  const size = 160;
  const cx = size / 2;
  const cy = size / 2;
  const radius = 60;
  const strokeWidth = 24;
  const circumference = 2 * Math.PI * radius;
  let cumulative = 0;

  return (
    <div className="flex items-center gap-6">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {segments.map((seg) => {
          const pct = seg.count / total;
          const dashLen = pct * circumference;
          const dashOffset = -cumulative * circumference;
          cumulative += pct;
          return (
            <circle
              key={seg.key}
              cx={cx}
              cy={cy}
              r={radius}
              fill="none"
              stroke={seg.color}
              strokeWidth={strokeWidth}
              strokeDasharray={`${dashLen} ${circumference - dashLen}`}
              strokeDashoffset={dashOffset}
              transform={`rotate(-90 ${cx} ${cy})`}
            />
          );
        })}
        <text x={cx} y={cy - 6} textAnchor="middle" className="fill-owl-blue-900 text-2xl font-bold">
          {total.toLocaleString()}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" className="fill-light-500 text-xs">
          unique hashes
        </text>
      </svg>
      <div className="space-y-1.5">
        {segments.map((seg) => (
          <div key={seg.key} className="flex items-center gap-2 text-sm">
            <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: seg.color }} />
            <span className="text-light-700">{seg.label}</span>
            <span className="text-light-400 ml-auto">{seg.count.toLocaleString()} ({(seg.count / total * 100).toFixed(1)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ClassificationProgress({ caseId, triageCase, stage, onRefresh }) {
  const [stats, setStats] = useState(null);
  const [classifying, setClassifying] = useState(false);
  const [showHashUpload, setShowHashUpload] = useState(false);

  const isRunning = stage?.status === 'running';
  const isCompleted = stage?.status === 'completed';
  const isFailed = stage?.status === 'failed';
  const isPending = stage?.status === 'pending';

  const loadStats = useCallback(async () => {
    if (!isCompleted && !isRunning) return;
    try {
      const data = await triageAPI.getClassification(caseId);
      setStats(data);
    } catch (err) {
      console.error('Failed to load classification stats:', err);
    }
  }, [caseId, isCompleted, isRunning]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  // Poll while classifying
  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(loadStats, 3000);
    return () => clearInterval(interval);
  }, [isRunning, loadStats]);

  const handleStartClassify = async () => {
    setClassifying(true);
    try {
      await triageAPI.startClassification(caseId);
      onRefresh();
    } catch (err) {
      alert(`Error starting classification: ${err.message}`);
    } finally {
      setClassifying(false);
    }
  };

  // Check if scan is complete (required for classification)
  const scanComplete = triageCase?.stages?.some(s => s.type === 'scan' && s.status === 'completed');

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Status header */}
      <div className="bg-white rounded-xl border border-light-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            {isRunning ? (
              <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
            ) : isCompleted ? (
              <CheckCircle2 className="w-6 h-6 text-green-500" />
            ) : isFailed ? (
              <AlertCircle className="w-6 h-6 text-red-500" />
            ) : (
              <Shield className="w-6 h-6 text-light-400" />
            )}
            <div>
              <h3 className="text-lg font-semibold text-owl-blue-900">
                {isRunning ? 'Classifying...' : isCompleted ? 'Classification Complete' : isFailed ? 'Classification Failed' : 'Ready to Classify'}
              </h3>
              <p className="text-sm text-light-500">
                {isPending && !scanComplete
                  ? 'Complete the scan stage first'
                  : isRunning
                  ? 'Checking file hashes against known databases...'
                  : isCompleted
                  ? 'Files classified by hash and path analysis'
                  : isPending
                  ? 'Hash lookup + path-based file classification'
                  : ''}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isPending && scanComplete && (
              <button
                onClick={handleStartClassify}
                disabled={classifying}
                className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 transition-colors"
              >
                {classifying ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Start Classification
              </button>
            )}
            {isFailed && (
              <button
                onClick={handleStartClassify}
                disabled={classifying}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 transition-colors"
              >
                {classifying ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Retry Classification
              </button>
            )}
          </div>
        </div>

        {/* Error message */}
        {isFailed && stage?.error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
            <p className="text-sm text-red-700">{stage.error}</p>
          </div>
        )}

        {/* Running progress */}
        {isRunning && (
          <div className="mb-4">
            <div className="h-2 bg-light-100 rounded-full overflow-hidden">
              <div className="h-full bg-owl-blue-500 rounded-full transition-all duration-500 animate-pulse" style={{ width: '100%' }} />
            </div>
            <p className="text-xs text-light-500 mt-1">Performing hash lookups and path analysis...</p>
          </div>
        )}

        {/* Classification pipeline steps */}
        {(isRunning || isCompleted) && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <div className="flex items-center gap-2 bg-light-50 rounded-lg p-3">
              <Database className="w-4 h-4 text-green-500" />
              <div>
                <p className="text-xs text-light-500">NSRL (CIRCL)</p>
                <p className="text-sm font-semibold text-owl-blue-900">{(stats?.known_good || 0).toLocaleString()}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 bg-light-50 rounded-lg p-3">
              <ShieldAlert className="w-4 h-4 text-red-500" />
              <div>
                <p className="text-xs text-light-500">Known Bad</p>
                <p className="text-sm font-semibold text-owl-blue-900">{(stats?.known_bad || 0).toLocaleString()}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 bg-light-50 rounded-lg p-3">
              <ShieldQuestion className="w-4 h-4 text-amber-500" />
              <div>
                <p className="text-xs text-light-500">Suspicious</p>
                <p className="text-sm font-semibold text-owl-blue-900">{(stats?.suspicious || 0).toLocaleString()}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 bg-light-50 rounded-lg p-3">
              <ShieldCheck className="w-4 h-4 text-purple-500" />
              <div>
                <p className="text-xs text-light-500">Custom Match</p>
                <p className="text-sm font-semibold text-owl-blue-900">{(stats?.custom_match || 0).toLocaleString()}</p>
              </div>
            </div>
          </div>
        )}

        {/* Summary stats */}
        {isCompleted && stats && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{(stats.total_classified || 0).toLocaleString()}</p>
              <p className="text-xs text-light-500">Files Classified</p>
            </div>
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{(stats.system_files || 0).toLocaleString()}</p>
              <p className="text-xs text-light-500">System Files</p>
            </div>
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{(stats.user_files || 0).toLocaleString()}</p>
              <p className="text-xs text-light-500">User Files</p>
            </div>
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{(stats.user_accounts || []).length}</p>
              <p className="text-xs text-light-500">User Accounts</p>
            </div>
          </div>
        )}
      </div>

      {/* Donut chart */}
      {isCompleted && stats && (
        <div className="bg-white rounded-xl border border-light-200 p-6">
          <h4 className="text-sm font-medium text-light-700 mb-4">Hash Classification Distribution</h4>
          <ClassificationPieChart stats={stats} />
        </div>
      )}

      {/* User accounts */}
      {isCompleted && stats && (stats.user_accounts || []).length > 0 && (
        <div className="bg-white rounded-xl border border-light-200 p-6">
          <h4 className="text-sm font-medium text-light-700 mb-3">Detected User Accounts</h4>
          <div className="flex flex-wrap gap-2">
            {stats.user_accounts.map((account) => (
              <span
                key={account}
                className="inline-flex items-center gap-1.5 px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-sm"
              >
                <FolderTree className="w-3.5 h-3.5" />
                {account}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Hash set management */}
      {(isPending || isCompleted) && (
        <div className="bg-white rounded-xl border border-light-200 p-6">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium text-light-700">Custom Hash Sets</h4>
            <button
              onClick={() => setShowHashUpload(!showHashUpload)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-owl-blue-600 hover:bg-owl-blue-50 rounded-lg transition-colors"
            >
              <Upload className="w-3.5 h-3.5" />
              Upload Hash Set
            </button>
          </div>
          {showHashUpload && (
            <HashSetUploadInline caseId={caseId} onUploaded={() => setShowHashUpload(false)} />
          )}
        </div>
      )}
    </div>
  );
}

function HashSetUploadInline({ caseId, onUploaded }) {
  const [name, setName] = useState('');
  const [hashText, setHashText] = useState('');
  const [uploading, setUploading] = useState(false);

  const handleUpload = async () => {
    if (!name.trim() || !hashText.trim()) return;
    setUploading(true);
    try {
      const hashes = hashText.split('\n').map(h => h.trim()).filter(Boolean);
      const result = await triageAPI.uploadHashSet(caseId, { name: name.trim(), hashes });
      alert(`Uploaded ${result.valid_hashes} valid hashes as "${name}"`);
      onUploaded();
    } catch (err) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="border border-light-200 rounded-lg p-4 space-y-3">
      <input
        type="text"
        placeholder="Hash set name (e.g., known_csam, project_hashes)"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full px-3 py-2 border border-light-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-owl-blue-300"
      />
      <textarea
        placeholder="Paste SHA-256 hashes, one per line..."
        value={hashText}
        onChange={(e) => setHashText(e.target.value)}
        rows={6}
        className="w-full px-3 py-2 border border-light-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-owl-blue-300 resize-y"
      />
      <div className="flex justify-end gap-2">
        <button
          onClick={onUploaded}
          className="px-3 py-1.5 text-sm text-light-600 hover:text-light-800"
        >
          Cancel
        </button>
        <button
          onClick={handleUpload}
          disabled={uploading || !name.trim() || !hashText.trim()}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-owl-blue-600 text-white rounded-lg text-sm hover:bg-owl-blue-700 disabled:opacity-50"
        >
          {uploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
          Upload
        </button>
      </div>
    </div>
  );
}
