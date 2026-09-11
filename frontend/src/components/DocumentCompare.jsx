import { useState, useCallback } from 'react'
import './DocumentCompare.css'

function DocumentCompare({ onBack }) {
    const [docA, setDocA] = useState(null)
    const [docB, setDocB] = useState(null)
    const [textA, setTextA] = useState('')
    const [textB, setTextB] = useState('')
    const [comparison, setComparison] = useState(null)
    const [isComparing, setIsComparing] = useState(false)
    const [dragTarget, setDragTarget] = useState(null)

    const readFileAsText = (file) => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = (e) => resolve(e.target.result)
            reader.onerror = reject
            reader.readAsText(file)
        })
    }

    const handleFileDrop = useCallback(async (e, side) => {
        e.preventDefault()
        setDragTarget(null)
        const file = e.dataTransfer.files[0]
        if (!file) return

        try {
            const text = await readFileAsText(file)
            if (side === 'A') {
                setDocA(file)
                setTextA(text)
            } else {
                setDocB(file)
                setTextB(text)
            }
        } catch {
            // If can't read as text, just store the file info
            if (side === 'A') {
                setDocA(file)
                setTextA(`[Binary file: ${file.name} — ${(file.size / 1024).toFixed(1)} KB]`)
            } else {
                setDocB(file)
                setTextB(`[Binary file: ${file.name} — ${(file.size / 1024).toFixed(1)} KB]`)
            }
        }
    }, [])

    const handleFileSelect = async (e, side) => {
        const file = e.target.files[0]
        if (!file) return

        try {
            const text = await readFileAsText(file)
            if (side === 'A') {
                setDocA(file)
                setTextA(text)
            } else {
                setDocB(file)
                setTextB(text)
            }
        } catch {
            if (side === 'A') {
                setDocA(file)
                setTextA(`[Binary file: ${file.name}]`)
            } else {
                setDocB(file)
                setTextB(`[Binary file: ${file.name}]`)
            }
        }
    }

    const compareDocuments = () => {
        if (!textA || !textB) return
        setIsComparing(true)

        // Simple line-by-line diff
        setTimeout(() => {
            const linesA = textA.split('\n')
            const linesB = textB.split('\n')
            const maxLines = Math.max(linesA.length, linesB.length)

            const diffLines = []
            let addedCount = 0
            let removedCount = 0
            let unchangedCount = 0

            for (let i = 0; i < maxLines; i++) {
                const lineA = i < linesA.length ? linesA[i] : undefined
                const lineB = i < linesB.length ? linesB[i] : undefined

                if (lineA === lineB) {
                    diffLines.push({ type: 'same', lineA, lineB, num: i + 1 })
                    unchangedCount++
                } else if (lineA === undefined) {
                    diffLines.push({ type: 'added', lineA: '', lineB, num: i + 1 })
                    addedCount++
                } else if (lineB === undefined) {
                    diffLines.push({ type: 'removed', lineA, lineB: '', num: i + 1 })
                    removedCount++
                } else {
                    diffLines.push({ type: 'changed', lineA, lineB, num: i + 1 })
                    addedCount++
                    removedCount++
                }
            }

            setComparison({
                diffLines,
                stats: {
                    totalLines: maxLines,
                    added: addedCount,
                    removed: removedCount,
                    unchanged: unchangedCount,
                    similarity: maxLines > 0 ? Math.round((unchangedCount / maxLines) * 100) : 0,
                },
            })
            setIsComparing(false)
        }, 500)
    }

    const exportReport = () => {
        if (!comparison) return

        const report = `DOCUMENT COMPARISON REPORT
${'='.repeat(60)}

Date: ${new Date().toLocaleDateString('en-IN')}

Document A: ${docA?.name || 'Unknown'}
Document B: ${docB?.name || 'Unknown'}

${'='.repeat(60)}
SUMMARY
${'='.repeat(60)}

Total Lines Compared: ${comparison.stats.totalLines}
Unchanged Lines: ${comparison.stats.unchanged}
Added Lines: ${comparison.stats.added}
Removed Lines: ${comparison.stats.removed}
Similarity: ${comparison.stats.similarity}%

${'='.repeat(60)}
DIFFERENCES
${'='.repeat(60)}

${comparison.diffLines
                .filter(d => d.type !== 'same')
                .map(d => {
                    if (d.type === 'added') return `+ Line ${d.num}: ${d.lineB}`
                    if (d.type === 'removed') return `- Line ${d.num}: ${d.lineA}`
                    return `~ Line ${d.num}:\n  A: ${d.lineA}\n  B: ${d.lineB}`
                })
                .join('\n\n')}

${'='.repeat(60)}
END OF REPORT
`
        const blob = new Blob([report], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `comparison_report_${Date.now()}.txt`
        a.click()
        URL.revokeObjectURL(url)
    }

    const resetCompare = () => {
        setDocA(null)
        setDocB(null)
        setTextA('')
        setTextB('')
        setComparison(null)
    }

    return (
        <div className="doc-compare animate-fade-in">
            <div className="doc-subview-header">
                <button className="back-btn" onClick={onBack}>← Back to Hub</button>
                <div className="subview-title-group">
                    <h2 className="subview-title">⚖️ Compare Documents</h2>
                    <p className="subview-subtitle">Upload two documents to compare side-by-side</p>
                </div>
            </div>

            {/* Upload Panels */}
            {!comparison && (
                <>
                    <div className="compare-upload-grid">
                        {/* Document A */}
                        <div
                            className={`compare-upload-panel glass-card ${dragTarget === 'A' ? 'dragging' : ''} ${docA ? 'has-file' : ''}`}
                            onDrop={(e) => handleFileDrop(e, 'A')}
                            onDragOver={(e) => { e.preventDefault(); setDragTarget('A') }}
                            onDragLeave={() => setDragTarget(null)}
                        >
                            <div className="panel-label">Document A</div>
                            {docA ? (
                                <div className="panel-file-info">
                                    <span className="panel-file-icon">📄</span>
                                    <div>
                                        <p className="panel-file-name">{docA.name}</p>
                                        <p className="panel-file-size">{(docA.size / 1024).toFixed(1)} KB • {textA.split('\n').length} lines</p>
                                    </div>
                                    <button className="panel-remove" onClick={() => { setDocA(null); setTextA('') }}>✕</button>
                                </div>
                            ) : (
                                <div className="panel-empty">
                                    <span className="panel-drop-icon">📁</span>
                                    <p>Drop file here</p>
                                    <label className="panel-browse-btn">
                                        Browse
                                        <input type="file" accept=".txt,.doc,.docx,.pdf" onChange={(e) => handleFileSelect(e, 'A')} className="hidden-input" />
                                    </label>
                                </div>
                            )}
                        </div>

                        {/* VS Badge */}
                        <div className="compare-vs-badge">VS</div>

                        {/* Document B */}
                        <div
                            className={`compare-upload-panel glass-card ${dragTarget === 'B' ? 'dragging' : ''} ${docB ? 'has-file' : ''}`}
                            onDrop={(e) => handleFileDrop(e, 'B')}
                            onDragOver={(e) => { e.preventDefault(); setDragTarget('B') }}
                            onDragLeave={() => setDragTarget(null)}
                        >
                            <div className="panel-label">Document B</div>
                            {docB ? (
                                <div className="panel-file-info">
                                    <span className="panel-file-icon">📄</span>
                                    <div>
                                        <p className="panel-file-name">{docB.name}</p>
                                        <p className="panel-file-size">{(docB.size / 1024).toFixed(1)} KB • {textB.split('\n').length} lines</p>
                                    </div>
                                    <button className="panel-remove" onClick={() => { setDocB(null); setTextB('') }}>✕</button>
                                </div>
                            ) : (
                                <div className="panel-empty">
                                    <span className="panel-drop-icon">📁</span>
                                    <p>Drop file here</p>
                                    <label className="panel-browse-btn">
                                        Browse
                                        <input type="file" accept=".txt,.doc,.docx,.pdf" onChange={(e) => handleFileSelect(e, 'B')} className="hidden-input" />
                                    </label>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Or paste text */}
                    <div className="compare-text-input glass-card">
                        <h4>Or paste document text directly:</h4>
                        <div className="text-input-grid">
                            <div className="text-input-group">
                                <label>Document A Text</label>
                                <textarea
                                    value={textA}
                                    onChange={(e) => { setTextA(e.target.value); if (!docA) setDocA({ name: 'Pasted Text A', size: e.target.value.length }) }}
                                    placeholder="Paste document A text here..."
                                    rows={6}
                                />
                            </div>
                            <div className="text-input-group">
                                <label>Document B Text</label>
                                <textarea
                                    value={textB}
                                    onChange={(e) => { setTextB(e.target.value); if (!docB) setDocB({ name: 'Pasted Text B', size: e.target.value.length }) }}
                                    placeholder="Paste document B text here..."
                                    rows={6}
                                />
                            </div>
                        </div>
                    </div>

                    {/* Compare Button */}
                    <button
                        className="compare-action-btn"
                        onClick={compareDocuments}
                        disabled={!textA || !textB || isComparing}
                    >
                        {isComparing ? (
                            <><span className="spinner"></span> Comparing...</>
                        ) : (
                            <><span>⚖️</span> Compare Documents</>
                        )}
                    </button>
                </>
            )}

            {/* Results */}
            {comparison && (
                <div className="compare-results">
                    {/* Stats Bar */}
                    <div className="compare-stats glass-card">
                        <div className="stats-header">
                            <h3>📊 Comparison Summary</h3>
                            <div className="stats-actions">
                                <button className="stats-btn" onClick={exportReport}>⬇️ Export Report</button>
                                <button className="stats-btn secondary" onClick={resetCompare}>🔄 New Comparison</button>
                            </div>
                        </div>
                        <div className="stats-grid">
                            <div className="stat-item">
                                <span className="stat-value">{comparison.stats.similarity}%</span>
                                <span className="stat-label">Similarity</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-value stat-unchanged">{comparison.stats.unchanged}</span>
                                <span className="stat-label">Unchanged</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-value stat-added">{comparison.stats.added}</span>
                                <span className="stat-label">Added</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-value stat-removed">{comparison.stats.removed}</span>
                                <span className="stat-label">Removed</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-value">{comparison.stats.totalLines}</span>
                                <span className="stat-label">Total Lines</span>
                            </div>
                        </div>

                        {/* Similarity Bar */}
                        <div className="similarity-bar-container">
                            <div className="similarity-bar">
                                <div
                                    className="similarity-fill"
                                    style={{ width: `${comparison.stats.similarity}%` }}
                                ></div>
                            </div>
                        </div>
                    </div>

                    {/* Side-by-Side Diff */}
                    <div className="compare-diff glass-card">
                        <div className="diff-header">
                            <span className="diff-label diff-label-a">📄 {docA?.name || 'Document A'}</span>
                            <span className="diff-label diff-label-b">📄 {docB?.name || 'Document B'}</span>
                        </div>
                        <div className="diff-content">
                            {comparison.diffLines.map((line, i) => (
                                <div key={i} className={`diff-row diff-${line.type}`}>
                                    <span className="diff-line-num">{line.num}</span>
                                    <div className="diff-cell diff-cell-a">
                                        {line.lineA !== undefined ? line.lineA || '\u00A0' : ''}
                                    </div>
                                    <div className="diff-cell diff-cell-b">
                                        {line.lineB !== undefined ? line.lineB || '\u00A0' : ''}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}

export default DocumentCompare
