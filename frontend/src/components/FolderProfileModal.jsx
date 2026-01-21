import React, { useState, useEffect, useCallback } from 'react';
import { X, FileText, Folder, Sparkles, Play, Loader2, AlertCircle, CheckCircle2, Edit2, ChevronDown, ChevronRight, Music, Save, Info, MessageSquare, Settings, Plus, Trash2 } from 'lucide-react';
import { evidenceAPI, profilesAPI, llmConfigAPI } from '../services/api';
import FilePreview from './FilePreview';

/**
 * FolderProfileModal Component
 * 
 * Modal for creating and testing folder processing profiles.
 * Allows users to:
 * - View files in a folder
 * - Select existing LLM profile and see its details
 * - Add processing instructions
 * - Generate and save a new profile
 * - Configure file processing options
 */
export default function FolderProfileModal({ 
  isOpen, 
  onClose,
  caseId,
  folderPath,
  onProfileSaved, // Callback to notify parent that a profile was saved
  editingProfileName = null, // If provided, load this profile for editing
}) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [selectedFileForPreview, setSelectedFileForPreview] = useState(null);
  
  const [profileName, setProfileName] = useState('');
  const [processingInstructions, setProcessingInstructions] = useState('');
  const [profileMode, setProfileMode] = useState('instructions'); // 'instructions' or 'existing'
  const [selectedExistingProfile, setSelectedExistingProfile] = useState('');
  const [selectedProfileDetails, setSelectedProfileDetails] = useState(null);
  const [loadingProfileDetails, setLoadingProfileDetails] = useState(false);
  const [availableProfiles, setAvailableProfiles] = useState([]);
  const [folderProcessingProfiles, setFolderProcessingProfiles] = useState([]);
  const [showEditProfiles, setShowEditProfiles] = useState(false);
  
  // Folder selection for edit mode
  const [selectedFolderPathForEdit, setSelectedFolderPathForEdit] = useState('');
  const [availableFolders, setAvailableFolders] = useState([]);
  
  // File processing configuration (from advanced modal)
  const [fileConfigs, setFileConfigs] = useState({});
  const [expandedFiles, setExpandedFiles] = useState({});
  
  // Basic Information
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
  
  // Common languages for transcription/translation
  const languages = [
    { code: 'en', name: 'English' },
    { code: 'es', name: 'Spanish' },
    { code: 'fr', name: 'French' },
    { code: 'de', name: 'German' },
    { code: 'it', name: 'Italian' },
    { code: 'pt', name: 'Portuguese' },
    { code: 'zh', name: 'Chinese' },
    { code: 'ja', name: 'Japanese' },
    { code: 'ko', name: 'Korean' },
    { code: 'ru', name: 'Russian' },
    { code: 'ar', name: 'Arabic' },
  ];
  
  // File roles for processing
  const fileRoles = [
    { value: 'audio', label: 'Audio' },
    { value: 'metadata', label: 'Metadata' },
    { value: 'interpretation', label: 'Interpretation' },
    { value: 'document', label: 'Document' },
    { value: 'ignore', label: 'Ignore' },
  ];
  
  // Load files and profiles when modal opens
  useEffect(() => {
    if (isOpen) {
      loadProfiles();
      loadAvailableModels();
      if (editingProfileName) {
        // In edit mode, load available folders
        loadAvailableFolders();
      } else if (caseId && folderPath) {
        // In create mode, load files from the provided folder
        loadFolderFiles();
      }
    }
  }, [isOpen, caseId, folderPath, editingProfileName]);
  
  // Load files when folder is selected in edit mode (user must click "Load Files" button)
  // Removed auto-load to avoid unnecessary API calls
  
  // Load available folders from evidence files
  const loadAvailableFolders = async () => {
    if (!caseId) return;
    
    try {
      const res = await evidenceAPI.list(caseId);
      const evidenceFiles = res?.files || [];
      
      // Extract unique folder paths from evidence files
      const folders = new Set();
      evidenceFiles.forEach(file => {
        if (file.stored_path) {
          // Extract folder path (everything except the filename)
          const pathParts = file.stored_path.split('/');
          if (pathParts.length > 1) {
            pathParts.pop(); // Remove filename
            const folderPath = pathParts.join('/');
            if (folderPath) {
              folders.add(folderPath);
            }
          }
        }
      });
      
      // Also check for common wiretap folder patterns
      evidenceFiles.forEach(file => {
        const filename = file.original_filename || file.stored_path || '';
        // Check for wiretap folder pattern (e.g., 00000174)
        const wiretapMatch = filename.match(/^(\d{8})/);
        if (wiretapMatch) {
          folders.add(wiretapMatch[1]);
        }
      });
      
      setAvailableFolders(Array.from(folders).sort());
    } catch (err) {
      console.error('Failed to load available folders:', err);
    }
  };
  
  // Load folder files for a specific path (used in edit mode)
  const loadFolderFilesForPath = async (pathToLoad) => {
    if (!caseId || !pathToLoad) {
      setError('Case ID and folder path are required');
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      const response = await evidenceAPI.listFolderFiles(caseId, pathToLoad);
      setFiles(response.files || []);
      // After loading files, initialize file configs if not already set
      if (response.files && response.files.length > 0) {
        // Don't overwrite existing configs, just add new ones
        const existingConfigs = { ...fileConfigs };
        response.files.filter(f => f.type === 'file').forEach(file => {
          if (!existingConfigs[file.path]) {
            // Initialize default config for files not already configured
            const ext = file.name.split('.').pop()?.toLowerCase() || '';
            const isAudio = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(ext);
            const isSRI = ['sri'].includes(ext);
            const isRTF = ['rtf'].includes(ext);
            
            let defaultRole = 'ignore';
            if (isAudio) defaultRole = 'audio';
            else if (isSRI) defaultRole = 'metadata';
            else if (isRTF) defaultRole = 'interpretation';
            
            existingConfigs[file.path] = {
              selected: defaultRole !== 'ignore',
              role: defaultRole,
              options: {
                transcribe: isAudio,
                translate: isAudio,
                transcribeLanguage: isAudio ? 'es' : '',
                translateLanguages: isAudio ? ['en'] : [],
                parser: isSRI ? 'sri' : (isRTF ? 'rtf' : ''),
                extractParticipants: isRTF,
                extractInterpretation: isRTF,
              }
            };
          }
        });
        setFileConfigs(existingConfigs);
      }
    } catch (err) {
      const errorMsg = err.message || 'Unknown error';
      console.error('Failed to load folder files:', err);
      setError(`Failed to load folder files: ${errorMsg}`);
    } finally {
      setLoading(false);
    }
  };
  
  // Load available LLM models
  const loadAvailableModels = useCallback(async () => {
    setLoadingModels(true);
    try {
      const modelsData = await llmConfigAPI.getModels();
      setAvailableModels(modelsData.models || []);
      
      // Set default model if none is set
      if (!ingestionLLMModelId && modelsData.models && modelsData.models.length > 0) {
        const ollamaModels = modelsData.models.filter(m => m.provider === 'ollama');
        if (ollamaModels.length > 0) {
          const defaultModel = ollamaModels.find(m => m.id === 'qwen2.5:7b-instruct') || ollamaModels[0];
          setIngestionLLMModelId(defaultModel.id);
          setIngestionLLMProvider('ollama');
        }
      }
    } catch (err) {
      console.error('Failed to load models:', err);
    } finally {
      setLoadingModels(false);
    }
  }, [ingestionLLMModelId]);
  
  // Load profile for editing when editingProfileName is provided
  useEffect(() => {
    if (isOpen && editingProfileName) {
      console.log('[FolderProfileModal] Loading profile for editing:', editingProfileName);
      loadProfileForEditing(editingProfileName);
    } else if (isOpen && !editingProfileName) {
      console.log('[FolderProfileModal] Opening in create mode (no editingProfileName)');
      // Always reset selectedExistingProfile when opening in create mode to prevent stale values
      // Check if it's invalid and reset it
      if (selectedExistingProfile === 'profile-name' || 
          !selectedExistingProfile || 
          selectedExistingProfile.trim() === '' ||
          !availableProfiles.find(p => p.name === selectedExistingProfile)) {
        console.log('[FolderProfileModal] Resetting selectedExistingProfile in create mode. Current value:', selectedExistingProfile);
        setSelectedExistingProfile('');
      }
    }
  }, [isOpen, editingProfileName, selectedExistingProfile, availableProfiles]);
  
  const loadProfiles = async () => {
    try {
      const profiles = await profilesAPI.list();
      // Filter out any profiles with invalid names
      const validProfiles = (profiles || []).filter(p => 
        p.name && 
        typeof p.name === 'string' && 
        p.name.trim() && 
        p.name !== 'profile-name' &&
        p.name.toLowerCase() !== 'profile name'
      );
      setAvailableProfiles(validProfiles);
      
      // Filter profiles with folder_processing
      const folderProfiles = validProfiles.filter(p => p.folder_processing);
      setFolderProcessingProfiles(folderProfiles);
      
      // Only set selectedExistingProfile if we don't have one and there's a valid profile
      if (validProfiles.length > 0 && !selectedExistingProfile) {
        const firstValidProfile = validProfiles.find(p => 
          p.name && p.name.trim() && p.name !== 'profile-name'
        );
        if (firstValidProfile) {
          console.log('[loadProfiles] Setting selectedExistingProfile to:', firstValidProfile.name);
          setSelectedExistingProfile(firstValidProfile.name);
        }
      }
    } catch (err) {
      console.error('Failed to load profiles:', err);
    }
  };
  
  // Reset state when modal closes (but NOT when editingProfileName changes)
  useEffect(() => {
    if (!isOpen && !editingProfileName) {
      // Only reset if modal is closed AND we're not in edit mode
      // This prevents resetting state when switching between edit and create modes
      setFiles([]);
      setProfileName('');
      setProcessingInstructions('');
      setSelectedProfileDetails(null);
      setFileConfigs({});
      setExpandedFiles({});
      setError(null);
      setSuccess(null);
      setProfileMode('instructions');
      // Explicitly reset selectedExistingProfile to empty string (not 'profile-name')
      console.log('[FolderProfileModal] Resetting selectedExistingProfile on modal close');
      setSelectedExistingProfile('');
      // Reset all profile fields
      setDescription('');
      setCaseType('');
      setIngestionSystemContext('');
      setSpecialEntityTypes([]);
      setIngestionTemperature(1.0);
      setIngestionLLMProvider('ollama');
      setIngestionLLMModelId('');
      setChatSystemContext('');
      setChatAnalysisGuidance('');
      setChatTemperature(1.0);
      // Reset folder selection
      setSelectedFolderPathForEdit('');
      setAvailableFolders([]);
    }
  }, [isOpen, editingProfileName]);
  
  const loadProfileForEditing = async (profileNameToEdit) => {
    if (!profileNameToEdit) {
      setError('No profile name provided for editing');
      setLoading(false);
      return;
    }
    
    // Validate that it's not a placeholder value
    const trimmedName = String(profileNameToEdit).trim();
    if (trimmedName === 'profile-name' || trimmedName === '' || trimmedName.toLowerCase() === 'profile name') {
      setError(`Invalid profile name: "${profileNameToEdit}". Please select a valid profile.`);
      setLoading(false);
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      console.log('[loadProfileForEditing] Loading profile:', trimmedName);
      console.log('[loadProfileForEditing] Profile name type:', typeof trimmedName);
      console.log('[loadProfileForEditing] Profile name length:', trimmedName?.length);
      
      const profile = await profilesAPI.get(trimmedName);
      console.log('[loadProfileForEditing] Profile loaded successfully:', profile);
      console.log('[loadProfileForEditing] Profile name from API:', profile?.name);
      console.log('[loadProfileForEditing] Profile llm_config from API:', profile?.llm_config);
      
      // Set basic information
      setProfileName(profile.name || '');
      setDescription(profile.description || '');
      setCaseType(profile.case_type || '');
      
      // Load ingestion configuration
      const ingestion = profile.ingestion || {};
      setIngestionSystemContext(ingestion.system_context || '');
      setSpecialEntityTypes(ingestion.special_entity_types || []);
      setIngestionTemperature(ingestion.temperature !== undefined ? ingestion.temperature : 1.0);
      
      // Load LLM config - always set the values from the saved profile
      const llmConfig = profile.llm_config || {};
      console.log('Loading profile for editing - llm_config:', llmConfig);
      // Set provider - use the value from profile, default to 'ollama' only if not present
      const loadedProvider = llmConfig.provider || 'ollama';
      const loadedModelId = llmConfig.model_id || '';
      console.log('Setting LLM provider to:', loadedProvider, 'model_id to:', loadedModelId);
      setIngestionLLMProvider(loadedProvider);
      setIngestionLLMModelId(loadedModelId);
      
      // Load chat configuration
      const chat = profile.chat || {};
      setChatSystemContext(chat.system_context || '');
      setChatAnalysisGuidance(chat.analysis_guidance || '');
      setChatTemperature(chat.temperature !== undefined ? chat.temperature : 1.0);
      
      // Load folder_processing configuration
      if (profile.folder_processing) {
        const folderProcessing = profile.folder_processing;
        
        // Set processing instructions from processing_rules
        if (folderProcessing.processing_rules) {
          setProcessingInstructions(folderProcessing.processing_rules);
        } else {
          setProcessingInstructions('');
        }
        
        // Set profile mode to 'existing' and select the profile itself
        setProfileMode('existing');
        setSelectedExistingProfile(profileNameToEdit);
        setSelectedProfileDetails(profile);
        
        // Load file configs from file_rules if available
        // Note: We can't map file_rules back to specific files without a folder,
        // but we can show the rules in the UI for reference
        if (folderProcessing.file_rules && folderProcessing.file_rules.length > 0) {
          // Build file configs from file_rules for display
          const configs = {};
          folderProcessing.file_rules.forEach((rule, idx) => {
            // Create a synthetic file path for display
            const syntheticPath = `rule_${idx}_${rule.pattern}`;
            configs[syntheticPath] = {
              selected: true,
              role: rule.role || 'document',
              options: {
                transcribe: rule.actions?.includes('transcribe') || false,
                translate: rule.actions?.includes('translate') || false,
                transcribeLanguage: rule.transcribe_languages?.[0] || 'es',
                translateLanguages: rule.translate_languages || [],
                parser: rule.parser || '',
                extractParticipants: rule.extract_participants || false,
                extractInterpretation: rule.extract_interpretation || false,
              }
            };
          });
          setFileConfigs(configs);
        } else {
          setFileConfigs({});
        }
      } else {
        // Profile doesn't have folder_processing - this shouldn't happen in edit mode
        setError('This profile does not have folder processing configuration');
      }
    } catch (err) {
      console.error('Failed to load profile for editing:', err);
      console.error('Profile name that failed:', profileNameToEdit);
      console.error('Error details:', err);
      const errorMessage = err.message || err.toString() || 'Unknown error';
      setError(`Failed to load profile '${profileNameToEdit}': ${errorMessage}. Make sure the profile exists and the backend server is running.`);
    } finally {
      setLoading(false);
    }
  };
  
  // Helper functions for special entity types
  const handleAddSpecialEntityType = () => {
    setSpecialEntityTypes([...specialEntityTypes, { name: '', description: '' }]);
  };
  
  const handleUpdateSpecialEntityType = (index, field, value) => {
    const updated = [...specialEntityTypes];
    updated[index] = { ...updated[index], [field]: value };
    setSpecialEntityTypes(updated);
  };
  
  const handleRemoveSpecialEntityType = (index) => {
    setSpecialEntityTypes(specialEntityTypes.filter((_, i) => i !== index));
  };
  
  // Load profile details when existing profile is selected
  useEffect(() => {
    console.log('[FolderProfileModal] useEffect for loadProfileDetails triggered:', {
      profileMode,
      selectedExistingProfile,
      isOpen,
      type: typeof selectedExistingProfile
    });
    
    if (profileMode === 'existing' && selectedExistingProfile && isOpen) {
      // Validate profile name before loading
      const trimmedName = String(selectedExistingProfile).trim();
      console.log('[FolderProfileModal] Validating profile name:', trimmedName);
      
      if (trimmedName && trimmedName !== 'profile-name' && trimmedName !== '' && trimmedName.toLowerCase() !== 'profile name') {
        console.log('[FolderProfileModal] Loading profile details for:', trimmedName);
        loadProfileDetails(trimmedName);
      } else {
        console.warn('[FolderProfileModal] Skipping loadProfileDetails - invalid profile name:', selectedExistingProfile, 'trimmed:', trimmedName);
        // Clear invalid selection
        if (trimmedName === 'profile-name' || trimmedName === '') {
          console.log('[FolderProfileModal] Clearing invalid selectedExistingProfile');
          setSelectedExistingProfile('');
        }
        setSelectedProfileDetails(null);
      }
    } else {
      setSelectedProfileDetails(null);
    }
  }, [selectedExistingProfile, profileMode, isOpen]);
  
  // Initialize file configs when files load (only when not editing)
  useEffect(() => {
    if (files.length > 0 && !editingProfileName) {
      const initialConfigs = {};
      files.filter(f => f.type === 'file').forEach(file => {
        const ext = file.name.split('.').pop()?.toLowerCase() || '';
        const isAudio = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(ext);
        const isSRI = ['sri'].includes(ext);
        const isRTF = ['rtf'].includes(ext);
        
        let defaultRole = 'ignore';
        if (isAudio) defaultRole = 'audio';
        else if (isSRI) defaultRole = 'metadata';
        else if (isRTF) defaultRole = 'interpretation';
        
        initialConfigs[file.path] = {
          selected: defaultRole !== 'ignore',
          role: defaultRole,
          options: {
            transcribe: isAudio,
            translate: isAudio,
            transcribeLanguage: isAudio ? 'es' : '',
            translateLanguages: isAudio ? ['en'] : [],
            parser: isSRI ? 'sri' : (isRTF ? 'rtf' : ''),
            extractParticipants: isRTF,
            extractInterpretation: isRTF,
          }
        };
      });
      setFileConfigs(initialConfigs);
    }
  }, [files, editingProfileName]);
  
  const loadProfileDetails = async (profileName) => {
    // Validate profile name before making API call
    if (!profileName || typeof profileName !== 'string' || !profileName.trim()) {
      console.error('[loadProfileDetails] Invalid profile name:', profileName);
      setSelectedProfileDetails(null);
      return;
    }
    
    const trimmedName = profileName.trim();
    if (trimmedName === 'profile-name' || trimmedName === '' || trimmedName.toLowerCase() === 'profile name') {
      console.error('[loadProfileDetails] Placeholder profile name detected:', trimmedName);
      setSelectedProfileDetails(null);
      return;
    }
    
    setLoadingProfileDetails(true);
    try {
      console.log('[loadProfileDetails] Loading profile:', trimmedName);
      const profile = await profilesAPI.get(trimmedName);
      setSelectedProfileDetails(profile);
      
      // When selecting an existing profile (not editing), populate form fields
      if (!editingProfileName && profileMode === 'existing') {
        // Only populate if fields are empty (don't overwrite user input)
        if (!description.trim()) {
          setDescription(profile.description || '');
        }
        if (!caseType.trim()) {
          setCaseType(profile.case_type || '');
        }
        
        const ingestion = profile.ingestion || {};
        if (!ingestionSystemContext.trim()) {
          setIngestionSystemContext(ingestion.system_context || '');
        }
        if (specialEntityTypes.length === 0) {
          setSpecialEntityTypes(ingestion.special_entity_types || []);
        }
        if (ingestionTemperature === 1.0) {
          setIngestionTemperature(ingestion.temperature !== undefined ? ingestion.temperature : 1.0);
        }
        
        const llmConfig = profile.llm_config || {};
        if (!ingestionLLMModelId) {
          if (llmConfig.provider) {
            setIngestionLLMProvider(llmConfig.provider);
          }
          if (llmConfig.model_id) {
            setIngestionLLMModelId(llmConfig.model_id);
          }
        }
        
        const chat = profile.chat || {};
        if (!chatSystemContext.trim()) {
          setChatSystemContext(chat.system_context || '');
        }
        if (!chatAnalysisGuidance.trim()) {
          setChatAnalysisGuidance(chat.analysis_guidance || '');
        }
        if (chatTemperature === 1.0) {
          setChatTemperature(chat.temperature !== undefined ? chat.temperature : 1.0);
        }
      }
    } catch (err) {
      console.error('Failed to load profile details:', err);
      setError(`Failed to load profile details: ${err.message}`);
      setSelectedProfileDetails(null);
    } finally {
      setLoadingProfileDetails(false);
    }
  };
  
  const updateFileConfig = (filePath, updates) => {
    setFileConfigs(prev => ({
      ...prev,
      [filePath]: {
        ...(prev[filePath] || {}),
        ...updates,
      }
    }));
  };
  
  const toggleFileExpanded = (filePath) => {
    setExpandedFiles(prev => ({
      ...prev,
      [filePath]: !prev[filePath]
    }));
  };
  
  const getFileType = (fileName) => {
    const ext = fileName.split('.').pop()?.toLowerCase() || '';
    if (['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(ext)) return 'audio';
    if (['sri'].includes(ext)) return 'metadata';
    if (['rtf'].includes(ext)) return 'interpretation';
    if (['txt', 'md', 'json', 'xml', 'pdf', 'doc', 'docx'].includes(ext)) return 'document';
    return 'other';
  };
  
  const loadFolderFiles = async () => {
    if (!caseId || !folderPath) {
      setError('Case ID and folder path are required');
      return;
    }
    
    setLoading(true);
    setError(null);
    try {
      const response = await evidenceAPI.listFolderFiles(caseId, folderPath);
      setFiles(response.files || []);
    } catch (err) {
      const errorMsg = err.message || 'Unknown error';
      console.error('Failed to load folder files:', err);
      setError(`Failed to load folder files: ${errorMsg}. Make sure the backend server has been restarted to pick up new endpoints.`);
    } finally {
      setLoading(false);
    }
  };
  
  const handleGenerateProfile = async () => {
    // When editing, profileName is pre-filled and cannot be changed
    const finalProfileName = editingProfileName || profileName.trim();
    
    if (!finalProfileName) {
      setError('Please enter a profile name');
      return;
    }
    
    // Validate profile name format (alphanumeric, hyphens, underscores only) - only for new profiles
    if (!editingProfileName) {
      const nameRegex = /^[a-zA-Z0-9_-]+$/;
      if (!nameRegex.test(finalProfileName)) {
        setError('Profile name must contain only alphanumeric characters, hyphens, and underscores');
        return;
      }
    }
    
    // When editing, we always use existing mode (profile is already loaded)
    const effectiveMode = editingProfileName ? 'existing' : profileMode;
    
    if (effectiveMode === 'instructions' && !processingInstructions.trim() && !editingProfileName) {
      setError('Please provide instructions for how to process this folder');
      return;
    }
    
    if (effectiveMode === 'existing' && !selectedExistingProfile && !editingProfileName) {
      setError('Please select an existing LLM profile');
      return;
    }
    
    setGenerating(true);
    setError(null);
    setSuccess(null);
    
    // Create a timeout warning if LLM generation takes too long (only for new profiles)
    let timeoutWarningId = null;
    if (effectiveMode === 'instructions' && !editingProfileName) {
      timeoutWarningId = setTimeout(() => {
        setSuccess('LLM is taking longer than usual... This may take up to 60 seconds. Please wait.');
      }, 20000); // Show message after 20 seconds
    }
    
    try {
      let folderProcessing = null;
      let baseProfile = null;
      
      if (effectiveMode === 'existing' || editingProfileName) {
        // Load the existing profile as base
        if (editingProfileName) {
          // When editing, use the profile being edited
          if (!selectedProfileDetails) {
            baseProfile = await profilesAPI.get(editingProfileName);
            setSelectedProfileDetails(baseProfile);
          } else {
            baseProfile = selectedProfileDetails;
          }
        } else {
          // When creating from existing profile
          if (!selectedProfileDetails) {
            baseProfile = await profilesAPI.get(selectedExistingProfile);
          } else {
            baseProfile = selectedProfileDetails;
          }
        }
        
        // Build folder_processing from file configs if any are configured
        const hasFileConfigs = Object.values(fileConfigs).some(c => c.selected && c.role !== 'ignore');
        if (hasFileConfigs) {
          folderProcessing = buildFolderProcessingConfig();
        } else if (baseProfile.folder_processing) {
          // Use existing folder_processing from base profile, but allow modifications
          folderProcessing = { ...baseProfile.folder_processing };
          // Update processing_rules if instructions were modified
          if (processingInstructions.trim()) {
            folderProcessing.processing_rules = processingInstructions.trim();
          }
        }
      } else {
        // Generate folder processing from instructions (only when creating new, not editing)
        let instructions = processingInstructions.trim();
        
        console.log('Generating folder profile with instructions:', instructions);
        const response = await evidenceAPI.generateFolderProfile({
          case_id: caseId,
          folder_path: folderPath || '',
          user_instructions: instructions,
          file_list: files.filter(f => f.type === 'file').map(f => ({
            name: f.name,
            path: f.path,
            type: f.type,
            size: f.size
          })),
        });
        
        console.log('Generate folder profile response:', response);
        
        if (response.success) {
          // The response.profile IS the folder_processing object, not an object containing it
          folderProcessing = response.profile.folder_processing || response.profile;
          
          console.log('Extracted folderProcessing:', folderProcessing);
          
          // Validate that folderProcessing is valid
          if (!folderProcessing || typeof folderProcessing !== 'object') {
            throw new Error('Generated profile structure is invalid');
          }
          
          // Ensure folderProcessing has required structure
          if (!folderProcessing.type) {
            folderProcessing.type = 'special';
          }
          if (!folderProcessing.file_rules) {
            folderProcessing.file_rules = [];
          }
          if (!folderProcessing.processing_rules) {
            folderProcessing.processing_rules = processingInstructions.trim();
          }
          if (!folderProcessing.output_format) {
            folderProcessing.output_format = 'wiretap_structured';
          }
          if (folderProcessing.related_files_indicator === undefined) {
            folderProcessing.related_files_indicator = true;
          }
        } else {
          throw new Error(response.error || response.detail || 'Failed to generate profile');
        }
        
        // For instructions mode, use generic profile as base
        const genericProfile = availableProfiles.find(p => p.name === 'generic');
        if (genericProfile) {
          try {
            baseProfile = await profilesAPI.get('generic');
          } catch (err) {
            console.warn('Failed to load generic profile, using defaults:', err);
            // Continue without base profile - backend will use defaults
          }
        }
      }
      
      // Combine processing instructions with any additional instructions
      let combinedInstructions = processingInstructions.trim();
      if ((effectiveMode === 'existing' || editingProfileName) && selectedProfileDetails) {
        // When editing, use the processing instructions directly if provided, otherwise use existing
        if (editingProfileName) {
          // When editing, use the processing instructions as-is (they were loaded from processing_rules)
          combinedInstructions = processingInstructions.trim() || selectedProfileDetails.description || '';
        } else {
          // When creating from existing profile, combine
          if (combinedInstructions) {
            combinedInstructions = `${selectedProfileDetails.description || ''}\n\nAdditional Instructions: ${combinedInstructions}`;
          } else {
            combinedInstructions = selectedProfileDetails.description || '';
          }
        }
      }
      
      // Validate folderProcessing exists before saving (only for new profiles with instructions mode)
      if (!folderProcessing && effectiveMode === 'instructions' && !editingProfileName) {
        throw new Error('Failed to generate folder processing configuration');
      }
      
      // When editing, ensure folderProcessing exists
      if (editingProfileName && !folderProcessing && baseProfile?.folder_processing) {
        folderProcessing = baseProfile.folder_processing;
      }
      
      // Build the profile data with all fields
      // Note: ProfileCreate expects llm_provider and llm_model_id as separate fields, not llm_config
      // When editing, ALWAYS use current state values directly - no defaults, no fallbacks
      // When creating, allow fallback to baseProfile if current state is empty
      let finalLLMProvider;
      let finalLLMModelId;
      
      if (editingProfileName) {
        // When editing, use current state values directly - NO defaults, preserve what user set
        // If state is empty/undefined, that means it wasn't loaded properly, so we should still save what we have
        finalLLMProvider = ingestionLLMProvider || 'ollama';  // Default only if truly empty (shouldn't happen if loaded correctly)
        finalLLMModelId = ingestionLLMModelId || '';  // Empty string is fine for model_id
        console.log('[EDIT MODE] Using state values - provider:', ingestionLLMProvider, '-> final:', finalLLMProvider, 'model_id:', ingestionLLMModelId, '-> final:', finalLLMModelId);
      } else {
        // When creating, allow fallback to baseProfile
        finalLLMProvider = ingestionLLMProvider || baseProfile?.llm_config?.provider || 'ollama';
        finalLLMModelId = ingestionLLMModelId || baseProfile?.llm_config?.model_id || '';
        console.log('[CREATE MODE] Using values with fallback - provider:', finalLLMProvider, 'model_id:', finalLLMModelId);
      }
      
      // When editing, use current state values directly. When creating, allow fallbacks.
      const finalDescription = editingProfileName
        ? description.trim()  // When editing, use current state
        : (description.trim() || combinedInstructions || baseProfile?.description || (folderPath ? `Folder processing profile for ${folderPath}` : 'Folder processing profile'));
      
      const finalCaseType = editingProfileName
        ? caseType.trim()  // When editing, use current state
        : (caseType.trim() || baseProfile?.case_type || '');
      
      const finalIngestionSystemContext = editingProfileName
        ? ingestionSystemContext.trim()  // When editing, use current state
        : (ingestionSystemContext.trim() || baseProfile?.ingestion?.system_context || '');
      
      const finalSpecialEntityTypes = editingProfileName
        ? specialEntityTypes  // When editing, use current state
        : (specialEntityTypes.length > 0 ? specialEntityTypes : (baseProfile?.ingestion?.special_entity_types || []));
      
      const finalChatSystemContext = editingProfileName
        ? chatSystemContext.trim()  // When editing, use current state
        : (chatSystemContext.trim() || baseProfile?.chat?.system_context || '');
      
      const finalChatAnalysisGuidance = editingProfileName
        ? chatAnalysisGuidance.trim()  // When editing, use current state
        : (chatAnalysisGuidance.trim() || baseProfile?.chat?.analysis_guidance || '');
      
      const profileData = {
        name: finalProfileName,
        description: finalDescription,
        case_type: finalCaseType,
        
        // Ingestion configuration
        ingestion_system_context: finalIngestionSystemContext,
        special_entity_types: finalSpecialEntityTypes,
        ingestion_temperature: ingestionTemperature,
        
        // LLM config (as separate fields for ProfileCreate model)
        // Always send these fields to ensure they're saved
        // CRITICAL: When editing, we MUST always send these fields (never undefined) to preserve user's selection
        llm_provider: finalLLMProvider,  // Always send - will be 'ollama' at minimum
        llm_model_id: finalLLMModelId,   // Always send - will be '' at minimum
        
        // Chat configuration
        chat_system_context: finalChatSystemContext,
        chat_analysis_guidance: finalChatAnalysisGuidance,
        chat_temperature: chatTemperature,
        
        // Folder processing configuration
        folder_processing: folderProcessing || undefined, // Use undefined instead of null if not provided
      };
      
      console.log('Saving profile with data:', JSON.stringify(profileData, null, 2));
      console.log('LLM Provider state:', ingestionLLMProvider, 'Final:', finalLLMProvider);
      console.log('LLM Model ID state:', ingestionLLMModelId, 'Final:', finalLLMModelId);
      console.log('Editing profile name:', editingProfileName);
      
      // Now set saving state and save
      setGenerating(false);
      setSaving(true);
      
      console.log('Starting save operation...');
      console.log('Profile data being sent:', {
        name: profileData.name,
        description: profileData.description?.substring(0, 100) + '...',
        case_type: profileData.case_type,
        has_folder_processing: !!profileData.folder_processing,
        folder_processing_type: profileData.folder_processing?.type,
      });
      
      try {
        console.log('Saving profile - sending data to backend:', {
          name: profileData.name,
          llm_provider: profileData.llm_provider,
          llm_model_id: profileData.llm_model_id,
          has_folder_processing: !!profileData.folder_processing
        });
        
        const savedProfile = await profilesAPI.save(profileData);
        console.log('Profile saved successfully:', savedProfile);
        console.log('Saved profile name:', savedProfile?.name);
        console.log('Saved profile llm_config:', savedProfile?.llm_config);
        
        if (!savedProfile) {
          throw new Error('Save operation returned no response');
        }
        
        if (!savedProfile.name) {
          throw new Error('Saved profile missing name');
        }
        
        // Reload profiles list to include the new profile
        await loadProfiles();
        
        // Notify parent component to reload profiles
        if (onProfileSaved) {
          onProfileSaved(savedProfile);
        }
        
        setSuccess('Profile saved successfully! You can now test it.');
        
        // Close modal after a short delay to show success message
        setTimeout(() => {
          onClose();
        }, 1500);
      } catch (saveErr) {
        console.error('Save error details:', saveErr);
        console.error('Save error stack:', saveErr.stack);
        
        // Extract error message from different possible formats
        let errorMessage = 'Failed to save profile';
        if (saveErr.message) {
          errorMessage = saveErr.message;
        } else if (saveErr.detail) {
          errorMessage = saveErr.detail;
        } else if (typeof saveErr === 'string') {
          errorMessage = saveErr;
        } else {
          errorMessage = `Failed to save profile: ${JSON.stringify(saveErr)}`;
        }
        
        throw new Error(errorMessage);
      }
      
    } catch (err) {
      console.error('Error generating/saving profile:', err);
      
      // Clear timeout warning if it exists
      if (timeoutWarningId) {
        clearTimeout(timeoutWarningId);
      }
      
      setError(`Failed to generate and save profile: ${err.message || 'Unknown error'}`);
    } finally {
      // Clear timeout warning if it exists
      if (timeoutWarningId) {
        clearTimeout(timeoutWarningId);
      }
      setGenerating(false);
      setSaving(false);
    }
  };
  
  const buildFolderProcessingConfig = () => {
    const fileRules = [];
    const processingParts = [];
    
    // Group files by role
    const filesByRole = {};
    Object.entries(fileConfigs).forEach(([filePath, config]) => {
      if (!config.selected || config.role === 'ignore') return;
      
      const fileName = filePath.split('/').pop() || filePath;
      const role = config.role;
      
      if (!filesByRole[role]) {
        filesByRole[role] = [];
      }
      filesByRole[role].push({ path: filePath, name: fileName, config });
    });
    
    // Build file rules for each role
    Object.entries(filesByRole).forEach(([role, roleFiles]) => {
      if (role === 'ignore') return;
      
      const rule = {
        pattern: roleFiles.map(f => `*${f.name.split('.').pop()}`).join(','),
        role: role,
      };
      
      if (role === 'audio') {
        const audioConfig = roleFiles[0].config.options;
        if (audioConfig.transcribe || audioConfig.translate) {
          rule.actions = [];
          if (audioConfig.transcribe) rule.actions.push('transcribe');
          if (audioConfig.translate) rule.actions.push('translate');
          
          if (audioConfig.transcribeLanguage) {
            rule.transcribe_languages = [audioConfig.transcribeLanguage];
          }
          if (audioConfig.translateLanguages && audioConfig.translateLanguages.length > 0) {
            rule.translate_languages = audioConfig.translateLanguages;
          }
          rule.whisper_model = 'base';
        }
      } else if (role === 'metadata') {
        const metaConfig = roleFiles[0].config.options;
        if (metaConfig.parser) {
          rule.parser = metaConfig.parser;
        }
      } else if (role === 'interpretation') {
        const interpConfig = roleFiles[0].config.options;
        if (interpConfig.parser) {
          rule.parser = interpConfig.parser;
        }
        if (interpConfig.extractParticipants !== undefined) {
          rule.extract_participants = interpConfig.extractParticipants;
        }
        if (interpConfig.extractInterpretation !== undefined) {
          rule.extract_interpretation = interpConfig.extractInterpretation;
        }
      }
      
      fileRules.push(rule);
      processingParts.push(`${role} files: ${roleFiles.map(f => f.name).join(', ')}`);
    });
    
    return {
      type: 'special',
      file_rules: fileRules,
      processing_rules: processingInstructions.trim() || `Process ${processingParts.join('; ')}. All files in this folder are related.`,
      output_format: 'wiretap_structured',
      related_files_indicator: true,
    };
  };
  
  const handleTestProfile = async () => {
    if (!profileName.trim()) {
      setError('Please enter a profile name');
      return;
    }
    
    setTesting(true);
    setError(null);
    setSuccess(null);
    
    try {
      const response = await evidenceAPI.testFolderProfile({
        case_id: caseId,
        folder_path: folderPath,
        profile_name: profileName,
      });
      
      if (response.success) {
        setSuccess(`Profile test started! Task ID: ${response.task_id}. Check background tasks for progress.`);
        // Close modal after a delay
        setTimeout(() => {
          onClose();
        }, 2000);
      } else {
        setError('Failed to start profile test');
      }
    } catch (err) {
      setError(`Failed to test profile: ${err.message}`);
    } finally {
      setTesting(false);
    }
  };
  
  if (!isOpen) return null;
  
  const fileCount = files.filter(f => f.type === 'file').length;
  const dirCount = files.filter(f => f.type === 'directory').length;
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col border border-light-200 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Folder className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              {editingProfileName ? 'Edit Folder Processing Profile' : 'Create Folder Processing Profile'}
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
          {/* Folder Info - only show if not editing */}
          {!editingProfileName && folderPath && (
            <div className="bg-light-50 rounded p-3 border border-light-200">
              <p className="text-sm text-light-700">
                <strong>Folder:</strong> {folderPath}
              </p>
              <p className="text-xs text-light-600 mt-1">
                {fileCount} file(s), {dirCount} folder(s)
              </p>
            </div>
          )}
          
          {/* Profile Info - show when editing */}
          {editingProfileName && (
            <div className="bg-light-50 rounded p-3 border border-light-200 space-y-3">
              <div>
                <p className="text-sm text-light-700">
                  <strong>Profile:</strong> {editingProfileName}
                </p>
                <p className="text-xs text-light-600 mt-1">
                  Editing folder processing configuration
                </p>
              </div>
              
              {/* Folder Selection for Edit Mode */}
              <div>
                <label className="block text-xs font-medium text-light-700 mb-2">
                  Select Folder to View Files (Optional)
                </label>
                <div className="flex gap-2">
                  <select
                    value={selectedFolderPathForEdit}
                    onChange={(e) => setSelectedFolderPathForEdit(e.target.value)}
                    className="flex-1 px-3 py-2 text-sm bg-white border border-light-300 rounded-lg text-light-900 focus:outline-none focus:border-owl-blue-500"
                    disabled={loading || generating || testing || saving}
                  >
                    <option value="">-- Select a folder --</option>
                    {availableFolders.map(folder => (
                      <option key={folder} value={folder}>{folder}</option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={selectedFolderPathForEdit}
                    onChange={(e) => setSelectedFolderPathForEdit(e.target.value)}
                    placeholder="Or enter folder path manually"
                    className="flex-1 px-3 py-2 text-sm bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
                    disabled={loading || generating || testing || saving}
                  />
                  <button
                    onClick={() => {
                      if (selectedFolderPathForEdit) {
                        loadFolderFilesForPath(selectedFolderPathForEdit);
                      }
                    }}
                    className="px-3 py-2 text-sm bg-owl-blue-500 hover:bg-owl-blue-600 text-white rounded-lg transition-colors disabled:bg-light-300 disabled:text-light-500"
                    disabled={loading || generating || testing || saving || !selectedFolderPathForEdit}
                  >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Load Files'}
                  </button>
                </div>
                <p className="text-xs text-light-600 mt-1">
                  Select a folder to view and configure its file processing rules
                </p>
              </div>
            </div>
          )}
          
          {/* View/Edit Folder Processing Profiles */}
          {folderProcessingProfiles.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-light-700">
                  Existing Folder Processing Profiles
                </label>
                <button
                  onClick={() => setShowEditProfiles(!showEditProfiles)}
                  className="text-xs text-owl-blue-600 hover:text-owl-blue-700"
                >
                  {showEditProfiles ? 'Hide' : 'Show'}
                </button>
              </div>
              {showEditProfiles && (
                <div className="border border-light-300 rounded-lg p-3 bg-light-50 space-y-2">
                  {folderProcessingProfiles.map((profile) => (
                    <div key={profile.name} className="flex items-center justify-between p-2 bg-white rounded border border-light-200">
                      <div>
                        <p className="text-sm font-medium text-light-900">{profile.name}</p>
                        <p className="text-xs text-light-600">{profile.description || 'No description'}</p>
                      </div>
                      <button
                        onClick={() => {
                          // Open ProfileEditor in a new window or navigate
                          window.open(`/profiles?edit=${profile.name}`, '_blank');
                        }}
                        className="flex items-center gap-1 px-2 py-1 text-xs text-owl-blue-600 hover:text-owl-blue-700 hover:bg-owl-blue-50 rounded transition-colors"
                      >
                        <Edit2 className="w-3 h-3" />
                        Edit
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          
          {/* Files List with Configuration - show if we have files or if editing with folder rules */}
          {files.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-light-700 mb-2">
                {editingProfileName ? 'File Processing Rules' : 'Files in Folder'}
              </label>
              <div className="border border-light-300 rounded-lg divide-y divide-light-200 bg-light-50 max-h-96 overflow-y-auto">
                {loading ? (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 className="w-5 h-5 animate-spin text-owl-blue-500" />
                    <span className="ml-2 text-sm text-light-600">Loading files...</span>
                  </div>
                ) : files.length === 0 ? (
                  <p className="text-sm text-light-600 p-4">
                    {editingProfileName && !selectedFolderPathForEdit
                      ? 'Select a folder above to view and configure its files'
                      : 'No files found in this folder'}
                  </p>
                ) : (
                files.filter(f => f.type === 'file').map((file, idx) => {
                  const config = fileConfigs[file.path] || { selected: false, role: 'ignore', options: {} };
                  const fileType = getFileType(file.name);
                  const isExpanded = expandedFiles[file.path];
                  const fileIcon = fileType === 'audio' ? <Music className="w-4 h-4 text-owl-purple-600" /> : <FileText className="w-4 h-4 text-light-600" />;
                  
                  return (
                    <div key={idx} className="bg-white">
                      <div className="flex items-center gap-2 p-3 hover:bg-light-50">
                        <input
                          type="checkbox"
                          checked={config.selected && config.role !== 'ignore'}
                          onChange={(e) => updateFileConfig(file.path, {
                            selected: e.target.checked,
                            role: e.target.checked ? (config.role === 'ignore' ? 'document' : config.role) : 'ignore',
                          })}
                          className="w-4 h-4 text-owl-blue-600 border-light-300 rounded focus:ring-owl-blue-500"
                        />
                        <button
                          onClick={() => toggleFileExpanded(file.path)}
                          className="flex items-center gap-2 flex-1 text-left"
                        >
                          {isExpanded ? <ChevronDown className="w-4 h-4 text-light-600" /> : <ChevronRight className="w-4 h-4 text-light-600" />}
                          {fileIcon}
                          <span className="text-sm text-light-900 flex-1">{file.name}</span>
                          {file.size && (
                            <span className="text-xs text-light-500">{(file.size / 1024).toFixed(1)} KB</span>
                          )}
                        </button>
                        <button
                          onClick={() => setSelectedFileForPreview(selectedFileForPreview === file.path ? null : file.path)}
                          className="text-xs text-owl-blue-600 hover:text-owl-blue-700 px-2 py-1 hover:bg-owl-blue-50 rounded"
                        >
                          Preview
                        </button>
                      </div>
                      
                      {isExpanded && config.selected && (
                        <div className="px-3 pb-3 pt-0 border-t border-light-200 bg-light-50 space-y-3">
                          {/* Role Selection */}
                          <div>
                            <label className="block text-xs font-medium text-light-700 mb-1">File Role</label>
                            <select
                              value={config.role}
                              onChange={(e) => updateFileConfig(file.path, { role: e.target.value })}
                              className="w-full px-2 py-1.5 text-xs bg-white border border-light-300 rounded focus:outline-none focus:border-owl-blue-500"
                            >
                              {fileRoles.map(role => (
                                <option key={role.value} value={role.value}>{role.label}</option>
                              ))}
                            </select>
                          </div>
                          
                          {/* Audio Processing Options */}
                          {config.role === 'audio' && (
                            <div className="space-y-2">
                              <label className="flex items-center gap-2 text-xs">
                                <input
                                  type="checkbox"
                                  checked={config.options.transcribe || false}
                                  onChange={(e) => updateFileConfig(file.path, {
                                    options: { ...config.options, transcribe: e.target.checked }
                                  })}
                                  className="w-3.5 h-3.5 text-owl-blue-600 border-light-300 rounded"
                                />
                                <span className="text-light-700">Transcribe</span>
                              </label>
                              
                              {config.options.transcribe && (
                                <div className="ml-6">
                                  <label className="block text-xs text-light-600 mb-1">Transcribe from:</label>
                                  <select
                                    value={config.options.transcribeLanguage || ''}
                                    onChange={(e) => updateFileConfig(file.path, {
                                      options: { ...config.options, transcribeLanguage: e.target.value }
                                    })}
                                    className="w-full px-2 py-1 text-xs bg-white border border-light-300 rounded"
                                  >
                                    {languages.map(lang => (
                                      <option key={lang.code} value={lang.code}>{lang.name}</option>
                                    ))}
                                  </select>
                                </div>
                              )}
                              
                              <label className="flex items-center gap-2 text-xs">
                                <input
                                  type="checkbox"
                                  checked={config.options.translate || false}
                                  onChange={(e) => updateFileConfig(file.path, {
                                    options: { ...config.options, translate: e.target.checked }
                                  })}
                                  className="w-3.5 h-3.5 text-owl-blue-600 border-light-300 rounded"
                                />
                                <span className="text-light-700">Translate</span>
                              </label>
                              
                              {config.options.translate && (
                                <div className="ml-6 space-y-1">
                                  <label className="block text-xs text-light-600 mb-1">Translate to:</label>
                                  {(config.options.translateLanguages || []).map((langCode, idx) => (
                                    <div key={idx} className="flex items-center gap-1">
                                      <select
                                        value={langCode}
                                        onChange={(e) => {
                                          const newLangs = [...(config.options.translateLanguages || [])];
                                          newLangs[idx] = e.target.value;
                                          updateFileConfig(file.path, { options: { ...config.options, translateLanguages: newLangs } });
                                        }}
                                        className="flex-1 px-2 py-1 text-xs bg-white border border-light-300 rounded"
                                      >
                                        {languages.map(lang => (
                                          <option key={lang.code} value={lang.code}>{lang.name}</option>
                                        ))}
                                      </select>
                                      <button
                                        onClick={() => {
                                          const newLangs = (config.options.translateLanguages || []).filter((_, i) => i !== idx);
                                          updateFileConfig(file.path, { options: { ...config.options, translateLanguages: newLangs } });
                                        }}
                                        className="text-red-600 hover:text-red-700 px-1"
                                      >
                                        ×
                                      </button>
                                    </div>
                                  ))}
                                  <button
                                    onClick={() => {
                                      const newLangs = [...(config.options.translateLanguages || []), 'en'];
                                      updateFileConfig(file.path, { options: { ...config.options, translateLanguages: newLangs } });
                                    }}
                                    className="text-xs text-owl-blue-600 hover:text-owl-blue-700"
                                  >
                                    + Add language
                                  </button>
                                </div>
                              )}
                            </div>
                          )}
                          
                          {/* Metadata/Interpretation Options */}
                          {(config.role === 'metadata' || config.role === 'interpretation') && (
                            <div className="space-y-2">
                              {config.role === 'metadata' && (
                                <div>
                                  <label className="block text-xs font-medium text-light-700 mb-1">Parser</label>
                                  <select
                                    value={config.options.parser || 'sri'}
                                    onChange={(e) => updateFileConfig(file.path, {
                                      options: { ...config.options, parser: e.target.value }
                                    })}
                                    className="w-full px-2 py-1.5 text-xs bg-white border border-light-300 rounded"
                                  >
                                    <option value="sri">SRI</option>
                                  </select>
                                </div>
                              )}
                              
                              {config.role === 'interpretation' && (
                                <>
                                  <div>
                                    <label className="block text-xs font-medium text-light-700 mb-1">Parser</label>
                                    <select
                                      value={config.options.parser || 'rtf'}
                                      onChange={(e) => updateFileConfig(file.path, {
                                        options: { ...config.options, parser: e.target.value }
                                      })}
                                      className="w-full px-2 py-1.5 text-xs bg-white border border-light-300 rounded"
                                    >
                                      <option value="rtf">RTF</option>
                                    </select>
                                  </div>
                                  <label className="flex items-center gap-2 text-xs">
                                    <input
                                      type="checkbox"
                                      checked={config.options.extractParticipants || false}
                                      onChange={(e) => updateFileConfig(file.path, {
                                        options: { ...config.options, extractParticipants: e.target.checked }
                                      })}
                                      className="w-3.5 h-3.5 text-owl-blue-600 border-light-300 rounded"
                                    />
                                    <span className="text-light-700">Extract Participants</span>
                                  </label>
                                  <label className="flex items-center gap-2 text-xs">
                                    <input
                                      type="checkbox"
                                      checked={config.options.extractInterpretation || false}
                                      onChange={(e) => updateFileConfig(file.path, {
                                        options: { ...config.options, extractInterpretation: e.target.checked }
                                      })}
                                      className="w-3.5 h-3.5 text-owl-blue-600 border-light-300 rounded"
                                    />
                                    <span className="text-light-700">Extract Interpretation</span>
                                  </label>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
          )}
          
          {/* File Preview */}
          {selectedFileForPreview && (
            <FilePreview
              caseId={caseId}
              filePath={selectedFileForPreview}
              fileName={selectedFileForPreview.split('/').pop() || selectedFileForPreview}
              fileType="file"
              onClose={() => setSelectedFileForPreview(null)}
            />
          )}
          
          {/* Basic Information */}
          <div>
            <h3 className="text-sm font-semibold text-light-700 mb-3 flex items-center gap-2">
              <Info className="w-4 h-4" />
              Basic Information
            </h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-light-700 mb-2">
                  Profile Name *
                </label>
                <input
                  type="text"
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                  placeholder="Enter profile name (e.g., wiretap_custom)"
                  className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
                  disabled={generating || testing || !!editingProfileName}
                />
                {editingProfileName && (
                  <p className="text-xs text-light-600 mt-1">
                    Profile name cannot be changed when editing
                  </p>
                )}
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
                  disabled={generating || testing || saving}
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
                  disabled={generating || testing || saving}
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
                  disabled={generating || testing || saving}
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
                    disabled={generating || testing || saving}
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
                            disabled={generating || testing || saving}
                          />
                          <input
                            type="text"
                            value={entity.description || ''}
                            onChange={(e) => handleUpdateSpecialEntityType(index, 'description', e.target.value)}
                            className="px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
                            placeholder="Description (e.g., A company used to obscure ownership)"
                            disabled={generating || testing || saving}
                          />
                        </div>
                        <button
                          onClick={() => handleRemoveSpecialEntityType(index)}
                          className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          title="Remove entity type"
                          disabled={generating || testing || saving}
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
                      disabled={generating || testing || saving}
                    >
                      Ollama (Local)
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setIngestionLLMProvider('openai');
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
                      disabled={generating || testing || saving}
                    >
                      OpenAI (Remote)
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-light-700 mb-2 mt-3">
                    Model
                  </label>
                  {loadingModels ? (
                    <div className="text-xs text-light-500">Loading models...</div>
                  ) : (
                    <select
                      value={ingestionLLMModelId}
                      onChange={(e) => setIngestionLLMModelId(e.target.value)}
                      className="w-full px-3 py-2 text-sm bg-white border border-light-300 rounded-lg text-light-900 focus:outline-none focus:border-owl-blue-500"
                      disabled={generating || testing || saving}
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
                    <div className="p-3 bg-light-50 rounded border border-light-200 mt-3">
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
                    disabled={generating || testing || saving}
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
                    disabled={generating || testing || saving}
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
                  disabled={generating || testing || saving}
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
                  disabled={generating || testing || saving}
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
                    disabled={generating || testing || saving}
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
                    disabled={generating || testing || saving}
                  />
                </div>
                <p className="text-xs text-light-600 mt-1">
                  Lower = more focused answers. Higher = more creative responses. Default: 1.0
                </p>
              </div>
            </div>
          </div>
          
          {/* Profile Mode Selection - hidden when editing */}
          {!editingProfileName && (
            <div>
              <label className="block text-sm font-medium text-light-700 mb-2">
                Processing Method
              </label>
              <div className="space-y-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="profileMode"
                    value="instructions"
                    checked={profileMode === 'instructions'}
                    onChange={(e) => setProfileMode(e.target.value)}
                    className="w-4 h-4 text-owl-blue-600 border-light-300 focus:ring-owl-blue-500"
                    disabled={generating || testing}
                  />
                  <span className="text-sm text-light-700">Use instructions (LLM generates profile)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="profileMode"
                    value="existing"
                    checked={profileMode === 'existing'}
                    onChange={(e) => setProfileMode(e.target.value)}
                    className="w-4 h-4 text-owl-blue-600 border-light-300 focus:ring-owl-blue-500"
                    disabled={generating || testing}
                  />
                  <span className="text-sm text-light-700">Use existing LLM profile</span>
                </label>
              </div>
            </div>
          )}
          
          {/* Existing Profile Selection (shown when mode is existing and not editing) */}
          {profileMode === 'existing' && !editingProfileName && (
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-light-700 mb-2">
                  Select LLM Profile
                </label>
                <select
                  value={selectedExistingProfile && selectedExistingProfile !== 'profile-name' ? selectedExistingProfile : ''}
                  onChange={(e) => {
                    const newValue = e.target.value;
                    console.log('[FolderProfileModal] Profile selected from dropdown:', newValue);
                    // Validate before setting
                    if (newValue && newValue !== 'profile-name' && newValue.trim() && newValue !== '') {
                      setSelectedExistingProfile(newValue.trim());
                    } else {
                      console.warn('[FolderProfileModal] Invalid profile selected, clearing:', newValue);
                      setSelectedExistingProfile('');
                    }
                  }}
                  className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 focus:outline-none focus:border-owl-blue-500"
                  disabled={generating || testing || saving || loadingProfileDetails}
                >
                  <option value="">-- Select a profile --</option>
                  {availableProfiles
                    .filter(profile => profile.name && profile.name.trim() && profile.name !== 'profile-name')
                    .map(profile => (
                      <option key={profile.name} value={profile.name}>
                        {profile.name} - {profile.description}
                      </option>
                    ))}
                </select>
                <p className="text-xs text-light-600 mt-1">
                  Select an existing LLM profile to use as a base for processing this folder.
                </p>
              </div>
              
              {/* Profile Details Display - show when editing or when existing profile is selected */}
              {(editingProfileName || (profileMode === 'existing' && selectedExistingProfile)) && (
                <>
                  {loadingProfileDetails && (
                    <div className="flex items-center justify-center py-4">
                      <Loader2 className="w-5 h-5 animate-spin text-owl-blue-500" />
                      <span className="ml-2 text-sm text-light-600">Loading profile details...</span>
                    </div>
                  )}
                  
                  {selectedProfileDetails && !loadingProfileDetails && (
                <div className="border border-owl-blue-200 rounded-lg p-4 bg-owl-blue-50">
                  <h4 className="text-sm font-semibold text-owl-blue-900 mb-3">Profile Details</h4>
                  <div className="space-y-4 text-sm">
                    <div>
                      <span className="font-medium text-light-700">Description:</span>
                      <p className="text-light-600 mt-1">{selectedProfileDetails.description || 'No description'}</p>
                    </div>
                    
                    {selectedProfileDetails.case_type && (
                      <div>
                        <span className="font-medium text-light-700">Case Type:</span>
                        <span className="text-light-600 ml-2">{selectedProfileDetails.case_type}</span>
                      </div>
                    )}
                    
                    {/* Model Selection */}
                    {selectedProfileDetails.llm_config && (
                      <div>
                        <span className="font-medium text-light-700">Model Selection:</span>
                        <div className="text-light-600 mt-1 bg-white p-2 rounded border border-light-200">
                          <div><span className="text-xs text-light-500">Provider:</span> {selectedProfileDetails.llm_config.provider || 'N/A'}</div>
                          <div className="mt-1"><span className="text-xs text-light-500">Model:</span> {selectedProfileDetails.llm_config.model_id || 'N/A'}</div>
                        </div>
                      </div>
                    )}
                    
                    {/* Temperature Options */}
                    <div>
                      <span className="font-medium text-light-700">Temperature Options:</span>
                      <div className="text-light-600 mt-1 bg-white p-2 rounded border border-light-200">
                        {selectedProfileDetails.ingestion && (
                          <div>
                            <span className="text-xs text-light-500">Ingestion Temperature:</span> {selectedProfileDetails.ingestion.temperature !== undefined ? selectedProfileDetails.ingestion.temperature : 1.0}
                          </div>
                        )}
                        {selectedProfileDetails.chat && (
                          <div className="mt-1">
                            <span className="text-xs text-light-500">Chat Temperature:</span> {selectedProfileDetails.chat.temperature !== undefined ? selectedProfileDetails.chat.temperature : 1.0}
                          </div>
                        )}
                      </div>
                    </div>
                    
                    {/* Ingestion System Context */}
                    {selectedProfileDetails.ingestion?.system_context && (
                      <div>
                        <span className="font-medium text-light-700">Ingestion System Context:</span>
                        <div className="text-light-600 mt-1 bg-white p-3 rounded border border-light-200 text-xs max-h-32 overflow-y-auto whitespace-pre-wrap">
                          {selectedProfileDetails.ingestion.system_context}
                        </div>
                      </div>
                    )}
                    
                    {/* Chat System Context */}
                    {selectedProfileDetails.chat?.system_context && (
                      <div>
                        <span className="font-medium text-light-700">Chat System Context:</span>
                        <div className="text-light-600 mt-1 bg-white p-3 rounded border border-light-200 text-xs max-h-32 overflow-y-auto whitespace-pre-wrap">
                          {selectedProfileDetails.chat.system_context}
                        </div>
                      </div>
                    )}
                    
                    {/* Analysis Guidance */}
                    {selectedProfileDetails.chat?.analysis_guidance && (
                      <div>
                        <span className="font-medium text-light-700">Analysis Guidance:</span>
                        <div className="text-light-600 mt-1 bg-white p-3 rounded border border-light-200 text-xs max-h-32 overflow-y-auto whitespace-pre-wrap">
                          {selectedProfileDetails.chat.analysis_guidance}
                        </div>
                      </div>
                    )}
                    
                    {/* Processing Rules */}
                    {selectedProfileDetails.folder_processing?.processing_rules && (
                      <div>
                        <span className="font-medium text-light-700">Processing Rules:</span>
                        <div className="text-light-600 mt-1 bg-white p-3 rounded border border-light-200 text-xs max-h-40 overflow-y-auto whitespace-pre-wrap">
                          {selectedProfileDetails.folder_processing.processing_rules}
                        </div>
                      </div>
                    )}
                    
                    {/* File Rules Summary */}
                    {selectedProfileDetails.folder_processing?.file_rules && selectedProfileDetails.folder_processing.file_rules.length > 0 && (
                      <div>
                        <span className="font-medium text-light-700">File Processing Rules:</span>
                        <div className="text-light-600 mt-1 space-y-2">
                          {selectedProfileDetails.folder_processing.file_rules.map((rule, idx) => (
                            <div key={idx} className="bg-white p-2 rounded border border-light-200 text-xs">
                              <div className="font-medium text-light-700 mb-1">Pattern: {rule.pattern}</div>
                              <div>Role: {rule.role}</div>
                              {rule.actions && rule.actions.length > 0 && (
                                <div>Actions: {rule.actions.join(', ')}</div>
                              )}
                              {rule.transcribe_languages && rule.transcribe_languages.length > 0 && (
                                <div>Transcribe from: {rule.transcribe_languages.join(', ')}</div>
                              )}
                              {rule.translate_languages && rule.translate_languages.length > 0 && (
                                <div>Translate to: {rule.translate_languages.join(', ')}</div>
                              )}
                              {rule.parser && (
                                <div>Parser: {rule.parser}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    
                    {/* Special Entity Types */}
                    {selectedProfileDetails.ingestion?.special_entity_types && selectedProfileDetails.ingestion.special_entity_types.length > 0 && (
                      <div>
                        <span className="font-medium text-light-700">Special Entity Types:</span>
                        <div className="text-light-600 mt-1">
                          {selectedProfileDetails.ingestion.special_entity_types.map((et, idx) => (
                            <span key={idx} className="inline-block mr-2 mb-1 px-2 py-0.5 bg-white rounded text-xs border border-light-200">
                              {et.name}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                  )}
                </>
              )}
            </div>
          )}
          
          {/* Folder Processing Configuration */}
          <div>
            <h3 className="text-sm font-semibold text-light-700 mb-3 flex items-center gap-2">
              <Folder className="w-4 h-4" />
              Folder Processing Configuration
            </h3>
            
            {/* Processing Instructions */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-light-700 mb-2">
                Processing Instructions {editingProfileName ? '' : (profileMode === 'existing' && '(Optional)')}
              </label>
              <textarea
                value={processingInstructions}
                onChange={(e) => setProcessingInstructions(e.target.value)}
                placeholder={editingProfileName
                  ? "Edit the processing instructions for this folder profile..."
                  : (profileMode === 'existing' 
                    ? "Add any additional processing instructions or modifications to the selected profile..."
                    : "Describe how to process this folder. For example: 'These are wiretap recordings. Audio files should be transcribed in Spanish and translated to English. .sri files contain call metadata. .rtf files have prosecutor interpretations. All files relate to the same call.'")}
                rows={6}
                className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500 resize-none"
                disabled={generating || testing || saving}
              />
              <p className="text-xs text-light-600 mt-1">
                {editingProfileName
                  ? 'Edit the processing rules that will be applied when processing folders with this profile.'
                  : (profileMode === 'existing' 
                    ? 'Add additional instructions or modifications that will be combined with the selected profile.'
                    : 'Explain how files should be processed and how they relate to each other.')}
              </p>
            </div>
          </div>
          
          {/* Generate and Save Button */}
          <button
            onClick={handleGenerateProfile}
            disabled={saving || generating || testing || !(editingProfileName || profileName.trim()) || ((editingProfileName ? 'existing' : profileMode) === 'instructions' && !processingInstructions.trim() && !editingProfileName) || ((editingProfileName ? 'existing' : profileMode) === 'existing' && !selectedExistingProfile && !editingProfileName)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
          >
            {(saving || generating) ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <div className="flex flex-col items-start">
                  <span>{saving ? 'Saving Profile...' : ((editingProfileName ? 'existing' : profileMode) === 'instructions' ? 'Calling LLM (may take up to 60s)...' : 'Generating...')}</span>
                  {generating && (editingProfileName ? 'existing' : profileMode) === 'instructions' && !editingProfileName && (
                    <span className="text-xs opacity-75">This can take 30-60 seconds. Please wait...</span>
                  )}
                </div>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                {editingProfileName ? 'Save Profile' : 'Generate & Save Profile'}
              </>
            )}
          </button>
          
          {/* Test Button */}
          {success && success.includes('saved successfully') && (
            <button
              onClick={handleTestProfile}
              disabled={testing || !profileName.trim()}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-owl-purple-500 hover:bg-owl-purple-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              {testing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Testing...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Test Profile
                </>
              )}
            </button>
          )}
          
          {/* Error Message */}
          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
              <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}
          
          {/* Success Message */}
          {success && (
            <div className="flex items-start gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
              <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-green-800">{success}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
