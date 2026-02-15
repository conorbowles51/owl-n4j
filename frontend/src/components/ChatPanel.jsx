import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  MessageSquare,
  Send,
  X,
  ChevronRight,
  Loader2,
  Sparkles,
  Target,
  Globe,
  History,
  Network,
  Settings,
  ChevronDown,
  ChevronUp,
  Info,
  Code,
  Clock,
  Search,
  Zap,
  Copy,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { chatAPI, llmConfigAPI } from '../services/api';
import ChatHistoryList from './ChatHistoryList';

/**
 * Format debug log as markdown — supports both new stages[] format and legacy format.
 */
function formatDebugLogAsMarkdown(debugLog, question) {
  const lines = [];

  lines.push('# RAG Pipeline Execution Trace');
  lines.push('');

  const timestamp = debugLog.timestamp || new Date().toISOString();
  lines.push(`**Timestamp:** ${timestamp}`);
  if (debugLog.total_duration_ms) {
    lines.push(`**Total Duration:** ${debugLog.total_duration_ms}ms`);
  }
  lines.push('');

  lines.push('## Question');
  lines.push(question || debugLog.question || '');
  lines.push('');

  if (debugLog.selected_keys && debugLog.selected_keys.length > 0) {
    lines.push(`**Selected Node Keys:** ${debugLog.selected_keys.join(', ')}`);
    lines.push('');
  }

  if (debugLog.pipeline_summary) {
    lines.push('## Pipeline Summary');
    lines.push(debugLog.pipeline_summary);
    lines.push('');
  }

  // New stages[] format
  if (debugLog.stages && debugLog.stages.length > 0) {
    lines.push('---');
    lines.push('');

    debugLog.stages.forEach((stage) => {
      lines.push(`## Stage #${stage.step}: ${stage.stage} (${stage.duration_ms}ms)`);
      lines.push('');

      if (stage.input && Object.keys(stage.input).length > 0) {
        lines.push('### Input');
        lines.push('```json');
        lines.push(JSON.stringify(stage.input, null, 2));
        lines.push('```');
        lines.push('');
      }

      if (stage.output && Object.keys(stage.output).length > 0) {
        lines.push('### Output');
        lines.push('```json');
        lines.push(JSON.stringify(stage.output, null, 2));
        lines.push('```');
        lines.push('');
      }

      if (stage.details && Object.keys(stage.details).length > 0) {
        lines.push('### Details');
        Object.entries(stage.details).forEach(([key, value]) => {
          if (value === null || value === undefined) return;
          lines.push(`#### ${key}`);
          if (typeof value === 'string') {
            lines.push('```');
            lines.push(value);
            lines.push('```');
          } else {
            lines.push('```json');
            lines.push(JSON.stringify(value, null, 2));
            lines.push('```');
          }
          lines.push('');
        });
      }

      lines.push('');
    });
  }

  // Legacy fields (backward compat for older debug logs)
  if (debugLog.context_mode && !debugLog.stages) {
    lines.push('## Context Mode');
    lines.push(`**Mode:** \`${debugLog.context_mode}\``);
    lines.push('');
  }

  if (debugLog.context_preview && !debugLog.stages) {
    lines.push('## Context Preview');
    lines.push('```');
    lines.push(debugLog.context_preview);
    lines.push('```');
    lines.push('');
  }

  if (debugLog.final_prompt && !debugLog.stages) {
    lines.push('## Final Prompt Sent to LLM');
    lines.push('```');
    lines.push(debugLog.final_prompt);
    lines.push('```');
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * PipelineStageDetail - Renders a single expandable stage in the trace
 */
function PipelineStageDetail({ stage, isExpanded, onToggle }) {
  const durationColor = stage.duration_ms < 500 ? 'text-green-600 bg-green-50' :
    stage.duration_ms < 2000 ? 'text-amber-600 bg-amber-50' : 'text-red-600 bg-red-50';

  const hasDetails = stage.details && Object.keys(stage.details).length > 0;

  return (
    <div className="border border-light-200 rounded-md overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-light-50 transition-colors"
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-xs font-mono text-light-500 w-6 shrink-0">#{stage.step}</span>
          <span className="text-xs font-semibold text-light-800 truncate">{stage.stage}</span>
        </div>
        <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${durationColor} shrink-0`}>
          {stage.duration_ms}ms
        </span>
        {isExpanded ? <ChevronUp className="w-3 h-3 text-light-400 shrink-0" /> : <ChevronDown className="w-3 h-3 text-light-400 shrink-0" />}
      </button>

      {isExpanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-light-100 bg-light-50">
          {/* Input */}
          {stage.input && Object.keys(stage.input).length > 0 && (
            <div className="mt-2">
              <div className="text-[10px] font-semibold text-blue-600 uppercase tracking-wide mb-1">Input</div>
              <pre className="text-[11px] text-light-700 bg-white border border-light-200 rounded p-2 overflow-x-auto max-h-40 whitespace-pre-wrap break-words">
                {JSON.stringify(stage.input, null, 2)}
              </pre>
            </div>
          )}

          {/* Output */}
          {stage.output && Object.keys(stage.output).length > 0 && (
            <div>
              <div className="text-[10px] font-semibold text-green-600 uppercase tracking-wide mb-1">Output</div>
              <pre className="text-[11px] text-light-700 bg-white border border-light-200 rounded p-2 overflow-x-auto max-h-40 whitespace-pre-wrap break-words">
                {JSON.stringify(stage.output, null, 2)}
              </pre>
            </div>
          )}

          {/* Details (prompts, queries, full data) */}
          {hasDetails && (
            <div>
              <div className="text-[10px] font-semibold text-purple-600 uppercase tracking-wide mb-1">Details</div>
              {Object.entries(stage.details).map(([key, value]) => {
                if (value === null || value === undefined) return null;
                const isLongText = typeof value === 'string' && value.length > 200;
                const isArray = Array.isArray(value);
                const isObject = typeof value === 'object' && !isArray;

                return (
                  <div key={key} className="mb-2">
                    <div className="text-[10px] text-light-500 font-mono mb-0.5">{key}</div>
                    <pre className="text-[11px] text-light-700 bg-white border border-light-200 rounded p-2 overflow-x-auto max-h-60 whitespace-pre-wrap break-words">
                      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
                    </pre>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * PipelineTrace - Full pipeline execution trace viewer
 */
function PipelineTrace({ debugLog, messageId, expandedStages, setExpandedStages }) {
  if (!debugLog || !debugLog.stages || debugLog.stages.length === 0) {
    return (
      <div className="text-xs text-light-500 italic p-2">No pipeline trace data available.</div>
    );
  }

  const [copied, setCopied] = React.useState(false);

  const handleCopyTrace = () => {
    const text = formatDebugLogAsMarkdown(debugLog, debugLog.question || '');
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const toggleStage = (stageKey) => {
    setExpandedStages(prev => {
      const next = new Set(prev);
      if (next.has(stageKey)) {
        next.delete(stageKey);
      } else {
        next.add(stageKey);
      }
      return next;
    });
  };

  return (
    <div className="mt-2 space-y-2">
      {/* Header with summary */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="w-3 h-3 text-purple-500" />
          <span className="text-[11px] text-purple-700 font-medium">
            Total: {debugLog.total_duration_ms || '?'}ms
          </span>
          <span className="text-[11px] text-light-500">
            ({debugLog.stages.length} stages)
          </span>
        </div>
        <button
          onClick={handleCopyTrace}
          className="flex items-center gap-1 text-[10px] text-light-500 hover:text-light-700 transition-colors"
          title="Copy trace as markdown"
        >
          <Copy className="w-3 h-3" />
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>

      {/* Pipeline summary */}
      {debugLog.pipeline_summary && (
        <div className="text-[11px] text-light-600 bg-purple-50 border border-purple-100 rounded px-2 py-1.5 font-mono">
          {debugLog.pipeline_summary}
        </div>
      )}

      {/* Stage timeline */}
      <div className="space-y-1">
        {debugLog.stages.map((stage, idx) => {
          const stageKey = `${messageId}-stage-${idx}`;
          return (
            <PipelineStageDetail
              key={stageKey}
              stage={stage}
              isExpanded={expandedStages.has(stageKey)}
              onToggle={() => toggleStage(stageKey)}
            />
          );
        })}
      </div>
    </div>
  );
}

/**
 * ChatPanel Component
 *
 * AI chat interface for asking questions about the investigation
 */
export default function ChatPanel({ 
  isOpen, 
  onToggle, 
  selectedNodes = [],
  onClose,
  onMessagesChange, // Callback to notify parent of message changes
  initialMessages = [], // Initial messages to load (e.g., from snapshot)
  onAutoSave, // Callback to auto-save chat history
  currentCaseId, // Current case ID for associating chat history
  currentCaseName, // Current case name
  currentCaseVersion, // Current case version
  isTableMode = false, // Whether we're in table view mode
}) {
  const [messages, setMessages] = useState(initialMessages);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [showChatHistory, setShowChatHistory] = useState(false);
  const [lastAutoSaveCount, setLastAutoSaveCount] = useState(0);
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [availableModels, setAvailableModels] = useState([]);
  const [currentConfig, setCurrentConfig] = useState(null);
  const [selectedProvider, setSelectedProvider] = useState('openai');
  const [selectedModelId, setSelectedModelId] = useState('gpt-5');
  const [confidenceThreshold, setConfidenceThreshold] = useState(2.0);
  const [includeGraphNodes, setIncludeGraphNodes] = useState(true); // Toggle for including graph nodes
  const [loadingConfig, setLoadingConfig] = useState(false);
  const [expandedTraces, setExpandedTraces] = useState(new Set()); // Track which message traces are expanded
  const [expandedStages, setExpandedStages] = useState(new Set()); // Track which stages are expanded within traces
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Update messages when initialMessages changes (e.g., when loading a snapshot)
  useEffect(() => {
    if (initialMessages && initialMessages.length > 0) {
      setMessages(initialMessages);
      onMessagesChange?.(initialMessages);
    }
  }, [initialMessages, onMessagesChange]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load model configuration
  const loadModelConfig = useCallback(async () => {
    try {
      setLoadingConfig(true);
      const [modelsData, configData, thresholdData] = await Promise.all([
        llmConfigAPI.getModels(),
        llmConfigAPI.getCurrentConfig(),
        llmConfigAPI.getConfidenceThreshold().catch(() => ({ threshold: 2.0 })), // Default to 2.0 if not available
      ]);
      setAvailableModels(modelsData.models || []);
      setCurrentConfig(configData);
      if (configData) {
        setSelectedProvider(configData.provider);
        setSelectedModelId(configData.model_id);
      }
      if (thresholdData && thresholdData.threshold !== undefined) {
        setConfidenceThreshold(thresholdData.threshold);
      }
    } catch (err) {
      console.error('Failed to load model config:', err);
    } finally {
      setLoadingConfig(false);
    }
  }, []);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      loadSuggestions();
      loadModelConfig();
    }
  }, [isOpen, selectedNodes, loadModelConfig]);

  // Load suggested questions
  const loadSuggestions = async () => {
    if (!currentCaseId) return;
    try {
      const selectedKeys = selectedNodes.map(n => n.key);
      const data = await chatAPI.getSuggestions(currentCaseId, selectedKeys.length > 0 ? selectedKeys : null);
      setSuggestions(data.suggestions || []);
    } catch (err) {
      console.error('Failed to load suggestions:', err);
    }
  };

  // Send message
  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const question = input.trim();
    setInput('');

    // Add user message
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: question,
      selectedNodes: selectedNodes.map(n => n.key), // Store context
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => {
      const newMessages = [...prev, userMessage];
      onMessagesChange?.(newMessages);
      return newMessages;
    });

    // Get selected node keys (only if includeGraphNodes is enabled)
    const selectedKeys = includeGraphNodes ? selectedNodes.map(n => n.key) : [];

    setIsLoading(true);

    try {
      const response = await chatAPI.ask(question, selectedKeys.length > 0 ? selectedKeys : null, selectedModelId, selectedProvider, confidenceThreshold);

      // Debug log is now stored in system logs, no need to download

      // Extract node keys from response - try multiple sources
      let nodeKeys = [];
      if (response.used_node_keys && Array.isArray(response.used_node_keys) && response.used_node_keys.length > 0) {
        nodeKeys = response.used_node_keys;
        console.log(`[ChatPanel] Using ${nodeKeys.length} node keys from response.used_node_keys`);
      } else if (response.debug_log) {
        // Fallback: extract from debug log
        const debugLog = response.debug_log;
        console.log('[ChatPanel] Extracting node keys from debug log...');
        
        if (debugLog.hybrid_filtering) {
          // Get all combined node keys from hybrid filtering
          const vectorKeys = debugLog.hybrid_filtering.vector_node_keys || [];
          const cypherKeys = debugLog.hybrid_filtering.cypher_node_keys || [];
          nodeKeys = [...new Set([...vectorKeys, ...cypherKeys])];
          console.log(`[ChatPanel] Found ${nodeKeys.length} node keys from hybrid_filtering (${vectorKeys.length} vector + ${cypherKeys.length} cypher)`);
        }
        
        if (nodeKeys.length === 0 && debugLog.focused_context && debugLog.focused_context.selected_node_keys) {
          nodeKeys = debugLog.focused_context.selected_node_keys;
          console.log(`[ChatPanel] Found ${nodeKeys.length} node keys from focused_context`);
        }
        
        if (nodeKeys.length === 0 && debugLog.cypher_filter_query && debugLog.cypher_filter_query.results) {
          const results = debugLog.cypher_filter_query.results;
          if (results.node_keys && Array.isArray(results.node_keys)) {
            nodeKeys = results.node_keys;
            console.log(`[ChatPanel] Found ${nodeKeys.length} node keys from cypher_filter_query`);
          }
        }
      }
      
      console.log(`[ChatPanel] Final node keys count: ${nodeKeys.length}`);
      
      // Add assistant message
      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.answer,
        contextMode: response.context_mode,
        contextDescription: response.context_description,
        cypherUsed: response.cypher_used,
        usedNodeKeys: nodeKeys, // Store node keys used to generate answer (from multiple sources)
        modelInfo: response.model_info, // Store model info
        resultGraph: response.result_graph || null, // Store result graph with documents and entities
        debugLog: response.debug_log || null, // Full pipeline execution trace
        timestamp: new Date().toISOString(),
      };
      
      // Update current config if provided
      if (response.model_info) {
        setCurrentConfig(response.model_info);
      }
      setMessages(prev => {
        const newMessages = [...prev, assistantMessage];
        onMessagesChange?.(newMessages);
        
        // Auto-save after significant queries
        // Consider a query "significant" if:
        // 1. It uses Cypher (has cypherUsed)
        // 2. Or we've accumulated 3+ messages since last save
        const isSignificant = !!response.cypher_used || newMessages.length - lastAutoSaveCount >= 3;
        
        if (isSignificant && onAutoSave && currentCaseId) {
          // Auto-save chat history
          onAutoSave(newMessages);
          setLastAutoSaveCount(newMessages.length);
        }
        
        return newMessages;
      });
    } catch (err) {
      // Add error message
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `Error: ${err.message}`,
        isError: true,
      };
      setMessages(prev => {
        const newMessages = [...prev, errorMessage];
        onMessagesChange?.(newMessages);
        return newMessages;
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Handle suggestion click
  const handleSuggestionClick = (suggestion) => {
    setInput(suggestion);
    inputRef.current?.focus();
  };

  // Handle key press
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Context indicator
  const contextInfo = selectedNodes.length > 0 
    ? {
        icon: Target,
        text: `Focused on ${selectedNodes.length} ${selectedNodes.length > 1 ? 'entities' : 'entity'}`,
        color: 'text-owl-purple-600',
      }
    : {
        icon: Globe,
        text: 'Full graph context',
        color: 'text-light-600',
      };

  const ContextIcon = contextInfo.icon;

  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className="fixed bottom-6 right-6 p-4 bg-owl-purple-500 hover:bg-owl-purple-600 text-white rounded-full shadow-lg transition-all hover:scale-105 z-50"
      >
        <MessageSquare className="w-6 h-6" />
      </button>
    );
  }

  return (
    <div className={`${isTableMode ? 'flex-shrink-0' : 'w-96'} bg-white border-l border-light-200 h-full flex flex-col shadow-sm ${isTableMode ? 'w-96' : ''}`}>
      {/* Header */}
      <div className="p-4 border-b border-light-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-owl-purple-500" />
          <div>
            <h2 className="font-semibold text-owl-blue-900">AI Assistant</h2>
            {currentConfig && (
              <p className="text-xs text-light-600">
                {selectedModelId} • {selectedProvider}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowModelSettings(!showModelSettings)}
            className="p-1 hover:bg-light-100 rounded transition-colors"
            title="Model Settings"
          >
            <Settings className="w-5 h-5 text-light-600" />
          </button>
          <button
            onClick={() => setShowChatHistory(true)}
            className="p-1 hover:bg-light-100 rounded transition-colors"
            title="View chat history"
          >
            <History className="w-5 h-5 text-light-600" />
          </button>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>
      </div>

      {/* Model Settings Panel */}
      {showModelSettings && (
        <div className="p-4 border-b border-light-200 bg-light-50 max-h-96 overflow-y-auto">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-light-700 mb-2">
                Provider
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setSelectedProvider('ollama');
                    // Set default model for provider
                    const ollamaModels = availableModels.filter(m => m.provider === 'ollama');
                    if (ollamaModels.length > 0) {
                      const defaultModel = ollamaModels.find(m => m.id === 'qwen2.5:32b-instruct') || ollamaModels[0];
                      setSelectedModelId(defaultModel.id);
                    }
                  }}
                  className={`flex-1 px-3 py-2 text-sm rounded transition-colors ${
                    selectedProvider === 'ollama'
                      ? 'bg-owl-purple-500 text-white'
                      : 'bg-white border border-light-300 text-light-700 hover:bg-light-100'
                  }`}
                >
                  Ollama (Local)
                </button>
                <button
                  onClick={() => {
                    setSelectedProvider('openai');
                    // Set default model for provider
                    const openaiModels = availableModels.filter(m => m.provider === 'openai');
                    if (openaiModels.length > 0) {
                      const defaultModel = openaiModels.find(m => m.id === 'gpt-5') || openaiModels[0];
                      setSelectedModelId(defaultModel.id);
                    }
                  }}
                  className={`flex-1 px-3 py-2 text-sm rounded transition-colors ${
                    selectedProvider === 'openai'
                      ? 'bg-owl-purple-500 text-white'
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
              <select
                value={selectedModelId}
                onChange={(e) => setSelectedModelId(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-light-300 rounded focus:outline-none focus:border-owl-purple-500 bg-white"
              >
                {availableModels
                  .filter(m => m.provider === selectedProvider)
                  .map(model => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                    </option>
                  ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-light-700 mb-2">
                Vector Search Confidence Threshold
              </label>
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-light-600">
                  <span>Strict (0.0)</span>
                  <span className="font-medium">{confidenceThreshold.toFixed(1)}</span>
                  <span>Lenient (3.0)</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="3"
                  step="0.1"
                  value={confidenceThreshold}
                  onChange={(e) => {
                    const newThreshold = parseFloat(e.target.value);
                    setConfidenceThreshold(newThreshold);
                    // Save threshold immediately
                    llmConfigAPI.setConfidenceThreshold(newThreshold).catch(err => {
                      console.error('Failed to save confidence threshold:', err);
                    });
                  }}
                  className="w-full accent-owl-purple-500"
                />
                <p className="text-xs text-light-500">
                  Only documents with similarity distance ≤ {confidenceThreshold.toFixed(1)} will be included. Lower values = stricter filtering. (L2 distance range: 0.0-3.0)
                </p>
              </div>
            </div>

            {/* Model Info */}
            {(() => {
              const selectedModel = availableModels.find(m => m.id === selectedModelId);
              if (!selectedModel) return null;
              
              return (
                <div className="p-3 bg-white rounded border border-light-200">
                  <div className="flex items-start gap-2 mb-2">
                    <Info className="w-4 h-4 text-owl-purple-600 mt-0.5 flex-shrink-0" />
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

            <button
              onClick={async () => {
                try {
                  await llmConfigAPI.setConfig({
                    provider: selectedProvider,
                    model_id: selectedModelId,
                  });
                  await loadModelConfig();
                  setShowModelSettings(false);
                } catch (err) {
                  alert('Failed to update model configuration: ' + err.message);
                }
              }}
              className="w-full px-4 py-2 bg-owl-purple-500 hover:bg-owl-purple-600 text-white rounded text-sm transition-colors"
            >
              Apply Configuration
            </button>
          </div>
        </div>
      )}

      {/* Context Indicator */}
      <div className="px-4 py-2 bg-light-50 border-b border-light-200 flex items-center gap-2">
        <ContextIcon className={`w-4 h-4 ${contextInfo.color}`} />
        <span className={`text-xs ${contextInfo.color}`}>{contextInfo.text}</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <Sparkles className="w-12 h-12 text-light-400 mx-auto mb-4" />
            <p className="text-light-600 text-sm">
              Ask me anything about this investigation
            </p>
            
            {/* Suggestions */}
            {suggestions.length > 0 && (
              <div className="mt-6 space-y-2">
                <p className="text-xs text-light-600 uppercase tracking-wide">
                  Suggested questions
                </p>
                {suggestions.slice(0, 4).map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSuggestionClick(suggestion)}
                    className="w-full text-left p-3 bg-light-50 hover:bg-light-100 rounded-lg text-sm text-light-700 hover:text-owl-blue-900 transition-colors border border-light-200"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg p-3 ${
                msg.role === 'user'
                  ? 'bg-owl-blue-700 text-white'
                  : msg.isError
                  ? 'bg-red-100 text-red-800 border border-red-200'
                  : 'bg-light-100 text-light-900 border border-light-200'
              }`}
            >
              {msg.role === 'user' ? (
                <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
              ) : (
                <>
                  <div className="text-sm prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-0.5 prose-headings:my-2 prose-strong:text-owl-blue-700 prose-table:text-xs">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                  {/* Processed By signature */}
                  {msg.modelInfo && (
                    <div className="mt-3 pt-2 border-t border-light-200">
                      <p className="text-xs text-light-500 italic">
                        Processed By: <span className="font-medium text-light-700">{msg.modelInfo.model_name}</span>
                      </p>
                    </div>
                  )}
                </>
              )}
              
              {/* Context badge and Show on Graph button for assistant messages */}
              {msg.role === 'assistant' && !msg.isError && (
                <div className="mt-2 pt-2 border-t border-light-300">
                  <div className="flex items-center gap-2 text-xs text-light-600 mb-2 flex-wrap">
                    {msg.contextMode === 'focused' ? (
                      <Target className="w-3 h-3" />
                    ) : (
                      <Globe className="w-3 h-3" />
                    )}
                    <span>{msg.contextDescription}</span>
                    {msg.cypherUsed && (
                      <span className="bg-owl-purple-100 text-owl-purple-700 px-1.5 py-0.5 rounded">
                        Query
                      </span>
                    )}
                    {msg.modelInfo && (
                      <span className="bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                        {msg.modelInfo.model_name} ({msg.modelInfo.server})
                      </span>
                    )}
                    {/* Pipeline Trace toggle */}
                    {msg.debugLog && msg.debugLog.stages && (
                      <button
                        onClick={() => {
                          setExpandedTraces(prev => {
                            const next = new Set(prev);
                            if (next.has(msg.id)) {
                              next.delete(msg.id);
                            } else {
                              next.add(msg.id);
                            }
                            return next;
                          });
                        }}
                        className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors ${
                          expandedTraces.has(msg.id)
                            ? 'bg-purple-100 text-purple-700'
                            : 'bg-light-100 text-light-500 hover:bg-purple-50 hover:text-purple-600'
                        }`}
                        title="Toggle pipeline execution trace"
                      >
                        <Code className="w-3 h-3" />
                        Pipeline Trace
                        {msg.debugLog.total_duration_ms && (
                          <span className="font-mono">({msg.debugLog.total_duration_ms}ms)</span>
                        )}
                      </button>
                    )}
                  </div>
                  {/* Pipeline Trace Panel */}
                  {msg.debugLog && expandedTraces.has(msg.id) && (
                    <PipelineTrace
                      debugLog={msg.debugLog}
                      messageId={msg.id}
                      expandedStages={expandedStages}
                      setExpandedStages={setExpandedStages}
                    />
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-light-100 rounded-lg p-3 flex items-center gap-2 border border-light-200">
              <Loader2 className="w-4 h-4 text-owl-purple-500 animate-spin" />
              <span className="text-sm text-light-700">Analyzing...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-light-200">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about the investigation..."
            className="flex-1 bg-white border border-light-300 rounded-lg px-3 py-2 text-sm text-light-900 placeholder-light-500 focus:outline-none focus:border-owl-purple-500 resize-none min-h-[40px] max-h-[120px]"
            rows={1}
            disabled={isLoading}
          />
          <button
            onClick={() => setIncludeGraphNodes(!includeGraphNodes)}
            disabled={isLoading}
            className={`p-2 rounded-lg transition-colors border ${
              includeGraphNodes
                ? 'bg-owl-purple-100 border-owl-purple-300 text-owl-purple-700 hover:bg-owl-purple-200'
                : 'bg-white border-light-300 text-light-600 hover:bg-light-50'
            }`}
            title={includeGraphNodes ? 'Including graph nodes - Click to use document search only' : 'Document search only - Click to include graph nodes'}
          >
            <Network className="w-5 h-5" />
          </button>
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="p-2 bg-owl-purple-500 hover:bg-owl-purple-600 disabled:bg-light-300 disabled:text-light-500 text-white rounded-lg transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Chat History List Modal */}
      <ChatHistoryList
        isOpen={showChatHistory}
        onClose={() => setShowChatHistory(false)}
        onLoadChat={(chatMessages) => {
          setMessages(chatMessages);
          onMessagesChange?.(chatMessages);
          setLastAutoSaveCount(chatMessages.length);
          setShowChatHistory(false);
        }}
        currentCaseId={currentCaseId}
      />
    </div>
  );
}
