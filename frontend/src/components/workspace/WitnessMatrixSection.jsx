import React, { useState } from 'react';
import { ChevronDown, ChevronRight, ChevronUp, Plus, User, Focus, Link2, MessageSquare, Edit2, Trash2 } from 'lucide-react';
import { workspaceAPI } from '../../services/api';
import AttachToTheoryModal from './AttachToTheoryModal';
import WitnessInterviewModal from './WitnessInterviewModal';
import WitnessModal from './WitnessModal';

/**
 * Witness Matrix Section
 * 
 * Displays witnesses categorized by Friendly/Neutral/Adverse
 * Shows witness interviews with full details
 */
export default function WitnessMatrixSection({
  caseId,
  witnesses,
  onRefresh,
  isCollapsed,
  onToggle,
  onFocus,
}) {
  const [showAddModal, setShowAddModal] = useState(false);
  const [editWitnessModal, setEditWitnessModal] = useState({ open: false, witness: null });
  const [attachModal, setAttachModal] = useState({ open: false, witness: null });
  const [interviewModal, setInterviewModal] = useState({ open: false, witness: null, interview: null });
  const [expandedWitnessId, setExpandedWitnessId] = useState(null);

  const categorizeWitnesses = (witnesses) => {
    const categories = {
      FRIENDLY: [],
      NEUTRAL: [],
      ADVERSE: [],
    };
    witnesses.forEach(w => {
      const cat = w.category || 'NEUTRAL';
      if (categories[cat]) {
        categories[cat].push(w);
      }
    });
    return categories;
  };

  const categorized = categorizeWitnesses(witnesses);

  const getCredibilityColor = (rating) => {
    if (!rating) return 'text-light-600';
    if (rating >= 4) return 'text-green-600';
    if (rating >= 3) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getCredibilityStars = (rating) => {
    if (!rating) return '';
    return '⭐'.repeat(rating);
  };

  const getRiskEmoji = (risk) => {
    if (!risk) return '';
    if (risk.toLowerCase().includes('high') || risk.toLowerCase().includes('critical')) return '🔴';
    if (risk.toLowerCase().includes('medium') || risk.toLowerCase().includes('moderate')) return '🟡';
    if (risk.toLowerCase().includes('low')) return '🟢';
    return '🟡'; // Default to yellow
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
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

  const handleAttachToTheory = async (theory, itemType, itemId) => {
    if (!caseId || !theory) return;
    try {
      const existing = theory.attached_witness_ids || [];
      const ids = existing.includes(itemId) ? existing : [...existing, itemId];
      await workspaceAPI.updateTheory(caseId, theory.theory_id, {
        ...theory,
        attached_witness_ids: ids,
      });
    } catch (err) {
      console.error('Failed to attach witness to theory:', err);
      throw err;
    }
  };

  const handleDeleteInterview = async (witness, interviewId) => {
    if (!caseId || !witness || !confirm('Are you sure you want to delete this interview?')) return;
    
    try {
      const updatedInterviews = (witness.interviews || []).filter(
        (i) => i.interview_id !== interviewId
      );
      const updatedWitness = {
        ...witness,
        interviews: updatedInterviews,
      };
      await workspaceAPI.updateWitness(caseId, witness.witness_id, updatedWitness);
      if (onRefresh) {
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to delete interview:', err);
      alert('Failed to delete interview');
    }
  };

  return (
    <div className="border-b border-light-200">
      <div
        className="p-4 cursor-pointer hover:bg-light-50 transition-colors flex items-center justify-between"
        onClick={(e) => onToggle && onToggle(e)}
      >
        <h3 className="text-sm font-semibold text-owl-blue-900">
          Witness Matrix ({witnesses.length})
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowAddModal(true);
            }}
            className="p-1 hover:bg-light-100 rounded"
            title="Add Witness"
          >
            <Plus className="w-4 h-4 text-owl-blue-600" />
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
          {['FRIENDLY', 'NEUTRAL', 'ADVERSE'].map((category) => (
            <div key={category}>
              <h4 className="text-xs font-medium text-light-700 mb-2">
                {category} ({categorized[category].length})
              </h4>
              {categorized[category].length === 0 ? (
                <p className="text-xs text-light-500 italic">No witnesses in this category</p>
              ) : (
                <div className="space-y-2">
                  {categorized[category].map((witness) => {
                    const isExpanded = expandedWitnessId === witness.witness_id;
                    const interviews = witness.interviews || [];
                    const latestInterview = interviews.length > 0 
                      ? interviews.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0))[0]
                      : null;

                    return (
                      <div
                        key={witness.witness_id}
                        className="border border-light-200 rounded-lg bg-light-50 hover:bg-light-100 transition-colors"
                      >
                        {/* Witness Header */}
                        <div className="p-3">
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <User className="w-4 h-4 text-owl-blue-600 flex-shrink-0" />
                                <span className="text-sm font-medium text-owl-blue-900">
                                  {witness.name}
                                  {witness.role && witness.organization && (
                                    <span className="text-light-600 font-normal">
                                      {' '}({witness.role}, {witness.organization})
                                    </span>
                                  )}
                                  {witness.role && !witness.organization && (
                                    <span className="text-light-600 font-normal">
                                      {' '}({witness.role})
                                    </span>
                                  )}
                                </span>
                              </div>
                              
                              {/* Latest Interview Summary */}
                              {latestInterview && (
                                <div className="mt-2 text-xs space-y-1">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    {latestInterview.status && (
                                      <span className="text-owl-blue-900 font-medium">
                                        Status: {latestInterview.status}
                                      </span>
                                    )}
                                    {latestInterview.credibility_rating && (
                                      <span className={`${getCredibilityColor(latestInterview.credibility_rating)}`}>
                                        Credibility: {getCredibilityStars(latestInterview.credibility_rating)} ({latestInterview.credibility_rating >= 4 ? 'High' : latestInterview.credibility_rating >= 3 ? 'Medium' : 'Low'})
                                      </span>
                                    )}
                                  </div>
                                  {latestInterview.statement && (
                                    <p className="text-light-700">
                                      Statement: {latestInterview.statement}
                                    </p>
                                  )}
                                  {latestInterview.risk_assessment && (
                                    <p className="text-red-600">
                                      Risk: {getRiskEmoji(latestInterview.risk_assessment)} {latestInterview.risk_assessment}
                                    </p>
                                  )}
                                </div>
                              )}

                              {/* No interviews message */}
                              {interviews.length === 0 && (
                                <p className="text-xs text-light-500 italic mt-1">No interviews recorded</p>
                              )}
                            </div>
                            <div className="flex items-center gap-1 flex-shrink-0">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditWitnessModal({ open: true, witness });
                                }}
                                className="p-1.5 hover:bg-light-200 rounded transition-colors"
                                title="Edit witness"
                              >
                                <Edit2 className="w-4 h-4 text-light-600" />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setInterviewModal({ open: true, witness, interview: null });
                                }}
                                className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors"
                                title="Add interview"
                              >
                                <MessageSquare className="w-4 h-4 text-owl-blue-600" />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setAttachModal({ open: true, witness });
                                }}
                                className="p-1.5 hover:bg-owl-blue-100 rounded transition-colors"
                                title="Attach to theory"
                              >
                                <Link2 className="w-4 h-4 text-owl-blue-600" />
                              </button>
                              {interviews.length > 0 && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setExpandedWitnessId(isExpanded ? null : witness.witness_id);
                                  }}
                                  className="p-1.5 hover:bg-light-200 rounded transition-colors text-light-600"
                                  title={isExpanded ? 'Collapse interviews' : 'Expand interviews'}
                                >
                                  {isExpanded ? (
                                    <ChevronUp className="w-4 h-4" />
                                  ) : (
                                    <ChevronDown className="w-4 h-4" />
                                  )}
                                </button>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Expanded Interviews List */}
                        {isExpanded && interviews.length > 0 && (
                          <div className="px-3 pb-3 border-t border-light-200 pt-3 space-y-3">
                            <h5 className="text-xs font-semibold text-owl-blue-900 mb-2">
                              Interviews ({interviews.length})
                            </h5>
                            {interviews
                              .sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0))
                              .map((interview) => (
                                <div
                                  key={interview.interview_id}
                                  className="bg-white rounded-lg border border-light-200 p-3"
                                >
                                  <div className="flex items-start justify-between gap-2 mb-2">
                                    <div className="flex-1">
                                      <div className="flex items-center gap-2 flex-wrap text-xs mb-1">
                                        {interview.date && (
                                          <span className="text-light-600">
                                            {formatDate(interview.date)}
                                          </span>
                                        )}
                                        {interview.duration && (
                                          <>
                                            <span className="text-light-400">•</span>
                                            <span className="text-light-600">{interview.duration}</span>
                                          </>
                                        )}
                                      </div>
                                      {interview.status && (
                                        <p className="text-xs text-owl-blue-900 font-medium mb-1">
                                          Status: {interview.status}
                                        </p>
                                      )}
                                      {interview.credibility_rating && (
                                        <p className={`text-xs ${getCredibilityColor(interview.credibility_rating)} mb-1`}>
                                          Credibility: {getCredibilityStars(interview.credibility_rating)} ({interview.credibility_rating >= 4 ? 'High' : interview.credibility_rating >= 3 ? 'Medium' : 'Low'})
                                        </p>
                                      )}
                                      {interview.statement && (
                                        <p className="text-xs text-light-700 mb-1">
                                          Statement: {interview.statement}
                                        </p>
                                      )}
                                      {interview.risk_assessment && (
                                        <p className="text-xs text-red-600">
                                          Risk: {getRiskEmoji(interview.risk_assessment)} {interview.risk_assessment}
                                        </p>
                                      )}
                                    </div>
                                    <div className="flex items-center gap-1 flex-shrink-0">
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setInterviewModal({ open: true, witness, interview });
                                        }}
                                        className="p-1 hover:bg-light-200 rounded transition-colors"
                                        title="Edit interview"
                                      >
                                        <Edit2 className="w-3.5 h-3.5 text-light-600" />
                                      </button>
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleDeleteInterview(witness, interview.interview_id);
                                        }}
                                        className="p-1 hover:bg-red-100 rounded transition-colors"
                                        title="Delete interview"
                                      >
                                        <Trash2 className="w-3.5 h-3.5 text-red-600" />
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {attachModal.open && attachModal.witness && (
        <AttachToTheoryModal
          isOpen={attachModal.open}
          onClose={() => setAttachModal({ open: false, witness: null })}
          caseId={caseId}
          itemType="witness"
          itemId={attachModal.witness.witness_id}
          itemName={attachModal.witness.name}
          onAttach={handleAttachToTheory}
        />
      )}

      {interviewModal.open && interviewModal.witness && (
        <WitnessInterviewModal
          isOpen={interviewModal.open}
          onClose={() => setInterviewModal({ open: false, witness: null, interview: null })}
          caseId={caseId}
          witness={interviewModal.witness}
          interview={interviewModal.interview}
          onSave={() => {
            if (onRefresh) {
              onRefresh();
            }
            setExpandedWitnessId(interviewModal.witness.witness_id);
          }}
        />
      )}

      {showAddModal && (
        <WitnessModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          caseId={caseId}
          onSave={() => {
            if (onRefresh) {
              onRefresh();
            }
          }}
        />
      )}

      {editWitnessModal.open && editWitnessModal.witness && (
        <WitnessModal
          isOpen={editWitnessModal.open}
          onClose={() => setEditWitnessModal({ open: false, witness: null })}
          caseId={caseId}
          witness={editWitnessModal.witness}
          onSave={() => {
            if (onRefresh) {
              onRefresh();
            }
          }}
        />
      )}
    </div>
  );
}
