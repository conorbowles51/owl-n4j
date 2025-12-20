import React, { useState } from 'react';
import { X, Lock, LogIn, LogOut, Eye, EyeOff } from 'lucide-react';
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
      onLoginSuccess(response.access_token, response.username);
      setCredentials({ username: '', password: '' });
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    await authAPI.logout();
    onLogout();
    onClose();
  };

  const content = (
    <div className={`w-full max-w-sm bg-dark-900 border border-dark-700 rounded-lg shadow-2xl overflow-hidden ${inline ? '' : ''}`}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-dark-700">
          <div className="flex items-center gap-2 text-light-100">
            <Lock className="w-5 h-5" />
            <span className="font-semibold">Authentication</span>
          </div>
          {!inline && (
            <button className="p-1" onClick={onClose} aria-label="Close">
              <X className="w-5 h-5 text-light-500 hover:text-light-200" />
            </button>
          )}
        </div>
        <div className="p-4 space-y-3">
          {inline && (
            <div className="flex flex-col items-center gap-4">
              <img
                src="/owl-logo.webp"
                alt="Owl Consultancy Group"
                className="w-40 h-40 object-contain"
                role="presentation"
              />
            </div>
          )}
          {isAuthenticated ? (
            <div className="space-y-3">
              <p className="text-sm text-light-300">
                Logged in as <span className="font-semibold text-light-100">{username}</span>
              </p>
              <button
                className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded text-sm text-light-100 uppercase tracking-wide transition-colors"
                onClick={handleLogout}
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="text-xs text-light-400 uppercase tracking-wide">Username</label>
                <input
                  type="text"
                  className="w-full mt-1 px-3 py-2 bg-dark-800 border border-dark-700 rounded focus:outline-none focus:border-cyan-500 text-black"
                  value={credentials.username}
                  onChange={(e) => setCredentials({ ...credentials, username: e.target.value })}
                  autoComplete="username"
                  required
                />
              </div>
              <div>
                <label className="text-xs text-light-400 uppercase tracking-wide">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    className="w-full mt-1 px-3 py-2 pr-10 bg-dark-800 border border-dark-700 rounded focus:outline-none focus:border-cyan-500 text-black"
                    value={credentials.password}
                    onChange={(e) => setCredentials({ ...credentials, password: e.target.value })}
                    autoComplete="current-password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-dark-400 hover:text-dark-200 focus:outline-none"
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
              {error && <p className="text-xs text-red-400">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-owl-purple-500 hover:bg-owl-purple-600 rounded text-sm text-white transition-colors disabled:opacity-50"
              >
                <LogIn className="w-4 h-4" />
                {loading ? 'Signing in…' : 'Login'}
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
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      {content}
    </div>
  );
}

