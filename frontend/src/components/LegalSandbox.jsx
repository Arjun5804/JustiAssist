import { useState } from 'react'
import './LegalSandbox.css'
import Loader from './Loader'

const QUIZ_TOPICS = [
    { id: 'Constitutional Law', icon: '🏛️', label: 'Constitutional Law' },
    { id: 'IPC', icon: '⚖️', label: 'IPC / BNS' },
    { id: 'CrPC', icon: '📜', label: 'CrPC / BNSS' },
    { id: 'Evidence Act', icon: '🔍', label: 'Evidence Act / BSA' },
    { id: 'Contract Law', icon: '📋', label: 'Contract Law' },
    { id: 'Family Law', icon: '👨‍👩‍👧', label: 'Family Law' },
]

const EXAM_TYPES = ['CLAT', 'AILET', 'JUDICIARY', 'BAR']

function LegalSandbox() {
    const [mode, setMode] = useState(null) // null, 'quiz', 'moot'

    if (mode === 'quiz') return <QuizMode onBack={() => setMode(null)} />
    if (mode === 'moot') return <MootCourtMode onBack={() => setMode(null)} />

    return (
        <div className="sandbox animate-fade-in">
            <div className="sandbox-hero">
                <div className="hero-glow"></div>
                <h1 className="sandbox-hero-title">
                    <span className="hero-icon">🧪</span>
                    Legal <span className="accent-text">Sandbox</span>
                </h1>
                <p className="sandbox-hero-subtitle">
                    Interactive tools for legal learning, exam preparation, and courtroom simulation
                </p>
            </div>

            <div className="sandbox-cards">
                <div className="sandbox-card glass-card" onClick={() => setMode('quiz')}>
                    <div className="card-icon-wrap quiz-icon">📝</div>
                    <h3>Entrance Preparation</h3>
                    <p>Practice MCQs for CLAT, AILET, Judiciary & Bar exams across key legal subjects</p>
                    <ul className="card-features">
                        <li>🎯 Topic-wise practice</li>
                        <li>📊 Difficulty levels</li>
                        <li>💡 Detailed explanations</li>
                        <li>📈 Performance tracking</li>
                    </ul>
                    <button className="card-cta">Start Practice →</button>
                </div>

                <div className="sandbox-card glass-card" onClick={() => setMode('moot')}>
                    <div className="card-icon-wrap moot-icon">🏛️</div>
                    <h3>Moot Court Simulator</h3>
                    <p>Argue cases before an AI judge with opposing counsel in real-time simulation</p>
                    <ul className="card-features">
                        <li>⚔️ AI opposing counsel</li>
                        <li>👨‍⚖️ Judge observations</li>
                        <li>📊 Round-by-round scoring</li>
                        <li>💡 Rebuttal suggestions</li>
                    </ul>
                    <button className="card-cta">Enter Courtroom →</button>
                </div>
            </div>
        </div>
    )
}

/* ===================== QUIZ MODE ===================== */
function QuizMode({ onBack }) {
    const [quizState, setQuizState] = useState('setup') // setup, active, review
    const [config, setConfig] = useState({ topic: 'Constitutional Law', difficulty: 'medium', num_questions: 5, exam_type: 'CLAT' })
    const [questions, setQuestions] = useState([])
    const [currentQ, setCurrentQ] = useState(0)
    const [answers, setAnswers] = useState({})
    const [showExplanation, setShowExplanation] = useState(false)
    const [loading, setLoading] = useState(false)
    const [score, setScore] = useState(null)

    const startQuiz = async () => {
        setLoading(true)
        try {
            const res = await fetch('/api/sandbox/quiz', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            })
            const data = await res.json()
            const qs = data.quiz?.questions || []
            setQuestions(qs)
            setAnswers({})
            setCurrentQ(0)
            setShowExplanation(false)
            setScore(null)
            setQuizState('active')
        } catch {
            // Local fallback
            setQuestions(getLocalQuizFallback(config))
            setAnswers({})
            setCurrentQ(0)
            setShowExplanation(false)
            setScore(null)
            setQuizState('active')
        } finally {
            setLoading(false)
        }
    }

    const getLocalQuizFallback = (cfg) => [
        { id: 1, question: `Which fundamental right is guaranteed under Article 14 of the Constitution?`, options: ['A) Right to Freedom', 'B) Right to Equality', 'C) Right to Education', 'D) Right to Life'], correct_answer: 'B', explanation: 'Article 14 guarantees equality before law and equal protection of laws.', difficulty: cfg.difficulty, topic_tag: cfg.topic },
        { id: 2, question: 'The Supreme Court of India was established under which Article?', options: ['A) Article 124', 'B) Article 226', 'C) Article 32', 'D) Article 136'], correct_answer: 'A', explanation: 'Article 124 establishes the Supreme Court of India and deals with its composition.', difficulty: cfg.difficulty, topic_tag: cfg.topic },
        { id: 3, question: 'Judicial review is a power of the courts based on:', options: ['A) Statutory law', 'B) Constitutional provisions', 'C) Customary practice', 'D) Executive order'], correct_answer: 'B', explanation: 'Judicial review is rooted in Articles 13, 32, and 226 of the Constitution.', difficulty: cfg.difficulty, topic_tag: cfg.topic },
        { id: 4, question: 'Right to Education was made a fundamental right by which amendment?', options: ['A) 42nd', 'B) 44th', 'C) 86th', 'D) 93rd'], correct_answer: 'C', explanation: 'The 86th Constitutional Amendment (2002) inserted Article 21A making education for 6-14 age group a fundamental right.', difficulty: cfg.difficulty, topic_tag: cfg.topic },
        { id: 5, question: 'Which writ is known as the "bulwark of personal liberty"?', options: ['A) Mandamus', 'B) Habeas Corpus', 'C) Certiorari', 'D) Prohibition'], correct_answer: 'B', explanation: 'Habeas Corpus is the most powerful writ for protection of personal liberty, requiring a detained person to be produced before court.', difficulty: cfg.difficulty, topic_tag: cfg.topic },
    ].slice(0, cfg.num_questions)

    const selectAnswer = (letter) => {
        if (answers[currentQ] !== undefined) return
        setAnswers(prev => ({ ...prev, [currentQ]: letter }))
        setShowExplanation(true)
    }

    const nextQuestion = () => {
        if (currentQ < questions.length - 1) {
            setCurrentQ(prev => prev + 1)
            setShowExplanation(false)
        } else {
            // Calculate score
            let correct = 0
            questions.forEach((q, i) => {
                if (answers[i] === q.correct_answer) correct++
            })
            setScore({ correct, total: questions.length, percentage: Math.round((correct / questions.length) * 100) })
            setQuizState('review')
        }
    }

    // ---- Setup screen ----
    if (quizState === 'setup') {
        return (
            <div className="sandbox animate-fade-in">
                <button className="back-btn" onClick={onBack}>← Back to Sandbox</button>
                <div className="quiz-setup">
                    <h2 className="setup-title">📝 Entrance Exam Preparation</h2>
                    <p className="setup-subtitle">Configure your practice session</p>

                    <div className="setup-section glass-card">
                        <label>Topic</label>
                        <div className="select-pills">
                            {QUIZ_TOPICS.map(t => (
                                <button key={t.id} className={`pill ${config.topic === t.id ? 'active' : ''}`}
                                    onClick={() => setConfig(prev => ({ ...prev, topic: t.id }))}>{t.icon} {t.label}</button>
                            ))}
                        </div>

                        <label>Exam Type</label>
                        <div className="select-pills">
                            {EXAM_TYPES.map(e => (
                                <button key={e} className={`pill ${config.exam_type === e ? 'active' : ''}`}
                                    onClick={() => setConfig(prev => ({ ...prev, exam_type: e }))}>{e}</button>
                            ))}
                        </div>

                        <label>Difficulty</label>
                        <div className="select-pills">
                            {['easy', 'medium', 'hard'].map(d => (
                                <button key={d} className={`pill ${config.difficulty === d ? 'active' : ''}`}
                                    onClick={() => setConfig(prev => ({ ...prev, difficulty: d }))}>{d.charAt(0).toUpperCase() + d.slice(1)}</button>
                            ))}
                        </div>

                        <label>Number of Questions</label>
                        <div className="select-pills">
                            {[3, 5, 8, 10].map(n => (
                                <button key={n} className={`pill ${config.num_questions === n ? 'active' : ''}`}
                                    onClick={() => setConfig(prev => ({ ...prev, num_questions: n }))}>{n}</button>
                            ))}
                        </div>
                    </div>

                    {loading && <Loader text="Generating questions..." />}

                    <button className="sandbox-submit-btn" onClick={startQuiz} disabled={loading}>
                        {loading ? <><span className="spinner"></span> Generating Questions...</> : <>🚀 Start Quiz</>}
                    </button>
                </div>
            </div>
        )
    }

    // ---- Review screen ----
    if (quizState === 'review' && score) {
        const emoji = score.percentage >= 80 ? '🏆' : score.percentage >= 60 ? '👍' : '📚'
        return (
            <div className="sandbox animate-fade-in">
                <button className="back-btn" onClick={onBack}>← Back to Sandbox</button>
                <div className="quiz-review glass-card">
                    <h2 className="review-title">{emoji} Quiz Complete!</h2>
                    <div className="score-circle">
                        <span className="score-pct">{score.percentage}%</span>
                        <span className="score-detail">{score.correct}/{score.total} correct</span>
                    </div>
                    <div className="review-questions">
                        {questions.map((q, i) => {
                            const isCorrect = answers[i] === q.correct_answer
                            return (
                                <div key={i} className={`review-q ${isCorrect ? 'correct' : 'incorrect'}`}>
                                    <div className="review-q-header">
                                        <span className={`review-badge ${isCorrect ? 'badge-correct' : 'badge-incorrect'}`}>
                                            {isCorrect ? '✓' : '✗'}
                                        </span>
                                        <strong>Q{i + 1}:</strong> {q.question}
                                    </div>
                                    <div className="review-q-answer">
                                        Your answer: <strong>{answers[i] || '—'}</strong> | Correct: <strong>{q.correct_answer}</strong>
                                    </div>
                                    <p className="review-explanation">{q.explanation}</p>
                                </div>
                            )
                        })}
                    </div>
                    <div className="review-actions">
                        <button className="sandbox-submit-btn" onClick={() => { setQuizState('setup'); setScore(null) }}>
                            🔄 New Quiz
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    // ---- Active quiz ----
    const q = questions[currentQ]
    if (!q) return null

    const userAnswer = answers[currentQ]
    const isCorrect = userAnswer === q.correct_answer

    return (
        <div className="sandbox animate-fade-in">
            <div className="quiz-header">
                <button className="back-btn" onClick={onBack}>← Exit</button>
                <div className="quiz-progress">
                    <span>Question {currentQ + 1} of {questions.length}</span>
                    <div className="progress-bar">
                        <div className="progress-fill" style={{ width: `${((currentQ + 1) / questions.length) * 100}%` }}></div>
                    </div>
                </div>
                <span className={`difficulty-tag ${q.difficulty}`}>{q.difficulty?.toUpperCase()}</span>
            </div>

            <div className="quiz-question glass-card">
                {q.topic_tag && <span className="topic-tag">{q.topic_tag}</span>}
                <h3 className="question-text">{q.question}</h3>

                <div className="options-grid">
                    {q.options?.map((opt, i) => {
                        const letter = opt.charAt(0)
                        let cls = 'option-btn'
                        if (userAnswer) {
                            if (letter === q.correct_answer) cls += ' correct-answer'
                            else if (letter === userAnswer && !isCorrect) cls += ' wrong-answer'
                        }
                        if (letter === userAnswer) cls += ' selected'
                        return (
                            <button key={i} className={cls} onClick={() => selectAnswer(letter)} disabled={!!userAnswer}>
                                {opt}
                            </button>
                        )
                    })}
                </div>

                {showExplanation && (
                    <div className={`explanation-box ${isCorrect ? 'explain-correct' : 'explain-wrong'}`}>
                        <h4>{isCorrect ? '✅ Correct!' : '❌ Incorrect'}</h4>
                        <p>{q.explanation}</p>
                    </div>
                )}

                {userAnswer && (
                    <button className="next-btn" onClick={nextQuestion}>
                        {currentQ < questions.length - 1 ? 'Next Question →' : 'View Results →'}
                    </button>
                )}
            </div>
        </div>
    )
}

/* ===================== MOOT COURT MODE ===================== */
function MootCourtMode({ onBack }) {
    const [phase, setPhase] = useState('setup') // setup, arguing
    const [config, setConfig] = useState({ case_scenario: '', user_role: 'petitioner', court_level: 'High Court' })
    const [rounds, setRounds] = useState([])
    const [currentArg, setCurrentArg] = useState('')
    const [loading, setLoading] = useState(false)
    const [roundNum, setRoundNum] = useState(1)

    const startMoot = () => {
        if (config.case_scenario.length < 20) return
        setPhase('arguing')
        setRounds([])
        setRoundNum(1)
    }

    const submitArgument = async () => {
        if (currentArg.length < 10 || loading) return
        setLoading(true)

        const history = rounds.flatMap(r => [
            { role: config.user_role, content: r.userArg },
            { role: r.response?.opposing_counsel ? 'opposing' : 'court', content: r.response?.opposing_counsel?.argument || '' }
        ])

        const payload = {
            case_scenario: config.case_scenario,
            user_role: config.user_role,
            user_argument: currentArg,
            court_level: config.court_level,
            round_number: roundNum,
            history,
        }

        try {
            const res = await fetch('/api/sandbox/moot-court', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            const data = await res.json()
            setRounds(prev => [...prev, { userArg: currentArg, response: data.result, round: roundNum }])
        } catch {
            setRounds(prev => [...prev, { userArg: currentArg, response: getDemoMootResponse(), round: roundNum }])
        }

        setCurrentArg('')
        setRoundNum(prev => prev + 1)
        setLoading(false)
    }

    const getDemoMootResponse = () => ({
        opposing_counsel: {
            argument: "The respondent submits that the petitioner's argument overlooks settled law. The cited precedent is distinguishable on facts and the statutory interpretation urged is contrary to legislative intent.",
            objections: ["Assumes facts not in evidence"],
            authorities_cited: ["State of Maharashtra v. Indian Hotel (2013) 6 SCC 568"]
        },
        judge_observations: {
            questions_to_student: ["How do you distinguish the cited precedent?", "What specific statutory provision confers jurisdiction?"],
            observations: "Both sides raise interesting points. The petitioner needs stronger factual foundation.",
            ruling_hint: "The court is inclined to examine procedural aspects first."
        },
        scoring: {
            argument_strength: 7, legal_reasoning: 6, citation_quality: 5, persuasiveness: 7, overall: 6,
            feedback: "Good foundational argument but needs stronger citations. Consider citing specific Supreme Court judgments."
        },
        suggested_rebuttal_points: ["Distinguish opposing counsel's case on facts", "Invoke Article 21", "Cite Section 482 CrPC inherent powers"]
    })

    // ---- Setup ----
    if (phase === 'setup') {
        return (
            <div className="sandbox animate-fade-in">
                <button className="back-btn" onClick={onBack}>← Back to Sandbox</button>
                <div className="moot-setup">
                    <h2 className="setup-title">🏛️ Moot Court Simulator</h2>
                    <p className="setup-subtitle">Set up your case and argue before an AI bench</p>

                    <div className="setup-section glass-card">
                        <label>Case Scenario <span className="required">*</span></label>
                        <textarea rows={5} placeholder="Describe the case facts and legal issues (e.g., A files a writ petition under Article 226 challenging the demolition of an unauthorized structure without prior notice. The municipal corporation argues the structure violated building regulations...)"
                            value={config.case_scenario} onChange={e => setConfig(prev => ({ ...prev, case_scenario: e.target.value }))} />
                        <span className="form-hint">{config.case_scenario.length}/20 minimum characters</span>

                        <label>Your Role</label>
                        <div className="select-pills">
                            {['petitioner', 'respondent'].map(r => (
                                <button key={r} className={`pill ${config.user_role === r ? 'active' : ''}`}
                                    onClick={() => setConfig(prev => ({ ...prev, user_role: r }))}>{r.charAt(0).toUpperCase() + r.slice(1)}</button>
                            ))}
                        </div>

                        <label>Court Level</label>
                        <div className="select-pills">
                            {['District Court', 'High Court', 'Supreme Court'].map(c => (
                                <button key={c} className={`pill ${config.court_level === c ? 'active' : ''}`}
                                    onClick={() => setConfig(prev => ({ ...prev, court_level: c }))}>{c}</button>
                            ))}
                        </div>
                    </div>

                    <button className="sandbox-submit-btn" onClick={startMoot} disabled={config.case_scenario.length < 20}>
                        🏛️ Enter Courtroom
                    </button>
                </div>
            </div>
        )
    }

    // ---- Arguing phase ----
    return (
        <div className="sandbox animate-fade-in">
            <div className="moot-header">
                <button className="back-btn" onClick={onBack}>← Exit</button>
                <h2 className="moot-title">🏛️ {config.court_level} — Moot Court</h2>
                <span className="round-badge">Round {roundNum}</span>
            </div>

            <div className="moot-case-banner glass-card">
                <strong>Case:</strong> {config.case_scenario.substring(0, 200)}{config.case_scenario.length > 200 ? '...' : ''}
                <span className="role-tag">{config.user_role.toUpperCase()}</span>
            </div>

            {/* Previous rounds */}
            <div className="moot-rounds">
                {rounds.map((r, i) => (
                    <div key={i} className="moot-round glass-card">
                        <h4 className="round-label">Round {r.round}</h4>

                        <div className="exchange-block user-block">
                            <span className="exchange-tag user-tag">YOUR ARGUMENT</span>
                            <p>{r.userArg}</p>
                        </div>

                        {r.response?.opposing_counsel && (
                            <div className="exchange-block opp-block">
                                <span className="exchange-tag opp-tag">OPPOSING COUNSEL</span>
                                <p>{r.response.opposing_counsel.argument}</p>
                                {r.response.opposing_counsel.authorities_cited?.length > 0 && (
                                    <div className="cited-authorities">
                                        📚 {r.response.opposing_counsel.authorities_cited.join(' | ')}
                                    </div>
                                )}
                            </div>
                        )}

                        {r.response?.judge_observations && (
                            <div className="exchange-block judge-block">
                                <span className="exchange-tag judge-tag">👨‍⚖️ COURT</span>
                                <p>{r.response.judge_observations.observations}</p>
                                {r.response.judge_observations.questions_to_student?.map((q, qi) => (
                                    <div key={qi} className="judge-question">❓ {q}</div>
                                ))}
                                {r.response.judge_observations.ruling_hint && (
                                    <div className="ruling-hint">💡 {r.response.judge_observations.ruling_hint}</div>
                                )}
                            </div>
                        )}

                        {r.response?.scoring && (
                            <div className="scoring-panel">
                                <div className="score-bars">
                                    {['argument_strength', 'legal_reasoning', 'citation_quality', 'persuasiveness'].map(k => (
                                        <div key={k} className="score-bar-row">
                                            <span className="score-label">{k.replace(/_/g, ' ')}</span>
                                            <div className="score-bar-track">
                                                <div className="score-bar-fill" style={{ width: `${(r.response.scoring[k] || 0) * 10}%` }}></div>
                                            </div>
                                            <span className="score-val">{r.response.scoring[k]}/10</span>
                                        </div>
                                    ))}
                                </div>
                                {r.response.scoring.feedback && (
                                    <p className="scoring-feedback">💬 {r.response.scoring.feedback}</p>
                                )}
                            </div>
                        )}

                        {r.response?.suggested_rebuttal_points?.length > 0 && (
                            <div className="rebuttal-hints">
                                <strong>💡 Suggested rebuttals:</strong>
                                <ul>{r.response.suggested_rebuttal_points.map((p, pi) => <li key={pi}>{p}</li>)}</ul>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* Input area */}
            <div className="moot-input glass-card">
                <label>Your Argument (Round {roundNum})</label>
                <textarea rows={4} placeholder="Present your argument to the court. Cite relevant sections, precedents, and legal principles..."
                    value={currentArg} onChange={e => setCurrentArg(e.target.value)} />
                {loading && <Loader text="Court in session..." />}
                <button className="sandbox-submit-btn" onClick={submitArgument} disabled={currentArg.length < 10 || loading}>
                    {loading ? <><span className="spinner"></span> Court in session...</> : <>⚖️ Submit Argument</>}
                </button>
            </div>
        </div>
    )
}

export default LegalSandbox
