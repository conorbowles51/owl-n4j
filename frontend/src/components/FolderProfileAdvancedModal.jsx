import React, { useState, useEffect } from 'react';
import { X, FileText, Folder, Settings, Play, Loader2, AlertCircle, CheckCircle2, Music, ChevronDown, ChevronRight, Save, ArrowLeft } from 'lucide-react';
import { evidenceAPI, profilesAPI } from '../services/api';
import FilePreview from './FilePreview';

/**
 * FolderProfileAdvancedModal Component
 * 
 * Advanced modal for manually configuring folder processing profiles.
 * Allows users to:
 * - Select which files to process vs ignore
 * - Configure processing options by file type (transcribe/translate for audio)
 * - Select LLM profiles for processing
 * - Build folder_processing JSON structure
 */
export default function FolderProfileAdvancedModal({ 
  isOpen, 
  onClose,
  onReturnToBasic,
  caseId,
  folderPath,
}) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [selectedFileForPreview, setSelectedFileForPreview] = useState(null);
  
  const [profileName, setProfileName] = useState('');
  const [availableProfiles, setAvailableProfiles] = useState([]);
  const [selectedLLMProfile, setSelectedLLMProfile] = useState('');
  
  // File processing configuration
  const [fileConfigs, setFileConfigs] = useState({}); // { fileName: { selected: bool, role: string, options: {...} } }
  
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
    if (isOpen && caseId && folderPath) {
      loadFolderFiles();
      loadProfiles();
    }
  }, [isOpen, caseId, folderPath]);
  
  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setFiles([]);
      setProfileName('');
      setFileConfigs({});
      setSelectedLLMProfile('');
      setError(null);
      setSuccess(null);
    }
  }, [isOpen]);
  
  // Initialize file configs when files load
  useEffect(() => {
    if (files.length > 0) {
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
            // Audio options
            transcribe: isAudio,
            translate: isAudio,
            transcribeLanguage: isAudio ? 'es' : '',
            translateLanguages: isAudio ? ['en'] : [],
            // Metadata options
            parser: isSRI ? 'sri' : (isRTF ? 'rtf' : ''),
            extractParticipants: isRTF,
            extractInterpretation: isRTF,
          }
        };
      });
      setFileConfigs(initialConfigs);
    }
  }, [files]);
  
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
      setError(`Failed to load folder files: ${errorMsg}`);
    } finally {
      setLoading(false);
    }
  };
  
  const loadProfiles = async () => {
    try {
      const profiles = await profilesAPI.list();
      setAvailableProfiles(profiles || []);
      if (profiles && profiles.length > 0 && !selectedLLMProfile) {
        setSelectedLLMProfile(profiles[0].name);
      }
    } catch (err) {
      console.error('Failed to load profiles:', err);
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
  
  const getFileType = (fileName) => {
    const ext = fileName.split('.').pop()?.toLowerCase() || '';
    if (['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'].includes(ext)) return 'audio';
    if (['sri'].includes(ext)) return 'metadata';
    if (['rtf'].includes(ext)) return 'interpretation';
    if (['txt', 'md', 'json', 'xml', 'pdf', 'doc', 'docx'].includes(ext)) return 'document';
    return 'other';
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
        // Get options from first audio file (assuming same config for all audio files)
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
      processing_rules: `Process ${processingParts.join('; ')}. All files in this folder are related.`,
      output_format: 'wiretap_structured',
      related_files_indicator: true,
    };
  };
  
  const handleSaveProfile = async () => {
    if (!profileName.trim()) {
      setError('Please enter a profile name');
      return;
    }
    
    if (!selectedLLMProfile || selectedLLMProfile.trim() === '') {
      setError('Please select an LLM profile');
      return;
    }
    
    const selectedFiles = Object.values(fileConfigs).filter(c => c.selected && c.role !== 'ignore');
    if (selectedFiles.length === 0) {
      setError('Please select at least one file to process');
      return;
    }
    
    setSaving(true);
    setError(null);
    setSuccess(null);
    
    try {
      // Build folder_processing configuration
      const folderProcessing = buildFolderProcessingConfig();
      
      // Get selected LLM profile details to merge
      const selectedProfile = availableProfiles.find(p => p.name === selectedLLMProfile);
      if (!selectedProfile) {
        throw new Error(`Selected LLM profile '${selectedLLMProfile}' not found in available profiles`);
      }
      
      // Load full profile details
      let profileDetails;
      try {
        profileDetails = await profilesAPI.get(selectedLLMProfile);
      } catch (err) {
        const errorMsg = err.message || String(err);
        if (errorMsg.includes('404') || errorMsg.includes('Not Found') || errorMsg.includes('not found')) {
          throw new Error(`Selected LLM profile '${selectedLLMProfile}' not found. Please select a different profile from the list.`);
        }
        throw new Error(`Failed to load profile '${selectedLLMProfile}': ${errorMsg}`);
      }
      
      // Save profile with folder_processing
      const profileData = {
        name: profileName.trim(),
        description: profileDetails.description || `Folder processing profile for ${folderPath}`,
        case_type: profileDetails.case_type || null,
        ingestion_system_context: profileDetails.ingestion?.system_context || null,
        special_entity_types: profileDetails.ingestion?.special_entity_types || [],
        ingestion_temperature: profileDetails.ingestion?.temperature !== undefined ? profileDetails.ingestion.temperature : 1.0,
        llm_provider: profileDetails.llm_config?.provider || null,
        llm_model_id: profileDetails.llm_config?.model_id || null,
        chat_system_context: profileDetails.chat?.system_context || null,
        chat_analysis_guidance: profileDetails.chat?.analysis_guidance || null,
        chat_temperature: profileDetails.chat?.temperature !== undefined ? profileDetails.chat.temperature : 1.0,
        folder_processing: folderProcessing,
      };
      
      await profilesAPI.save(profileData);
      setSuccess('Profile saved successfully! You can now test it or return to basic mode.');
      
    } catch (err) {
      setError(`Failed to save profile: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };
  
  const handleSaveAndTest = async () => {
    if (!profileName.trim()) {
      setError('Please enter a profile name');
      return;
    }
    
    const selectedFiles = Object.values(fileConfigs).filter(c => c.selected && c.role !== 'ignore');
    if (selectedFiles.length === 0) {
      setError('Please select at least one file to process');
      return;
    }
    
    setTesting(true);
    setError(null);
    setSuccess(null);
    
    try {
      // Build folder_processing configuration
      const folderProcessing = buildFolderProcessingConfig();
      
      // Save the profile first
      const selectedProfile = availableProfiles.find(p => p.name === selectedLLMProfile);
      if (!selectedProfile) {
        throw new Error('Selected LLM profile not found');
      }
      
      const profileDetails = await profilesAPI.get(selectedLLMProfile);
      const profileData = {
        name: profileName.trim(),
        description: profileDetails.description || `Folder processing profile for ${folderPath}`,
        case_type: profileDetails.case_type || null,
        ingestion_system_context: profileDetails.ingestion?.system_context || null,
        special_entity_types: profileDetails.ingestion?.special_entity_types || [],
        ingestion_temperature: profileDetails.ingestion?.temperature !== undefined ? profileDetails.ingestion.temperature : 1.0,
        llm_provider: profileDetails.llm_config?.provider || null,
        llm_model_id: profileDetails.llm_config?.model_id || null,
        chat_system_context: profileDetails.chat?.system_context || null,
        chat_analysis_guidance: profileDetails.chat?.analysis_guidance || null,
        chat_temperature: profileDetails.chat?.temperature !== undefined ? profileDetails.chat.temperature : 1.0,
        folder_processing: folderProcessing,
      };
      
      await profilesAPI.save(profileData);
      
      const response = await evidenceAPI.testFolderProfile({
        case_id: caseId,
        folder_path: folderPath,
        profile_name: profileName,
      });
      
      if (response.success) {
        setSuccess(`Profile test started! Task ID: ${response.task_id}. Check background tasks for progress.`);
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
  const selectedFileList = files.filter(f => f.type === 'file');
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col border border-light-200 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Settings className="w-5 h-5 text-owl-blue-600" />
            <h2 className="text-lg font-semibold text-owl-blue-900">
              Advanced Folder Processing Profile
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {onReturnToBasic && (
              <button
                onClick={onReturnToBasic}
                className="px-3 py-1.5 text-sm text-owl-blue-700 bg-owl-blue-50 hover:bg-owl-blue-100 rounded transition-colors border border-owl-blue-200 flex items-center gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                Basic
              </button>
            )}
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
          {/* Folder Info */}
          <div className="bg-light-50 rounded p-3 border border-light-200">
            <p className="text-sm text-light-700">
              <strong>Folder:</strong> {folderPath}
            </p>
            <p className="text-xs text-light-600 mt-1">
              {fileCount} file(s), {dirCount} folder(s)
            </p>
          </div>
          
          {/* Profile Name and LLM Profile */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                Profile Name *
              </label>
              <input
                type="text"
                value={profileName}
                onChange={(e) => setProfileName(e.target.value)}
                placeholder="Enter profile name"
                className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-blue-500"
                disabled={testing}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-light-700 mb-1">
                LLM Profile
              </label>
              <select
                value={selectedLLMProfile}
                onChange={(e) => setSelectedLLMProfile(e.target.value)}
                className="w-full px-3 py-2 bg-white border border-light-300 rounded-lg text-light-900 focus:outline-none focus:border-owl-blue-500"
                disabled={testing}
              >
                {availableProfiles.map(profile => (
                  <option key={profile.name} value={profile.name}>
                    {profile.name} - {profile.description}
                  </option>
                ))}
              </select>
            </div>
          </div>
          
          {/* Files Configuration */}
          <div>
            <label className="block text-sm font-medium text-light-700 mb-2">
              File Processing Configuration
            </label>
            <div className="border border-light-300 rounded-lg divide-y divide-light-200">
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-5 h-5 animate-spin text-owl-blue-500" />
                  <span className="ml-2 text-sm text-light-600">Loading files...</span>
                </div>
              ) : selectedFileList.length === 0 ? (
                <p className="text-sm text-light-600 p-4">No files found</p>
              ) : (
                selectedFileList.map((file, idx) => {
                  const config = fileConfigs[file.path] || { selected: false, role: 'ignore', options: {} };
                  const fileType = getFileType(file.name);
                  
                  return (
                    <FileConfigRow
                      key={idx}
                      file={file}
                      config={config}
                      fileType={fileType}
                      onConfigChange={(updates) => updateFileConfig(file.path, updates)}
                      fileRoles={fileRoles}
                      languages={languages}
                      caseId={caseId}
                      onPreview={(path) => setSelectedFileForPreview(selectedFileForPreview === path ? null : path)}
                      previewing={selectedFileForPreview === file.path}
                    />
                  );
                })
              )}
            </div>
          </div>
          
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
          
          {/* Action Buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleSaveProfile}
              disabled={saving || testing || !profileName.trim()}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-owl-blue-500 hover:bg-owl-blue-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  Save Profile
                </>
              )}
            </button>
            <button
              onClick={handleSaveAndTest}
              disabled={testing || saving || !profileName.trim()}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-owl-purple-500 hover:bg-owl-purple-600 disabled:bg-light-300 disabled:text-light-500 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              {testing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Testing...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Save & Test
                </>
              )}
            </button>
          </div>
          
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

// File Configuration Row Component
function FileConfigRow({ file, config, fileType, onConfigChange, fileRoles, languages, caseId, onPreview, previewing }) {
  const [expanded, setExpanded] = useState(false);
  const fileIcon = fileType === 'audio' ? <Music className="w-4 h-4 text-owl-purple-600" /> : <FileText className="w-4 h-4 text-light-600" />;
  
  return (
    <div className="bg-white">
      <div className="flex items-center gap-2 p-3 hover:bg-light-50">
        <input
          type="checkbox"
          checked={config.selected && config.role !== 'ignore'}
          onChange={(e) => onConfigChange({
            selected: e.target.checked,
            role: e.target.checked ? (config.role === 'ignore' ? 'document' : config.role) : 'ignore',
          })}
          className="w-4 h-4 text-owl-blue-600 border-light-300 rounded focus:ring-owl-blue-500"
        />
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 flex-1 text-left"
        >
          {expanded ? <ChevronDown className="w-4 h-4 text-light-600" /> : <ChevronRight className="w-4 h-4 text-light-600" />}
          {fileIcon}
          <span className="text-sm text-light-900 flex-1">{file.name}</span>
          {file.size && (
            <span className="text-xs text-light-500">{(file.size / 1024).toFixed(1)} KB</span>
          )}
        </button>
        <button
          onClick={() => onPreview(file.path)}
          className="text-xs text-owl-blue-600 hover:text-owl-blue-700 px-2 py-1 hover:bg-owl-blue-50 rounded"
        >
          Preview
        </button>
      </div>
      
      {expanded && config.selected && (
        <div className="px-3 pb-3 pt-0 border-t border-light-200 bg-light-50 space-y-3">
          {/* Role Selection */}
          <div>
            <label className="block text-xs font-medium text-light-700 mb-1">
              File Role
            </label>
            <select
              value={config.role}
              onChange={(e) => onConfigChange({ role: e.target.value })}
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
                  onChange={(e) => onConfigChange({
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
                    onChange={(e) => onConfigChange({
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
                  onChange={(e) => onConfigChange({
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
                          onConfigChange({ options: { ...config.options, translateLanguages: newLangs } });
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
                          onConfigChange({ options: { ...config.options, translateLanguages: newLangs } });
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
                      onConfigChange({ options: { ...config.options, translateLanguages: newLangs } });
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
                  <label className="block text-xs font-medium text-light-700 mb-1">
                    Parser
                  </label>
                  <select
                    value={config.options.parser || 'sri'}
                    onChange={(e) => onConfigChange({
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
                    <label className="block text-xs font-medium text-light-700 mb-1">
                      Parser
                    </label>
                    <select
                      value={config.options.parser || 'rtf'}
                      onChange={(e) => onConfigChange({
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
                      onChange={(e) => onConfigChange({
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
                      onChange={(e) => onConfigChange({
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
}
