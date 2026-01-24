import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { caseMembersAPI } from '../services/api';

/**
 * Permission structure from backend:
 * {
 *   case: { view: bool, edit: bool, delete: bool },
 *   collaborators: { invite: bool, remove: bool },
 *   evidence: { upload: bool }
 * }
 *
 * Presets: 'owner', 'editor', 'viewer'
 */

const defaultPermissions = {
  case: { view: false, edit: false, delete: false },
  collaborators: { invite: false, remove: false },
  evidence: { upload: false },
};

// Full permissions for owners and super_admins
const fullPermissions = {
  case: { view: true, edit: true, delete: true },
  collaborators: { invite: true, remove: true },
  evidence: { upload: true },
};

const CasePermissionContext = createContext({
  currentCasePermissions: defaultPermissions,
  currentMembership: null,
  isOwner: false,
  isSuperAdmin: false,
  canEdit: false,
  canDelete: false,
  canInvite: false,
  canRemoveCollaborators: false,
  canUploadEvidence: false,
  isLoading: false,
  error: null,
  refreshPermissions: async () => {},
  clearPermissions: () => {},
  setUserRole: () => {},
});

/**
 * CasePermissionProvider
 *
 * Provides permission context for the current case.
 * Fetches the user's membership/permissions when a case is selected.
 * Super admins get full permissions automatically.
 */
export function CasePermissionProvider({ children, userRole: initialUserRole = null }) {
  const [currentCaseId, setCurrentCaseId] = useState(null);
  const [currentMembership, setCurrentMembership] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [userRole, setUserRole] = useState(initialUserRole);

  // Check if user is super_admin
  const isSuperAdmin = useMemo(() => {
    return userRole === 'super_admin';
  }, [userRole]);

  // Initialize permissions based on user role - super_admin gets full permissions by default
  const [currentCasePermissions, setCurrentCasePermissions] = useState(
    initialUserRole === 'super_admin' ? fullPermissions : defaultPermissions
  );

  // Update permissions when userRole changes
  React.useEffect(() => {
    if (userRole === 'super_admin') {
      setCurrentCasePermissions(fullPermissions);
    }
  }, [userRole]);

  /**
   * Refresh permissions for a specific case
   * @param {string} caseId - Case ID to fetch permissions for
   */
  const refreshPermissions = useCallback(async (caseId) => {
    if (!caseId) {
      setCurrentCaseId(null);
      setCurrentMembership(null);
      setCurrentCasePermissions(defaultPermissions);
      return;
    }

    setCurrentCaseId(caseId);

    // Super admins get full permissions without API call
    if (userRole === 'super_admin') {
      setCurrentMembership({ preset: 'owner', is_owner: true });
      setCurrentCasePermissions(fullPermissions);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const membership = await caseMembersAPI.getMyMembership(caseId);
      setCurrentMembership(membership);

      // Extract permissions from membership response
      if (membership && membership.permissions) {
        setCurrentCasePermissions(membership.permissions);
      } else if (membership && membership.membership_role === 'owner') {
        // If user is owner but no permissions field, use full permissions
        setCurrentCasePermissions(fullPermissions);
      } else {
        // SAFE: Default to restrictive permissions if unclear
        console.warn('Membership exists but no permissions - defaulting to viewer');
        setCurrentCasePermissions(defaultPermissions);
      }
    } catch (err) {
      console.error('Failed to fetch case permissions:', err);
      setError(err.message || 'Failed to fetch permissions');
      // SAFE: On error, default to NO permissions (safest option)
      setCurrentMembership(null);
      setCurrentCasePermissions(defaultPermissions);
    } finally {
      setIsLoading(false);
    }
  }, [userRole]);

  /**
   * Clear permissions (e.g., when logging out or leaving case view)
   */
  const clearPermissions = useCallback(() => {
    setCurrentCaseId(null);
    setCurrentMembership(null);
    setCurrentCasePermissions(defaultPermissions);
    setError(null);
  }, []);

  // Derived permission checks - super_admin always has full permissions
  const isOwner = useMemo(() => {
    if (isSuperAdmin) return true;
    return currentMembership?.preset === 'owner' || currentMembership?.is_owner === true;
  }, [currentMembership, isSuperAdmin]);

  const canEdit = useMemo(() => {
    if (isSuperAdmin) return true;
    return currentCasePermissions.case?.edit === true;
  }, [currentCasePermissions, isSuperAdmin]);

  const canDelete = useMemo(() => {
    if (isSuperAdmin) return true;
    return currentCasePermissions.case?.delete === true;
  }, [currentCasePermissions, isSuperAdmin]);

  const canInvite = useMemo(() => {
    if (isSuperAdmin) return true;
    return currentCasePermissions.collaborators?.invite === true;
  }, [currentCasePermissions, isSuperAdmin]);

  const canRemoveCollaborators = useMemo(() => {
    if (isSuperAdmin) return true;
    return currentCasePermissions.collaborators?.remove === true;
  }, [currentCasePermissions, isSuperAdmin]);

  const canUploadEvidence = useMemo(() => {
    if (isSuperAdmin) return true;
    return currentCasePermissions.evidence?.upload === true;
  }, [currentCasePermissions, isSuperAdmin]);

  const value = useMemo(() => ({
    currentCaseId,
    currentCasePermissions,
    currentMembership,
    isOwner,
    isSuperAdmin,
    canEdit,
    canDelete,
    canInvite,
    canRemoveCollaborators,
    canUploadEvidence,
    isLoading,
    error,
    refreshPermissions,
    clearPermissions,
    setUserRole,
  }), [
    currentCaseId,
    currentCasePermissions,
    currentMembership,
    isOwner,
    isSuperAdmin,
    canEdit,
    canDelete,
    canInvite,
    canRemoveCollaborators,
    canUploadEvidence,
    isLoading,
    error,
    refreshPermissions,
    clearPermissions,
  ]);

  return (
    <CasePermissionContext.Provider value={value}>
      {children}
    </CasePermissionContext.Provider>
  );
}

/**
 * Hook to access case permission context
 */
export function useCasePermissions() {
  const context = useContext(CasePermissionContext);
  if (!context) {
    throw new Error('useCasePermissions must be used within a CasePermissionProvider');
  }
  return context;
}

export default CasePermissionContext;
