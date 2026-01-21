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
  Folder,
  AlertCircle,
} from 'lucide-react';
import { profilesAPI, llmConfigAPI } from '../services/api';

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
  const [ingestionLLMProvider, setIngestionLLMProvider] = useState('ollama');
  const [ingestionLLMModelId, setIngestionLLMModelId] = useState('');
  const [availableModels, setAvailableModels] = useState([]);
  const [loadingModels, setLoadingModels] = useState(false);
  
  // Chat Configuration
  const [chatSystemContext, setChatSystemContext] = useState('');
  const [chatAnalysisGuidance, setChatAnalysisGuidance] = useState('');
  const [chatTemperature, setChatTemperature] = useState(1.0);
  
  // Folder Processing Configuration
  const [folderProcessingJson, setFolderProcessingJson] = useState('');

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

  // Load available LLM models
  const loadAvailableModels = useCallback(async (isNewProfile = false) => {
    setLoadingModels(true);
    try {
      const modelsData = await llmConfigAPI.getModels();
      setAvailableModels(modelsData.models || []);
      
      // Only set default model if creating a new profile and no model is set
      if (isNewProfile && !ingestionLLMModelId && modelsData.models && modelsData.models.length > 0) {
        const openaiModels = modelsData.models.filter(m => m.provider === 'openai');
        if (openaiModels.length > 0) {
          const defaultModel = openaiModels.find(m => m.id === 'gpt-5') || openaiModels[0];
          setIngestionLLMModelId(defaultModel.id);
          setIngestionLLMProvider('openai');
        }
      }
    } catch (err) {
      console.error('Failed to load models:', err);
    } finally {
      setLoadingModels(false);
    }
  }, [ingestionLLMModelId]);

  // Load available profiles for cloning (only when creating new profile)
  useEffect(() => {
    if (isOpen && !profileName) {
      loadAvailableProfiles();
    }
  }, [isOpen, profileName]);

  // Load available models when modal opens
  useEffect(() => {
    if (isOpen) {
      // Only set defaults if creating a new profile (no profileName)
      loadAvailableModels(!profileName);
    }
  }, [isOpen, profileName, loadAvailableModels]);

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
    setIngestionLLMProvider('openai');
    setIngestionLLMModelId('gpt-5');
      setChatSystemContext('');
      setChatAnalysisGuidance('');
      setChatTemperature(1.0);
      setFolderProcessingJson('');
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
      
      // Load LLM config from profile
      const llmConfig = profile.llm_config || {};
      if (llmConfig.provider) {
        setIngestionLLMProvider(llmConfig.provider);
      } else {
        setIngestionLLMProvider('ollama');
      }
      if (llmConfig.model_id) {
        setIngestionLLMModelId(llmConfig.model_id);
      } else {
        setIngestionLLMModelId('');
      }
      
      setChatSystemContext(chat.system_context || '');
      setChatAnalysisGuidance(chat.analysis_guidance || '');
      setChatTemperature(chat.temperature !== undefined ? chat.temperature : 1.0);
      
      // Load folder_processing config when cloning
      const folderProcessing = profile.folder_processing || null;
      setFolderProcessingJson(folderProcessing ? JSON.stringify(folderProcessing, null, 2) : '');
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
      
      // Load LLM config from profile
      const llmConfig = profile.llm_config || {};
      if (llmConfig.provider) {
        setIngestionLLMProvider(llmConfig.provider);
      } else {
        setIngestionLLMProvider('ollama');
      }
      if (llmConfig.model_id) {
        setIngestionLLMModelId(llmConfig.model_id);
      } else {
        setIngestionLLMModelId('');
      }
      
      setChatSystemContext(chat.system_context || '');
      setChatAnalysisGuidance(chat.analysis_guidance || '');
      setChatTemperature(chat.temperature !== undefined ? chat.temperature : 1.0);
      
      // Load folder_processing config
      const folderProcessing = profile.folder_processing || null;
      setFolderProcessingJson(folderProcessing ? JSON.stringify(folderProcessing, null, 2) : '');
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
        llm_provider: ingestionLLMProvider,
        llm_model_id: ingestionLLMModelId,
        // Chat config
        chat_system_context: chatSystemContext.trim() || null,
        chat_analysis_guidance: chatAnalysisGuidance.trim() || null,
        chat_temperature: chatTemperature,
      };
      
      // Parse folder_processing JSON if provided
      if (folderProcessingJson.trim()) {
        try {
          profileData.folder_processing = JSON.parse(folderProcessingJson.trim());
        } catch (parseErr) {
          setError(`Invalid folder processing JSON: ${parseErr.message}`);
          setSaving(false);
          return;
        }
      }
      
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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col border border-light-200 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              {profileName ? 'Edit Profile' : 'Create Profile'}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="p-1 hover:bg-light-100 rounded transition-colors"
            >
              <X className="w-5 h-5 text-light-600" />
            </button>
          </div>
        </div>

        {/* Content - scrollable */}
        <div className="flex-1 overflow-y-auto space-y-4 pr-2">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-light-600">Loading profile...</div>
            </div>
          ) : (
            <>
              {/* Error Message */}
              {error && (
                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-red-800">{error}</p>
                </div>
              )}

              {/* Basic Information */}
              <div>
                <h3 className="text-sm font-semibold text-light-700 mb-3 flex items-center gap-2">
                  <Info className="w-4 h-4" />
                  Basic Information
                </h3>

                {/* Clone from existing profile (only for new profiles) */}
                {!profileName && (
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
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
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 focus:outline-none focus:border-owl-blue-500"
                      disabled={loadingProfiles || loading}
                    >
                      <option value="">-- Start from scratch --</option>
                      {availableProfiles.map((profile) => (
                        <option key={profile.name} value={profile.name}>
                          {profile.name} - {profile.description}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-light-600 mt-1">
                      Select a profile to clone its settings, then modify as needed.
                    </p>
                  </div>
                )}
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      Profile Name *
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
                      placeholder="e.g., fraud, terrorism"
                      disabled={!!profileName}
                    />
                    <p className="text-xs text-light-600 mt-1">
                      Lowercase letters, numbers, hyphens, underscores only
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      Case Type
                    </label>
                    <input
                      type="text"
                      value={caseType}
                      onChange={(e) => setCaseType(e.target.value)}
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
                      placeholder="e.g., Fraud Investigation"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      Description *
                    </label>
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={3}
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 resize-none"
                      placeholder="Brief description of what this profile is for"
                    />
                  </div>
                </div>
              </div>

              {/* Ingestion Configuration */}
              <div>
                <h3 className="text-sm font-semibold text-light-700 mb-3 flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Ingestion Configuration
                </h3>
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      System Context *
                    </label>
                    <textarea
                      value={ingestionSystemContext}
                      onChange={(e) => setIngestionSystemContext(e.target.value)}
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 font-mono text-sm resize-none"
                      rows={6}
                      placeholder="You are an expert analyst extracting entities and relationships from documents. Focus on identifying key people, organizations, locations, events, and their connections..."
                    />
                  </div>

                  {/* Special Entity Types */}
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <label className="block text-sm font-medium text-light-700">
                        Special Entity Types (Optional)
                      </label>
                      <button
                        onClick={handleAddSpecialEntityType}
                        className="flex items-center gap-1 px-3 py-1.5 text-sm text-owl-blue-700 hover:bg-owl-blue-50 rounded-lg transition-colors"
                      >
                        <Plus className="w-4 h-4" />
                        Add Type
                      </button>
                    </div>
                    <p className="text-xs text-light-600 mb-3">
                      Define domain-specific entity types for the LLM to extract (e.g., ShellCompany, NomineeDirector)
                    </p>

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
                              className="px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
                              placeholder="Entity name (e.g., ShellCompany)"
                            />
                            <input
                              type="text"
                              value={entity.description || ''}
                              onChange={(e) => handleUpdateSpecialEntityType(index, 'description', e.target.value)}
                              className="px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
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

                  {/* LLM Provider and Model Selection */}
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      LLM Provider & Model
                    </label>
                    <p className="text-xs text-light-600 mb-3">
                      Select the LLM provider and model to use for entity extraction during document ingestion.
                    </p>
                  
                  <div>
                    <label className="block text-xs font-medium text-light-700 mb-2">
                      Provider
                    </label>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setIngestionLLMProvider('ollama');
                          // Set default model for provider
                          const ollamaModels = availableModels.filter(m => m.provider === 'ollama');
                          if (ollamaModels.length > 0) {
                            const defaultModel = ollamaModels.find(m => m.id === 'qwen2.5:7b-instruct') || ollamaModels[0];
                            setIngestionLLMModelId(defaultModel.id);
                          }
                        }}
                        className={`flex-1 px-3 py-2 text-sm rounded transition-colors ${
                          ingestionLLMProvider === 'ollama'
                            ? 'bg-owl-blue-600 text-white'
                            : 'bg-white border border-light-300 text-light-700 hover:bg-light-100'
                        }`}
                      >
                        Ollama (Local)
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setIngestionLLMProvider('openai');
                          // Set default model for provider
                          const openaiModels = availableModels.filter(m => m.provider === 'openai');
                          if (openaiModels.length > 0) {
                            const defaultModel = openaiModels.find(m => m.id === 'gpt-5') || openaiModels[0];
                            setIngestionLLMModelId(defaultModel.id);
                          }
                        }}
                        className={`flex-1 px-3 py-2 text-sm rounded transition-colors ${
                          ingestionLLMProvider === 'openai'
                            ? 'bg-owl-blue-600 text-white'
                            : 'bg-white border border-light-300 text-light-700 hover:bg-light-100'
                        }`}
                      >
                        OpenAI (Remote)
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-light-700 mb-2">
                      Model
                    </label>
                    {loadingModels ? (
                      <div className="text-xs text-light-500">Loading models...</div>
                    ) : (
                      <select
                        value={ingestionLLMModelId}
                        onChange={(e) => setIngestionLLMModelId(e.target.value)}
                        className="w-full px-3 py-2 text-sm bg-white border border-light-300 rounded-lg text-light-900 focus:outline-none focus:border-owl-blue-500"
                      >
                        <option value="">-- Select a model --</option>
                        {availableModels
                          .filter(m => m.provider === ingestionLLMProvider)
                          .map(model => (
                            <option key={model.id} value={model.id}>
                              {model.name}
                            </option>
                          ))}
                      </select>
                    )}
                  </div>

                  {/* Model Info */}
                  {(() => {
                    const selectedModel = availableModels.find(m => m.id === ingestionLLMModelId);
                    if (!selectedModel) return null;
                    
                    return (
                      <div className="p-3 bg-light-50 rounded border border-light-200">
                        <div className="flex items-start gap-2">
                          <Info className="w-4 h-4 text-owl-blue-600 mt-0.5 flex-shrink-0" />
                          <div className="flex-1">
                            <p className="text-xs text-light-700 mb-2">{selectedModel.description}</p>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div>
                                <p className="font-medium text-light-900 mb-1">Pros:</p>
                                <ul className="text-light-600 space-y-0.5">
                                  {selectedModel.pros.slice(0, 3).map((pro, i) => (
                                    <li key={i}>• {pro}</li>
                                  ))}
                                </ul>
                              </div>
                              <div>
                                <p className="font-medium text-light-900 mb-1">Cons:</p>
                                <ul className="text-light-600 space-y-0.5">
                                  {selectedModel.cons.slice(0, 3).map((con, i) => (
                                    <li key={i}>• {con}</li>
                                  ))}
                                </ul>
                              </div>
                            </div>
                            {selectedModel.context_window && (
                              <p className="text-xs text-light-500 mt-2">
                                Context Window: {selectedModel.context_window.toLocaleString()} tokens
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                  </div>

                  {/* Ingestion Temperature */}
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      Temperature (Ingestion)
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
                        className="w-20 px-2 py-1 bg-white border border-light-300 rounded-lg text-light-900 focus:outline-none focus:border-owl-blue-500"
                      />
                    </div>
                    <p className="text-xs text-light-600 mt-1">
                      Lower (0.0-0.5) = more deterministic extraction. Higher (1.0-2.0) = more creative. Default: 1.0
                    </p>
                  </div>
                </div>
              </div>

              {/* Chat Configuration */}
              <div>
                <h3 className="text-sm font-semibold text-light-700 mb-3 flex items-center gap-2">
                  <MessageSquare className="w-4 h-4" />
                  Chat Configuration
                </h3>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      System Context
                    </label>
                    <textarea
                      value={chatSystemContext}
                      onChange={(e) => setChatSystemContext(e.target.value)}
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 resize-none"
                      rows={3}
                      placeholder="You are an AI assistant helping investigators analyze case documents..."
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      Analysis Guidance
                    </label>
                    <textarea
                      value={chatAnalysisGuidance}
                      onChange={(e) => setChatAnalysisGuidance(e.target.value)}
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 resize-none"
                      rows={3}
                      placeholder="Identify suspicious patterns, highlight connections, and flag potential red flags..."
                    />
                  </div>

                  {/* Chat Temperature */}
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      Temperature (Chat)
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
                      className="w-20 px-2 py-1 bg-white border border-light-300 rounded-lg text-light-900 focus:outline-none focus:border-owl-blue-500"
                    />
                  </div>
                  <p className="text-xs text-light-600 mt-1">
                    Lower = more focused answers. Higher = more creative responses. Default: 1.0
                  </p>
                  </div>
                </div>
              </div>

              {/* Folder Processing Configuration */}
              {profileName && (
                <div>
                  <h3 className="text-sm font-semibold text-light-700 mb-3 flex items-center gap-2">
                    <Folder className="w-4 h-4" />
                    Folder Processing Configuration
                  </h3>
                  
                  <div>
                    <label className="block text-sm font-medium text-light-700 mb-2">
                      Folder Processing Rules (JSON)
                    </label>
                    <textarea
                      value={folderProcessingJson}
                      onChange={(e) => setFolderProcessingJson(e.target.value)}
                      className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 font-mono text-xs resize-none"
                      rows={20}
                      placeholder='{\n  "type": "special",\n  "file_rules": [...],\n  "processing_rules": "...",\n  "output_format": "wiretap_structured"\n}'
                    />
                    <p className="text-xs text-light-600 mt-1">
                      JSON configuration for folder processing. Leave empty if this profile does not handle folder processing.
                      <br />
                      <strong>Note:</strong> Invalid JSON will prevent saving. The folder_processing configuration will be preserved when editing other profile fields.
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-light-200 flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-light-700 hover:bg-light-100 rounded-lg transition-colors"
            disabled={saving}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="flex items-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving...' : 'Save Profile'}
          </button>
        </div>
      </div>
    </div>
  );
}

