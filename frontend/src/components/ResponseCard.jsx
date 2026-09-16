import './ResponseCard.css'

function ResponseCard({ response }) {
    const formatAnswer = (text) => {
        if (!text) return ''
        return text
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
    }

    const getConfidenceClass = (score) => {
        if (score >= 0.7) return 'high'
        if (score >= 0.4) return 'medium'
        return 'low'
    }

    const getGroundingClass = (status) => {
        if (status === 'pass') return 'pass'
        if (status === 'partial') return 'partial'
        return 'fail'
    }

    const getGroundingLabel = (score) => {
        if (score >= 0.7) return 'Strong'
        if (score >= 0.4) return 'Moderate'
        return 'Limited'
    }

    const isStatutory = (type) => ['ipc', 'crpc', 'bns', 'bnss', 'bsa', 'statutory', 'act'].includes(type?.toLowerCase());
    const isUploaded = (type) => type?.toLowerCase() === 'user_upload' || type?.toLowerCase() === 'session_document';

    const confidencePercent = Math.round(response.confidence_score * 100)

    return (
        <div className="response-container animate-fade-in">
            {/* Confidence Header */}
            <div className="confidence-header glass-card">
                <div className={`query-type-badge ${response.query_type === 'bail_related' ? 'bail' : 'legal'}`}>
                    {response.query_type === 'bail_related' ? '🔓 Bail Query' : '📚 Legal Info'}
                </div>

                <div className="confidence-meter">
                    <span className="confidence-label">Evidence Grounding</span>
                    <div className="confidence-bar">
                        <div
                            className={`confidence-fill ${getConfidenceClass(response.confidence_score)}`}
                            style={{ width: `${confidencePercent}%` }}
                        />
                    </div>
                    <span className="confidence-value">{getGroundingLabel(response.confidence_score)}</span>
                </div>

                <div className={`grounding-status ${getGroundingClass(response.grounding_status)}`}>
                    <span className="status-dot" />
                    <span className="status-text">
                        {response.grounding_status === 'pass' ? 'Fully Grounded' :
                            response.grounding_status === 'partial' ? 'Partially Grounded' : 'Low Grounding'}
                    </span>
                </div>
            </div>

            {/* Sources Used Badge */}
            {response.sources_used && response.sources_used.length > 0 && (
                <div className="sources-badge">
                    <span className="sources-label">Sources:</span>
                    {response.sources_used.map((source, i) => (
                        <span key={i} className={`source-tag ${source}`}>
                            {source === 'local_vectors' && '📁 Local DB'}
                            {source === 'indian_kanoon' && '⚖️ Indian Kanoon'}
                            {source === 'legal_news' && '📰 News'}
                            {source === 'firecrawl_web' && '🌐 Web Search'}
                        </span>
                    ))}
                </div>
            )}


            {/* Claim Verification Summary */}
            {response.verification_verdicts && response.verification_verdicts.length > 0 && (
                <div className="verification-summary-badge">
                    <span className="verify-icon">✓</span>
                    <span className="verify-text">
                        {response.verification_verdicts.length} claim{response.verification_verdicts.length !== 1 ? 's' : ''} verified against available evidence
                    </span>
                </div>
            )}

            {/* Main Answer or Abstention */}
            {response.is_abstention ? (
                <div className="abstention-card glass-card">
                    <h3>⚠️ Insufficient Evidence</h3>
                    <p className="abstention-text">
                        JustiAssist could not provide a reliable answer from the available evidence.
                        Please refine your query or provide additional relevant material.
                    </p>
                </div>
            ) : (
                <div className="answer-card glass-card">
                    <h3>📋 Answer</h3>
                    <div
                        className="answer-content"
                        dangerouslySetInnerHTML={{ __html: formatAnswer(response.answer) }}
                    />
                </div>
            )}

            {/* PROMINENT: Indian Kanoon Cases */}
            {response.kanoon_cases && response.kanoon_cases.length > 0 && (
                <div className="kanoon-cases-card glass-card highlight-card">
                    <h3>
                        <span className="section-icon">⚖️</span>
                        Relevant Case Law
                        <span className="live-badge">LIVE</span>
                    </h3>
                    <p className="section-subtitle">Recent judgments from Indian Kanoon</p>
                    <div className="cases-list">
                        {response.kanoon_cases.map((caseItem, index) => (
                            <div key={index} className="case-item">
                                <div className="case-header">
                                    <span className="case-title">{caseItem.title}</span>
                                    {caseItem.court && (
                                        <span className="case-court">{caseItem.court}</span>
                                    )}
                                </div>
                                {caseItem.citation && (
                                    <div className="case-citation">📎 {caseItem.citation}</div>
                                )}
                                {caseItem.preview && (
                                    <p className="case-preview">{caseItem.preview}...</p>
                                )}
                                {caseItem.date && (
                                    <span className="case-date">{caseItem.date}</span>
                                )}
                                <a
                                    href={caseItem.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="case-link"
                                >
                                    View Full Judgment →
                                </a>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* PROMINENT: Legal News */}
            {response.news_context && response.news_context.length > 0 && (
                <div className="news-context-card glass-card highlight-card">
                    <h3>
                        <span className="section-icon">📰</span>
                        Current Legal Developments
                        <span className="live-badge">LIVE</span>
                    </h3>
                    <p className="section-subtitle">Recent news relevant to your query</p>
                    <div className="news-list">
                        {response.news_context.map((news, index) => (
                            <div key={index} className="news-item">
                                <div className="news-title">{news.title}</div>
                                <div className="news-meta">
                                    <span className="news-source">{news.source}</span>
                                    <span className="news-date">{news.date}</span>
                                </div>
                                {news.url && (
                                    <a
                                        href={news.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="news-link"
                                    >
                                        Read Article →
                                    </a>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}


            {/* Bail Assessment (conditional) */}
            {response.bail_assessment && (
                <div className="bail-assessment-card glass-card">
                    <h3>⚖️ Bail Assessment</h3>
                    <div className="bail-summary">
                        <div className={`likelihood-badge ${response.bail_assessment.bail_likelihood?.toLowerCase()}`}>
                            {response.bail_assessment.bail_likelihood} Likelihood
                        </div>
                        {response.bail_assessment.legal_reasoning && (
                            <div className="legal-reasoning">
                                <div className="reasoning-item">
                                    <strong>Status:</strong> {response.bail_assessment.legal_reasoning.bailable_status}
                                </div>
                                <div className="reasoning-item">
                                    <strong>Max Punishment:</strong> {response.bail_assessment.legal_reasoning.max_punishment}
                                </div>
                                <div className="reasoning-item">
                                    <strong>Severity:</strong> {response.bail_assessment.legal_reasoning.severity_score}/10
                                </div>
                                {response.bail_assessment.legal_reasoning.applicable_crpc && (
                                    <div className="reasoning-item">
                                        <strong>Provisions:</strong> {response.bail_assessment.legal_reasoning.applicable_crpc.join(', ')}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Citations */}
            {response.citations && response.citations.length > 0 && (
                <div className="citations-card glass-card">
                    <h3>{response.is_abstention ? '📂 Available Material' : '📖 Legal Evidence & Citations'}</h3>
                    <div className="citations-list">
                        {response.citations.map((citation, index) => (
                            <div key={index} className="citation-item">
                                <div className="citation-header">
                                    <span className="citation-section">{citation.section}</span>
                                    <span className={`citation-type ${isStatutory(citation.law_type) ? 'statutory' : isUploaded(citation.law_type) ? 'uploaded' : 'external'}`}>
                                        {isStatutory(citation.law_type) ? '📜 Statutory' : 
                                         isUploaded(citation.law_type) ? '📁 Document' : 
                                         citation.law_type}
                                    </span>
                                    <span className="citation-score">
                                        {(citation.relevance_score * 100).toFixed(0)}% match
                                    </span>
                                </div>
                                <p className="citation-text">{citation.text_preview}</p>
                                <span className="citation-source">Source: {citation.source}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Processing Details */}
            {response.processing_info && (
                <details className="processing-details">
                    <summary>🔍 Processing Details</summary>
                    <div className="processing-content">
                        {response.fetch_times_ms && (
                            <div className="fetch-times">
                                <strong>Fetch Times:</strong>
                                {Object.entries(response.fetch_times_ms).map(([source, time]) => (
                                    <span key={source} className="fetch-time-item">
                                        {source}: {time}ms
                                    </span>
                                ))}
                            </div>
                        )}
                        <ul>
                            {response.processing_info.steps?.map((step, index) => (
                                <li key={index}>{step}</li>
                            ))}
                        </ul>
                    </div>
                </details>
            )}
        </div>
    )
}

export default ResponseCard
