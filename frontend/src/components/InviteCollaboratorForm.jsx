import React, { useState, useEffect } from 'react';
import {
  UserPlus,
  X,
  Loader2,
  Search,
  ChevronDown,
} from 'lucide-react';
import { caseMembersAPI, usersAPI } from '../services/api';

/**
 * InviteCollaboratorForm Component
 *
 * Sub-component for inviting a new collaborator to a case.
 * Provides user search/select and permission preset selection.
 */
export default function InviteCollaboratorForm({
  caseId,
  existingMemberIds = [],
  onInviteComplete,
  onCancel,
}) {
  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedPreset, setSelectedPreset] = useState('viewer');
  const [isInviting, setIsInviting] = useState(false);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  /**
   * Load available users
   */
  useEffect(() => {
    const loadUsers = async () => {
      setLoadingUsers(true);
      try {
        const data = await usersAPI.list();
        // Filter out users who are already members
        const availableUsers = (data?.users || []).filter(
          (user) => !existingMemberIds.includes(user.id)
        );
        setUsers(availableUsers);
      } catch (err) {
        console.error('Failed to load users:', err);
        setError('Failed to load users');
      } finally {
        setLoadingUsers(false);
      }
    };

    loadUsers();
  }, [existingMemberIds]);

  /**
   * Filter users by search term
   */
  const filteredUsers = users.filter((user) => {
    const term = searchTerm.toLowerCase();
    return (
      (user.name || '').toLowerCase().includes(term) ||
      (user.email || '').toLowerCase().includes(term)
    );
  });

  /**
   * Handle invite submission
   */
  const handleInvite = async () => {
    if (!selectedUserId) {
      setError('Please select a user to invite');
      return;
    }

    setIsInviting(true);
    setError(null);

    try {
      await caseMembersAPI.add(caseId, selectedUserId, selectedPreset);
      onInviteComplete?.();
    } catch (err) {
      console.error('Failed to invite collaborator:', err);
      setError(err.message || 'Failed to invite collaborator');
    } finally {
      setIsInviting(false);
    }
  };

  const selectedUser = users.find((u) => u.id === selectedUserId);

  return (
    <div className="border border-owl-blue-200 rounded-lg p-4 bg-owl-blue-50">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-owl-blue-900 flex items-center gap-2">
          <UserPlus className="w-4 h-4" />
          Invite Collaborator
        </h3>
        <button
          onClick={onCancel}
          className="p-1 hover:bg-owl-blue-100 rounded transition-colors"
        >
          <X className="w-4 h-4 text-light-600" />
        </button>
      </div>

      {error && (
        <div className="mb-3 p-2 bg-red-50 text-red-700 text-sm rounded border border-red-200">
          {error}
        </div>
      )}

      <div className="space-y-3">
        {/* User Selection */}
        <div>
          <label className="block text-xs font-medium text-light-700 mb-1">
            Select User
          </label>
          {loadingUsers ? (
            <div className="flex items-center gap-2 p-2 text-light-600 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading users...
            </div>
          ) : users.length === 0 ? (
            <p className="text-sm text-light-600 p-2">
              No available users to invite. All users are already members.
            </p>
          ) : (
            <div className="relative">
              {/* Search Input */}
              <div className="relative mb-2">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-light-400" />
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Search users..."
                  className="w-full pl-8 pr-3 py-2 text-sm border border-light-300 rounded bg-white focus:outline-none focus:border-owl-blue-500"
                />
              </div>

              {/* User List */}
              <div className="max-h-40 overflow-y-auto border border-light-300 rounded bg-white">
                {filteredUsers.length === 0 ? (
                  <p className="p-2 text-sm text-light-600 text-center">
                    No users found
                  </p>
                ) : (
                  filteredUsers.map((user) => (
                    <button
                      key={user.id}
                      onClick={() => setSelectedUserId(user.id)}
                      className={`w-full flex items-center gap-2 p-2 text-left hover:bg-light-100 transition-colors ${
                        selectedUserId === user.id ? 'bg-owl-blue-100' : ''
                      }`}
                    >
                      <div className="w-6 h-6 rounded-full bg-owl-blue-100 flex items-center justify-center text-owl-blue-700 font-medium text-xs">
                        {(user.name || user.email || '?')[0].toUpperCase()}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-owl-blue-900 truncate">
                          {user.name || user.email}
                        </p>
                        {user.name && user.email && (
                          <p className="text-xs text-light-600 truncate">{user.email}</p>
                        )}
                      </div>
                      {selectedUserId === user.id && (
                        <span className="text-owl-blue-600 text-xs">Selected</span>
                      )}
                    </button>
                  ))
                )}
              </div>

              {/* Selected User Display */}
              {selectedUser && (
                <div className="mt-2 p-2 bg-owl-blue-100 rounded text-sm">
                  Selected: <span className="font-medium">{selectedUser.name || selectedUser.email}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Permission Preset Selection */}
        <div>
          <label className="block text-xs font-medium text-light-700 mb-1">
            Permission Level
          </label>
          <select
            value={selectedPreset}
            onChange={(e) => setSelectedPreset(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-light-300 rounded bg-white focus:outline-none focus:border-owl-blue-500"
          >
            <option value="viewer">Viewer - Read-only access</option>
            <option value="editor">Editor - Can edit case and upload evidence</option>
          </select>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 pt-2">
          <button
            onClick={handleInvite}
            disabled={isInviting || !selectedUserId}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed text-white rounded-lg transition-colors text-sm"
          >
            {isInviting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <UserPlus className="w-4 h-4" />
            )}
            {isInviting ? 'Inviting...' : 'Invite'}
          </button>
          <button
            onClick={onCancel}
            disabled={isInviting}
            className="px-4 py-2 bg-white hover:bg-light-100 disabled:opacity-50 text-light-700 rounded-lg transition-colors text-sm border border-light-300"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
