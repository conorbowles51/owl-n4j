import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Sparkles,
  Loader2,
  Check,
  X,
  ChevronDown,
  ChevronUp,
  Brain,
  Shield,
  AlertTriangle,
  Eye,
  Lightbulb,
} from 'lucide-react';
import { graphAPI } from '../../services/api';

const CONFIDENCE_STYLES = {
  high: 'bg-emerald-100 text-emerald-700 border-emerald-300',
  medium: 'bg-amber-100 text-amber-700 border-amber-300',
  low: 'bg-red-100 text-red-700 border-red-300',
};

const CATEGORY_META = {
  inconsistency: { label: 'Inconsistency', icon: AlertTriangle, color: 'text-red-600 bg-red-50' },
  connection: { label: 'Connection', icon: Eye, color: 'text-blue-600 bg-blue-50' },
  defense_opportunity: { label: 'Defense', icon: Shield, color: 'text-emerald-600 bg-emerald-50' },
  brady_giglio: { label: 'Brady/Giglio', icon: Brain, color: 'text-purple-600 bg-purple-50' },
  pattern: { label: 'Pattern', icon: Lightbulb, color: 'text-amber-600 bg-amber-50' },
};

function InsightCard({ insight, onAccept, onReject, accepting, rejecting }) {
  const [expanded, setExpanded] = useState(false);
  const conf = CONFIDENCE_STYLES[insight.confidence] || CONFIDENCE_STYLES.medium;
  const cat = CATEGORY_META[insight.category] || CATEGORY_META.pattern;
  const CatIcon = cat.icon;

  return (
    <div className="border border-light-200 rounded-lg bg-white shadow-sm">
      <div className="px-3 py-2.5 space-y-2">
        <div className="flex items-start gap-2">
          <p className="flex-1 text-sm text-owl-blue-900 leading-snug">{insight.text}</p>
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-1.5 py-0.5 rounded border ${conf}`}>
            {insight.confidence}
          </span>
          <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-1.5 py-0.5 rounded ${cat.color}`}>
            <CatIcon className="w-3 h-3" />
            {cat.label}
          </span>
        </div>

        {insight.reasoning && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-light-500 hover:text-owl-blue-600 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            Reasoning
          </button>
        )}
        {expanded && insight.reasoning && (
          <p className="text-xs text-light-600 bg-light-50 rounded p-2 leading-relaxed">
            {insight.reasoning}
          </p>
        )}
      </div>

      <div className="flex border-t border-light-200 divide-x divide-light-200">
        <button
          onClick={onAccept}
          disabled={accepting || rejecting}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-medium text-emerald-600 hover:bg-emerald-50 transition-colors disabled:opacity-50"
        >
          {accepting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
          Accept
        </button>
        <button
          onClick={onReject}
          disabled={accepting || rejecting}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-medium text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
        >
          {rejecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
          Reject
        </button>
      </div>
    </div>
  );
}

export default function InsightsPanel({ caseId, authUsername }) {
  const [insights, setInsights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [actionInProgress, setActionInProgress] = useState(null);

  const fetchInsights = useCallback(async () => {
    if (!caseId) return;
    try {
      setLoading(true);
      setError(null);
      const data = await graphAPI.getCaseInsights(caseId);
      setInsights(data.insights || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    fetchInsights();
  }, [fetchInsights]);

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      setError(null);
      await graphAPI.generateInsights(caseId);
      await fetchInsights();
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleAccept = async (insight) => {
    const actionKey = `accept-${insight.entity_key}-${insight.insight_index}`;
    try {
      setActionInProgress(actionKey);
      await graphAPI.verifyInsight(
        insight.entity_key,
        insight.insight_index,
        authUsername || 'investigator',
        caseId,
      );
      await fetchInsights();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleReject = async (insight) => {
    const actionKey = `reject-${insight.entity_key}-${insight.insight_index}`;
    try {
      setActionInProgress(actionKey);
      await graphAPI.rejectInsight(insight.entity_key, insight.insight_index, caseId);
      await fetchInsights();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleBulkAcceptHigh = async () => {
    const highInsights = insights.filter((i) => i.confidence === 'high');
    if (highInsights.length === 0) return;
    setActionInProgress('bulk-accept');
    try {
      for (const insight of highInsights) {
        await graphAPI.verifyInsight(
          insight.entity_key,
          insight.insight_index,
          authUsername || 'investigator',
          caseId,
        );
      }
      await fetchInsights();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleBulkRejectLow = async () => {
    const lowInsights = [...insights].filter((i) => i.confidence === 'low');
    if (lowInsights.length === 0) return;
    setActionInProgress('bulk-reject');
    try {
      // Process in reverse order so indices don't shift
      const sorted = lowInsights.sort((a, b) => b.insight_index - a.insight_index);
      for (const insight of sorted) {
        await graphAPI.rejectInsight(insight.entity_key, insight.insight_index, caseId);
      }
      await fetchInsights();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionInProgress(null);
    }
  };

  const grouped = useMemo(() => {
    const map = {};
    for (const insight of insights) {
      const key = insight.entity_key;
      if (!map[key]) {
        map[key] = {
          entity_key: key,
          entity_name: insight.entity_name,
          entity_type: insight.entity_type,
          items: [],
        };
      }
      map[key].items.push(insight);
    }
    return Object.values(map);
  }, [insights]);

  const highCount = insights.filter((i) => i.confidence === 'high').length;
  const lowCount = insights.filter((i) => i.confidence === 'low').length;

  const TYPE_COLORS = {
    Person: 'bg-blue-500',
    Company: 'bg-emerald-500',
    Organisation: 'bg-purple-500',
    Bank: 'bg-amber-500',
    BankAccount: 'bg-rose-500',
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-light-200">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-owl-blue-600" />
            <h3 className="text-sm font-semibold text-owl-blue-900">AI Insights</h3>
            {insights.length > 0 && (
              <span className="text-xs text-light-500 bg-light-100 px-1.5 py-0.5 rounded-full">
                {insights.length}
              </span>
            )}
          </div>
          <button
            onClick={handleGenerate}
            disabled={generating || !!actionInProgress}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-owl-blue-600 rounded-lg hover:bg-owl-blue-700 transition-colors disabled:opacity-50"
          >
            {generating ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            {generating ? 'Generating...' : 'Generate'}
          </button>
        </div>

        {insights.length > 0 && (
          <div className="flex items-center gap-2">
            {highCount > 0 && (
              <button
                onClick={handleBulkAcceptHigh}
                disabled={!!actionInProgress}
                className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded hover:bg-emerald-100 transition-colors disabled:opacity-50"
              >
                <Check className="w-3 h-3" />
                Accept {highCount} High
              </button>
            )}
            {lowCount > 0 && (
              <button
                onClick={handleBulkRejectLow}
                disabled={!!actionInProgress}
                className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-red-600 bg-red-50 border border-red-200 rounded hover:bg-red-100 transition-colors disabled:opacity-50"
              >
                <X className="w-3 h-3" />
                Reject {lowCount} Low
              </button>
            )}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-auto px-4 py-3">
        {error && (
          <div className="mb-3 p-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg">
            {error}
          </div>
        )}

        {loading && !generating ? (
          <div className="flex flex-col items-center justify-center py-12 text-light-500">
            <Loader2 className="w-6 h-6 animate-spin mb-2" />
            <span className="text-sm">Loading insights...</span>
          </div>
        ) : generating ? (
          <div className="flex flex-col items-center justify-center py-12 text-owl-blue-600">
            <Loader2 className="w-6 h-6 animate-spin mb-2" />
            <span className="text-sm font-medium">Generating insights...</span>
            <span className="text-xs text-light-500 mt-1">Analyzing entities with AI</span>
          </div>
        ) : insights.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-light-500">
            <Brain className="w-8 h-8 mb-2 text-light-300" />
            <p className="text-sm font-medium">No pending insights</p>
            <p className="text-xs mt-1">Click Generate to analyze your case.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {grouped.map((group) => (
              <div key={group.entity_key}>
                <div className="flex items-center gap-2 mb-2">
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 ${TYPE_COLORS[group.entity_type] || 'bg-gray-400'}`} />
                  <span className="text-xs font-semibold text-owl-blue-800 truncate">
                    {group.entity_name}
                  </span>
                  <span className="text-[10px] text-light-500">{group.entity_type}</span>
                </div>
                <div className="space-y-2 ml-4">
                  {group.items.map((insight) => {
                    const acceptKey = `accept-${insight.entity_key}-${insight.insight_index}`;
                    const rejectKey = `reject-${insight.entity_key}-${insight.insight_index}`;
                    return (
                      <InsightCard
                        key={`${insight.entity_key}-${insight.insight_index}`}
                        insight={insight}
                        onAccept={() => handleAccept(insight)}
                        onReject={() => handleReject(insight)}
                        accepting={actionInProgress === acceptKey}
                        rejecting={actionInProgress === rejectKey}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
