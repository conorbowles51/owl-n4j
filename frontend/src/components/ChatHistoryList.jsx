import React, { useState, useEffect } from 'react';
import { MessageSquare, X, Trash2, Calendar, Clock } from 'lucide-react';
import { chatHistoryAPI } from '../services/api';

/**
 * ChatHistoryList Component
 * 
 * Displays a list of saved chat histories
 */
export default function ChatHistoryList({ isOpen, onClose, onLoadChat, currentCaseId }) {
  const [chatHistories, setChatHistories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedChat, setSelectedChat] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadChatHistories();
    }
  }, [isOpen, currentCaseId]);

  const loadChatHistories = async () => {
    setLoading(true);
    try {
      const data = await chatHistoryAPI.list();
      // Filter by current case if provided
      const filtered = currentCaseId 
        ? data.filter(chat => chat.case_id === currentCaseId)
        : data;
      setChatHistories(filtered);
    } catch (err) {
      console.error('Failed to load chat histories:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (chatId, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this chat history?')) {
      return;
    }

    try {
      await chatHistoryAPI.delete(chatId);
      await loadChatHistories();
      if (selectedChat?.id === chatId) {
        setSelectedChat(null);
      }
    } catch (err) {
      console.error('Failed to delete chat history:', err);
      alert(`Failed to delete chat history: ${err.message}`);
    }
  };

  const handleView = async (chat) => {
    try {
      const fullChat = await chatHistoryAPI.get(chat.id);
      setSelectedChat(fullChat);
    } catch (err) {
      console.error('Failed to load chat history:', err);
      alert(`Failed to load chat history: ${err.message}`);
    }
  };

  const handleLoad = () => {
    if (onLoadChat && selectedChat) {
      onLoadChat(selectedChat.messages);
      onClose();
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg w-full max-w-4xl h-[80vh] flex flex-col border border-light-200 shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-light-200">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-owl-purple-500" />
            <h2 className="text-lg font-semibold text-owl-blue-900">Chat Histories</h2>
            <span className="text-xs text-light-600 bg-light-100 px-2 py-1 rounded">
              {chatHistories.length} chat{chatHistories.length !== 1 ? 's' : ''}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-light-100 rounded transition-colors"
          >
            <X className="w-5 h-5 text-light-600" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Chat Histories List */}
          <div className="w-1/2 border-r border-light-200 overflow-y-auto">
            {loading ? (
              <div className="p-8 text-center text-light-600">Loading chat histories...</div>
            ) : chatHistories.length === 0 ? (
              <div className="p-8 text-center text-light-600">
                <MessageSquare className="w-12 h-12 mx-auto mb-3 text-light-400" />
                <p>No chat histories saved yet</p>
              </div>
            ) : (
              <div className="p-2">
                {chatHistories.map((chat) => (
                  <div
                    key={chat.id}
                    onClick={() => handleView(chat)}
                    className={`p-3 mb-2 rounded-lg cursor-pointer transition-colors ${
                      selectedChat?.id === chat.id
                        ? 'bg-owl-purple-100 border border-owl-purple-300'
                        : 'bg-light-50 hover:bg-light-100 border border-light-200'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-owl-blue-900 truncate">{chat.name}</h3>
                        <div className="flex items-center gap-3 mt-2 text-xs text-light-600">
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {formatDate(chat.created_at)}
                          </span>
                          <span>{chat.message_count} messages</span>
                        </div>
                        {chat.snapshot_id && (
                          <div className="mt-1 text-xs text-owl-purple-600">
                            From snapshot
                          </div>
                        )}
                        {chat.case_name && (
                          <div className="mt-1 text-xs text-owl-blue-600">
                            Case: {chat.case_name}
                            {chat.case_version && ` (v${chat.case_version})`}
                          </div>
                        )}
                      </div>
                      <button
                        onClick={(e) => handleDelete(chat.id, e)}
                        className="p-1 hover:bg-light-200 rounded transition-colors ml-2"
                        title="Delete chat history"
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Chat Details */}
          <div className="w-1/2 p-4 overflow-y-auto">
            {selectedChat ? (
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold text-owl-blue-900 mb-2">{selectedChat.name}</h3>
                  <div className="text-xs text-light-600">
                    <p>Created: {formatDate(selectedChat.created_at)}</p>
                    <p>Messages: {selectedChat.message_count}</p>
                    {selectedChat.snapshot_id && (
                      <p className="mt-2 text-owl-purple-600">Associated with snapshot</p>
                    )}
                    {selectedChat.case_name && (
                      <div className="mt-2 pt-2 border-t border-light-200">
                        <p className="font-medium text-owl-blue-700">Associated Case:</p>
                        <p>{selectedChat.case_name}</p>
                        {selectedChat.case_version && (
                          <p className="text-light-500">Version {selectedChat.case_version}</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {selectedChat.messages && selectedChat.messages.length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-owl-blue-900 mb-2">Messages</h4>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {selectedChat.messages.map((msg, idx) => (
                        <div key={idx} className={`rounded p-2 text-xs border ${
                          msg.role === 'user' 
                            ? 'bg-owl-blue-50 border-owl-blue-200' 
                            : 'bg-light-50 border-light-200'
                        }`}>
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`font-medium ${
                              msg.role === 'user' ? 'text-owl-blue-700' : 'text-owl-purple-600'
                            }`}>
                              {msg.role === 'user' ? 'User' : 'AI'}
                            </span>
                            {msg.timestamp && (
                              <span className="text-light-500 text-xs">
                                <Clock className="w-3 h-3 inline mr-1" />
                                {new Date(msg.timestamp).toLocaleTimeString()}
                              </span>
                            )}
                          </div>
                          <p className="text-light-700 whitespace-pre-wrap">{msg.content}</p>
                          {msg.cypherUsed && (
                            <details className="mt-2">
                              <summary className="text-xs text-light-600 cursor-pointer">Cypher Query</summary>
                              <pre className="mt-1 p-2 bg-light-100 rounded text-xs overflow-x-auto">
                                {msg.cypherUsed}
                              </pre>
                            </details>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={handleLoad}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-owl-purple-500 hover:bg-owl-purple-600 text-white rounded-lg transition-colors"
                  >
                    <MessageSquare className="w-4 h-4" />
                    Load Chat
                  </button>
                </div>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-light-600">
                <div className="text-center">
                  <MessageSquare className="w-12 h-12 mx-auto mb-3 text-light-400" />
                  <p>Select a chat history to view details</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

