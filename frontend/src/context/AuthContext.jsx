/**
 * JustiAssist Auth Context
 * Global authentication state management with JWT tokens.
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authFetch, apiLogin, apiSignup } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(() => localStorage.getItem('justiassist_token'))
  const [isLoading, setIsLoading] = useState(true)

  // Check stored token on mount
  useEffect(() => {
    if (token) {
      verifyToken()
    } else {
      setIsLoading(false)
    }
  }, [])

  const verifyToken = async () => {
    try {
      const res = await authFetch('/api/auth/me')
      if (res.ok) {
        const data = await res.json()
        setUser(data.user)
      } else {
        // Token invalid or expired
        localStorage.removeItem('justiassist_token')
        setToken(null)
        setUser(null)
      }
    } catch {
      localStorage.removeItem('justiassist_token')
      setToken(null)
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }

  const login = useCallback(async (email, password) => {
    const res = await apiLogin(email, password)
    if (res.access_token) {
      localStorage.setItem('justiassist_token', res.access_token)
      setToken(res.access_token)
      setUser(res.user)
      return { success: true }
    }
    return { success: false, error: res.detail || 'Login failed' }
  }, [])

  const signup = useCallback(async (email, password, displayName) => {
    const res = await apiSignup(email, password, displayName)
    if (res.access_token) {
      localStorage.setItem('justiassist_token', res.access_token)
      setToken(res.access_token)
      setUser(res.user)
      return { success: true }
    }
    return { success: false, error: res.detail || 'Signup failed' }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('justiassist_token')
    setToken(null)
    setUser(null)
  }, [])

  const value = {
    user,
    token,
    isAuthenticated: !!user,
    isLoading,
    login,
    signup,
    logout,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export default AuthContext
