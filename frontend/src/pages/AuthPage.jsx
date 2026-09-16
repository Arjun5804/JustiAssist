/**
 * JustiAssist Auth Page
 * Professional login/signup interface with animated transitions.
 */
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import './AuthPage.css'

export default function AuthPage() {
  const { login, signup } = useAuth()
  const [isLogin, setIsLogin] = useState(true)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      let result
      if (isLogin) {
        result = await login(email, password)
      } else {
        if (!displayName.trim()) {
          setError('Please enter your name')
          setIsLoading(false)
          return
        }
        result = await signup(email, password, displayName)
      }

      if (!result.success) {
        setError(result.error)
      }
    } catch {
      setError('Connection error. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const toggleMode = () => {
    setIsLogin(!isLogin)
    setError('')
  }

  return (
    <div className="auth-page">
      <div className="auth-bg-pattern"></div>

      <div className="auth-container animate-fade-in">
        {/* Brand Section */}
        <div className="auth-brand">
          <div className="auth-logo">
            <span className="auth-logo-icon">⚖️</span>
            <h1>JustiAssist</h1>
          </div>
          <p className="auth-tagline">
            AI-Powered Legal Intelligence Platform
          </p>
          <div className="auth-features">
            <div className="auth-feature-item">
              <span>🤖</span>
              <span>5 Specialized AI Agents</span>
            </div>
            <div className="auth-feature-item">
              <span>🔒</span>
              <span>Zero-Hallucination Engine</span>
            </div>
            <div className="auth-feature-item">
              <span>📚</span>
              <span>Complete Indian Law Database</span>
            </div>
            <div className="auth-feature-item">
              <span>💬</span>
              <span>Persistent Chat Memory</span>
            </div>
          </div>
        </div>

        {/* Form Section */}
        <div className="auth-form-section">
          <div className="auth-form-card">
            <div className="auth-tab-switch">
              <button
                className={`auth-tab ${isLogin ? 'active' : ''}`}
                onClick={() => { setIsLogin(true); setError('') }}
              >
                Login
              </button>
              <button
                className={`auth-tab ${!isLogin ? 'active' : ''}`}
                onClick={() => { setIsLogin(false); setError('') }}
              >
                Sign Up
              </button>
            </div>

            <form onSubmit={handleSubmit} className="auth-form">
              <h2>{isLogin ? 'Welcome Back' : 'Create Account'}</h2>
              <p className="auth-subtitle">
                {isLogin
                  ? 'Sign in to access your legal workspace'
                  : 'Join JustiAssist for intelligent legal research'
                }
              </p>

              {!isLogin && (
                <div className="auth-field">
                  <label htmlFor="auth-name">Full Name</label>
                  <input
                    id="auth-name"
                    type="text"
                    placeholder="Enter your name"
                    value={displayName}
                    onChange={e => setDisplayName(e.target.value)}
                    required={!isLogin}
                  />
                </div>
              )}

              <div className="auth-field">
                <label htmlFor="auth-email">Email Address</label>
                <input
                  id="auth-email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required
                />
              </div>

              <div className="auth-field">
                <label htmlFor="auth-password">Password</label>
                <input
                  id="auth-password"
                  type="password"
                  placeholder="Min 6 characters"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  minLength={6}
                />
              </div>

              {error && (
                <div className="auth-error">
                  <span>⚠️</span> {error}
                </div>
              )}

              <button
                type="submit"
                className="auth-submit-btn"
                disabled={isLoading}
              >
                {isLoading ? (
                  <span className="auth-spinner">⟳</span>
                ) : (
                  isLogin ? 'Sign In' : 'Create Account'
                )}
              </button>
            </form>

            <div className="auth-footer">
              <button className="auth-toggle-link" onClick={toggleMode}>
                {isLogin
                  ? "Don't have an account? Sign up"
                  : 'Already have an account? Sign in'
                }
              </button>
            </div>

            <div className="auth-skip">
              <a href="#" onClick={(e) => {
                e.preventDefault()
                // Allow skipping auth for guests
                window.location.reload()
              }}>
                Continue as Guest →
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
