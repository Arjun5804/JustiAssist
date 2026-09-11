import { useState, useCallback } from 'react'
import { connectSSE } from '../api'
import PipelineVisualizer from './PipelineVisualizer'
import ResponseCard from './ResponseCard'
import Loader from './Loader'
import './DocumentUpload.css'

function DocumentUpload({ sessionId, setSessionId }) {
    const [files, setFiles] = useState([])
    const [uploadedDocs, setUploadedDocs] = useState([])
    const [isUploading, setIsUploading] = useState(false)
    const [query, setQuery] = useState('')
    const [response, setResponse] = useState(null)
    const [error, setError] = useState(null)
    const [isQuerying, setIsQuerying] = useState(false)
    const [pipelineStages, setPipelineStages] = useState([])

    const INITIAL_STAGES = [
        { id: 'classify', name: 'Classifying', icon: '🔍', status: 'pending' },
        { id: 'reformulate', name: 'Reformulating', icon: '📝', status: 'pending' },
        { id: 'retrieve', name: 'Retrieving', icon: '📚', status: 'pending' },
        { id: 'rerank', name: 'Reranking', icon: '⚖️', status: 'pending' },
        { id: 'score', name: 'Scoring', icon: '📊', status: 'pending' },
        { id: 'generate', name: 'Generating', icon: '✨', status: 'pending' },
    ]

    const handleFileSelect = (e) => {
        const selectedFiles = Array.from(e.target.files)
        setFiles(prev => [...prev, ...selectedFiles])
    }

    const handleDrop = useCallback((e) => {
        e.preventDefault()
        const droppedFiles = Array.from(e.dataTransfer.files)
        setFiles(prev => [...prev, ...droppedFiles])
    }, [])

    const handleDragOver = (e) => {
        e.preventDefault()
    }

    const removeFile = (index) => {
        setFiles(prev => prev.filter((_, i) => i !== index))
    }

    const uploadDocuments = async () => {
        if (files.length === 0) return

        setIsUploading(true)
        setError(null)

        try {
            for (const file of files) {
                const formData = new FormData()
                formData.append('file', file)
                formData.append('query', query || 'Document analysis')
                formData.append('mode', 'auto')
                if (sessionId) {
                    formData.append('session_id', sessionId)
                }
                formData.append('document_type', detectDocumentType(file.name))

                const response = await fetch('/upload-document', {
                    method: 'POST',
                    body: formData,
                })

                if (!response.ok) {
                    const error = await response.json()
                    throw new Error(error.detail || 'Upload failed')
                }

                const result = await response.json()

                // Save session ID for subsequent uploads
                if (!sessionId && result.session_id) {
                    setSessionId(result.session_id)
                }

                setUploadedDocs(prev => [...prev, {
                    name: file.name,
                    type: result.document_type,
                    chunks: result.document_chunks,
                    preview: result.document_preview,
                }])
            }

            setFiles([])
        } catch (err) {
            setError(err.message)
        } finally {
            setIsUploading(false)
        }
    }

    const detectDocumentType = (filename) => {
        const lower = filename.toLowerCase()
        if (lower.includes('fir')) return 'FIR'
        if (lower.includes('chargesheet') || lower.includes('charge_sheet')) return 'CHARGESHEET'
        if (lower.includes('order') || lower.includes('judgment')) return 'COURT_ORDER'
        if (lower.includes('bail')) return 'BAIL_APPLICATION'
        return 'OTHER'
    }

    const queryWithDocuments = () => {
        if (!query.trim() || !sessionId) return

        setIsQuerying(true)
        setError(null)
        setResponse(null)
        setPipelineStages(INITIAL_STAGES)

        const options = {
            mode: 'auto',
            sessionId: sessionId
        }

        const callbacks = {
            onStage: (stageId, status, data) => {
                setPipelineStages(prev => prev.map(s =>
                    s.id === stageId ? { ...s, status, ...(data || {}) } : s
                ))
            },
            onComplete: (resp) => {
                setResponse(resp)
                setIsQuerying(false)
            },
            onError: (msg) => {
                setError(msg)
                setIsQuerying(false)
            }
        }

        connectSSE(query.trim(), options, callbacks)
    }

    const clearSession = async () => {
        if (!sessionId) return

        try {
            await fetch(`/session/${sessionId}/documents`, {
                method: 'DELETE',
            })
            setUploadedDocs([])
            setSessionId(null)
            setResponse(null)
            setError(null)
        } catch (err) {
            console.error('Failed to clear session:', err)
        }
    }

    return (
        <div className="document-upload animate-fade-in">
            <div className="upload-header glass-card">
                <div className="header-glow"></div>
                <h2>
                    <span className="header-icon">📁</span>
                    Document Analysis
                </h2>
                <p className="subtitle">
                    Upload case files and chat with them using legal AI
                </p>
            </div>

            {/* Session Info */}
            {sessionId && (
                <div className="session-info glass-card">
                    <span className="session-badge">
                        <span className="pulse-dot"></span>
                        Active Session: {sessionId.slice(0, 8)}
                    </span>
                    <button className="clear-btn" onClick={clearSession}>
                        Clear All
                    </button>
                </div>
            )}

            {/* Layout Grid */}
            <div className="upload-layout">
                <div className="upload-left">
                    {/* Upload Zone */}
                    <div
                        className={`upload-zone glass-card ${files.length > 0 ? 'has-files' : ''}`}
                        onDrop={handleDrop}
                        onDragOver={handleDragOver}
                    >
                        <div className="upload-icon-wrapper">
                            <span className="upload-icon">📄</span>
                        </div>
                        <h3>Upload Documents</h3>
                        <p>Drag & drop documents here</p>
                        <span className="divider">or</span>
                        <label className="file-input-label">
                            Browse Files
                            <input
                                type="file"
                                multiple
                                accept=".pdf,.txt,.doc,.docx"
                                onChange={handleFileSelect}
                                className="file-input"
                            />
                        </label>
                        <p className="file-types">Supported: PDF, TXT, DOC, DOCX</p>
                    </div>

                    {/* Selected Files */}
                    {files.length > 0 && (
                        <div className="selected-files glass-card animate-slide-up">
                            <h3>Selected Files</h3>
                            <ul className="file-list">
                                {files.map((file, index) => (
                                    <li key={index} className="file-item">
                                        <span className="file-type-icon">📎</span>
                                        <div className="file-info">
                                            <span className="file-name">{file.name}</span>
                                            <span className="file-size">{(file.size / 1024).toFixed(1)} KB</span>
                                        </div>
                                        <button
                                            className="remove-btn"
                                            onClick={() => removeFile(index)}
                                            title="Remove"
                                        >
                                            ✕
                                        </button>
                                    </li>
                                ))}
                            </ul>
                            <button
                                className="upload-btn primary-gradient"
                                onClick={uploadDocuments}
                                disabled={isUploading}
                            >
                                {isUploading ? (
                                    <><span className="spinner"></span> Uploading...</>
                                ) : (
                                    <><span>⬆️</span> Upload to AI Engine</>
                                )}
                            </button>
                        </div>
                    )}
                </div>

                <div className="upload-right">
                    {/* Uploaded Documents List */}
                    {uploadedDocs.length > 0 ? (
                        <div className="uploaded-docs glass-card animate-fade-in">
                            <h3>📚 Loaded in Intelligence</h3>
                            <div className="docs-grid">
                                {uploadedDocs.map((doc, index) => (
                                    <div key={index} className="mini-doc-card">
                                        <div className="doc-type-indicator" data-type={doc.type}></div>
                                        <span className="mini-doc-name">{doc.name}</span>
                                        <span className={`doc-tag tag-${doc.type.toLowerCase()}`}>{doc.type}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div className="empty-docs glass-card">
                            <div className="empty-icon">📂</div>
                            <p>No documents uploaded yet to this session.</p>
                        </div>
                    )}

                    {/* Query Input Section */}
                    {sessionId && (
                        <div className="query-section glass-card animate-fade-in">
                            <h3>🔍 Ask About Documents</h3>
                            <div className="query-input-box">
                                <textarea
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    placeholder="E.g., What are the main allegations? List all sections mentioned in the FIR."
                                    rows={3}
                                    disabled={isQuerying}
                                />
                                <button
                                    className="query-btn secondary-gradient"
                                    onClick={queryWithDocuments}
                                    disabled={isQuerying || !query.trim()}
                                >
                                    {isQuerying ? (
                                        <><span className="spinner"></span> Analyzing...</>
                                    ) : (
                                        <><span>✨</span> Analyze</>
                                    )}
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Error Message */}
            {error && (
                <div className="error-card glass-card animate-shake">
                    <span className="error-icon">⚠️</span>
                    <p>{error}</p>
                    <button onClick={() => setError(null)} className="dismiss-btn">✕</button>
                </div>
            )}

            {/* Visualizer and Results */}
            <div className="results-container">
                {isQuerying && (
                    <div className="query-loading-state">
                        <Loader text="Analyzing Documents..." hint="Cross-referencing legal provisions" />
                        <PipelineVisualizer stages={pipelineStages} />
                    </div>
                )}

                {response && !isQuerying && (
                    <div className="uploaded-response-wrapper animate-fade-in">
                        <div className="result-header">
                            <span className="result-icon">📋</span>
                            <h3>Legal Analysis Results</h3>
                        </div>
                        <ResponseCard response={response} />
                    </div>
                )}
            </div>
        </div>
    )
}

export default DocumentUpload
