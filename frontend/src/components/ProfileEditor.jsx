import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  Save,
  Plus,
  Trash2,
  Settings,
  Info,
  FileText,
  MessageSquare,
} from 'lucide-react';
import { profilesAPI } from '../services/api';

/**
 * ProfileEditor Component
 * 
 * Allows users to create or edit LLM profiles for evidence processing.
 * 
 * Profile Structure:
 * {
 *   name: "profile_name",
 *   description: "Profile description",
 *   case_type: "Type of case",
 *   ingestion: {
 *     system_context: "System prompt for entity extraction",
 *     special_entity_types: [{ name: "EntityType", description: "Description" }],
 *     temperature: 1.0
 *   },
 *   chat: {
 *     system_context: "System prompt for chat",
 *     analysis_guidance: "Guidance for analysis",
 *     temperature: 1.0
 *   }
 * }
 */
export default function ProfileEditor({ isOpen, onClose, profileName = null, onProfileSaved = null }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  
  // Available profiles for cloning
  const [availableProfiles, setAvailableProfiles] = useState([]);
  const [cloneFromProfile, setCloneFromProfile] = useState('');
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  
  // Basic Information
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [caseType, setCaseType] = useState('');
  
  // Ingestion Configuration
  const [ingestionSystemContext, setIngestionSystemContext] = useState('');
  const [specialEntityTypes, setSpecialEntityTypes] = useState([]);
  const [ingestionTemperature, setIngestionTemperature] = useState(1.0);
  
  // Chat Configuration
  const [chatSystemContext, setChatSystemContext] = useState('');
  const [chatAnalysisGuidance, setChatAnalysisGuidance] = useState('');
  const [chatTemperature, setChatTemperature] = useState(1.0);

  // Load available profiles for cloning
  const loadAvailableProfiles = async () => {
    setLoadingProfiles(true);
    try {
      const profiles = await profilesAPI.list();
      setAvailableProfiles(profiles || []);
    } catch (err) {
      console.error('Failed to load profiles:', err);
    } finally {
      setLoadingProfiles(false);
    }
  };

  // Load available profiles for cloning (only when creating new profile)
  useEffect(() => {
    if (isOpen && !profileName) {
      loadAvailableProfiles();
    }
  }, [isOpen, profileName]);

  // Load profile when modal opens
  useEffect(() => {
    if (isOpen) {
      if (profileName) {
        loadProfile();
        setCloneFromProfile('');
      } else {
        resetToDefaults();
      }
    } else {
      resetToDefaults();
    }
  }, [isOpen, profileName]);

  // Handle cloning when a profile is selected
  useEffect(() => {
    if (!isOpen || profileName) return;
    
    if (cloneFromProfile) {
      cloneProfile(cloneFromProfile);
    }
  }, [cloneFromProfile, isOpen, profileName]);

  const resetToDefaults = () => {
    setName('');
    setDescription('');
    setCaseType('');
    setIngestionSystemContext('');
    setSpecialEntityTypes([]);
    setIngestionTemperature(1.0);
    setChatSystemContext('');
    setChatAnalysisGuidance('');
    setChatTemperature(1.0);
    setCloneFromProfile('');
    setError(null);
  };

  const cloneProfile = async (profileNameToClone) => {
    if (!profileNameToClone) return;
    
    setLoading(true);
    setError(null);
    try {
      const profile = await profilesAPI.get(profileNameToClone);
      
      // Load all fields except name (user should set their own name)
      setDescription(profile.description || '');
      setCaseType(profile.case_type || '');
      
      const ingestion = profile.ingestion || {};
      const chat = profile.chat || {};
      
      setIngestionSystemContext(ingestion.system_context || '');
      setSpecialEntityTypes(ingestion.special_entity_types || []);
      setIngestionTemperature(ingestion.temperature !== undefined ? ingestion.temperature : 1.0);
      
      setChatSystemContext(chat.system_context || '');
      setChatAnalysisGuidance(chat.analysis_guidance || '');
      setChatTemperature(chat.temperature !== undefined ? chat.temperature : 1.0);
    } catch (err) {
      console.error('Failed to clone profile:', err);
      setError(err.message || 'Failed to clone profile');
    } finally {
      setLoading(false);
    }
  };

  const loadProfile = async () => {
    if (!profileName) return;
    
    setLoading(true);
    setError(null);
    try {
      const profile = await profilesAPI.get(profileName);
      
      setName(profile.name || '');
      setDescription(profile.description || '');
      setCaseType(profile.case_type || '');
      
      const ingestion = profile.ingestion || {};
      const chat = profile.chat || {};
      
      setIngestionSystemContext(ingestion.system_context || '');
      setSpecialEntityTypes(ingestion.special_entity_types || []);
      setIngestionTemperature(ingestion.temperature !== undefined ? ingestion.temperature : 1.0);
      
      setChatSystemContext(chat.system_context || '');
      setChatAnalysisGuidance(chat.analysis_guidance || '');
      setChatTemperature(chat.temperature !== undefined ? chat.temperature : 1.0);
    } catch (err) {
      console.error('Failed to load profile:', err);
      setError(err.message || 'Failed to load profile');
    } finally {
      setLoading(false);
    }
  };

  // Special Entity Type handlers
  const handleAddSpecialEntityType = () => {
    setSpecialEntityTypes([{ name: '', description: '' }, ...specialEntityTypes]);
  };

  const handleRemoveSpecialEntityType = (index) => {
    setSpecialEntityTypes(specialEntityTypes.filter((_, i) => i !== index));
  };

  const handleUpdateSpecialEntityType = (index, field, value) => {
    const updated = [...specialEntityTypes];
    updated[index] = { ...updated[index], [field]: value };
    setSpecialEntityTypes(updated);
  };

  const handleSave = async () => {
    if (!name.trim()) {
      setError('Profile name is required');
      return;
    }
    
    if (!description.trim()) {
      setError('Profile description is required');
      return;
    }
    
    // Validate special entity types - if any exist, they must have names
    if (specialEntityTypes.some(e => e.name && !e.name.trim())) {
      setError('All special entity types must have a name');
      return;
    }
    
    setSaving(true);
    setError(null);
    
    try {
      const profileData = {
        name: name.trim(),
        description: description.trim(),
        case_type: caseType.trim() || null,
        // Ingestion config
        ingestion_system_context: ingestionSystemContext.trim() || null,
        special_entity_types: specialEntityTypes
          .filter(e => e.name && e.name.trim())
          .map(e => ({
            name: e.name.trim(),
            description: e.description?.trim() || null,
          })),
        ingestion_temperature: ingestionTemperature,
        // Chat config
        chat_system_context: chatSystemContext.trim() || null,
        chat_analysis_guidance: chatAnalysisGuidance.trim() || null,
        chat_temperature: chatTemperature,
      };
      
      await profilesAPI.save(profileData);
      alert('Profile saved successfully!');
      
      if (onProfileSaved) {
        onProfileSaved(name.trim());
      }
      
      onClose();
    } catch (err) {
      console.error('Failed to save profile:', err);
      setError(err.message || 'Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="w-full max-w-4xl max-h-[90vh] bg-white rounded-lg shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-light-200 bg-light-50">
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-owl-blue-700" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              {profileName ? 'Edit Profile' : 'Create Profile'}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-light-200 text-light-600 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-light-600">Loading profile...</div>
            </div>
          ) : (
            <>
              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              {/* Basic Information */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-light-900 uppercase tracking-wide flex items-center gap-2">
                  <Info className="w-4 h-4" />
                  Basic Information
                </h3>

                {/* Clone from existing profile (only for new profiles) */}
                {!profileName && (
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-1">
                      Clone from Existing Profile (Optional)
                    </label>
                    <select
                      value={cloneFromProfile}
                      onChange={(e) => {
                        const selected = e.target.value;
                        setCloneFromProfile(selected);
                        if (!selected) {
                          const currentName = name;
                          resetToDefaults();
                          if (currentName) setName(currentName);
                        }
                      }}
                      className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500 bg-white"
                      disabled={loadingProfiles || loading}
                    >
                      <option value="">-- Start from scratch --</option>
                      {availableProfiles.map((profile) => (
                        <option key={profile.name} value={profile.name}>
                          {profile.name} - {profile.description}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-light-500 mt-1">
                      Select a profile to clone its settings, then modify as needed.
                    </p>
                  </div>
                )}
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-1">
                      Profile Name *
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                      placeholder="e.g., fraud, terrorism"
                      disabled={!!profileName}
                    />
                    <p className="text-xs text-light-500 mt-1">
                      Lowercase letters, numbers, hyphens, underscores only
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-1">
                      Case Type
                    </label>
                    <input
                      type="text"
                      value={caseType}
                      onChange={(e) => setCaseType(e.target.value)}
                      className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                      placeholder="e.g., Fraud Investigation"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    Description *
                  </label>
                  <input
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    placeholder="Brief description of what this profile is for"
                  />
                </div>
              </div>

              {/* Ingestion Configuration */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-light-900 uppercase tracking-wide flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Ingestion Configuration
                </h3>
                
                <div className="bg-owl-blue-50 border border-owl-blue-200 rounded-lg p-3">
                  <p className="text-xs text-owl-blue-800">
                    <strong>Tip:</strong> The ingestion system context tells the LLM how to extract entities and relationships from documents. 
                    Be specific about what to look for and what entity types to create.
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    System Context *
                  </label>
                  <textarea
                    value={ingestionSystemContext}
                    onChange={(e) => setIngestionSystemContext(e.target.value)}
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500 font-mono text-sm"
                    rows={6}
                    placeholder="You are an expert analyst extracting entities and relationships from documents. Focus on identifying key people, organizations, locations, events, and their connections..."
                  />
                </div>

                {/* Special Entity Types */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <label className="block text-sm font-medium text-light-700">
                        Special Entity Types (Optional)
                      </label>
                      <p className="text-xs text-light-500">
                        Define domain-specific entity types for the LLM to extract (e.g., ShellCompany, NomineeDirector)
                      </p>
                    </div>
                    <button
                      onClick={handleAddSpecialEntityType}
                      className="flex items-center gap-1 px-3 py-1.5 text-sm text-owl-blue-700 hover:bg-owl-blue-50 rounded-lg transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                      Add Type
                    </button>
                  </div>

                  {specialEntityTypes.length > 0 && (
                    <div className="space-y-2">
                      {specialEntityTypes.map((entity, index) => (
                        <div
                          key={index}
                          className="flex items-start gap-3 p-3 border border-light-300 rounded-lg bg-light-50"
                        >
                          <div className="flex-1 grid grid-cols-2 gap-3">
                            <input
                              type="text"
                              value={entity.name}
                              onChange={(e) => handleUpdateSpecialEntityType(index, 'name', e.target.value)}
                              className="px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                              placeholder="Entity name (e.g., ShellCompany)"
                            />
                            <input
                              type="text"
                              value={entity.description || ''}
                              onChange={(e) => handleUpdateSpecialEntityType(index, 'description', e.target.value)}
                              className="px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                              placeholder="Description (e.g., A company used to obscure ownership)"
                            />
                          </div>
                          <button
                            onClick={() => handleRemoveSpecialEntityType(index)}
                            className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                            title="Remove entity type"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Ingestion Temperature */}
                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    Temperature
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={ingestionTemperature}
                      onChange={(e) => setIngestionTemperature(parseFloat(e.target.value))}
                      className="flex-1"
                    />
                    <input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={ingestionTemperature}
                      onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        if (!isNaN(val) && val >= 0 && val <= 2) {
                          setIngestionTemperature(val);
                        }
                      }}
                      className="w-20 px-2 py-1 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    />
                  </div>
                  <p className="text-xs text-light-500 mt-1">
                    Lower (0.0-0.5) = more deterministic extraction. Higher (1.0-2.0) = more creative. Default: 1.0
                  </p>
                </div>
              </div>

              {/* Chat Configuration */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-light-900 uppercase tracking-wide flex items-center gap-2">
                  <MessageSquare className="w-4 h-4" />
                  Chat Configuration
                </h3>

                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    System Context
                  </label>
                  <textarea
                    value={chatSystemContext}
                    onChange={(e) => setChatSystemContext(e.target.value)}
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    rows={3}
                    placeholder="You are an AI assistant helping investigators analyze case documents..."
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    Analysis Guidance
                  </label>
                  <textarea
                    value={chatAnalysisGuidance}
                    onChange={(e) => setChatAnalysisGuidance(e.target.value)}
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    rows={3}
                    placeholder="Identify suspicious patterns, highlight connections, and flag potential red flags..."
                  />
                </div>

                {/* Chat Temperature */}
                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    Temperature
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={chatTemperature}
                      onChange={(e) => setChatTemperature(parseFloat(e.target.value))}
                      className="flex-1"
                    />
                    <input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={chatTemperature}
                      onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        if (!isNaN(val) && val >= 0 && val <= 2) {
                          setChatTemperature(val);
                        }
                      }}
                      className="w-20 px-2 py-1 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    />
                  </div>
                  <p className="text-xs text-light-500 mt-1">
                    Lower = more focused answers. Higher = more creative responses. Default: 1.0
                  </p>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-light-200 bg-light-50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-light-700 hover:bg-light-200 rounded-lg transition-colors"
            disabled={saving}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="flex items-center gap-2 px-4 py-2 bg-owl-blue-600 text-white rounded-lg hover:bg-owl-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving...' : 'Save Profile'}
          </button>
        </div>
      </div>
    </div>
  );
}

