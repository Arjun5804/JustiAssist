import { useState } from 'react'
import './CounterArgument.css'
import Loader from './Loader'

const CASE_TYPES = [
    { id: 'criminal', label: 'Criminal', icon: '⚖️' },
    { id: 'civil', label: 'Civil', icon: '📋' },
    { id: 'constitutional', label: 'Constitutional', icon: '🏛️' },
    { id: 'family', label: 'Family', icon: '👨‍👩‍👧' },
    { id: 'property', label: 'Property', icon: '🏠' },
]

const FOCUS_AREAS = [
    { id: 'procedural', label: 'Procedural', icon: '📜' },
    { id: 'substantive', label: 'Substantive', icon: '⚖️' },
    { id: 'evidentiary', label: 'Evidentiary', icon: '🔍' },
    { id: 'constitutional', label: 'Constitutional', icon: '🏛️' },
]

const STRENGTH_COLORS = {
    strong: { color: '#38ef7d', bg: 'rgba(56,239,125,0.1)', border: 'rgba(56,239,125,0.3)' },
    moderate: { color: '#f2c94c', bg: 'rgba(242,201,76,0.1)', border: 'rgba(242,201,76,0.3)' },
    speculative: { color: '#8fa4f0', bg: 'rgba(143,164,240,0.1)', border: 'rgba(143,164,240,0.3)' },
    high: { color: '#38ef7d', bg: 'rgba(56,239,125,0.1)', border: 'rgba(56,239,125,0.3)' },
    medium: { color: '#f2c94c', bg: 'rgba(242,201,76,0.1)', border: 'rgba(242,201,76,0.3)' },
    low: { color: '#8fa4f0', bg: 'rgba(143,164,240,0.1)', border: 'rgba(143,164,240,0.3)' },
}

function CounterArgument() {
    const [step, setStep] = useState('input')
    const [isLoading, setIsLoading] = useState(false)
    const [result, setResult] = useState(null)
    const [error, setError] = useState(null)

    const [form, setForm] = useState({
        legal_argument: '',
        case_type: 'criminal',
        sections_involved: '',
        client_role: 'respondent',
        jurisdiction: 'Delhi',
        focus_areas: [],
    })

    const updateForm = (field, value) => setForm(prev => ({ ...prev, [field]: value }))
    const toggleFocus = (id) => setForm(prev => ({
        ...prev,
        focus_areas: prev.focus_areas.includes(id)
            ? prev.focus_areas.filter(f => f !== id)
            : [...prev.focus_areas, id]
    }))

    const canSubmit = form.legal_argument.length >= 20

    const handleGenerate = async () => {
        if (!canSubmit) return
        setIsLoading(true)
        setError(null)

        const payload = {
            ...form,
            sections_involved: form.sections_involved
                ? form.sections_involved.split(',').map(s => s.trim()).filter(Boolean)
                : [],
        }

        try {
            const res = await fetch('/api/counter-arguments', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            if (!res.ok) throw new Error((await res.json()).detail || 'Generation failed')
            const data = await res.json()
            setResult(data)
            setStep('results')
        } catch (err) {
            setError(err.message)
            setResult({
                status: 'demo',
                result: getLocalDemo(payload),
                grounded: false,
                note: 'Demo — server unavailable',
            })
            setStep('results')
        } finally {
            setIsLoading(false)
        }
    }

    const getLocalDemo = (p) => ({
        argument_analysis: {
            summary: `The argument raises points in a ${p.case_type} matter regarding ${p.sections_involved?.join(', ') || 'general provisions'}.`,
            strengths: ['Relies on established statutory framework', 'Follows conventional reasoning'],
            weaknesses: ['Provision interpretation contestable', 'Procedural issues not addressed', 'Ignores recent judicial trends'],
        },
        opposing_viewpoints: [
            { title: 'Alternative Statutory Interpretation', argument: 'Provisions must be read harmoniously. Purposive interpretation yields a different conclusion supporting the respondent.', legal_basis: 'General Clauses Act, 1897; Harmonious construction', strength: 'strong' },
            { title: 'Constitutional Challenge', argument: 'Application of cited provisions violates Articles 14, 19, and 21. Must pass reasonableness and proportionality tests.', legal_basis: 'Articles 14, 19, 21 — Constitution of India', strength: 'strong' },
            { title: 'Factual Dispute', argument: 'Factual foundation is contested. Material evidence suggests an alternative narrative undermining the core premise.', legal_basis: 'Sections 101-114, Indian Evidence Act', strength: 'moderate' },
        ],
        rebuttals: [
            { original_point: 'Primary statutory interpretation', counter: 'Provision must be read in entirety including provisos. Selective reading distorts intent. Supreme Court mandates holistic reading.', supporting_law: 'CIT v. Hindustan Bulk Carriers (2003) 3 SCC 57' },
            { original_point: 'Reliance on factual assertions', counter: 'Burden of proof lies with the proponent under Section 101. Documentary evidence doesn\'t conclusively establish claimed facts.', supporting_law: 'Section 101-103, Indian Evidence Act' },
            { original_point: 'Cited precedent applicability', counter: 'Precedent is distinguishable on facts. Ratio pertains to a materially different matrix and cannot be mechanically applied.', supporting_law: 'Doctrine of precedent; per incuriam rule' },
        ],
        procedural_defenses: [
            { defense: 'Limitation / Delay', description: 'Challenge timeliness. Seek dismissal if beyond limitation period.', relevant_provision: 'Section 3, Limitation Act 1963', effectiveness: 'high' },
            { defense: 'Non-Joinder of Necessary Party', description: 'Essential parties not impleaded, rendering proceedings defective.', relevant_provision: 'Order 1 Rule 10, CPC', effectiveness: 'medium' },
            { defense: 'Lack of Jurisdiction', description: 'Court lacks territorial or pecuniary jurisdiction.', relevant_provision: 'Section 15-20 CPC; Section 177-184 CrPC', effectiveness: 'high' },
        ],
        precedents: [
            { case_name: 'Lalita Kumari v. Govt. of U.P.', citation: '(2014) 2 SCC 1', ratio: 'Mandatory FIR registration and preliminary inquiry scope', application: 'Procedural safeguards may not have been followed' },
            { case_name: 'K.S. Puttaswamy v. Union of India', citation: '(2017) 10 SCC 1', ratio: 'Right to privacy as fundamental right', application: 'Constitutional challenge to overreach' },
        ],
        recommended_strategy: 'Combine procedural challenges with substantive counter-arguments. Lead with strongest procedural defense for early dismissal while preparing substantive rebuttal for trial.',
        confidence_score: 0.72,
    })

    const resetForm = () => {
        setStep('input')
        setResult(null)
        setError(null)
    }

    const exportReport = () => {
        if (!result?.result) return
        const r = result.result

        const report = `COUNTER ARGUMENT GENERATOR — ANALYSIS REPORT
${'='.repeat(60)}
Date: ${new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'long', year: 'numeric' })}
Case Type: ${form.case_type.toUpperCase()} | Role: ${form.client_role}
Sections: ${form.sections_involved || 'General'}

${'='.repeat(60)}
ORIGINAL ARGUMENT ANALYSIS
${'='.repeat(60)}
${r.argument_analysis?.summary}

Strengths: ${r.argument_analysis?.strengths?.join('; ')}
Weaknesses: ${r.argument_analysis?.weaknesses?.join('; ')}

${'='.repeat(60)}
OPPOSING VIEWPOINTS
${'='.repeat(60)}
${r.opposing_viewpoints?.map((v, i) => `${i + 1}. ${v.title} [${v.strength}]\n   ${v.argument}\n   Legal Basis: ${v.legal_basis}`).join('\n\n')}

${'='.repeat(60)}
POINT-BY-POINT REBUTTALS
${'='.repeat(60)}
${r.rebuttals?.map((rb, i) => `${i + 1}. RE: "${rb.original_point}"\n   ${rb.counter}\n   Law: ${rb.supporting_law}`).join('\n\n')}

${'='.repeat(60)}
PROCEDURAL DEFENSES
${'='.repeat(60)}
${r.procedural_defenses?.map((d, i) => `${i + 1}. ${d.defense} [${d.effectiveness}]\n   ${d.description}\n   Provision: ${d.relevant_provision}`).join('\n\n')}

${'='.repeat(60)}
PRECEDENTS & AUTHORITIES
${'='.repeat(60)}
${r.precedents?.map(p => `${p.case_name} ${p.citation}\n  Ratio: ${p.ratio}\n  Application: ${p.application}`).join('\n\n')}

${'='.repeat(60)}
RECOMMENDED STRATEGY
${'='.repeat(60)}
${r.recommended_strategy}

Confidence: ${Math.round((r.confidence_score || 0.7) * 100)}%

DISCLAIMER: AI-generated analysis for reference only. Consult a qualified advocate.
`
        const blob = new Blob([report], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `CounterArgument_Report_${Date.now()}.txt`
        a.click()
        URL.revokeObjectURL(url)
    }

    // =================== RESULTS ===================
    if (step === 'results' && result?.result) {
        const r = result.result
        const analysis = r.argument_analysis

        return (
            <div className="counter-arg animate-fade-in">
                {/* Header */}
                <div className="ca-results-header">
                    <button className="back-btn" onClick={resetForm}>← New Analysis</button>
                    <div className="results-title-group">
                        <h2 className="results-title">⚔️ Counter Argument Analysis</h2>
                        <p className="results-subtitle">
                            {form.case_type.charAt(0).toUpperCase() + form.case_type.slice(1)} • {form.client_role}
                            {result.status === 'demo' && <span className="demo-badge">DEMO</span>}
                        </p>
                    </div>
                    <button className="export-btn" onClick={exportReport}>📥 Export</button>
                </div>

                {/* Argument Analysis */}
                {analysis && (
                    <div className="analysis-section glass-card">
                        <h3 className="section-title">🔎 Argument Analysis</h3>
                        <p className="analysis-summary">{analysis.summary}</p>
                        <div className="sw-grid">
                            <div className="sw-col">
                                <h4 className="sw-heading strengths-heading">✅ Strengths</h4>
                                <ul>{analysis.strengths?.map((s, i) => <li key={i}>{s}</li>)}</ul>
                            </div>
                            <div className="sw-col">
                                <h4 className="sw-heading weaknesses-heading">❌ Weaknesses</h4>
                                <ul>{analysis.weaknesses?.map((w, i) => <li key={i}>{w}</li>)}</ul>
                            </div>
                        </div>
                    </div>
                )}

                {/* Opposing Viewpoints */}
                {r.opposing_viewpoints && (
                    <div className="viewpoints-section">
                        <h3 className="section-title">🎯 Opposing Viewpoints</h3>
                        <div className="viewpoints-grid">
                            {r.opposing_viewpoints.map((vp, i) => {
                                const sc = STRENGTH_COLORS[vp.strength] || STRENGTH_COLORS.moderate
                                return (
                                    <div key={i} className="viewpoint-card glass-card">
                                        <div className="vp-header">
                                            <h4>{vp.title}</h4>
                                            <span className="strength-badge" style={{
                                                color: sc.color, background: sc.bg, borderColor: sc.border
                                            }}>{vp.strength?.toUpperCase()}</span>
                                        </div>
                                        <p className="vp-argument">{vp.argument}</p>
                                        <div className="vp-basis">
                                            <span className="basis-label">Legal Basis:</span> {vp.legal_basis}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                )}

                {/* Rebuttals */}
                {r.rebuttals && (
                    <div className="rebuttals-section glass-card">
                        <h3 className="section-title">💥 Point-by-Point Rebuttals</h3>
                        <div className="rebuttals-list">
                            {r.rebuttals.map((rb, i) => (
                                <div key={i} className="rebuttal-row">
                                    <div className="rebuttal-original">
                                        <span className="rebuttal-tag original-tag">THEIR POINT</span>
                                        <p>{rb.original_point}</p>
                                    </div>
                                    <div className="rebuttal-arrow">⟶</div>
                                    <div className="rebuttal-counter">
                                        <span className="rebuttal-tag counter-tag">YOUR COUNTER</span>
                                        <p>{rb.counter}</p>
                                        <span className="supporting-law">📜 {rb.supporting_law}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Procedural Defenses */}
                {r.procedural_defenses && (
                    <div className="defenses-section">
                        <h3 className="section-title">🛡️ Procedural Defenses</h3>
                        <div className="defenses-grid">
                            {r.procedural_defenses.map((d, i) => {
                                const ec = STRENGTH_COLORS[d.effectiveness] || STRENGTH_COLORS.medium
                                return (
                                    <div key={i} className="defense-card glass-card">
                                        <div className="defense-header">
                                            <h4>{d.defense}</h4>
                                            <span className="effectiveness-badge" style={{
                                                color: ec.color, background: ec.bg, borderColor: ec.border
                                            }}>{d.effectiveness?.toUpperCase()}</span>
                                        </div>
                                        <p className="defense-desc">{d.description}</p>
                                        <div className="defense-provision">📜 {d.relevant_provision}</div>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                )}

                {/* Precedents */}
                {r.precedents && (
                    <div className="precedents-section glass-card">
                        <h3 className="section-title">📚 Precedents & Authorities</h3>
                        <div className="precedents-list">
                            {r.precedents.map((p, i) => (
                                <div key={i} className="precedent-row">
                                    <div className="precedent-name">
                                        <strong>{p.case_name}</strong>
                                        {p.citation && <span className="precedent-citation">{p.citation}</span>}
                                    </div>
                                    <p className="precedent-ratio"><em>Ratio:</em> {p.ratio}</p>
                                    <p className="precedent-application"><em>Application:</em> {p.application}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Strategy + Footer */}
                <div className="ca-footer glass-card">
                    {r.recommended_strategy && (
                        <div className="strategy-block">
                            <h4>🎯 Recommended Strategy</h4>
                            <p>{r.recommended_strategy}</p>
                        </div>
                    )}
                    <div className="ca-footer-meta">
                        <span>Confidence: <strong>{Math.round((r.confidence_score || 0.7) * 100)}%</strong></span>
                        {result.grounded && <span className="grounded-tag">✓ Grounded in statutory provisions</span>}
                    </div>
                    <p className="disclaimer">⚠️ AI-generated analysis for reference only. Not a substitute for professional legal advice.</p>
                </div>
            </div>
        )
    }

    // =================== INPUT FORM ===================
    return (
        <div className="counter-arg animate-fade-in">
            {/* Hero */}
            <div className="ca-hero">
                <div className="hero-glow"></div>
                <h1 className="ca-hero-title">
                    <span className="hero-icon">⚔️</span>
                    Counter Argument<span className="accent-text"> Generator</span>
                </h1>
                <p className="ca-hero-subtitle">
                    Develop opposing viewpoints, rebuttals, and procedural defenses with AI-powered legal analysis
                </p>
            </div>

            {/* Main Form */}
            <div className="ca-form glass-card">
                <h3 className="form-card-title">📝 Enter the Legal Argument to Counter</h3>

                <div className="form-group full-width">
                    <label>Legal Argument / Opposing Claim <span className="required">*</span></label>
                    <textarea
                        rows={7}
                        placeholder="Paste or type the legal argument, claim, or contention that you need to counter. Include specific sections cited, factual assertions made, and conclusions drawn..."
                        value={form.legal_argument}
                        onChange={e => updateForm('legal_argument', e.target.value)}
                    />
                    <span className="form-hint">{form.legal_argument.length}/20 minimum characters</span>
                </div>

                <div className="form-row">
                    <div className="form-group">
                        <label>Case Type</label>
                        <div className="select-pills">
                            {CASE_TYPES.map(ct => (
                                <button
                                    key={ct.id}
                                    className={`pill ${form.case_type === ct.id ? 'active' : ''}`}
                                    onClick={() => updateForm('case_type', ct.id)}
                                >
                                    {ct.icon} {ct.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="form-group">
                        <label>Your Role</label>
                        <div className="select-pills">
                            {['petitioner', 'respondent', 'accused', 'complainant'].map(r => (
                                <button
                                    key={r}
                                    className={`pill ${form.client_role === r ? 'active' : ''}`}
                                    onClick={() => updateForm('client_role', r)}
                                >
                                    {r.charAt(0).toUpperCase() + r.slice(1)}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="form-row">
                    <div className="form-group">
                        <label>Sections Involved</label>
                        <input
                            type="text"
                            placeholder="e.g. IPC 302, CrPC 161, Evidence Act 45"
                            value={form.sections_involved}
                            onChange={e => updateForm('sections_involved', e.target.value)}
                        />
                        <span className="form-hint">Comma-separated</span>
                    </div>
                    <div className="form-group">
                        <label>Jurisdiction</label>
                        <input
                            type="text"
                            placeholder="e.g. Delhi, Maharashtra"
                            value={form.jurisdiction}
                            onChange={e => updateForm('jurisdiction', e.target.value)}
                        />
                    </div>
                </div>

                <div className="form-group full-width">
                    <label>Focus Areas <span className="optional">(optional — select one or more)</span></label>
                    <div className="select-pills">
                        {FOCUS_AREAS.map(fa => (
                            <button
                                key={fa.id}
                                className={`pill ${form.focus_areas.includes(fa.id) ? 'active' : ''}`}
                                onClick={() => toggleFocus(fa.id)}
                            >
                                {fa.icon} {fa.label}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="ca-error glass-card">
                    <span>⚠️</span> {error}
                    <button onClick={() => setError(null)}>✕</button>
                </div>
            )}

            {/* Loading */}
            {isLoading && (
                <Loader text="Generating counter arguments..." hint="Analyzing legal provisions and precedents" />
            )}

            {/* Submit */}
            <button
                className="ca-submit-btn"
                onClick={handleGenerate}
                disabled={!canSubmit || isLoading}
            >
                {isLoading ? (
                    <><span className="spinner"></span> Generating Counter Arguments...</>
                ) : (
                    <><span>⚔️</span> Generate Counter Arguments</>
                )}
            </button>
        </div>
    )
}

export default CounterArgument
