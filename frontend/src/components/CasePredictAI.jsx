import { useState } from 'react'
import './CasePredictAI.css'
import Loader from './Loader'
import MotionToggle from './MotionToggle'

const CASE_TYPES = [
    { id: 'criminal', label: 'Criminal', icon: '⚖️', desc: 'IPC/BNS offences, FIR matters' },
    { id: 'civil', label: 'Civil', icon: '📋', desc: 'Property, contract, tort disputes' },
    { id: 'constitutional', label: 'Constitutional', icon: '🏛️', desc: 'Fundamental rights, writ petitions' },
    { id: 'family', label: 'Family', icon: '👨‍👩‍👧', desc: 'Divorce, custody, maintenance' },
    { id: 'property', label: 'Property', icon: '🏠', desc: 'Land, title, partition disputes' },
]

const COURT_LEVELS = [
    { id: 'district', label: 'District Court' },
    { id: 'sessions', label: 'Sessions Court' },
    { id: 'high_court', label: 'High Court' },
    { id: 'supreme_court', label: 'Supreme Court' },
]

const CLIENT_ROLES = [
    { id: 'petitioner', label: 'Petitioner' },
    { id: 'respondent', label: 'Respondent' },
    { id: 'accused', label: 'Accused' },
    { id: 'complainant', label: 'Complainant' },
]

const STRATEGY_COLORS = {
    Aggressive: { accent: '#f45c43', gradient: 'linear-gradient(135deg, #f45c43, #eb3349)' },
    Balanced: { accent: '#667eea', gradient: 'linear-gradient(135deg, #667eea, #764ba2)' },
    Conservative: { accent: '#38ef7d', gradient: 'linear-gradient(135deg, #11998e, #38ef7d)' },
}

function CasePredictAI() {
    const [step, setStep] = useState('input')
    const [isLoading, setIsLoading] = useState(false)
    const [result, setResult] = useState(null)
    const [error, setError] = useState(null)
    const [expandedStrategy, setExpandedStrategy] = useState(null)
    const [showPrior, setShowPrior] = useState(false)

    const [form, setForm] = useState({
        case_type: '',
        sections_involved: '',
        case_facts: '',
        court_level: 'sessions',
        jurisdiction: 'Delhi',
        prior_proceedings: '',
        client_role: 'accused',
    })

    const updateForm = (field, value) => setForm(prev => ({ ...prev, [field]: value }))

    const canSubmit = form.case_type && form.case_facts.length >= 20

    const handlePredict = async () => {
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
            const res = await fetch('/api/predict/case', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })

            if (!res.ok) {
                const errData = await res.json()
                throw new Error(errData.detail || 'Prediction failed')
            }

            const data = await res.json()
            setResult(data)
            setStep('results')
        } catch (err) {
            setError(err.message)
            // Use local demo fallback
            setResult({
                status: 'demo',
                prediction: getLocalDemoPrediction(payload),
                grounded: false,
                note: 'Demo prediction — server unavailable',
            })
            setStep('results')
        } finally {
            setIsLoading(false)
        }
    }

    const getLocalDemoPrediction = (payload) => ({
        outcome_prediction: {
            favorable_percentage: 55,
            unfavorable_percentage: 30,
            settlement_percentage: 15,
            summary: `Based on the ${payload.case_type} case at ${payload.court_level} level, moderate prospects are indicated. Key evidence strength and applicable legal provisions will drive the outcome.`,
            key_factors: [
                'Strength of evidence presented',
                'Applicable statutory provisions',
                'Judicial precedents in similar cases',
                `Court trends in ${payload.jurisdiction}`,
            ],
        },
        strategies: [
            {
                name: 'Aggressive',
                approach: 'File preliminary objections, seek urgent hearing dates, and challenge opposing party head-on with constitutional arguments and progressive precedents.',
                pros: ['Early resolution possible', 'Demonstrates confidence'],
                cons: ['Higher costs', 'May antagonize bench'],
                success_rate: '45%',
                recommended_actions: ['File preliminary applications', 'Seek interim relief', 'Build case law compilation'],
            },
            {
                name: 'Balanced',
                approach: 'Combine strong legal arguments with mediation openness. Present case methodically while exploring settlement through court-annexed ADR.',
                pros: ['Maintains goodwill', 'Preserves all options'],
                cons: ['May take longer', 'Could seem indecisive'],
                success_rate: '60%',
                recommended_actions: ['File detailed written submissions', 'Offer mediation', 'Prepare expert witnesses'],
            },
            {
                name: 'Conservative',
                approach: 'Focus on settlement negotiations and alternative dispute resolution. Use litigation threat as leverage while keeping compromise doors open.',
                pros: ['Lowest risk', 'Faster resolution'],
                cons: ['May yield less', 'Could appear weak'],
                success_rate: '70%',
                recommended_actions: ['Initiate mediation', 'Draft settlement terms', 'Engage senior counsel'],
            },
        ],
        risk_factors: [
            { risk: 'Judicial delay', severity: 'medium', mitigation: 'Apply for expedited hearing' },
            { risk: 'Adverse provision interpretation', severity: 'high', mitigation: 'Prepare comprehensive legal brief' },
            { risk: 'Evidence challenges', severity: 'medium', mitigation: 'Secure documents and affidavits early' },
        ],
        relevant_provisions: [
            { section: 'Article 21', law: 'Constitution of India', relevance: 'Right to life and personal liberty' },
            { section: 'Section 482 CrPC', law: 'CrPC / BNSS', relevance: 'Inherent powers of High Court' },
        ],
        precedent_cases: [
            { case_name: 'Arnesh Kumar v. State of Bihar', citation: '(2014) 8 SCC 273', relevance: 'Arrest procedure guidelines' },
            { case_name: 'Satender Kumar Antil v. CBI', citation: '(2022) 10 SCC 51', relevance: 'Bail jurisprudence' },
        ],
        timeline_estimate: '6-18 months',
        confidence_score: 0.65,
    })

    const resetForm = () => {
        setStep('input')
        setResult(null)
        setError(null)
        setExpandedStrategy(null)
    }

    const exportReport = () => {
        if (!result?.prediction) return
        const p = result.prediction
        const op = p.outcome_prediction

        const report = `CASEPREDICT AI — CASE ANALYSIS REPORT
${'='.repeat(60)}
Date: ${new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'long', year: 'numeric' })}
Case Type: ${form.case_type.toUpperCase()}
Court: ${form.court_level} | Jurisdiction: ${form.jurisdiction}
Client Role: ${form.client_role}
Sections: ${form.sections_involved || 'General'}

${'='.repeat(60)}
OUTCOME PREDICTION
${'='.repeat(60)}
Favorable: ${op.favorable_percentage}%
Unfavorable: ${op.unfavorable_percentage}%
Settlement: ${op.settlement_percentage}%

${op.summary}

Key Factors:
${op.key_factors?.map((f, i) => `  ${i + 1}. ${f}`).join('\n')}

${'='.repeat(60)}
STRATEGIC APPROACHES
${'='.repeat(60)}
${p.strategies?.map(s => `
--- ${s.name.toUpperCase()} (Success Rate: ${s.success_rate}) ---
${s.approach}

Pros: ${s.pros?.join(', ')}
Cons: ${s.cons?.join(', ')}

Recommended Actions:
${s.recommended_actions?.map((a, i) => `  ${i + 1}. ${a}`).join('\n')}
`).join('\n')}

${'='.repeat(60)}
RISK FACTORS
${'='.repeat(60)}
${p.risk_factors?.map(r => `[${r.severity.toUpperCase()}] ${r.risk}\n  Mitigation: ${r.mitigation}`).join('\n\n')}

${'='.repeat(60)}
RELEVANT LEGAL PROVISIONS
${'='.repeat(60)}
${p.relevant_provisions?.map(prov => `${prov.section} (${prov.law}) — ${prov.relevance}`).join('\n')}

${'='.repeat(60)}
PRECEDENT CASES
${'='.repeat(60)}
${p.precedent_cases?.map(c => `${c.case_name} ${c.citation}\n  ${c.relevance}`).join('\n\n')}

Timeline Estimate: ${p.timeline_estimate}
AI Confidence: ${Math.round((p.confidence_score || 0.65) * 100)}%

${'='.repeat(60)}
DISCLAIMER: This is an AI-generated prediction for analytical purposes only.
Not a substitute for professional legal advice. Consult a qualified advocate.
`
        const blob = new Blob([report], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `CasePredictAI_Report_${Date.now()}.txt`
        a.click()
        URL.revokeObjectURL(url)
    }

    const getSeverityColor = (severity) => {
        switch (severity) {
            case 'high': return '#f45c43'
            case 'medium': return '#f2c94c'
            case 'low': return '#38ef7d'
            default: return '#8fa4f0'
        }
    }

    // =================== RENDER ===================

    if (step === 'results' && result?.prediction) {
        const pred = result.prediction
        const outcome = pred.outcome_prediction

        return (
            <div className="case-predict animate-fade-in">
                {/* Header */}
                <div className="predict-results-header">
                    <button className="back-btn" onClick={resetForm}>← New Prediction</button>
                    <div className="results-title-group">
                        <h2 className="results-title">🧠 CasePredictAI Results</h2>
                        <p className="results-subtitle">
                            {form.case_type.charAt(0).toUpperCase() + form.case_type.slice(1)} Case • {form.court_level.replace('_', ' ')} • {form.jurisdiction}
                            {result.status === 'demo' && <span className="demo-badge">DEMO</span>}
                        </p>
                    </div>
                    <div className="results-actions-top">
                        <button className="export-btn" onClick={exportReport}>📥 Export Report</button>
                    </div>
                </div>

                {/* Outcome Gauge */}
                <div className="outcome-section glass-card">
                    <h3 className="section-title">📊 Outcome Prediction</h3>
                    <div className="outcome-bars">
                        <div className="outcome-bar-row">
                            <span className="bar-label">Favorable</span>
                            <div className="bar-track">
                                <div className="bar-fill favorable" style={{ width: `${outcome.favorable_percentage}%` }}></div>
                            </div>
                            <span className="bar-value favorable-text">{outcome.favorable_percentage}%</span>
                        </div>
                        <div className="outcome-bar-row">
                            <span className="bar-label">Unfavorable</span>
                            <div className="bar-track">
                                <div className="bar-fill unfavorable" style={{ width: `${outcome.unfavorable_percentage}%` }}></div>
                            </div>
                            <span className="bar-value unfavorable-text">{outcome.unfavorable_percentage}%</span>
                        </div>
                        <div className="outcome-bar-row">
                            <span className="bar-label">Settlement</span>
                            <div className="bar-track">
                                <div className="bar-fill settlement" style={{ width: `${outcome.settlement_percentage}%` }}></div>
                            </div>
                            <span className="bar-value settlement-text">{outcome.settlement_percentage}%</span>
                        </div>
                    </div>
                    <p className="outcome-summary">{outcome.summary}</p>
                    {outcome.key_factors && (
                        <div className="key-factors">
                            <h4>Key Factors</h4>
                            <ul>
                                {outcome.key_factors.map((f, i) => <li key={i}>{f}</li>)}
                            </ul>
                        </div>
                    )}
                </div>

                {/* Strategies */}
                <div className="strategies-section">
                    <h3 className="section-title">🎯 Strategic Approaches</h3>
                    <div className="strategies-grid">
                        {pred.strategies?.map((strategy, i) => {
                            const colors = STRATEGY_COLORS[strategy.name] || STRATEGY_COLORS.Balanced
                            const isExpanded = expandedStrategy === i

                            return (
                                <div
                                    key={i}
                                    className={`strategy-card glass-card ${isExpanded ? 'expanded' : ''}`}
                                    onClick={() => setExpandedStrategy(isExpanded ? null : i)}
                                >
                                    <div className="strategy-header" style={{ borderLeftColor: colors.accent }}>
                                        <div className="strategy-name-row">
                                            <h4>{strategy.name}</h4>
                                            <span className="success-rate" style={{ color: colors.accent }}>{strategy.success_rate}</span>
                                        </div>
                                        <p className="strategy-approach">{strategy.approach}</p>
                                    </div>

                                    {isExpanded && (
                                        <div className="strategy-details animate-fade-in">
                                            <div className="pros-cons">
                                                <div className="pros">
                                                    <h5>✅ Pros</h5>
                                                    <ul>{strategy.pros?.map((p, j) => <li key={j}>{p}</li>)}</ul>
                                                </div>
                                                <div className="cons">
                                                    <h5>❌ Cons</h5>
                                                    <ul>{strategy.cons?.map((c, j) => <li key={j}>{c}</li>)}</ul>
                                                </div>
                                            </div>
                                            <div className="actions-list">
                                                <h5>📋 Recommended Actions</h5>
                                                <ol>
                                                    {strategy.recommended_actions?.map((a, j) => <li key={j}>{a}</li>)}
                                                </ol>
                                            </div>
                                        </div>
                                    )}

                                    <span className="expand-hint">{isExpanded ? 'Click to collapse' : 'Click for details'}</span>
                                </div>
                            )
                        })}
                    </div>
                </div>

                {/* Risk Factors */}
                {pred.risk_factors && (
                    <div className="risk-section glass-card">
                        <h3 className="section-title">⚠️ Risk Assessment</h3>
                        <div className="risk-list">
                            {pred.risk_factors.map((risk, i) => (
                                <div key={i} className="risk-row">
                                    <div className="risk-header-row">
                                        <span className="risk-severity-dot" style={{ background: getSeverityColor(risk.severity) }}></span>
                                        <span className="risk-text">{risk.risk}</span>
                                        <span className="risk-badge" style={{
                                            color: getSeverityColor(risk.severity),
                                            background: `${getSeverityColor(risk.severity)}15`,
                                            borderColor: `${getSeverityColor(risk.severity)}33`
                                        }}>{risk.severity?.toUpperCase()}</span>
                                    </div>
                                    <p className="risk-mitigation">💡 {risk.mitigation}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Legal Provisions + Precedents */}
                <div className="legal-refs-grid">
                    {pred.relevant_provisions && (
                        <div className="legal-card glass-card">
                            <h3 className="section-title">📜 Relevant Provisions</h3>
                            <ul className="provisions-list">
                                {pred.relevant_provisions.map((prov, i) => (
                                    <li key={i}>
                                        <strong>{prov.section}</strong> <span className="law-name">({prov.law})</span>
                                        <p>{prov.relevance}</p>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {pred.precedent_cases && (
                        <div className="legal-card glass-card">
                            <h3 className="section-title">📚 Precedent Cases</h3>
                            <ul className="precedents-list">
                                {pred.precedent_cases.map((c, i) => (
                                    <li key={i}>
                                        <strong>{c.case_name}</strong>
                                        {c.citation && <span className="case-citation">{c.citation}</span>}
                                        <p>{c.relevance}</p>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>

                {/* Footer Info */}
                <div className="predict-footer glass-card">
                    <div className="footer-stats">
                        <div className="footer-stat">
                            <span className="footer-stat-label">Timeline</span>
                            <span className="footer-stat-value">{pred.timeline_estimate || 'N/A'}</span>
                        </div>
                        <div className="footer-stat">
                            <span className="footer-stat-label">AI Confidence</span>
                            <span className="footer-stat-value">{Math.round((pred.confidence_score || 0.65) * 100)}%</span>
                        </div>
                        {result.grounded && (
                            <div className="footer-stat">
                                <span className="footer-stat-label">Grounded</span>
                                <span className="footer-stat-value grounded-yes">✓ {result.sections_retrieved} sections</span>
                            </div>
                        )}
                    </div>
                    <p className="disclaimer">⚠️ AI-generated prediction for analytical purposes only. Not a substitute for professional legal advice.</p>
                </div>
            </div>
        )
    }

    // =================== INPUT FORM ===================
    return (
        <div className="case-predict animate-fade-in">
            {/* Hero */}
            <div className="predict-hero">
                <div className="hero-glow"></div>
                <h1 className="predict-hero-title">
                    <span className="hero-icon">🧠</span>
                    CasePredict<span className="accent-text">AI</span>
                </h1>
                <p className="predict-hero-subtitle">
                    Advanced AI-powered case outcome prediction with multiple strategic approaches
                </p>
            </div>

            {/* Case Type Selection */}
            <div className="form-section">
                <label className="form-section-label">Select Case Type</label>
                <div className="case-type-grid">
                    {CASE_TYPES.map(ct => (
                        <button
                            key={ct.id}
                            className={`case-type-card glass-card ${form.case_type === ct.id ? 'selected' : ''}`}
                            onClick={() => updateForm('case_type', ct.id)}
                        >
                            <span className="ct-icon">{ct.icon}</span>
                            <span className="ct-label">{ct.label}</span>
                            <span className="ct-desc">{ct.desc}</span>
                        </button>
                    ))}
                </div>
            </div>

            {/* Case Details Form */}
            <div className="form-section glass-card form-card">
                <h3 className="form-card-title">📝 Case Details</h3>

                <div className="form-row">
                    <div className="form-group">
                        <label>Sections / Statutes Involved</label>
                        <input
                            type="text"
                            placeholder="e.g. IPC 302, IPC 120B, NDPS 21"
                            value={form.sections_involved}
                            onChange={e => updateForm('sections_involved', e.target.value)}
                        />
                        <span className="form-hint">Comma-separated section numbers</span>
                    </div>
                    <div className="form-group">
                        <label>Jurisdiction / State</label>
                        <input
                            type="text"
                            placeholder="e.g. Delhi, Maharashtra"
                            value={form.jurisdiction}
                            onChange={e => updateForm('jurisdiction', e.target.value)}
                        />
                    </div>
                </div>

                <div className="form-row">
                    <div className="form-group">
                        <label>Court Level</label>
                        <div className="select-pills">
                            {COURT_LEVELS.map(cl => (
                                <button
                                    key={cl.id}
                                    className={`pill ${form.court_level === cl.id ? 'active' : ''}`}
                                    onClick={() => updateForm('court_level', cl.id)}
                                >
                                    {cl.label}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="form-group">
                        <label>Client Role</label>
                        <div className="select-pills">
                            {CLIENT_ROLES.map(cr => (
                                <button
                                    key={cr.id}
                                    className={`pill ${form.client_role === cr.id ? 'active' : ''}`}
                                    onClick={() => updateForm('client_role', cr.id)}
                                >
                                    {cr.label}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="form-group full-width">
                    <label>Case Facts <span className="required">*</span></label>
                    <textarea
                        placeholder="Describe the case facts in detail — charges, circumstances, evidence available, parties involved, relevant dates..."
                        rows={6}
                        value={form.case_facts}
                        onChange={e => updateForm('case_facts', e.target.value)}
                    />
                    <span className="form-hint">{form.case_facts.length}/20 minimum characters</span>
                </div>

                <div className="form-group full-width">
                    <MotionToggle
                        checked={showPrior}
                        onChange={setShowPrior}
                        label="Prior Proceedings"
                        id="priorProceedingsToggle"
                    />
                    {showPrior && (
                        <textarea
                            placeholder="Any previous hearings, orders, appeals, or bail proceedings..."
                            rows={3}
                            value={form.prior_proceedings}
                            onChange={e => updateForm('prior_proceedings', e.target.value)}
                            style={{ marginTop: '0.75rem' }}
                        />
                    )}
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="predict-error glass-card">
                    <span>⚠️</span> {error}
                    <button onClick={() => setError(null)}>✕</button>
                </div>
            )}

            {/* Loading */}
            {isLoading && (
                <Loader text="Analyzing case..." hint="Evaluating outcomes, strategies, and risks" />
            )}

            {/* Submit */}
            <button
                className="predict-submit-btn"
                onClick={handlePredict}
                disabled={!canSubmit || isLoading}
            >
                {isLoading ? (
                    <><span className="spinner"></span> Analyzing Case...</>
                ) : (
                    <><span>🧠</span> Predict Case Outcome</>
                )}
            </button>
        </div>
    )
}

export default CasePredictAI
