import React, { useState, useEffect, useCallback } from 'react';
import {
  MessageSquare, Loader2, Send, Lightbulb, ChevronDown,
  ChevronUp, Sparkles, X, Play, AlertTriangle,
} from 'lucide-react';
import { triageAPI } from '../../services/api';

function SuggestionCard({ suggestion, onAction }) {
  const priorityColors = {
    high: 'border-red-200 bg-red-50',
    medium: 'border-amber-200 bg-amber-50',
    low: 'border-blue-200 bg-blue-50',
  };
  const priorityBadge = {
    high: 'bg-red-100 text-red-700',
    medium: 'bg-amber-100 text-amber-700',
    low: 'bg-blue-100 text-blue-700',
  };

  const priority = suggestion.priority || 'medium';

  return (
    <div className={`border rounded-lg p-3 ${priorityColors[priority] || priorityColors.medium}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${priorityBadge[priority]}`}>
              {priority.toUpperCase()}
            </span>
            <span className="text-sm font-medium text-light-800">{suggestion.action}</span>
          </div>
          <p className="text-xs text-light-600">{suggestion.detail}</p>
        </div>
        {(suggestion.processor || suggestion.stage_type) && (
          <button
            onClick={() => onAction && onAction(suggestion)}
            className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-owl-blue-600 bg-white border border-owl-blue-200 rounded hover:bg-owl-blue-50 flex-shrink-0"
          >
            <Play className="w-3 h-3" />
            Act
          </button>
        )}
      </div>
    </div>
  );
}

export default function TriageAdvisor({ caseId, triageCase, onAction }) {
  const [isOpen, setIsOpen] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  const loadSuggestions = useCallback(async () => {
    if (!caseId) return;
    setLoadingSuggestions(true);
    try {
      const data = await triageAPI.advisorSuggest(caseId);
      setSuggestions(data.suggestions || []);
    } catch (err) {
      console.error('Failed to load suggestions:', err);
    } finally {
      setLoadingSuggestions(false);
    }
  }, [caseId]);

  useEffect(() => {
    if (isOpen) loadSuggestions();
  }, [isOpen, loadSuggestions]);

  const handleSend = async () => {
    const q = input.trim();
    if (!q || sending) return;

    setMessages((prev) => [...prev, { role: 'user', content: q }]);
    setInput('');
    setSending(true);

    try {
      const data = await triageAPI.advisorChat(caseId, { question: q });
      setMessages((prev) => [
        ...prev,
        { role: 'advisor', content: data.answer || 'No response.' },
      ]);
      // Update suggestions if provided
      if (data.suggestions?.length) {
        setSuggestions(data.suggestions);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'advisor', content: `Error: ${err.message || 'Failed to get response'}` },
      ]);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 flex items-center gap-2 px-4 py-2.5 bg-owl-blue-600 text-white rounded-full shadow-lg hover:bg-owl-blue-700 transition-colors z-50"
        title="Open Triage Advisor"
      >
        <Sparkles className="w-4 h-4" />
        Advisor
        {suggestions.length > 0 && (
          <span className="bg-white text-owl-blue-600 text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
            {suggestions.length}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 w-96 max-h-[600px] bg-white rounded-xl shadow-2xl border border-light-200 flex flex-col z-50">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-light-200 bg-owl-blue-50 rounded-t-xl">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-owl-blue-600" />
          <span className="text-sm font-semibold text-owl-blue-900">Triage Advisor</span>
        </div>
        <button onClick={() => setIsOpen(false)} className="p-1 hover:bg-owl-blue-100 rounded">
          <X className="w-4 h-4 text-light-500" />
        </button>
      </div>

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div className="px-3 py-2 border-b border-light-200 bg-light-50 max-h-48 overflow-y-auto">
          <div className="flex items-center gap-1.5 mb-2">
            <Lightbulb className="w-3.5 h-3.5 text-amber-500" />
            <span className="text-xs font-semibold text-light-700">Suggested Actions</span>
          </div>
          <div className="space-y-2">
            {suggestions.map((s, i) => (
              <SuggestionCard key={i} suggestion={s} onAction={onAction} />
            ))}
          </div>
        </div>
      )}
      {loadingSuggestions && (
        <div className="px-3 py-2 border-b border-light-200 flex items-center gap-2 text-xs text-light-500">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading suggestions...
        </div>
      )}

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3 min-h-[200px] max-h-[300px]">
        {messages.length === 0 && (
          <div className="text-center text-xs text-light-400 py-8">
            Ask a question about your triage case...
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-owl-blue-600 text-white'
                  : 'bg-light-100 text-light-800'
              }`}
            >
              <p className="whitespace-pre-wrap text-xs">{msg.content}</p>
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-light-100 rounded-lg px-3 py-2">
              <Loader2 className="w-4 h-4 animate-spin text-light-500" />
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-3 py-2 border-t border-light-200 flex items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about this triage case..."
          className="flex-1 px-3 py-1.5 text-sm border border-light-200 rounded-lg focus:outline-none focus:border-owl-blue-400"
          disabled={sending}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || sending}
          className="p-1.5 bg-owl-blue-600 text-white rounded-lg disabled:opacity-40 hover:bg-owl-blue-700 transition-colors"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
