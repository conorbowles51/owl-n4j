import React, { useState } from 'react';
import { X, UserPlus, Eye, EyeOff } from 'lucide-react';
import { usersAPI } from '../services/api';

/**
 * CreateUserModal Component
 *
 * Modal for super_admin users to create new users
 */
export default function CreateUserModal({
  isOpen,
  onClose,
  onUserCreated,
}) {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('user');
  const [showPassword, setShowPassword] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleCreate = async () => {
    if (!email.trim()) {
      setError('Email is required');
      return;
    }
    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    if (!password.trim()) {
      setError('Password is required');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setIsCreating(true);
    setError('');
    try {
      await usersAPI.create({
        email: email.trim(),
        name: name.trim(),
        password: password,
        role: role,
      });
      // Reset form
      setEmail('');
      setName('');
      setPassword('');
      setRole('user');
      onUserCreated?.();
      onClose();
    } catch (err) {
      console.error('Failed to create user:', err);
      setError(err.message || 'Failed to create user');
    } finally {
      setIsCreating(false);
    }
  };

  const handleCancel = () => {
    setEmail('');
    setName('');
    setPassword('');
    setRole('user');
    setError('');
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-md border border-light-200 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <UserPlus className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              Create New User
            </h2>
          </div>
          <button
            onClick={handleCancel}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        <div className="space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Email *
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
              className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
              autoFocus
              disabled={isCreating}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="John Doe"
              className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
              disabled={isCreating}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Password *
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                className="w-full px-3 py-2 pr-10 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
                disabled={isCreating}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-light-100 rounded transition-colors"
                disabled={isCreating}
              >
                {showPassword ? (
                  <EyeOff className="w-4 h-4 text-light-500" />
                ) : (
                  <Eye className="w-4 h-4 text-light-500" />
                )}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Role
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 focus:outline-none focus:border-owl-blue-500"
              disabled={isCreating}
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
              <option value="super_admin">Super Admin</option>
            </select>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={handleCreate}
              disabled={isCreating || !email.trim() || !name.trim() || !password.trim()}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              <UserPlus className="w-4 h-4" />
              {isCreating ? 'Creating...' : 'Create User'}
            </button>
            <button
              onClick={handleCancel}
              disabled={isCreating}
              className="px-4 py-2 bg-light-100 hover:bg-light-200 disabled:opacity-50 text-light-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
