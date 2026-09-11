import { useState } from 'react'
import DocumentGenerate from './DocumentGenerate'
import DocumentReview from './DocumentReview'
import DocumentCompare from './DocumentCompare'
import DocumentUpload from './DocumentUpload'
import './DocumentHub.css'

function DocumentHub({ sessionId, setSessionId }) {
    const [activeView, setActiveView] = useState('hub') // 'hub' | 'generate' | 'review' | 'compare' | 'chat'

    const goBack = () => setActiveView('hub')

    if (activeView === 'generate') {
        return <DocumentGenerate onBack={goBack} />
    }
    if (activeView === 'review') {
        return <DocumentReview onBack={goBack} />
    }
    if (activeView === 'compare') {
        return <DocumentCompare onBack={goBack} />
    }
    if (activeView === 'chat') {
        return (
            <div className="doc-upload-container animate-fade-in">
                <div className="doc-subview-header">
                    <button className="back-btn" onClick={goBack}>← Back to Hub</button>
                    <div className="subview-title-group">
                        <h2 className="subview-title">💬 Chat with Documents</h2>
                        <p className="subview-subtitle">Upload case files and ask questions directly</p>
                    </div>
                </div>
                <DocumentUpload sessionId={sessionId} setSessionId={setSessionId} />
            </div>
        )
    }

    return (
        <div className="doc-hub">
            {/* Hero Header */}
            <div className="doc-hub-hero">
                <div className="hero-badge">
                    <span className="hero-badge-icon">📑</span>
                    AI-Powered
                </div>
                <h2 className="doc-hub-title">
                    Document Generation Hub
                </h2>
                <p className="doc-hub-subtitle">
                    Create, review, and compare professional legal documents with AI-powered precision
                </p>
            </div>

            {/* Section Label */}
            <div className="doc-hub-section-label">
                <span className="section-line"></span>
                <span className="section-text">Document Actions</span>
                <span className="section-line"></span>
            </div>

            {/* Action Cards */}
            <div className="doc-hub-cards">
                {/* Generate Card */}
                <div className="doc-action-card" onClick={() => setActiveView('generate')}>
                    <div className="card-glow card-glow-generate"></div>
                    <div className="card-icon-wrapper card-icon-generate">
                        <span className="card-icon">✨</span>
                    </div>
                    <h3 className="card-title">Generate New Document</h3>
                    <p className="card-description">
                        Create professional legal documents from scratch using our AI-powered templates. Choose from a variety of document types and customize them to your specific needs.
                    </p>
                    <ul className="card-features">
                        <li><span className="feature-check">✓</span>AI-powered document generation</li>
                        <li><span className="feature-check">✓</span>Multiple document templates</li>
                        <li><span className="feature-check">✓</span>Real-time customization</li>
                        <li><span className="feature-check">✓</span>Instant download options</li>
                    </ul>
                    <button className="card-cta card-cta-generate">
                        Start Generating
                        <span className="cta-arrow">→</span>
                    </button>
                </div>

                {/* Review Card */}
                <div className="doc-action-card" onClick={() => setActiveView('review')}>
                    <div className="card-glow card-glow-review"></div>
                    <div className="card-icon-wrapper card-icon-review">
                        <span className="card-icon">🔍</span>
                    </div>
                    <h3 className="card-title">Review Existing Document</h3>
                    <p className="card-description">
                        Upload and analyze your legal documents with comprehensive AI-powered review tools. Get detailed insights, risk assessments, and improvement suggestions.
                    </p>
                    <ul className="card-features">
                        <li><span className="feature-check">✓</span>Comprehensive document analysis</li>
                        <li><span className="feature-check">✓</span>Risk assessment reports</li>
                        <li><span className="feature-check">✓</span>Compliance checking</li>
                        <li><span className="feature-check">✓</span>Detailed improvement suggestions</li>
                    </ul>
                    <button className="card-cta card-cta-review">
                        Start Reviewing
                        <span className="cta-arrow">→</span>
                    </button>
                </div>

                {/* Chat/Analyze Card - NEW */}
                <div className="doc-action-card" onClick={() => setActiveView('chat')}>
                    <div className="card-glow card-glow-chat"></div>
                    <div className="card-icon-wrapper card-icon-chat">
                        <span className="card-icon">💬</span>
                    </div>
                    <h3 className="card-title">Chat with Documents</h3>
                    <p className="card-description">
                        Upload FIRs, charge sheets, or case files and ask questions. Get instant answers based on the document content and legal context.
                    </p>
                    <ul className="card-features">
                        <li><span className="feature-check">✓</span>Interactive Q&A</li>
                        <li><span className="feature-check">✓</span>Fact extraction</li>
                        <li><span className="feature-check">✓</span>Context-aware answers</li>
                        <li><span className="feature-check">✓</span>Works with PDF/Word/Text</li>
                    </ul>
                    <button className="card-cta card-cta-chat">
                        Start Chatting
                        <span className="cta-arrow">→</span>
                    </button>
                </div>

                {/* Compare Card */}
                <div className="doc-action-card" onClick={() => setActiveView('compare')}>
                    <div className="card-glow card-glow-compare"></div>
                    <div className="card-icon-wrapper card-icon-compare">
                        <span className="card-icon">⚖️</span>
                    </div>
                    <h3 className="card-title">Compare Documents</h3>
                    <p className="card-description">
                        Compare multiple legal documents side-by-side to identify differences, similarities, and potential issues. Perfect for contract negotiations and revisions.
                    </p>
                    <ul className="card-features">
                        <li><span className="feature-check">✓</span>Side-by-side comparison</li>
                        <li><span className="feature-check">✓</span>Difference highlighting</li>
                        <li><span className="feature-check">✓</span>Version tracking</li>
                        <li><span className="feature-check">✓</span>Export comparison reports</li>
                    </ul>
                    <button className="card-cta card-cta-compare">
                        Start Comparing
                        <span className="cta-arrow">→</span>
                    </button>
                </div>
            </div>
        </div>
    )
}

export default DocumentHub
