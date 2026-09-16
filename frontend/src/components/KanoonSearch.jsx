import { useState } from 'react'
import './KanoonSearch.css'
import MotionToggle from './MotionToggle'

function KanoonSearch() {
    const [query, setQuery] = useState('')
    const [results, setResults] = useState(null)
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState(null)
    const [docType, setDocType] = useState('all')
    const [showFilters, setShowFilters] = useState(false)

    const docTypes = [
        { value: 'all', label: 'All Documents' },
        { value: 'judgments', label: 'Judgments' },
        { value: 'acts', label: 'Acts & Laws' },
        { value: 'sc', label: 'Supreme Court' },
        { value: 'hc', label: 'High Courts' },
    ]

    const handleSearch = async (e) => {
        e.preventDefault()
        if (!query.trim()) return

        setIsLoading(true)
        setError(null)

        try {
            const params = new URLSearchParams({
                query: query.trim(),
                doc_type: docType,
            })

            const response = await fetch(`/api/kanoon/search?${params}`)
            const data = await response.json()

            if (data.error) {
                setError(data.error)
                setResults(null)
            } else {
                setResults(data)
            }
        } catch {
            setError('Failed to search Indian Kanoon')
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <div className="kanoon-search">
            <div className="kanoon-header">
                <h2>
                    <span className="kanoon-icon">📚</span>
                    Indian Kanoon Search
                </h2>
                <p className="kanoon-subtitle">
                    Search millions of legal documents, judgments, and acts
                </p>
            </div>

            <form onSubmit={handleSearch} className="search-form glass-card">
                <div className="search-row">
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search case laws, sections, acts... (e.g., 'IPC 302 murder bail')"
                        className="search-input"
                    />
                    <button type="submit" className="search-btn" disabled={isLoading}>
                        {isLoading ? '🔄' : '🔍'}
                    </button>
                </div>

                <div className="filter-toggle-row">
                    <MotionToggle
                        checked={showFilters}
                        onChange={setShowFilters}
                        label="Filter by Type"
                        id="kanoonFilterToggle"
                    />
                </div>

                {showFilters && (
                    <div className="filter-row">
                        {docTypes.map((dt) => (
                            <label key={dt.value} className={`filter-chip ${docType === dt.value ? 'active' : ''}`}>
                                <input
                                    type="radio"
                                    name="docType"
                                    value={dt.value}
                                    checked={docType === dt.value}
                                    onChange={(e) => setDocType(e.target.value)}
                                />
                                {dt.label}
                            </label>
                        ))}
                    </div>
                )}
            </form>

            {error && (
                <div className="kanoon-error glass-card">
                    <span>⚠️</span> {error}
                    {error.includes('not configured') && (
                        <p className="hint">Add INDIAN_KANOON_API_KEY to .env file</p>
                    )}
                </div>
            )}

            {results && (
                <div className="kanoon-results">
                    <p className="results-count">
                        Found <strong>{results.total_results}</strong> results
                        <span className="search-time">({results.search_time_ms}ms)</span>
                    </p>

                    <div className="results-list">
                        {results.documents?.map((doc, index) => (
                            <article key={index} className="result-item glass-card">
                                <div className="result-header">
                                    <span className={`doc-type-badge ${doc.doc_type}`}>
                                        {doc.doc_type}
                                    </span>
                                    {doc.court && <span className="court-name">{doc.court}</span>}
                                    {doc.date && <span className="doc-date">{doc.date}</span>}
                                </div>

                                <h3 className="result-title">{doc.title}</h3>

                                {doc.headline && (
                                    <p className="result-headline"
                                        dangerouslySetInnerHTML={{ __html: doc.headline }}
                                    />
                                )}

                                {doc.citation && (
                                    <p className="result-citation">📎 {doc.citation}</p>
                                )}

                                <a
                                    href={doc.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="view-link"
                                >
                                    View on Indian Kanoon →
                                </a>
                            </article>
                        ))}
                    </div>

                    {results.documents?.length === 0 && (
                        <p className="no-results">No documents found for "{query}"</p>
                    )}
                </div>
            )}

            <p className="kanoon-attribution">
                Powered by <a href="https://indiankanoon.org" target="_blank" rel="noopener noreferrer">Indian Kanoon</a>
            </p>
        </div>
    )
}

export default KanoonSearch
