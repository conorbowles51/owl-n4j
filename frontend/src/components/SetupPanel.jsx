import React, { useState } from 'react';
import { Shield, Eye, EyeOff, User, KeyRound, Mail, UserPlus } from 'lucide-react';
import { setupAPI } from '../services/api';

export default function SetupPanel({ onSetupComplete }) {
  const [formData, setFormData] = useState({
    email: '',
    name: '',
    password: '',
    confirmPassword: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const validateForm = () => {
    if (!formData.email) {
      setError('Email is required');
      return false;
    }
    if (!formData.email.includes('@')) {
      setError('Please enter a valid email address');
      return false;
    }
    if (!formData.name) {
      setError('Name is required');
      return false;
    }
    if (!formData.password) {
      setError('Password is required');
      return false;
    }
    if (formData.password.length < 8) {
      setError('Password must be at least 8 characters');
      return false;
    }
    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match');
      return false;
    }
    return true;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');

    if (!validateForm()) {
      return;
    }

    setLoading(true);
    try {
      await setupAPI.createInitialUser({
        email: formData.email,
        name: formData.name,
        password: formData.password,
      });

      onSetupComplete();
    } catch (err) {
      setError(err.message || 'Setup failed. Please try again.');
      console.error('Setup error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white rounded-xl shadow-2xl overflow-hidden border border-light-200">
      {/* Header */}
      <div className="bg-gradient-to-r from-owl-blue-800 to-owl-blue-900 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-white/10 rounded-lg backdrop-blur-sm">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Initial Setup</h2>
            <p className="text-xs text-owl-blue-200">Create your administrator account</p>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="p-6">
        {/* Logo */}
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

        {/* Welcome message */}
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-xl">
          <p className="text-sm text-blue-800">
            Welcome! This appears to be the first time running the application.
            Please create an administrator account to get started.
          </p>
        </div>

        {/* Setup Form */}
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
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                autoComplete="email"
                required
              />
            </div>
          </div>

          {/* Name Field */}
          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Name
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <User className="w-5 h-5 text-light-400" />
              </div>
              <input
                type="text"
                className="w-full pl-10 pr-4 py-2.5 bg-light-50 border border-light-300 rounded-xl text-light-900 placeholder-light-400 focus:outline-none focus:ring-2 focus:ring-owl-blue-500/20 focus:border-owl-blue-500 transition-all duration-200"
                placeholder="Enter your name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                autoComplete="name"
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
                type={showPassword ? 'text' : 'password'}
                className="w-full pl-10 pr-12 py-2.5 bg-light-50 border border-light-300 rounded-xl text-light-900 placeholder-light-400 focus:outline-none focus:ring-2 focus:ring-owl-blue-500/20 focus:border-owl-blue-500 transition-all duration-200"
                placeholder="Enter your password (min 8 characters)"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                autoComplete="new-password"
                required
                minLength={8}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-light-400 hover:text-light-600 transition-colors"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>

          {/* Confirm Password Field */}
          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              Confirm Password
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <KeyRound className="w-5 h-5 text-light-400" />
              </div>
              <input
                type={showConfirmPassword ? 'text' : 'password'}
                className="w-full pl-10 pr-12 py-2.5 bg-light-50 border border-light-300 rounded-xl text-light-900 placeholder-light-400 focus:outline-none focus:ring-2 focus:ring-owl-blue-500/20 focus:border-owl-blue-500 transition-all duration-200"
                placeholder="Confirm your password"
                value={formData.confirmPassword}
                onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-light-400 hover:text-light-600 transition-colors"
                aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
              >
                {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-xl">
              <div className="p-1 bg-red-100 rounded-full">
                <svg className="w-4 h-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
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
                <svg
                  className="animate-spin h-5 w-5 text-white"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  ></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                <span>Creating account...</span>
              </>
            ) : (
              <>
                <UserPlus className="w-5 h-5" />
                <span>Create Administrator Account</span>
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
