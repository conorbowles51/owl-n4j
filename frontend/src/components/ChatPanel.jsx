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
  Info
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { chatAPI, llmConfigAPI } from '../services/api';
import ChatHistoryList from './ChatHistoryList';

/**
 * Format debug log as markdown
 */
function formatDebugLogAsMarkdown(debugLog, question) {
  const lines = [];
  
  // Header
  lines.push('# AI Assistant Debug Log');
  lines.push('');
  
  // Timestamp
  const timestamp = debugLog.timestamp || new Date().toISOString();
  lines.push(`**Timestamp:** ${timestamp}`);
  lines.push('');
  
  // Question
  lines.push('## Question');
  lines.push(question);
  lines.push('');
  
  // Selected Keys
  if (debugLog.selected_keys && debugLog.selected_keys.length > 0) {
    lines.push(`**Selected Node Keys:** ${debugLog.selected_keys.join(', ')}`);
    lines.push('');
  }
  
  // Graph Summary
  if (debugLog.graph_summary) {
    lines.push('## Graph Summary');
    lines.push(`- **Total Nodes:** ${debugLog.graph_summary.total_nodes || 0}`);
    lines.push(`- **Total Relationships:** ${debugLog.graph_summary.total_relationships || 0}`);
    lines.push(`- **Entity Types:** ${(debugLog.graph_summary.entity_types || []).join(', ')}`);
    lines.push(`- **Relationship Types:** ${(debugLog.graph_summary.relationship_types || []).join(', ')}`);
    lines.push('');
  }
  
  // Vector Search
  if (debugLog.vector_search) {
    lines.push('## Vector Search (Semantic Document Search)');
    if (debugLog.vector_search.enabled) {
      lines.push('- **Status:** Enabled');
      lines.push(`- **Question:** ${debugLog.vector_search.question || 'N/A'}`);
      lines.push(`- **Embedding Dimensions:** ${debugLog.vector_search.embedding_dimensions || 'N/A'}`);
      lines.push(`- **Top K:** ${debugLog.vector_search.top_k || 'N/A'}`);
      
      const results = debugLog.vector_search.results || [];
      if (results.length > 0) {
        lines.push(`- **Documents Found:** ${results.length}`);
        lines.push('');
        lines.push('### Vector Search Results');
        results.forEach((result, i) => {
          lines.push(`\n#### Document ${i + 1}`);
          lines.push(`- **Document ID:** \`${result.document_id || 'N/A'}\``);
          lines.push(`- **Filename:** ${result.filename || 'N/A'}`);
          lines.push(`- **Distance:** ${result.distance !== undefined ? result.distance.toFixed(4) : 'N/A'}`);
          lines.push(`- **Text Preview:** ${result.text_preview || 'N/A'}`);
        });
      } else {
        lines.push('- **Documents Found:** 0');
      }
    } else {
      lines.push('- **Status:** Disabled');
      lines.push(`- **Reason:** ${debugLog.vector_search.reason || 'Unknown'}`);
    }
    
    if (debugLog.vector_search.error) {
      lines.push(`- **Error:** ${debugLog.vector_search.error}`);
    }
    
    lines.push('');
  }
  
  // Neo4j Document Query
  if (debugLog.neo4j_document_query) {
    lines.push('## Neo4j Query: Nodes from Documents');
    lines.push('');
    lines.push('### Cypher Query');
    lines.push('```cypher');
    lines.push(debugLog.neo4j_document_query.cypher || 'N/A');
    lines.push('```');
    lines.push('');
    
    if (debugLog.neo4j_document_query.parameters) {
      lines.push('### Parameters');
      Object.entries(debugLog.neo4j_document_query.parameters).forEach(([key, value]) => {
        if (Array.isArray(value)) {
          lines.push(`- **${key}:** \`${JSON.stringify(value)}\` (${value.length} items)`);
        } else {
          lines.push(`- **${key}:** \`${value}\``);
        }
      });
      lines.push('');
    }
    
    if (debugLog.neo4j_document_query.results) {
      lines.push('### Query Results');
      lines.push(`- **Nodes Found:** ${debugLog.neo4j_document_query.results.nodes_found || 0}`);
      const nodes = debugLog.neo4j_document_query.results.nodes || [];
      if (nodes.length > 0) {
        lines.push('');
        lines.push('#### Nodes');
        nodes.slice(0, 20).forEach(node => {
          lines.push(`- **${node.name || 'Unknown'}** (\`${node.key || 'N/A'}\`) - ${node.type || 'Unknown'}`);
        });
        if (nodes.length > 20) {
          lines.push(`\n... and ${nodes.length - 20} more nodes`);
        }
      }
    }
    
    if (debugLog.neo4j_document_query.error) {
      lines.push(`**Error:** ${debugLog.neo4j_document_query.error}`);
    }
    
    lines.push('');
  }
  
  // Cypher Filter Query
  if (debugLog.cypher_filter_query) {
    lines.push('## Cypher Filter Query (LLM-Generated)');
    lines.push('');
    lines.push('### Generated Cypher Query');
    lines.push('```cypher');
    lines.push(debugLog.cypher_filter_query.generated_cypher || 'N/A');
    lines.push('```');
    lines.push('');
    
    if (debugLog.cypher_filter_query.results) {
      if (typeof debugLog.cypher_filter_query.results === 'object') {
        lines.push('### Query Results');
        lines.push(`- **Nodes Found:** ${debugLog.cypher_filter_query.results.nodes_found || 0}`);
        if (debugLog.cypher_filter_query.results.node_keys) {
          lines.push(`- **Node Keys:** ${debugLog.cypher_filter_query.results.node_keys.join(', ')}`);
        }
      } else {
        lines.push(`### Query Results: ${debugLog.cypher_filter_query.results}`);
      }
    }
    
    if (debugLog.cypher_filter_query.error) {
      lines.push(`**Error:** ${debugLog.cypher_filter_query.error}`);
    }
    
    lines.push('');
  }
  
  // Cypher Answer Query
  if (debugLog.cypher_answer_query) {
    lines.push('## Cypher Answer Query (Direct Question Query)');
    lines.push('');
    lines.push('### Generated Cypher Query');
    lines.push('```cypher');
    lines.push(debugLog.cypher_answer_query.generated_cypher || 'N/A');
    lines.push('```');
    lines.push('');
    
    if (debugLog.cypher_answer_query.results) {
      if (typeof debugLog.cypher_answer_query.results === 'object') {
        lines.push('### Query Results');
        lines.push(`- **Rows Returned:** ${debugLog.cypher_answer_query.results.rows_returned || 0}`);
        const sample = debugLog.cypher_answer_query.results.sample_results || [];
        if (sample.length > 0) {
          lines.push('');
          lines.push('#### Sample Results');
          sample.slice(0, 10).forEach((row, i) => {
            lines.push(`${i + 1}. ${JSON.stringify(row)}`);
          });
        }
      } else {
        lines.push(`### Query Results: ${debugLog.cypher_answer_query.results}`);
      }
    }
    
    lines.push('');
  }
  
  // Focused Context Query
  if (debugLog.focused_context_query) {
    lines.push('## Focused Context Query (User-Selected Nodes)');
    lines.push('');
    lines.push('### Cypher Query');
    lines.push('```cypher');
    lines.push(debugLog.focused_context_query.cypher || 'N/A');
    lines.push('```');
    lines.push('');
    if (debugLog.focused_context_query.parameters) {
      lines.push('### Parameters');
      Object.entries(debugLog.focused_context_query.parameters).forEach(([key, value]) => {
        if (Array.isArray(value)) {
          lines.push(`- **${key}:** \`${JSON.stringify(value)}\` (${value.length} items)`);
        } else {
          lines.push(`- **${key}:** \`${value}\``);
        }
      });
      lines.push('');
    }
    lines.push(`- **Selected Node Keys:** ${(debugLog.focused_context_query.selected_node_keys || []).join(', ')}`);
    lines.push('');
  }
  
  // Focused Context Results
  if (debugLog.focused_context) {
    lines.push('## Focused Context Results');
    lines.push('');
    lines.push(`- **Entities Count:** ${debugLog.focused_context.entities_count || 0}`);
    const entities = debugLog.focused_context.entities || [];
    if (entities.length > 0) {
      lines.push('');
      lines.push('### Selected Entities');
      entities.forEach(entity => {
        lines.push(`- **${entity.name || 'Unknown'}** (\`${entity.key || 'N/A'}\`) - ${entity.type || 'Unknown'}`);
      });
    }
    lines.push('');
  }
  
  // Hybrid Filtering
  if (debugLog.hybrid_filtering) {
    lines.push('## Hybrid Filtering Summary');
    lines.push('');
    lines.push(`- **Vector Document IDs:** ${JSON.stringify(debugLog.hybrid_filtering.vector_doc_ids || [])}`);
    lines.push(`- **Vector Node Keys:** ${(debugLog.hybrid_filtering.vector_node_keys || []).length} nodes`);
    lines.push(`- **Cypher Node Keys:** ${(debugLog.hybrid_filtering.cypher_node_keys || []).length} nodes`);
    lines.push(`- **Combined Node Keys:** ${debugLog.hybrid_filtering.total_combined || 0} nodes`);
    lines.push('');
    const combined = debugLog.hybrid_filtering.combined_node_keys || [];
    if (combined.length > 0) {
      lines.push('### Combined Node Keys (First 50)');
      lines.push(combined.join(', '));
      lines.push('');
    }
  }
  
  // Context Mode
  if (debugLog.context_mode) {
    lines.push('## Context Mode');
    lines.push(`**Mode:** \`${debugLog.context_mode}\``);
    lines.push('');
  }
  
  // Context Preview
  if (debugLog.context_preview) {
    lines.push('## Context Preview');
    lines.push('');
    lines.push('```');
    lines.push(debugLog.context_preview);
    lines.push('```');
    lines.push('');
  }
  
  // Final Prompt
  if (debugLog.final_prompt) {
    lines.push('## Final Prompt Sent to LLM');
    lines.push('');
    lines.push('```');
    lines.push(debugLog.final_prompt);
    lines.push('```');
    lines.push('');
  }
  
  return lines.join('\n');
}

// Debug logs are now stored in system logs (no need to download)

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
    try {
      const selectedKeys = selectedNodes.map(n => n.key);
      const data = await chatAPI.getSuggestions(selectedKeys.length > 0 ? selectedKeys : null);
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
    <div className="w-96 bg-white border-l border-light-200 h-full flex flex-col shadow-sm">
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
                  </div>
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
