import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Calendar, Focus, Edit2, Plus } from 'lucide-react';
import { workspaceAPI } from '../../services/api';
import DeadlineEditorModal from './DeadlineEditorModal';

/**
 * Case Deadlines Section
 * 
 * Displays case deadlines in the new format:
 * - Trial date with court info at top
 * - List of upcoming deadlines with days until
 * - Judge and court information
 */
export default function CaseDeadlinesSection({
  caseId,
  deadlines: externalDeadlines,
  onRefresh,
  isCollapsed,
  onToggle,
  onFocus,
}) {
  const [deadlineConfig, setDeadlineConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showEditor, setShowEditor] = useState(false);

  useEffect(() => {
    const loadDeadlines = async () => {
      if (!caseId) return;
      
      setLoading(true);
      try {
        const data = await workspaceAPI.getDeadlines(caseId);
        setDeadlineConfig(data);
      } catch (err) {
        console.error('Failed to load deadlines:', err);
        setDeadlineConfig({
          trial_date: null,
          trial_court: null,
          judge: null,
          court_division: null,
          deadlines: [],
        });
      } finally {
        setLoading(false);
      }
    };

    loadDeadlines();
  }, [caseId]);

  const handleSave = async (config) => {
    try {
      await workspaceAPI.updateDeadlines(caseId, config);
      setDeadlineConfig(config);
      if (onRefresh) {
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to save deadlines:', err);
      throw err;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return null;
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  const formatShortDate = (dateString) => {
    if (!dateString) return null;
    try {
      return new Date(dateString).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  const getDaysUntil = (dateString) => {
    if (!dateString) return null;
    try {
      const dueDate = new Date(dateString);
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      dueDate.setHours(0, 0, 0, 0);
      const days = Math.ceil((dueDate - today) / (1000 * 60 * 60 * 24));
      return days;
    } catch {
      return null;
    }
  };

  const getUrgencyEmoji = (urgencyLevel, daysUntil) => {
    if (urgencyLevel === 'URGENT' || (daysUntil !== null && daysUntil <= 7)) {
      return '🔴';
    }
    if (urgencyLevel === 'HIGH' || (daysUntil !== null && daysUntil <= 30)) {
      return '🟡';
    }
    return '';
  };

  const getUrgencyText = (urgencyLevel, daysUntil) => {
    if (urgencyLevel === 'URGENT' || (daysUntil !== null && daysUntil <= 7)) {
      return 'URGENT';
    }
    if (urgencyLevel === 'HIGH' || (daysUntil !== null && daysUntil <= 30)) {
      return 'HIGH';
    }
    return '';
  };

  const config = deadlineConfig || {
    trial_date: null,
    trial_court: null,
    judge: null,
    court_division: null,
    deadlines: [],
  };

  const deadlineItems = config.deadlines || [];
  const sortedDeadlines = [...deadlineItems]
    .filter(d => !d.completed)
    .sort((a, b) => {
      const dateA = a.due_date ? new Date(a.due_date).getTime() : 0;
      const dateB = b.due_date ? new Date(b.due_date).getTime() : 0;
      return dateA - dateB;
    });

  const deadlineCount = sortedDeadlines.length;

  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={(e) => onToggle && onToggle(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900">
          Case Deadlines ({deadlineCount})
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowEditor(true);
            }}
            className="p-1 hover:bg-light-100 rounded"
            title="Edit deadlines"
          >
            <Edit2 className="w-4 h-4 text-owl-blue-600" />
          </button>
          {onFocus && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onFocus(e);
              }}
              className="p-1 hover:bg-light-100 rounded"
              title="Focus on this section"
            >
              <Focus className="w-4 h-4 text-owl-blue-600" />
            </button>
          )}
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4 text-light-600" />
          ) : (
            <ChevronDown className="w-4 h-4 text-light-600" />
          )}
        </div>
      </div>

      {!isCollapsed && (
        <div className="px-4 pb-4 space-y-4">
          {loading ? (
            <p className="text-xs text-light-500">Loading deadlines...</p>
          ) : (
            <>
              {/* Trial Date Section */}
              {config.trial_date && (
                <div className="text-sm text-owl-blue-900 font-medium">
                  <span className="text-base">🔴</span> TRIAL DATE: {formatDate(config.trial_date)}
                  {config.trial_court && ` | ${config.trial_court}`}
                </div>
              )}

              {/* Upcoming Deadlines */}
              {sortedDeadlines.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-owl-blue-900 flex items-center gap-2">
                    <span className="text-base">📅</span>
                    Upcoming Deadlines:
                  </h4>
                  <div className="space-y-1 text-xs text-light-700">
                    {sortedDeadlines.map((deadline) => {
                      const daysUntil = getDaysUntil(deadline.due_date);
                      const urgencyEmoji = getUrgencyEmoji(deadline.urgency_level, daysUntil);
                      const urgencyText = getUrgencyText(deadline.urgency_level, daysUntil);
                      const isPastDue = daysUntil !== null && daysUntil < 0;
                      
                      return (
                        <div
                          key={deadline.deadline_id || deadline.title}
                          className={isPastDue ? 'text-red-600' : ''}
                        >
                          {formatShortDate(deadline.due_date)}
                          {daysUntil !== null && (
                            <span className="text-light-600">
                              {' '}({isPastDue ? `${Math.abs(daysUntil)} days overdue` : `${daysUntil} days`})
                            </span>
                          )}
                          {' — '}
                          {deadline.title}
                          {urgencyEmoji && urgencyText && (
                            <span className="ml-1">
                              {urgencyEmoji} {urgencyText}
                            </span>
                          )}
                        </div>
                      );
                    })}
                    
                    {/* Trial Date in Deadlines List */}
                    {config.trial_date && (
                      <div className="text-light-700 font-medium pt-1">
                        {formatShortDate(config.trial_date)}
                        {(() => {
                          const daysUntil = getDaysUntil(config.trial_date);
                          return daysUntil !== null ? ` (${daysUntil} days)` : '';
                        })()}
                        {' — TRIAL BEGINS'}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {sortedDeadlines.length === 0 && !config.trial_date && (
                <p className="text-xs text-light-500 italic">
                  No deadlines set. Click the edit button to add deadlines.
                </p>
              )}

              {/* Judge and Court Info */}
              {(config.judge || config.court_division) && (
                <div className="text-xs text-light-600 pt-2 border-t border-light-200">
                  {config.judge && (
                    <span>
                      Judge: {config.judge}
                    </span>
                  )}
                  {(config.judge && (config.trial_court || config.court_division)) && ' | '}
                  {(config.trial_court || config.court_division) && (
                    <span>
                      Court: {config.trial_court && `${config.trial_court}`}
                      {config.trial_court && config.court_division && ', '}
                      {config.court_division}
                    </span>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {showEditor && (
        <DeadlineEditorModal
          isOpen={showEditor}
          onClose={() => setShowEditor(false)}
          caseId={caseId}
          deadlineConfig={config}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
