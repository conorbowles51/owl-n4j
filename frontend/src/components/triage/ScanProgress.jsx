import React, { useState, useEffect, useCallback } from 'react';
import {
  Play, RotateCcw, Loader2, CheckCircle2, AlertCircle,
  HardDrive, FileText, FolderOpen,
} from 'lucide-react';
import { triageAPI } from '../../services/api';

function formatSize(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

const CATEGORY_COLORS = {
  documents: '#3b82f6',
  images: '#8b5cf6',
  video: '#ec4899',
  audio: '#f59e0b',
  archives: '#6b7280',
  executables: '#ef4444',
  databases: '#10b981',
  emails: '#06b6d4',
  web: '#f97316',
  system: '#9ca3af',
  other: '#d1d5db',
};

function CategoryBar({ categories, totalFiles }) {
  if (!categories || totalFiles === 0) return null;

  const sorted = Object.entries(categories)
    .sort(([, a], [, b]) => b - a);

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium text-light-700">File Categories</h4>
      <div className="h-4 rounded-full overflow-hidden flex bg-light-100">
        {sorted.map(([cat, count]) => {
          const pct = (count / totalFiles) * 100;
          if (pct < 0.5) return null;
          return (
            <div
              key={cat}
              style={{ width: `${pct}%`, backgroundColor: CATEGORY_COLORS[cat] || '#d1d5db' }}
              className="h-full"
              title={`${cat}: ${count.toLocaleString()} (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-3">
        {sorted.map(([cat, count]) => (
          <div key={cat} className="flex items-center gap-1.5 text-xs text-light-600">
            <div
              className="w-2.5 h-2.5 rounded-sm"
              style={{ backgroundColor: CATEGORY_COLORS[cat] || '#d1d5db' }}
            />
            <span className="capitalize">{cat}</span>
            <span className="text-light-400">({count.toLocaleString()})</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ScanProgress({ caseId, triageCase, stage, onRefresh }) {
  const [stats, setStats] = useState(null);
  const [scanning, setScanning] = useState(false);

  const isRunning = stage?.status === 'running';
  const isCompleted = stage?.status === 'completed';
  const isFailed = stage?.status === 'failed';
  const isPending = stage?.status === 'pending';
  const scanStats = triageCase?.scan_stats || {};

  // Load stats when scan is complete
  const loadStats = useCallback(async () => {
    if (!isCompleted && !isRunning) return;
    try {
      const data = await triageAPI.getStats(caseId);
      setStats(data);
    } catch (err) {
      console.error('Failed to load scan stats:', err);
    }
  }, [caseId, isCompleted, isRunning]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  // Poll stats while scanning
  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(loadStats, 3000);
    return () => clearInterval(interval);
  }, [isRunning, loadStats]);

  const handleStartScan = async (resume = false) => {
    setScanning(true);
    try {
      await triageAPI.startScan(caseId, resume);
      onRefresh();
    } catch (err) {
      alert(`Error starting scan: ${err.message}`);
    } finally {
      setScanning(false);
    }
  };

  const displayStats = stats || scanStats;
  const totalFiles = displayStats.total_files || stage?.files_processed || 0;
  const totalSize = displayStats.total_size || 0;
  const categories = displayStats.by_category || {};

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
              <HardDrive className="w-6 h-6 text-light-400" />
            )}
            <div>
              <h3 className="text-lg font-semibold text-owl-blue-900">
                {isRunning ? 'Scanning...' : isCompleted ? 'Scan Complete' : isFailed ? 'Scan Failed' : 'Ready to Scan'}
              </h3>
              <p className="text-sm text-light-500">
                {triageCase?.source_path}
              </p>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {isPending && (
              <button
                onClick={() => handleStartScan(false)}
                disabled={scanning}
                className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 disabled:opacity-50 transition-colors"
              >
                {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Start Scan
              </button>
            )}
            {isFailed && (
              <button
                onClick={() => handleStartScan(true)}
                disabled={scanning}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 transition-colors"
              >
                {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
                Resume Scan
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

        {/* Progress bar */}
        {isRunning && (
          <div className="mb-4">
            <div className="flex justify-between text-sm text-light-600 mb-1">
              <span>Files scanned</span>
              <span>{totalFiles.toLocaleString()}</span>
            </div>
            <div className="h-2 bg-light-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-owl-blue-500 rounded-full transition-all duration-500"
                style={{ width: '100%' }}
              />
            </div>
          </div>
        )}

        {/* Summary stats */}
        {totalFiles > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{totalFiles.toLocaleString()}</p>
              <p className="text-xs text-light-500">Total Files</p>
            </div>
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{formatSize(totalSize)}</p>
              <p className="text-xs text-light-500">Total Size</p>
            </div>
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">{Object.keys(categories).length}</p>
              <p className="text-xs text-light-500">Categories</p>
            </div>
            <div className="bg-light-50 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold text-owl-blue-900">
                {displayStats.os_detected || scanStats.os_detected || '?'}
              </p>
              <p className="text-xs text-light-500">OS Detected</p>
            </div>
          </div>
        )}
      </div>

      {/* Category breakdown */}
      {totalFiles > 0 && (
        <div className="bg-white rounded-xl border border-light-200 p-6">
          <CategoryBar categories={categories} totalFiles={totalFiles} />
        </div>
      )}
    </div>
  );
}
