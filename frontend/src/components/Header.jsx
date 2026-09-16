import { useState } from 'react'
import './Header.css'
import MotionToggle from './MotionToggle'
import { useAuth } from '../context/AuthContext'

function Header({ onShowAuth }) {
    const { user, isAuthenticated, logout } = useAuth()
    const [reduceMotion, setReduceMotion] = useState(false)

    const handleMotionToggle = (checked) => {
        setReduceMotion(checked)
        if (checked) {
            document.documentElement.style.setProperty('--animation-duration', '0s')
            document.documentElement.classList.add('reduce-motion')
        } else {
            document.documentElement.style.removeProperty('--animation-duration')
            document.documentElement.classList.remove('reduce-motion')
        }
    }

    return (
        <header className="header">
            <div className="header-content">
                <div className="logo">
                    <span className="logo-icon">⚖️</span>
                    <div className="logo-text">
                        <h1>JustiAssist</h1>
                        <span className="version-badge">v4.0</span>
                    </div>
                </div>
                <p className="tagline">
                    Agentic Legal AI
                </p>
            </div>

            <div className="header-actions">
                <MotionToggle
                    checked={reduceMotion}
                    onChange={handleMotionToggle}
                    label="Reduce Motion"
                    id="reduceMotionToggle"
                />

                {isAuthenticated ? (
                    <div className="user-menu">
                        <span className="user-avatar">👤</span>
                        <span className="user-name">{user?.display_name}</span>
                        <button className="logout-btn" onClick={logout} title="Logout">
                            ↗
                        </button>
                    </div>
                ) : (
                    <button className="login-btn" onClick={onShowAuth}>
                        Login
                    </button>
                )}
            </div>
        </header>
    )
}

export default Header
