import { useState, useCallback } from 'react'
import { connectSSE } from './api'
import './App.css'
import { AuthProvider, useAuth } from './context/AuthContext'
import AuthPage from './pages/AuthPage'
import Header from './components/Header'
import NavMenu from './components/NavMenu'
import QueryInput from './components/QueryInput'
import PipelineVisualizer from './components/PipelineVisualizer'
import Loader from './components/Loader'
import ResponseCard from './components/ResponseCard'
import NewsWidget from './components/NewsWidget'
import ChatHistory from './components/ChatHistory'

import SampleQueries from './components/SampleQueries'
import KanoonSearch from './components/KanoonSearch'
import DocumentHub from './components/DocumentHub'
import CasePredictAI from './components/CasePredictAI'
import CounterArgument from './components/CounterArgument'
import LegalSandbox from './components/LegalSandbox'
import Footer from './components/Footer'

function AppContent() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('auto')
  const [isLoading, setIsLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [pipelineStages, setPipelineStages] = useState([])
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('query')
  const [sessionId, setSessionId] = useState(null)
  const [conversationId, setConversationId] = useState(null)
  const [showAuth, setShowAuth] = useState(false)

  // Pipeline stages for visualization (v2.0 — includes web search and quality review)
  const stages = [
    { id: 'classify', name: 'Classifying', icon: '🔍' },
    { id: 'reformulate', name: 'Reformulating', icon: '📝' },
    { id: 'retrieve', name: 'Retrieving', icon: '📚' },
    { id: 'score', name: 'Scoring', icon: '📊' },
    { id: 'web_search', name: 'Web Search', icon: '🌐' },
    { id: 'generate', name: 'Generating', icon: '✨' },
    { id: 'quality_review', name: 'Quality Review', icon: '✅' },
  ]

  // SSE Connection for real-time pipeline updates
  const connectToSSE = (queryData) => {
    const options = {
      mode: queryData.mode || mode,
      sessionId: sessionId || queryData.session_id,
      custodyDays: queryData.custody_days || null,
      offenseSections: queryData.offense_sections || null
    };

    const callbacks = {
      onStage: (stageId, status, data) => {
        setPipelineStages(prev => prev.map(s =>
          s.id === stageId ? { ...s, status, data: data || null } : s
        ))
      },
      onComplete: (resp) => {
        setResponse(resp)
        setIsLoading(false)
      },
      onError: (msg) => {
        setError(msg)
        setIsLoading(false)
        // Fallback to regular API if SSE fails
        submitQuery(queryData)
      }
    };

    return connectSSE(queryData.query, options, callbacks)
  }

  // Regular API submission (fallback)
  const submitQuery = async (queryData) => {
    try {
      const response = await fetch('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(queryData),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Request failed')
      }

      const data = await response.json()
      setResponse(data)

      // Mark all stages as complete
      setPipelineStages(stages.map(s => ({ ...s, status: 'complete' })))
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  // Handle form submission
  const handleSubmit = async (queryData) => {
    setIsLoading(true)
    setError(null)
    setResponse(null)
    setPipelineStages(stages.map(s => ({ ...s, status: 'pending' })))

    // Start SSE connection
    connectToSSE(queryData)
  }

  const handleSampleQuery = (sampleQuery) => {
    setQuery(sampleQuery)
    setActiveTab('query')
  }

  const handleSelectConversation = (convoId) => {
    setConversationId(convoId)
    setActiveTab('query')
  }

  // Show auth page if user explicitly requested it
  if (showAuth && !isAuthenticated) {
    return <AuthPage />
  }

  // Show loading while checking auth
  if (authLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <Loader text="Initializing JustiAssist..." />
      </div>
    )
  }

  return (
    <div className="app">
      <Header onShowAuth={() => setShowAuth(true)} />

      {/* Animated Navigation Menu */}
      <NavMenu activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="main-content">
        {/* Query Tab */}
        {activeTab === 'query' && (
          <div className="query-tab animate-fade-in">
            <QueryInput
              query={query}
              setQuery={setQuery}
              mode={mode}
              setMode={setMode}
              onSubmit={handleSubmit}
              isLoading={isLoading}
              activeStage={pipelineStages.find(s => s.status === 'active')?.name}
            />

            {/* Pipeline Visualizer - Shows during loading */}
            {isLoading && (
              <>
                <Loader text="Processing your query..." hint="CrewAI agents working..." />
                <PipelineVisualizer stages={pipelineStages} />
              </>
            )}

            {/* Error Display */}
            {error && (
              <div className="error-card glass-card animate-fade-in">
                <span className="error-icon">⚠️</span>
                <p>{error}</p>
                <button onClick={() => setError(null)} className="dismiss-btn">✕</button>
              </div>
            )}

            {/* Response */}
            {response && !isLoading && (
              <ResponseCard response={response} />
            )}

            {/* Sample Queries */}
            {!response && !isLoading && (
              <SampleQueries onSelect={handleSampleQuery} />
            )}
          </div>
        )}

        {/* Chat History Tab */}
        {activeTab === 'history' && (
          <div className="history-tab animate-fade-in">
            <ChatHistory
              onSelectConversation={handleSelectConversation}
              activeConversationId={conversationId}
            />
          </div>
        )}

        {/* Case Law Tab */}
        {activeTab === 'caselaw' && (
          <div className="caselaw-tab animate-fade-in">
            <KanoonSearch />
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="documents-tab animate-fade-in">
            <DocumentHub sessionId={sessionId} setSessionId={setSessionId} />
          </div>
        )}

        {/* CasePredictAI Tab */}
        {activeTab === 'predict' && (
          <div className="predict-tab animate-fade-in">
            <CasePredictAI />
          </div>
        )}

        {/* Counter Argument Tab */}
        {activeTab === 'counter' && (
          <div className="counter-tab animate-fade-in">
            <CounterArgument />
          </div>
        )}

        {/* Legal Sandbox Tab */}
        {activeTab === 'sandbox' && (
          <div className="sandbox-tab animate-fade-in">
            <LegalSandbox />
          </div>
        )}

        {/* News Tab */}
        {activeTab === 'news' && (
          <div className="news-tab animate-fade-in">
            <NewsWidget fullPage={true} />
          </div>
        )}
      </main>

      <Footer />
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

export default App
