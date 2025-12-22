import React, { useState, useMemo } from 'react';
import { 
  X, User, Building2, Wallet, MapPin, FileText, ArrowRight, ArrowLeft,
  CheckCircle2, AlertTriangle, ExternalLink, Quote, ChevronDown, ChevronUp,
  Star, CheckSquare, UserCheck
} from 'lucide-react';
import { graphAPI } from '../services/api';

/**
 * Icon mapping for entity types
 */
const TYPE_ICONS = {
  Person: User,
  Company: Building2,
  Account: Wallet,
  Location: MapPin,
  Document: FileText,
};

/**
 * Confidence level styling
 */
const CONFIDENCE_STYLES = {
  high: {
    bg: 'bg-green-50',
    border: 'border-green-200',
    text: 'text-green-700',
    badge: 'bg-green-100 text-green-800',
  },
  medium: {
    bg: 'bg-yellow-50',
    border: 'border-yellow-200',
    text: 'text-yellow-700',
    badge: 'bg-yellow-100 text-yellow-800',
  },
  low: {
    bg: 'bg-orange-50',
    border: 'border-orange-200',
    text: 'text-orange-700',
    badge: 'bg-orange-100 text-orange-800',
  },
};

/**
 * Importance level styling
 */
const IMPORTANCE_STYLES = {
  5: { label: 'Critical', color: 'text-red-600', bg: 'bg-red-50' },
  4: { label: 'High', color: 'text-orange-600', bg: 'bg-orange-50' },
  3: { label: 'Medium', color: 'text-yellow-600', bg: 'bg-yellow-50' },
  2: { label: 'Low', color: 'text-blue-600', bg: 'bg-blue-50' },
  1: { label: 'Minimal', color: 'text-gray-500', bg: 'bg-gray-50' },
};

const DEFAULT_VISIBLE_COUNT = 5;

/**
 * Get icon for entity type
 */
function getTypeIcon(type) {
  return TYPE_ICONS[type] || FileText;
}

/**
 * Citation Link Component
 * Renders a clickable link to view the source document
 */
function CitationLink({ sourceDoc, page, onViewDocument }) {
  if (!sourceDoc) return null;

  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (onViewDocument) {
      onViewDocument(sourceDoc, page);
    }
  };

  return (
    <button
      onClick={handleClick}
      className="inline-flex items-center gap-1 text-xs text-owl-blue-600 hover:text-owl-blue-800 hover:underline transition-colors"
      title={`View source: ${sourceDoc}${page ? `, page ${page}` : ''}`}
    >
      <ExternalLink className="w-3 h-3" />
      <span>{sourceDoc}{page ? `, p.${page}` : ''}</span>
    </button>
  );
}

/**
 * Verified Fact Item Component
 */
function VerifiedFactItem({ fact, index, nodeKey, onViewDocument, onPinToggle, isPinning }) {
  const importance = fact.importance || 3;
  const importanceStyle = IMPORTANCE_STYLES[importance] || IMPORTANCE_STYLES[3];
  const isPinned = fact.pinned || false;
  const isVerifiedByUser = !!fact.verified_by;

  const handlePinClick = async (e) => {
    e.stopPropagation();
    if (onPinToggle) {
      onPinToggle(index, !isPinned);
    }
  };

  return (
    <div className={`p-3 rounded-lg border ${isPinned ? 'bg-amber-50/50 border-amber-200' : 'bg-green-50/50 border-green-100'}`}>
      <div className="flex items-start gap-2">
        <div className="flex flex-col items-center gap-1">
          <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0" />
          <button
            onClick={handlePinClick}
            disabled={isPinning}
            className={`p-0.5 rounded transition-colors ${
              isPinned 
                ? 'text-amber-500 hover:text-amber-600' 
                : 'text-light-400 hover:text-amber-500'
            } ${isPinning ? 'opacity-50 cursor-not-allowed' : ''}`}
            title={isPinned ? 'Unpin fact' : 'Pin fact'}
          >
            <Star className={`w-3.5 h-3.5 ${isPinned ? 'fill-current' : ''}`} />
          </button>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            {/* <span className={`text-xs px-1.5 py-0.5 rounded ${importanceStyle.bg} ${importanceStyle.color} font-medium`}>
              {importanceStyle.label}
            </span> */}
            {isVerifiedByUser && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 font-medium inline-flex items-center gap-1">
                <UserCheck className="w-3 h-3" />
                Verified by {fact.verified_by}
              </span>
            )}
          </div>
          <p className="text-sm text-light-800 leading-relaxed">
            {fact.text}
          </p>
          {fact.quote && (
            <div className="mt-2 flex items-start gap-1.5 text-xs text-light-600 italic">
              <Quote className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span className="line-clamp-2">"{fact.quote}"</span>
            </div>
          )}
          {/* Show original insight info if this was converted from an AI insight */}
          {fact.original_confidence && (
            <div className="mt-1.5 text-xs text-light-500">
              <span className="font-medium">Originally AI insight:</span> {fact.original_confidence} confidence
              {fact.original_reasoning && ` - ${fact.original_reasoning}`}
            </div>
          )}
          <div className="mt-2">
            <CitationLink 
              sourceDoc={fact.source_doc} 
              page={fact.page}
              onViewDocument={onViewDocument}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * AI Insight Item Component
 */
function AIInsightItem({ insight, index, nodeKey, username, onVerify, isVerifying }) {
  const [showVerifyForm, setShowVerifyForm] = useState(false);
  const [sourceDoc, setSourceDoc] = useState('');
  const [page, setPage] = useState('');

  const confidence = insight.confidence || 'medium';
  const styles = CONFIDENCE_STYLES[confidence] || CONFIDENCE_STYLES.medium;

  const handleVerifyClick = async () => {
    if (!showVerifyForm) {
      setShowVerifyForm(true);
      return;
    }
    
    if (onVerify) {
      await onVerify(index, sourceDoc || null, page ? parseInt(page, 10) : null);
      setShowVerifyForm(false);
      setSourceDoc('');
      setPage('');
    }
  };

  const handleCancel = () => {
    setShowVerifyForm(false);
    setSourceDoc('');
    setPage('');
  };

  return (
    <div className={`p-3 ${styles.bg} rounded-lg border ${styles.border}`}>
      <div className="flex items-start gap-2">
        <AlertTriangle className={`w-4 h-4 ${styles.text} mt-0.5 flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs px-1.5 py-0.5 rounded ${styles.badge} uppercase font-medium`}>
              {confidence} confidence
            </span>
          </div>
          <p className="text-sm text-light-800 leading-relaxed">
            {insight.text}
          </p>
          {insight.reasoning && (
            <p className="mt-1.5 text-xs text-light-600">
              <span className="font-medium">Reasoning:</span> {insight.reasoning}
            </p>
          )}
          
          {/* Verify controls */}
          <div className="mt-3 pt-2 border-t border-light-200/50">
            {!showVerifyForm ? (
              <button
                onClick={handleVerifyClick}
                disabled={isVerifying}
                className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded bg-white border border-light-300 text-light-700 hover:bg-light-50 hover:border-light-400 transition-colors disabled:opacity-50"
              >
                <CheckSquare className="w-3.5 h-3.5" />
                Mark as Verified
              </button>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-light-600">Optional: Add source reference</p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={sourceDoc}
                    onChange={(e) => setSourceDoc(e.target.value)}
                    placeholder="Source document"
                    className="flex-1 text-xs px-2 py-1 rounded border border-light-300 focus:outline-none focus:ring-1 focus:ring-owl-blue-500"
                  />
                  <input
                    type="number"
                    value={page}
                    onChange={(e) => setPage(e.target.value)}
                    placeholder="Page"
                    className="w-16 text-xs px-2 py-1 rounded border border-light-300 focus:outline-none focus:ring-1 focus:ring-owl-blue-500"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleVerifyClick}
                    disabled={isVerifying}
                    className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded bg-green-600 text-white hover:bg-green-700 transition-colors disabled:opacity-50"
                  >
                    <CheckSquare className="w-3.5 h-3.5" />
                    {isVerifying ? 'Verifying...' : 'Confirm Verification'}
                  </button>
                  <button
                    onClick={handleCancel}
                    disabled={isVerifying}
                    className="text-xs px-2 py-1 rounded border border-light-300 text-light-600 hover:bg-light-50 transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Collapsible Section Component
 */
function CollapsibleSection({ title, icon: Icon, iconColor, count, children, defaultExpanded = true, emptyMessage }) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [showAll, setShowAll] = useState(false);

  const items = React.Children.toArray(children);
  const visibleItems = showAll ? items : items.slice(0, DEFAULT_VISIBLE_COUNT);
  const hasMore = items.length > DEFAULT_VISIBLE_COUNT;

  if (items.length === 0 && emptyMessage) {
    return (
      <div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full flex items-center justify-between text-left group"
        >
          <label className={`text-xs font-medium ${iconColor} uppercase tracking-wide flex items-center gap-1.5 cursor-pointer`}>
            <Icon className="w-3.5 h-3.5" />
            {title} (0)
          </label>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-light-500 group-hover:text-light-700" />
          ) : (
            <ChevronDown className="w-4 h-4 text-light-500 group-hover:text-light-700" />
          )}
        </button>
        {isExpanded && (
          <p className="mt-2 text-xs text-light-500 italic">{emptyMessage}</p>
        )}
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between text-left group"
      >
        <label className={`text-xs font-medium ${iconColor} uppercase tracking-wide flex items-center gap-1.5 cursor-pointer`}>
          <Icon className="w-3.5 h-3.5" />
          {title} ({count || items.length})
        </label>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-light-500 group-hover:text-light-700" />
        ) : (
          <ChevronDown className="w-4 h-4 text-light-500 group-hover:text-light-700" />
        )}
      </button>
      
      {isExpanded && (
        <>
          <div className="mt-2 space-y-2">
            {visibleItems}
          </div>
          
          {hasMore && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="mt-2 text-xs text-owl-blue-600 hover:text-owl-blue-800 hover:underline"
            >
              {showAll ? 'Show less' : `Show all ${items.length}...`}
            </button>
          )}
        </>
      )}
    </div>
  );
}

/**
 * NodeDetails Component
 * 
 * Displays detailed information about a selected node with:
 * - Summary (factual only)
 * - Verified Facts (with source citations, collapsible, sortable)
 * - AI Insights (clearly labeled as inferences, with verify option)
 * - Connections
 * - Properties
 */
export default function NodeDetails({ 
  node, 
  onClose, 
  onSelectNode, 
  onViewDocument,
  onNodeUpdate,
  username,
  compact = false 
}) {
  const [isPinning, setIsPinning] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [localFacts, setLocalFacts] = useState(null);
  const [localInsights, setLocalInsights] = useState(null);

  if (!node) return null;

  const Icon = getTypeIcon(node.type);

  const containerClass = compact 
    ? 'w-full bg-white/50 flex flex-col'
    : 'w-80 bg-white border-l border-light-200 h-full flex flex-col';
  const headerPadding = compact ? 'p-3' : 'p-4';
  const iconSize = compact ? 'w-4 h-4' : 'w-5 h-5';
  const titleSize = compact ? 'text-sm font-semibold' : 'font-semibold';
  const contentClass = compact 
    ? 'p-3 space-y-3'
    : 'flex-1 overflow-y-auto p-4 space-y-4';

  // Use local state if available, otherwise use node data
  const verifiedFacts = localFacts !== null ? localFacts : (node.verified_facts || []);
  const aiInsights = localInsights !== null ? localInsights : (node.ai_insights || []);
  
  // Check if we have the new structured data or legacy notes
  const hasStructuredData = verifiedFacts.length > 0 || aiInsights.length > 0;

  // Sort facts: pinned first, then by importance (descending)
  const sortedFacts = useMemo(() => {
    return [...verifiedFacts].sort((a, b) => {
      // Pinned items first
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      // Then by importance (higher first)
      const importanceA = a.importance || 3;
      const importanceB = b.importance || 3;
      return importanceB - importanceA;
    });
  }, [verifiedFacts]);

  // Handle pin toggle
  const handlePinToggle = async (factIndex, pinned) => {
    setIsPinning(true);
    try {
      // Find the original index in the unsorted array
      const originalFact = sortedFacts[factIndex];
      const originalIndex = verifiedFacts.findIndex(f => f === originalFact);
      
      const result = await graphAPI.pinFact(node.key, originalIndex, pinned);
      if (result.success) {
        setLocalFacts(result.verified_facts);
        if (onNodeUpdate) {
          onNodeUpdate({ ...node, verified_facts: result.verified_facts });
        }
      }
    } catch (err) {
      console.error('Failed to toggle pin:', err);
    } finally {
      setIsPinning(false);
    }
  };

  // Handle verify insight
  const handleVerifyInsight = async (insightIndex, sourceDoc, page) => {
    if (!username) {
      alert('You must be logged in to verify insights.');
      return;
    }
    
    setIsVerifying(true);
    try {
      const result = await graphAPI.verifyInsight(node.key, insightIndex, username, sourceDoc, page);
      if (result.success) {
        setLocalFacts(result.verified_facts);
        setLocalInsights(result.ai_insights);
        if (onNodeUpdate) {
          onNodeUpdate({ 
            ...node, 
            verified_facts: result.verified_facts,
            ai_insights: result.ai_insights 
          });
        }
      }
    } catch (err) {
      console.error('Failed to verify insight:', err);
      alert('Failed to verify insight: ' + err.message);
    } finally {
      setIsVerifying(false);
    }
  };

  // Reset local state when node changes
  React.useEffect(() => {
    setLocalFacts(null);
    setLocalInsights(null);
  }, [node.key]);

  return (
    <div className={containerClass}>
      {/* Header */}
      <div className={`${headerPadding} border-b border-light-200 flex items-start justify-between`}>
        <div className="flex items-start gap-3">
          <div className="p-2 bg-owl-blue-100 rounded-lg">
            <Icon className={`${iconSize} text-owl-blue-700`} />
          </div>
          <div>
            <h2 className={`${titleSize} text-owl-blue-900`}>{node.name}</h2>
            <span className="text-xs text-light-600 bg-light-100 px-2 py-0.5 rounded">
              {node.type}
            </span>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-4 h-4 text-light-600" />
          </button>
        )}
      </div>

      {/* Content */}
      <div className={contentClass}>
        {/* Key */}
        <div>
          <label className="text-xs font-medium text-light-600 uppercase tracking-wide">
            Key
          </label>
          <p className="text-sm text-light-800 font-mono mt-1">{node.key}</p>
        </div>

        {/* Summary */}
        {node.summary && (
          <div>
            <label className="text-xs font-medium text-light-600 uppercase tracking-wide">
              Summary
            </label>
            <p className="text-sm text-light-800 mt-1 leading-relaxed">
              {node.summary}
            </p>
          </div>
        )}

        {/* Verified Facts Section */}
        <CollapsibleSection
          title="Verified Facts"
          icon={CheckCircle2}
          iconColor="text-green-700"
          count={sortedFacts.length}
          defaultExpanded={true}
          emptyMessage="No verified facts yet."
        >
          {sortedFacts.map((fact, idx) => (
            <VerifiedFactItem 
              key={idx} 
              fact={fact}
              index={idx}
              nodeKey={node.key}
              onViewDocument={onViewDocument}
              onPinToggle={handlePinToggle}
              isPinning={isPinning}
            />
          ))}
        </CollapsibleSection>

        {/* AI Insights Section */}
        <CollapsibleSection
          title="AI Insights - Unverified"
          icon={AlertTriangle}
          iconColor="text-orange-700"
          count={aiInsights.length}
          defaultExpanded={aiInsights.length > 0}
          emptyMessage="No AI insights."
        >
          {aiInsights.length > 0 && (
            <p className="text-xs text-light-500 mb-2">
              These are inferences drawn by AI. Click "Mark as Verified" to confirm after investigation.
            </p>
          )}
          {aiInsights.map((insight, idx) => (
            <AIInsightItem 
              key={idx} 
              insight={insight}
              index={idx}
              nodeKey={node.key}
              username={username}
              onVerify={handleVerifyInsight}
              isVerifying={isVerifying}
            />
          ))}
        </CollapsibleSection>

        {/* Legacy Notes (for backwards compatibility with old data) */}
        {!hasStructuredData && node.notes && (
          <div>
            <label className="text-xs font-medium text-light-600 uppercase tracking-wide">
              Document Notes
            </label>
            <div className="mt-1 text-sm text-light-700 bg-light-50 rounded-lg p-3 max-h-48 overflow-y-auto whitespace-pre-wrap font-mono text-xs border border-light-200">
              {node.notes}
            </div>
          </div>
        )}

        {/* Connections */}
        {node.connections && node.connections.length > 0 && (
          <CollapsibleSection
            title="Connections"
            icon={ArrowRight}
            iconColor="text-light-600"
            count={node.connections.length}
            defaultExpanded={true}
          >
            {node.connections.map((conn, idx) => (
              <button
                key={idx}
                onClick={() => onSelectNode?.(conn.key)}
                className="w-full text-left p-2 bg-light-50 hover:bg-light-100 rounded-lg transition-colors group border border-light-200"
              >
                <div className="flex items-center gap-2">
                  {conn.direction === 'outgoing' ? (
                    <ArrowRight className="w-4 h-4 text-owl-purple-500" />
                  ) : (
                    <ArrowLeft className="w-4 h-4 text-owl-purple-500" />
                  )}
                  <span className="text-xs text-owl-purple-600 font-mono">
                    {conn.relationship}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <span className="text-sm text-light-800 group-hover:text-owl-blue-900">
                    {conn.name}
                  </span>
                  <span className="text-xs text-light-600">
                    {conn.type}
                  </span>
                </div>
              </button>
            ))}
          </CollapsibleSection>
        )}

        {/* Properties */}
        {node.properties && Object.keys(node.properties).length > 0 && (
          <div>
            <label className="text-xs font-medium text-light-600 uppercase tracking-wide">
              Properties
            </label>
            <div className="mt-2 space-y-1">
              {Object.entries(node.properties)
                .filter(([key]) => !['id', 'key', 'name', 'summary', 'notes', 'type', 'verified_facts', 'ai_insights'].includes(key))
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between text-sm">
                    <span className="text-light-600">{key}</span>
                    <span className="text-light-800 font-mono text-xs">
                      {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
