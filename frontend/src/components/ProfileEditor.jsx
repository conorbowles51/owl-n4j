import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  Save,
  Plus,
  Trash2,
  Settings,
  ChevronDown,
  ChevronUp,
  Info,
} from 'lucide-react';
import { profilesAPI, llmConfigAPI } from '../services/api';

/**
 * ProfileEditor Component
 * 
 * Allows users to create or edit LLM profiles for evidence processing.
 */
export default function ProfileEditor({ isOpen, onClose, profileName = null }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  
  // Available profiles for cloning
  const [availableProfiles, setAvailableProfiles] = useState([]);
  const [cloneFromProfile, setCloneFromProfile] = useState('');
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  
  // Form fields
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [caseType, setCaseType] = useState('');
  const [agentDescription, setAgentDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [characteristics, setCharacteristics] = useState('');
  const [chatSystemContext, setChatSystemContext] = useState('');
  const [chatAnalysisGuidance, setChatAnalysisGuidance] = useState('');
  const [temperature, setTemperature] = useState(1.0);
  
  // LLM Configuration
  const [llmProvider, setLlmProvider] = useState('ollama');
  const [llmModelId, setLlmModelId] = useState('qwen2.5:32b-instruct');
  const [availableModels, setAvailableModels] = useState([]);
  
  // Entities list
  const [entities, setEntities] = useState([]);
  
  // Relationship examples
  const [relationshipExamples, setRelationshipExamples] = useState(['']);
  
  // Generate a random hex color
  const generateRandomColor = () => {
    const colors = [
      '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
      '#6366F1', '#EC4899', '#14B8A6', '#6B7280', '#F97316',
      '#06B6D4', '#84CC16', '#A855F7', '#F43F5E', '#0EA5E9',
      '#22C55E', '#EAB308', '#DC2626', '#9333EA', '#EC4899',
    ];
    return colors[Math.floor(Math.random() * colors.length)];
  };

  // Default entities from generic profile with random colors
  const getDefaultEntities = () => [
    { name: 'Person', color: generateRandomColor(), description: 'Individual people mentioned in documents' },
    { name: 'Organisation', color: generateRandomColor(), description: 'Companies, institutions, or groups' },
    { name: 'Location', color: generateRandomColor(), description: 'Geographic locations, addresses, places' },
    { name: 'Event', color: generateRandomColor(), description: 'Occurrences, incidents, happenings' },
    { name: 'Date', color: generateRandomColor(), description: 'Specific dates or time periods' },
    { name: 'Document', color: generateRandomColor(), description: 'Documents, files, records' },
    { name: 'Concept', color: generateRandomColor(), description: 'Abstract ideas, topics, themes' },
    { name: 'Product', color: generateRandomColor(), description: 'Products, services, items' },
    { name: 'Other', color: generateRandomColor(), description: 'Other entities not fitting the above categories' },
  ];

  // Define functions before using them in useEffect
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

  const loadAvailableModels = useCallback(async () => {
    try {
      console.log('[ProfileEditor] Loading available models...');
      const modelsData = await llmConfigAPI.getModels();
      console.log('[ProfileEditor] Models data received:', modelsData);
      const models = modelsData.models || modelsData || [];
      console.log('[ProfileEditor] Setting models:', models.length, 'models');
      setAvailableModels(models);
    } catch (err) {
      console.error('[ProfileEditor] Failed to load models:', err);
      setAvailableModels([]);
    }
  }, []);

  // Load available profiles for cloning (only when creating new profile)
  useEffect(() => {
    if (isOpen && !profileName) {
      loadAvailableProfiles();
    }
  }, [isOpen, profileName]);

  // Load models and profile when modal opens
  useEffect(() => {
    if (isOpen) {
      loadAvailableModels();
      if (profileName) {
        loadProfile();
        setCloneFromProfile(''); // Clear clone selection when editing
      } else {
        // New profile - initialize with defaults (with random colors)
        resetToDefaults();
      }
    } else if (!isOpen) {
      // Reset when modal closes
      resetToDefaults();
    }
  }, [isOpen, profileName, loadAvailableModels]);

  // Handle cloning when a profile is selected
  useEffect(() => {
    if (!isOpen || profileName) return; // Only for new profiles when modal is open
    
    if (cloneFromProfile) {
      cloneProfile(cloneFromProfile);
    }
    // Note: We don't reset when cloneFromProfile is empty because that would
    // interfere with the initial reset when the modal opens
  }, [cloneFromProfile, isOpen, profileName]);

  const resetToDefaults = () => {
    setName('');
    setDescription('');
    setCaseType('');
    setAgentDescription('');
    setInstructions('');
    setCharacteristics('');
    setChatSystemContext('');
    setChatAnalysisGuidance('');
    setTemperature(1.0);
    setLlmProvider('ollama');
    setLlmModelId('qwen2.5:32b-instruct');
    setEntities(getDefaultEntities().map(e => ({ ...e })));
    setRelationshipExamples(['Person works for Organisation', 'Event occurred at Location']);
    setCloneFromProfile('');
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
      setAgentDescription(profile.agent_description || '');
      setInstructions(profile.instructions || '');
      setCharacteristics(profile.characteristics || '');
      
      const ingestion = profile.ingestion || {};
      const chat = profile.chat || {};
      
      setChatSystemContext(chat.system_context || '');
      setChatAnalysisGuidance(chat.analysis_guidance || '');
      setTemperature(ingestion.temperature !== undefined ? ingestion.temperature : 1.0);
      
      // Load entities
      const entityTypes = ingestion.entity_types || [];
      const entityDefs = ingestion.entity_definitions || {};
      const loadedEntities = entityTypes.map(type => ({
        name: type,
        color: entityDefs[type]?.color || generateRandomColor(),
        description: entityDefs[type]?.description || '',
      }));
      setEntities(loadedEntities.length > 0 ? loadedEntities : getDefaultEntities().map(e => ({ ...e })));
      
      // Load relationship examples
      const examples = ingestion.relationship_examples || [];
      setRelationshipExamples(examples.length > 0 ? examples : ['Person works for Organisation', 'Event occurred at Location']);
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
      setAgentDescription(profile.agent_description || '');
      setInstructions(profile.instructions || '');
      setCharacteristics(profile.characteristics || '');
      
      const ingestion = profile.ingestion || {};
      const chat = profile.chat || {};
      
      setChatSystemContext(chat.system_context || '');
      setChatAnalysisGuidance(chat.analysis_guidance || '');
      setTemperature(ingestion.temperature !== undefined ? ingestion.temperature : 1.0);
      
      // Load LLM configuration
      const llmConfig = profile.llm_config || {};
      setLlmProvider(llmConfig.provider || 'ollama');
      setLlmModelId(llmConfig.model_id || 'qwen2.5:32b-instruct');
      
      // Load entities
      const entityTypes = ingestion.entity_types || [];
      const entityDefs = ingestion.entity_definitions || {};
      const loadedEntities = entityTypes.map(type => ({
        name: type,
        color: entityDefs[type]?.color || generateRandomColor(),
        description: entityDefs[type]?.description || '',
      }));
      setEntities(loadedEntities.length > 0 ? loadedEntities : getDefaultEntities().map(e => ({ ...e })));
      
      // Load relationship examples
      const examples = ingestion.relationship_examples || [];
      setRelationshipExamples(examples.length > 0 ? examples : ['']);
    } catch (err) {
      console.error('Failed to load profile:', err);
      setError(err.message || 'Failed to load profile');
    } finally {
      setLoading(false);
    }
  };

  const handleAddEntity = () => {
    setEntities([{ name: '', color: generateRandomColor(), description: '' }, ...entities]);
  };

  const handleRemoveEntity = (index) => {
    setEntities(entities.filter((_, i) => i !== index));
  };

  const handleUpdateEntity = (index, field, value) => {
    const updated = [...entities];
    updated[index] = { ...updated[index], [field]: value };
    setEntities(updated);
  };

  const handleAddRelationshipExample = () => {
    setRelationshipExamples([...relationshipExamples, '']);
  };

  const handleRemoveRelationshipExample = (index) => {
    setRelationshipExamples(relationshipExamples.filter((_, i) => i !== index));
  };

  const handleUpdateRelationshipExample = (index, value) => {
    const updated = [...relationshipExamples];
    updated[index] = value;
    setRelationshipExamples(updated);
  };

  const handleSave = async () => {
    if (!name.trim()) {
      setError('Profile name is required');
      return;
    }
    
    if (entities.length === 0) {
      setError('At least one entity type is required');
      return;
    }
    
    if (entities.some(e => !e.name.trim())) {
      setError('All entities must have a name');
      return;
    }
    
    setSaving(true);
    setError(null);
    
    try {
      const profileData = {
        name: name.trim(),
        description: description.trim(),
        case_type: caseType.trim() || null,
        agent_description: agentDescription.trim() || null,
        instructions: instructions.trim() || null,
        characteristics: characteristics.trim() || null,
        entities: entities.map(e => ({
          name: e.name.trim(),
          color: e.color,
          description: e.description.trim() || null,
        })),
        relationship_examples: relationshipExamples.filter(e => e.trim()).map(e => e.trim()),
        chat_system_context: chatSystemContext.trim() || null,
        chat_analysis_guidance: chatAnalysisGuidance.trim() || null,
        temperature: temperature,
        llm_provider: llmProvider,
        llm_model_id: llmModelId,
      };
      
      await profilesAPI.save(profileData);
      alert('Profile saved successfully!');
      onClose();
      // Reload window to refresh profile list
      window.location.reload();
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
              {profileName ? 'Edit LLM Profile' : 'Create LLM Profile'}
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
                <h3 className="text-sm font-semibold text-light-900 uppercase tracking-wide">
                  Basic Information
                </h3>

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
                          // Reset to defaults if "Start from scratch" is selected
                          const currentName = name; // Preserve name if user has typed it
                          resetToDefaults();
                          if (currentName) {
                            setName(currentName); // Restore name
                          }
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
                      Select a profile to clone its settings. You can modify all fields after cloning.
                    </p>
                  </div>
                )}
                
                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    Profile Name *
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    placeholder="e.g., fraud, money-laundering"
                    disabled={!!profileName} // Can't change name when editing
                  />
                  <p className="text-xs text-light-500 mt-1">
                    Use lowercase letters, numbers, hyphens, and underscores only
                  </p>
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
                    placeholder="Brief description of this profile"
                  />
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
                    placeholder="e.g., Fraud Investigation, Money Laundering Case"
                  />
                </div>
              </div>

              {/* Agent Configuration */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-light-900 uppercase tracking-wide">
                  Agent Configuration
                </h3>

                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    Agent Description
                  </label>
                  <textarea
                    value={agentDescription}
                    onChange={(e) => setAgentDescription(e.target.value)}
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    rows={3}
                    placeholder="Describe what kind of agent this is and its role"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    Instructions
                  </label>
                  <textarea
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    rows={4}
                    placeholder="Specific instructions on how the agent should behave and what to look for when processing documents"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-light-700 mb-1">
                    Characteristics
                  </label>
                  <textarea
                    value={characteristics}
                    onChange={(e) => setCharacteristics(e.target.value)}
                    className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    rows={3}
                    placeholder="Describe the characteristics the agent should have"
                  />
                </div>
              </div>

              {/* Entity Types */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-light-900 uppercase tracking-wide">
                    Entity Types
                  </h3>
                  <button
                    onClick={handleAddEntity}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm text-owl-blue-700 hover:bg-owl-blue-50 rounded-lg transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Add Entity
                  </button>
                </div>

                <div className="space-y-3">
                  {entities.map((entity, index) => (
                    <div
                      key={index}
                      className="flex items-start gap-3 p-4 border border-light-300 rounded-lg bg-light-50"
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={entity.color}
                          onChange={(e) => handleUpdateEntity(index, 'color', e.target.value)}
                          className="w-12 h-10 border border-light-300 rounded cursor-pointer"
                          title="Node color"
                        />
                      </div>
                      <div className="flex-1 space-y-2">
                        <input
                          type="text"
                          value={entity.name}
                          onChange={(e) => handleUpdateEntity(index, 'name', e.target.value)}
                          className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                          placeholder="Entity name (e.g., Person, Company)"
                        />
                        <textarea
                          value={entity.description}
                          onChange={(e) => handleUpdateEntity(index, 'description', e.target.value)}
                          className="w-full px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500 text-sm"
                          rows={2}
                          placeholder="Instructions for the LLM on how to identify this entity type in documents"
                        />
                      </div>
                      <button
                        onClick={() => handleRemoveEntity(index)}
                        className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        title="Remove entity"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Relationship Examples */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-light-900 uppercase tracking-wide">
                      Relationship Examples
                    </h3>
                    <p className="text-xs text-light-500 mt-1">
                      Provide examples of relationships. The LLM will infer similar relationships from documents.
                    </p>
                  </div>
                  <button
                    onClick={handleAddRelationshipExample}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm text-owl-blue-700 hover:bg-owl-blue-50 rounded-lg transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Add Example
                  </button>
                </div>

                <div className="space-y-2">
                  {relationshipExamples.map((example, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={example}
                        onChange={(e) => handleUpdateRelationshipExample(index, e.target.value)}
                        className="flex-1 px-3 py-2 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                        placeholder="e.g., Person works for Organisation, Event occurred at Location"
                      />
                      <button
                        onClick={() => handleRemoveRelationshipExample(index)}
                        className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                        title="Remove example"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* LLM Configuration */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-light-900 uppercase tracking-wide">
                  LLM Configuration
                </h3>

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
                      value={temperature}
                      onChange={(e) => setTemperature(parseFloat(e.target.value))}
                      className="flex-1"
                    />
                    <input
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={temperature}
                      onChange={(e) => {
                        const val = parseFloat(e.target.value);
                        if (!isNaN(val) && val >= 0 && val <= 2) {
                          setTemperature(val);
                        }
                      }}
                      className="w-20 px-2 py-1 border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500"
                    />
                  </div>
                  <p className="text-xs text-light-500 mt-1">
                    Controls creativity: Lower (0.0-0.5) = more deterministic, Higher (1.0-2.0) = more creative. Default: 1.0
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-light-700 mb-2">
                    LLM Provider
                  </label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setLlmProvider('ollama');
                        // Set default model for provider
                        const ollamaModels = availableModels.filter(m => m.provider === 'ollama');
                        if (ollamaModels.length > 0) {
                          const defaultModel = ollamaModels.find(m => m.id === 'qwen2.5:32b-instruct') || ollamaModels[0];
                          setLlmModelId(defaultModel.id);
                        }
                      }}
                      className={`flex-1 px-3 py-2 text-sm rounded transition-colors ${
                        llmProvider === 'ollama'
                          ? 'bg-owl-purple-500 text-white'
                          : 'bg-white border border-light-300 text-light-700 hover:bg-light-100'
                      }`}
                    >
                      Ollama (Local)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setLlmProvider('openai');
                        // Set default model for provider
                        const openaiModels = availableModels.filter(m => m.provider === 'openai');
                        if (openaiModels.length > 0) {
                          const defaultModel = openaiModels.find(m => m.id === 'gpt-4o') || openaiModels[0];
                          setLlmModelId(defaultModel.id);
                        }
                      }}
                      className={`flex-1 px-3 py-2 text-sm rounded transition-colors ${
                        llmProvider === 'openai'
                          ? 'bg-owl-purple-500 text-white'
                          : 'bg-white border border-light-300 text-light-700 hover:bg-light-100'
                      }`}
                    >
                      OpenAI (Remote)
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-light-700 mb-2">
                    Model
                  </label>
                  {availableModels.length === 0 ? (
                    <div className="px-3 py-2 text-sm text-light-500 border border-light-300 rounded-lg bg-light-50">
                      Loading models...
                    </div>
                  ) : (
                    <select
                      value={llmModelId}
                      onChange={(e) => setLlmModelId(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-light-300 rounded-lg focus:outline-none focus:border-owl-blue-500 bg-white"
                    >
                      {availableModels
                        .filter(m => m.provider === llmProvider)
                        .map(model => (
                          <option key={model.id} value={model.id}>
                            {model.name}
                          </option>
                        ))}
                    </select>
                  )}
                  {availableModels.filter(m => m.provider === llmProvider).length === 0 && availableModels.length > 0 && (
                    <p className="text-xs text-red-600 mt-1">
                      No models available for {llmProvider === 'ollama' ? 'Ollama' : 'OpenAI'}
                    </p>
                  )}
                </div>

                {/* Model Info */}
                {availableModels.length > 0 && (() => {
                  const selectedModel = availableModels.find(m => m.id === llmModelId);
                  if (!selectedModel) {
                    return (
                      <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                        <p className="text-xs text-yellow-800">
                          Selected model "{llmModelId}" not found in available models. Please select a different model.
                        </p>
                      </div>
                    );
                  }
                  
                  return (
                    <div className="p-3 bg-light-50 rounded-lg border border-light-200">
                      <div className="flex items-start gap-2 mb-2">
                        <Info className="w-4 h-4 text-owl-purple-600 mt-0.5 flex-shrink-0" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-light-900 mb-2">{selectedModel.name}</p>
                          <p className="text-xs text-light-700 mb-3">{selectedModel.description}</p>
                          <div className="grid grid-cols-2 gap-3 text-xs">
                            <div>
                              <p className="font-medium text-light-900 mb-1">Pros:</p>
                              <ul className="text-light-600 space-y-0.5">
                                {selectedModel.pros.map((pro, i) => (
                                  <li key={i}>• {pro}</li>
                                ))}
                              </ul>
                            </div>
                            <div>
                              <p className="font-medium text-light-900 mb-1">Cons:</p>
                              <ul className="text-light-600 space-y-0.5">
                                {selectedModel.cons.map((con, i) => (
                                  <li key={i}>• {con}</li>
                                ))}
                              </ul>
                            </div>
                          </div>
                          {selectedModel.context_window && (
                            <p className="text-xs text-light-500 mt-3 pt-2 border-t border-light-200">
                              <span className="font-medium">Context Window:</span> {selectedModel.context_window.toLocaleString()} tokens
                            </p>
                          )}
                          {selectedModel.parameters && selectedModel.parameters !== 'N/A' && (
                            <p className="text-xs text-light-500 mt-1">
                              <span className="font-medium">Parameters:</span> {selectedModel.parameters}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>

              {/* Chat Configuration */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold text-light-900 uppercase tracking-wide">
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
                    placeholder="System context for chat interactions"
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
                    placeholder="Guidance for analysis and responses"
                  />
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

