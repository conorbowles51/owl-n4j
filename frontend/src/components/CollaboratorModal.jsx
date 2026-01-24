import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  Users,
  Crown,
  Shield,
  Eye,
  Trash2,
  Loader2,
  AlertCircle,
  UserPlus,
} from 'lucide-react';
import { caseMembersAPI, usersAPI } from '../services/api';
import { useCasePermissions } from '../contexts/CasePermissionContext';
import InviteCollaboratorForm from './InviteCollaboratorForm';

/**
 * Transform backend member response to frontend format
 * Backend: { user_id, membership_role, permissions, user: {id, email, name} }
 * Frontend: { user_id, user_name, user_email, preset, permissions }
 */
function transformMemberData(member) {
  // Map membership_role to preset
  let preset = 'viewer'; // default
  if (member.membership_role === 'owner') {
    preset = 'owner';
  } else if (member.permissions?.evidence?.upload) {
    preset = 'editor';
  }

  return {
    user_id: member.user_id,
    user_name: member.user?.name || '',
    user_email: member.user?.email || '',
    preset: preset,
    permissions: member.permissions || {},
    membership_role: member.membership_role,
  };
}

/**
 * Permission preset badges
 */
const PresetBadge = ({ preset }) => {
  const config = {
    owner: { icon: Crown, label: 'Owner', className: 'bg-amber-100 text-amber-700' },
    editor: { icon: Shield, label: 'Editor', className: 'bg-blue-100 text-blue-700' },
    viewer: { icon: Eye, label: 'Viewer', className: 'bg-gray-100 text-gray-700' },
  };

  const { icon: Icon, label, className } = config[preset] || config.viewer;

  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded ${className}`}>
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
};

/**
 * CollaboratorModal Component
 *
 * Modal for managing case collaborators - listing, inviting, updating, and removing members.
 */
export default function CollaboratorModal({
  isOpen,
  onClose,
  caseData,
  onMembersChanged,
}) {
  const { canInvite, canRemoveCollaborators, isOwner } = useCasePermissions();

  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [removingUserId, setRemovingUserId] = useState(null);
  const [updatingUserId, setUpdatingUserId] = useState(null);
  const [showInviteForm, setShowInviteForm] = useState(false);

  /**
   * Load case members
   */
  const loadMembers = useCallback(async () => {
    if (!caseData?.id) return;

    setLoading(true);
    setError(null);

    try {
      const data = await caseMembersAPI.list(caseData.id);
      // Transform backend data to frontend format
      const transformedMembers = (data?.members || []).map(transformMemberData);

      // Sort: owners first, then by name
      const sortedMembers = transformedMembers.sort((a, b) => {
        if (a.preset === 'owner' && b.preset !== 'owner') return -1;
        if (a.preset !== 'owner' && b.preset === 'owner') return 1;
        return (a.user_name || '').localeCompare(b.user_name || '');
      });
      setMembers(sortedMembers);
    } catch (err) {
      console.error('Failed to load members:', err);
      setError(err.message || 'Failed to load collaborators');
    } finally {
      setLoading(false);
    }
  }, [caseData?.id]);

  useEffect(() => {
    if (isOpen && caseData?.id) {
      loadMembers();
    }
  }, [isOpen, caseData?.id, loadMembers]);

  /**
   * Handle removing a member
   */
  const handleRemoveMember = async (userId, userName) => {
    if (!confirm(`Are you sure you want to remove "${userName}" from this case?`)) {
      return;
    }

    setRemovingUserId(userId);
    try {
      await caseMembersAPI.remove(caseData.id, userId);
      await loadMembers();
      onMembersChanged?.();
    } catch (err) {
      console.error('Failed to remove member:', err);
      alert(`Failed to remove member: ${err.message}`);
    } finally {
      setRemovingUserId(null);
    }
  };

  /**
   * Handle updating a member's permissions
   */
  const handleUpdatePermission = async (userId, newPreset) => {
    setUpdatingUserId(userId);
    try {
      await caseMembersAPI.update(caseData.id, userId, newPreset);
      await loadMembers();
      onMembersChanged?.();
    } catch (err) {
      console.error('Failed to update permissions:', err);
      alert(`Failed to update permissions: ${err.message}`);
    } finally {
      setUpdatingUserId(null);
    }
  };

  /**
   * Handle invite completion
   */
  const handleInviteComplete = () => {
    setShowInviteForm(false);
    loadMembers();
    onMembersChanged?.();
  };

  if (!isOpen) return null;

  const caseTitle = caseData?.title || caseData?.name || 'Case';

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg w-full max-w-lg max-h-[85vh] flex flex-col border border-light-200 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              Collaborators
            </h2>
            {members.length > 0 && (
              <span className="text-xs text-light-600 bg-light-100 px-2 py-1 rounded">
                {members.length}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Case Info */}
        <div className="px-4 py-2 bg-light-50 border-b border-light-200">
          <p className="text-sm text-light-700">
            Managing collaborators for: <span className="font-medium text-owl-blue-900">{caseTitle}</span>
          </p>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {/* Error State */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-50 text-red-700 rounded-lg mb-4">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <p className="text-sm">{error}</p>
            </div>
          )}

          {/* Loading State */}
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-owl-blue-500" />
              <span className="ml-2 text-light-600">Loading collaborators...</span>
            </div>
          ) : (
            <>
              {/* Invite Form */}
              {showInviteForm && canInvite ? (
                <div className="mb-4">
                  <InviteCollaboratorForm
                    caseId={caseData.id}
                    existingMemberIds={members.map(m => m.user_id)}
                    onInviteComplete={handleInviteComplete}
                    onCancel={() => setShowInviteForm(false)}
                  />
                </div>
              ) : canInvite && (
                <button
                  onClick={() => setShowInviteForm(true)}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 mb-4 border-2 border-dashed border-light-300 hover:border-owl-blue-400 text-light-600 hover:text-owl-blue-600 rounded-lg transition-colors"
                >
                  <UserPlus className="w-4 h-4" />
                  Invite Collaborator
                </button>
              )}

              {/* Members List */}
              {members.length === 0 ? (
                <div className="text-center py-8 text-light-600">
                  <Users className="w-12 h-12 mx-auto mb-3 text-light-400" />
                  <p>No collaborators yet</p>
                  {canInvite && (
                    <p className="text-sm mt-1">Invite team members to collaborate on this case</p>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  {members.map((member) => {
                    const isOwnerMember = member.preset === 'owner';
                    const canRemove = canRemoveCollaborators && !isOwnerMember;
                    const canUpdatePermissions = canInvite && !isOwnerMember;

                    return (
                      <div
                        key={member.user_id}
                        className="flex items-center justify-between p-3 bg-light-50 hover:bg-light-100 rounded-lg transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-owl-blue-100 flex items-center justify-center text-owl-blue-700 font-medium text-sm">
                            {(member.user_name || member.user_email || '?')[0].toUpperCase()}
                          </div>
                          <div>
                            <p className="font-medium text-owl-blue-900">
                              {member.user_name || member.user_email}
                            </p>
                            {member.user_name && member.user_email && (
                              <p className="text-xs text-light-600">{member.user_email}</p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {/* Permission Selector or Badge */}
                          {canUpdatePermissions ? (
                            <select
                              value={member.preset}
                              onChange={(e) => handleUpdatePermission(member.user_id, e.target.value)}
                              disabled={updatingUserId === member.user_id}
                              className="text-xs px-2 py-1 border border-light-300 rounded bg-white focus:outline-none focus:border-owl-blue-500"
                            >
                              <option value="viewer">Viewer</option>
                              <option value="editor">Editor</option>
                            </select>
                          ) : (
                            <PresetBadge preset={member.preset} />
                          )}

                          {/* Remove Button */}
                          {canRemove && (
                            <button
                              onClick={() => handleRemoveMember(member.user_id, member.user_name || member.user_email)}
                              disabled={removingUserId === member.user_id}
                              className="p-1 hover:bg-red-100 rounded transition-colors"
                              title="Remove collaborator"
                            >
                              {removingUserId === member.user_id ? (
                                <Loader2 className="w-4 h-4 animate-spin text-red-500" />
                              ) : (
                                <Trash2 className="w-4 h-4 text-red-500" />
                              )}
                            </button>
                          )}

                          {/* Loading indicator for permission update */}
                          {updatingUserId === member.user_id && (
                            <Loader2 className="w-4 h-4 animate-spin text-owl-blue-500" />
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-light-200 bg-light-50">
          <div className="flex items-center justify-between">
            <div className="text-xs text-light-600">
              <p className="flex items-center gap-1">
                <Crown className="w-3 h-3 text-amber-600" /> Owner: Full access, cannot be removed
              </p>
              <p className="flex items-center gap-1 mt-0.5">
                <Shield className="w-3 h-3 text-blue-600" /> Editor: Can edit case and upload evidence
              </p>
              <p className="flex items-center gap-1 mt-0.5">
                <Eye className="w-3 h-3 text-gray-600" /> Viewer: Read-only access
              </p>
            </div>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-light-100 hover:bg-light-200 text-light-700 rounded-lg transition-colors text-sm"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
