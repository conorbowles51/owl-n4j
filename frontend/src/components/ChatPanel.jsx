import React, { useState, useRef, useEffect } from 'react';
import { 
  MessageSquare, 
  Send, 
  X, 
  ChevronRight, 
  Loader2, 
  Sparkles,
  Target,
  Globe
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { chatAPI } from '../services/api';

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
  onMessagesChange // Callback to notify parent of message changes
}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
      loadSuggestions();
    }
  }, [isOpen, selectedNodes]);

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
    };
    setMessages(prev => {
      const newMessages = [...prev, userMessage];
      onMessagesChange?.(newMessages);
      return newMessages;
    });

    // Get selected node keys
    const selectedKeys = selectedNodes.map(n => n.key);

    setIsLoading(true);

    try {
      const response = await chatAPI.ask(question, selectedKeys.length > 0 ? selectedKeys : null);

      // Add assistant message
      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.answer,
        contextMode: response.context_mode,
        contextDescription: response.context_description,
        cypherUsed: response.cypher_used,
      };
      setMessages(prev => {
        const newMessages = [...prev, assistantMessage];
        onMessagesChange?.(newMessages);
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
          <h2 className="font-semibold text-owl-blue-900">AI Assistant</h2>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-light-100 rounded transition-colors"
        >
          <X className="w-5 h-5 text-light-600" />
        </button>
      </div>

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
                <div className="text-sm prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-0.5 prose-headings:my-2 prose-strong:text-owl-blue-700 prose-table:text-xs">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              )}
              
              {/* Context badge for assistant messages */}
              {msg.role === 'assistant' && !msg.isError && (
                <div className="mt-2 pt-2 border-t border-light-300 flex items-center gap-2 text-xs text-light-600">
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
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="p-2 bg-owl-purple-500 hover:bg-owl-purple-600 disabled:bg-light-300 disabled:text-light-500 text-white rounded-lg transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
