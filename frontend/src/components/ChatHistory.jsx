/**
 * JustiAssist Chat History Panel
 * Shows past conversations with search, clear, and resume functionality.
 */
import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { authFetch } from '../api'
import './ChatHistory.css'

export default function ChatHistory({ onSelectConversation, activeConversationId }) {
  const { isAuthenticated } = useAuth()
  const [conversations, setConversations] = useState([])
  const [messages, setMessages] = useState([])
  const [selectedConvo, setSelectedConvo] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  useEffect(() => {
    if (isAuthenticated) loadConversations()
  }, [isAuthenticated])

  const loadConversations = async () => {
    setIsLoading(true)
    try {
      const res = await authFetch('/api/chat/conversations?limit=15')
      if (res.ok) {
        const data = await res.json()
        setConversations(data.conversations || [])
      }
    } catch (err) {
      console.error('Error loading conversations:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const loadMessages = async (convoId) => {
    setSelectedConvo(convoId)
    try {
      const res = await authFetch(`/api/chat/history?conversation_id=${convoId}&limit=50`)
      if (res.ok) {
        const data = await res.json()
        setMessages(data.messages || [])
      }
    } catch (err) {
      console.error('Error loading messages:', err)
    }
  }

  const clearAllHistory = async () => {
    try {
      const res = await authFetch('/api/chat/history', { method: 'DELETE' })
      if (res.ok) {
        setConversations([])
        setMessages([])
        setSelectedConvo(null)
        setShowConfirm(false)
      }
    } catch (err) {
      console.error('Error clearing history:', err)
    }
  }

  const formatDate = (isoStr) => {
    if (!isoStr) return ''
    const d = new Date(isoStr)
    const now = new Date()
    const diff = now - d
    if (diff < 86400000) return 'Today'
    if (diff < 172800000) return 'Yesterday'
    return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })
  }

  if (!isAuthenticated) {
    return (
      <div className="chat-history-panel">
        <div className="chat-history-empty">
          <span className="chat-history-empty-icon">🔒</span>
          <p>Login to access chat history</p>
          <small>Your conversations are saved securely</small>
        </div>
      </div>
    )
  }

  return (
    <div className="chat-history-panel">
      <div className="chat-history-header">
        <h3>💬 Chat History</h3>
        <div className="chat-history-actions">
          <button className="chat-refresh-btn" onClick={loadConversations} title="Refresh">
            ⟳
          </button>
          <button className="chat-clear-btn" onClick={() => setShowConfirm(true)} title="Clear All">
            🗑️
          </button>
        </div>
      </div>

      {/* Clear Confirmation */}
      {showConfirm && (
        <div className="chat-confirm-dialog">
          <p>Delete all chat history?</p>
          <div className="chat-confirm-btns">
            <button className="chat-confirm-yes" onClick={clearAllHistory}>Delete All</button>
            <button className="chat-confirm-no" onClick={() => setShowConfirm(false)}>Cancel</button>
          </div>
        </div>
      )}

      {/* Conversation List */}
      {!selectedConvo ? (
        <div className="chat-convo-list">
          {isLoading ? (
            <div className="chat-history-loading">Loading...</div>
          ) : conversations.length === 0 ? (
            <div className="chat-history-empty">
              <span className="chat-history-empty-icon">📝</span>
              <p>No conversations yet</p>
              <small>Start asking legal questions</small>
            </div>
          ) : (
            conversations.map((convo) => (
              <div
                key={convo.conversation_id}
                className={`chat-convo-item ${convo.conversation_id === activeConversationId ? 'active' : ''}`}
                onClick={() => loadMessages(convo.conversation_id)}
              >
                <div className="chat-convo-preview">{convo.preview}</div>
                <div className="chat-convo-meta">
                  <span>{formatDate(convo.last_active)}</span>
                  <span>{convo.message_count} msgs</span>
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
        /* Message Detail View */
        <div className="chat-message-detail">
          <button className="chat-back-btn" onClick={() => { setSelectedConvo(null); setMessages([]) }}>
            ← Back to conversations
          </button>
          <div className="chat-messages-list">
            {messages.map((msg, i) => (
              <div key={msg.id || i} className={`chat-msg chat-msg-${msg.role}`}>
                <div className="chat-msg-role">
                  {msg.role === 'user' ? '👤 You' : '⚖️ JustiAssist'}
                </div>
                <div className="chat-msg-content">{msg.content?.substring(0, 500)}{msg.content?.length > 500 ? '...' : ''}</div>
                {msg.confidence_score && (
                  <div className="chat-msg-meta">
                    Confidence: {Math.round(msg.confidence_score * 100)}%
                    {msg.grounding_status && <span className={`chat-grounding-badge ${msg.grounding_status}`}>
                      {msg.grounding_status === 'pass' ? '✓ Verified' : msg.grounding_status}
                    </span>}
                  </div>
                )}
              </div>
            ))}
          </div>

          <button
            className="chat-resume-btn"
            onClick={() => {
              if (onSelectConversation) onSelectConversation(selectedConvo)
            }}
          >
            Resume this conversation →
          </button>
        </div>
      )}
    </div>
  )
}
