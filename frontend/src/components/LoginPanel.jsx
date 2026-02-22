import React, { useState } from 'react';
import { X, Shield, LogIn, LogOut, Eye, EyeOff, Mail, KeyRound, CheckCircle, Lock, Loader2 } from 'lucide-react';
import { authAPI } from '../services/api';

export default function LoginPanel({
  isOpen,
  onClose,
  onLoginSuccess,
  onLogout,
  isAuthenticated,
  username,
  inline = false,
}) {
  const [credentials, setCredentials] = useState({ username: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [pwForm, setPwForm] = useState({ current: '', newPw: '', confirm: '' });
  const [pwError, setPwError] = useState('');
  const [pwSuccess, setPwSuccess] = useState('');
  const [pwLoading, setPwLoading] = useState(false);
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);

  if (!isOpen && !inline) {
    return null;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const response = await authAPI.login({
        username: credentials.username,
        password: credentials.password,
      });
      
      onLoginSuccess(response.access_token, response.username, response.name, response.role);
      setCredentials({ username: '', password: '' });
      onClose();
    } catch (err) {
      setError(err.message || 'Login failed. Please try again.');
      console.error('Login error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPwError('');
    setPwSuccess('');

    if (pwForm.newPw.length < 6) {
      setPwError('New password must be at least 6 characters.');
      return;
    }
    if (pwForm.newPw !== pwForm.confirm) {
      setPwError('New passwords do not match.');
      return;
    }

    setPwLoading(true);
    try {
      await authAPI.changePassword(pwForm.current, pwForm.newPw);
      setPwSuccess('Password updated successfully.');
      setPwForm({ current: '', newPw: '', confirm: '' });
      setTimeout(() => { setPwSuccess(''); setShowChangePassword(false); }, 2000);
    } catch (err) {
      setPwError(err.message || 'Failed to change password.');
    } finally {
      setPwLoading(false);
    }
  };

  const handleLogout = async () => {
    await authAPI.logout();
    onLogout();
    onClose();
  };

  const content = (
    <div className="w-full max-w-md bg-white rounded-xl shadow-2xl overflow-hidden border border-light-200">
      {/* Header */}
      <div className="bg-gradient-to-r from-owl-blue-800 to-owl-blue-900 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-white/10 rounded-lg backdrop-blur-sm">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">
                {isAuthenticated ? 'Account' : 'Sign In'}
              </h2>
              <p className="text-xs text-owl-blue-200">
                {isAuthenticated ? 'Manage your session' : ''}
              </p>
            </div>
          </div>
          {!inline && (
            <button 
              className="p-1.5 hover:bg-white/10 rounded-lg transition-colors" 
              onClick={onClose} 
              aria-label="Close"
            >
              <X className="w-5 h-5 text-white/80 hover:text-white" />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="p-6">
        {/* Logo for inline mode */}
        {inline && (
          <div className="flex flex-col items-center mb-6">
            <img
              src="/owl-logo.webp"
              alt="Owl Consultancy Group"
              className="w-32 h-32 object-contain drop-shadow-lg"
              role="presentation"
            />
            <h1 className="mt-3 text-xl font-bold text-owl-blue-900">
              Owl Consultancy Group
            </h1>
            <p className="text-sm text-light-500">Intelligence Analysis Platform</p>
          </div>
        )}

        {isAuthenticated ? (
          /* Authenticated State */
          <div className="space-y-4">
            <div className="flex items-center gap-4 p-4 bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl border border-green-200">
              <div className="p-3 bg-green-100 rounded-full">
                <CheckCircle className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <p className="text-sm text-light-600">Signed in as</p>
                <p className="font-semibold text-light-900">{username}</p>
              </div>
            </div>

            {/* Change Password */}
            <button
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-light-50 hover:bg-light-100 border border-light-200 rounded-xl text-sm font-medium text-light-700 transition-all duration-200"
              onClick={() => { setShowChangePassword(!showChangePassword); setPwError(''); setPwSuccess(''); }}
            >
              <Lock className="w-4 h-4" />
              {showChangePassword ? 'Cancel' : 'Change Password'}
            </button>

            {showChangePassword && (
              <form onSubmit={handleChangePassword} className="space-y-3 p-4 bg-light-50 rounded-xl border border-light-200">
                <div>
                  <label className="block text-xs font-medium text-light-600 mb-1">Current Password</label>
                  <div className="relative">
                    <input
                      type={showCurrentPw ? 'text' : 'password'}
                      value={pwForm.current}
                      onChange={(e) => setPwForm({ ...pwForm, current: e.target.value })}
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-owl-blue-500/20 focus:border-owl-blue-500 pr-10"
                      placeholder="Enter current password"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowCurrentPw(!showCurrentPw)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-light-400 hover:text-light-600"
                    >
                      {showCurrentPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-light-600 mb-1">New Password</label>
                  <div className="relative">
                    <input
                      type={showNewPw ? 'text' : 'password'}
                      value={pwForm.newPw}
                      onChange={(e) => setPwForm({ ...pwForm, newPw: e.target.value })}
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-owl-blue-500/20 focus:border-owl-blue-500 pr-10"
                      placeholder="Enter new password"
                      required
                      minLength={6}
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPw(!showNewPw)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-light-400 hover:text-light-600"
                    >
                      {showNewPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-light-600 mb-1">Confirm New Password</label>
                  <input
                    type={showNewPw ? 'text' : 'password'}
                    value={pwForm.confirm}
                    onChange={(e) => setPwForm({ ...pwForm, confirm: e.target.value })}
                    className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-owl-blue-500/20 focus:border-owl-blue-500"
                    placeholder="Confirm new password"
                    required
                    minLength={6}
                  />
                </div>

                {pwError && (
                  <div className="flex items-center gap-2 p-2 bg-red-50 border border-red-200 rounded-lg">
                    <X className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
                    <p className="text-xs text-red-600">{pwError}</p>
                  </div>
                )}
                {pwSuccess && (
                  <div className="flex items-center gap-2 p-2 bg-green-50 border border-green-200 rounded-lg">
                    <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                    <p className="text-xs text-green-600">{pwSuccess}</p>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={pwLoading}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-owl-blue-600 hover:bg-owl-blue-700 disabled:bg-light-300 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
                >
                  {pwLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
                  {pwLoading ? 'Updating...' : 'Update Password'}
                </button>
              </form>
            )}
            
            <button
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-light-100 hover:bg-light-200 border border-light-300 rounded-xl text-sm font-medium text-light-700 transition-all duration-200 hover:shadow-sm"
              onClick={handleLogout}
            >
              <LogOut className="w-4 h-4" />
              Sign Out
            </button>
          </div>
        ) : (
          /* Login Form */
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email Field */}
            <div>
              <label className="block text-sm font-medium text-light-700 mb-2">
                Email
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Mail className="w-5 h-5 text-light-400" />
                </div>
                <input
                  type="email"
                  className="w-full pl-10 pr-4 py-2.5 bg-light-50 border border-light-300 rounded-xl text-light-900 placeholder-light-400 focus:outline-none focus:ring-2 focus:ring-owl-blue-500/20 focus:border-owl-blue-500 transition-all duration-200"
                  placeholder="Enter your email"
                  value={credentials.username}
                  onChange={(e) => setCredentials({ ...credentials, username: e.target.value })}
                  autoComplete="email"
                  required
                />
              </div>
            </div>

            {/* Password Field */}
            <div>
              <label className="block text-sm font-medium text-light-700 mb-2">
                Password
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <KeyRound className="w-5 h-5 text-light-400" />
                </div>
                <input
                  type={showPassword ? "text" : "password"}
                  className="w-full pl-10 pr-12 py-2.5 bg-light-50 border border-light-300 rounded-xl text-light-900 placeholder-light-400 focus:outline-none focus:ring-2 focus:ring-owl-blue-500/20 focus:border-owl-blue-500 transition-all duration-200"
                  placeholder="Enter your password"
                  value={credentials.password}
                  onChange={(e) => setCredentials({ ...credentials, password: e.target.value })}
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-light-400 hover:text-light-600 transition-colors"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <EyeOff className="w-5 h-5" />
                  ) : (
                    <Eye className="w-5 h-5" />
                  )}
                </button>
              </div>
            </div>

            {/* Error Message */}
            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-xl">
                <div className="p-1 bg-red-100 rounded-full">
                  <X className="w-4 h-4 text-red-500" />
                </div>
                <p className="text-sm text-red-600">{error}</p>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gradient-to-r from-owl-blue-600 to-owl-blue-700 hover:from-owl-blue-700 hover:to-owl-blue-800 disabled:from-light-300 disabled:to-light-400 disabled:cursor-not-allowed text-white font-medium rounded-xl shadow-lg shadow-owl-blue-500/25 hover:shadow-owl-blue-500/40 transition-all duration-200"
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Signing in...</span>
                </>
              ) : (
                <>
                  <LogIn className="w-5 h-5" />
                  <span>Sign In</span>
                </>
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  );

  if (inline) {
    return content;
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      {content}
    </div>
  );
}

