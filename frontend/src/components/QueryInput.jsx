import { useState, useRef } from 'react'
import './QueryInput.css'
import MotionToggle from './MotionToggle'

function QueryInput({ query, setQuery, mode, setMode, onSubmit, isLoading, activeStage }) {
    const [custodyDays, setCustodyDays] = useState('')
    const [offenseSections, setOffenseSections] = useState('')
    const [uploadedFile, setUploadedFile] = useState(null)
    const [isUploading, setIsUploading] = useState(false)
    const [sessionId, setSessionId] = useState(null)
    const [uploadStatus, setUploadStatus] = useState(null)
    const [showAdvanced, setShowAdvanced] = useState(false)
    const fileInputRef = useRef(null)

    const modes = [
        { id: 'auto', label: 'Auto Detect', icon: '🔄' },
        { id: 'legal', label: 'Legal Info', icon: '📚' },
        { id: 'bail', label: 'Bail Query', icon: '🔓' },
    ]

    const handleFileSelect = async (e) => {
        const file = e.target.files[0]
        if (!file) return

        const allowedTypes = ['application/pdf', 'text/plain',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document']

        if (!allowedTypes.includes(file.type) && !file.name.match(/\.(pdf|txt|doc|docx)$/i)) {
            setUploadStatus({ type: 'error', message: 'Please upload PDF, TXT, DOC, or DOCX files' })
            return
        }

        if (file.size > 5 * 1024 * 1024) {
            setUploadStatus({ type: 'error', message: 'File size must be under 5MB' })
            return
        }

        setUploadedFile(file)
        setIsUploading(true)
        setUploadStatus({ type: 'info', message: 'Uploading document...' })

        try {
            const formData = new FormData()
            formData.append('file', file)
            formData.append('query', query || 'Analyze this document for bail eligibility')
            formData.append('mode', 'bail')
            if (sessionId) formData.append('session_id', sessionId)
            formData.append('document_type', detectDocType(file.name))

            const response = await fetch('/upload-document', {
                method: 'POST',
                body: formData,
            })

            if (!response.ok) {
                const error = await response.json()
                throw new Error(error.detail || 'Upload failed')
            }

            const result = await response.json()
            setSessionId(result.session_id)
            setUploadStatus({
                type: 'success',
                message: `✓ ${file.name} uploaded (${result.document_chunks} chunks)`
            })
        } catch (err) {
            setUploadStatus({ type: 'error', message: err.message })
            setUploadedFile(null)
        } finally {
            setIsUploading(false)
        }
    }

    const detectDocType = (filename) => {
        const lower = filename.toLowerCase()
        if (lower.includes('fir')) return 'FIR'
        if (lower.includes('chargesheet')) return 'CHARGESHEET'
        return 'OTHER'
    }

    const removeFile = async () => {
        // Clear from backend if session exists
        if (sessionId) {
            try {
                await fetch(`/session/${sessionId}/documents`, {
                    method: 'DELETE',
                })
            } catch (err) {
                console.error('Failed to clear session documents:', err)
            }
        }

        // Clear local state
        setUploadedFile(null)
        setUploadStatus(null)
        setSessionId(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
    }

    const handleSubmit = (e) => {
        e.preventDefault()
        if (!query.trim()) return

        const queryData = {
            query: query.trim(),
            mode,
            session_id: sessionId,
        }

        if (mode === 'bail') {
            if (custodyDays) queryData.custody_days = parseInt(custodyDays)
            if (offenseSections) {
                queryData.offense_sections = offenseSections.split(',').map(s => s.trim()).filter(Boolean)
            }
        }

        onSubmit(queryData)
    }

    return (
        <section className="query-section glass-card">
            <h2>Ask Your Legal Question</h2>

            {/* Mode Selector */}
            <div className="mode-selector">
                {modes.map((m) => (
                    <button
                        key={m.id}
                        className={`mode-btn ${mode === m.id ? 'active' : ''}`}
                        onClick={() => setMode(m.id)}
                        type="button"
                    >
                        <span className="mode-icon">{m.icon}</span>
                        {m.label}
                    </button>
                ))}
            </div>

            {/* Query Input */}
            <form onSubmit={handleSubmit}>
                <div className="query-input-container">
                    <textarea
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="E.g., What is the punishment for theft under IPC 379? OR Can I get bail for a murder charge after 90 days?"
                        rows={3}
                        disabled={isLoading}
                    />
                </div>

                {/* Bail Options */}
                {mode === 'bail' && (
                    <div className="bail-options animate-fade-in">
                        <div className="bail-toggle-row">
                            <MotionToggle
                                checked={showAdvanced}
                                onChange={setShowAdvanced}
                                label="Advanced Bail Options"
                                id="advancedBailToggle"
                            />
                        </div>

                        {showAdvanced && (
                            <>
                                <div className="document-upload-section">
                                    <label className="upload-label">
                                        📄 Upload FIR / Charge Sheet (optional)
                                    </label>
                                    <div className="upload-row">
                                        <input
                                            ref={fileInputRef}
                                            type="file"
                                            accept=".pdf,.txt,.doc,.docx"
                                            onChange={handleFileSelect}
                                            className="file-input-hidden"
                                            id="docUpload"
                                            disabled={isUploading}
                                        />
                                        <label htmlFor="docUpload" className={`upload-btn-inline ${isUploading ? 'uploading' : ''}`}>
                                            {isUploading ? '⏳ Uploading...' : '📎 Choose File'}
                                        </label>
                                        {uploadedFile && (
                                            <div className="uploaded-file-badge">
                                                <span className="file-name">{uploadedFile.name}</span>
                                                <button type="button" className="remove-file-btn" onClick={removeFile}>✕</button>
                                            </div>
                                        )}
                                    </div>
                                    {uploadStatus && (
                                        <div className={`upload-status ${uploadStatus.type}`}>
                                            {uploadStatus.message}
                                        </div>
                                    )}
                                </div>

                                <div className="bail-fields-row">
                                    <div className="option-group">
                                        <label htmlFor="custodyDays">Days in Custody</label>
                                        <input
                                            type="number"
                                            id="custodyDays"
                                            min="0"
                                            placeholder="e.g., 45"
                                            value={custodyDays}
                                            onChange={(e) => setCustodyDays(e.target.value)}
                                        />
                                    </div>
                                    <div className="option-group">
                                        <label htmlFor="offenseSections">Charged Sections</label>
                                        <input
                                            type="text"
                                            id="offenseSections"
                                            placeholder="e.g., IPC 302, IPC 307"
                                            value={offenseSections}
                                            onChange={(e) => setOffenseSections(e.target.value)}
                                        />
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                )}

                {/* Submit Button */}
                <button
                    type="submit"
                    className={`submit-btn ${isLoading ? 'loading' : ''}`}
                    disabled={isLoading || !query.trim()}
                >
                    {isLoading ? (
                        <>
                            <span className="spinner"></span>
                            {activeStage ? `${activeStage}...` : 'Processing...'}
                        </>
                    ) : (
                        <>
                            <span className="btn-icon">✨</span>
                            Get Legal Insights
                        </>
                    )}
                </button>
            </form>
        </section>
    )
}

export default QueryInput
