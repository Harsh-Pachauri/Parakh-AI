import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import apiClient from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('viva_user') || 'null')
    } catch {
      return null
    }
  })
  const [token, setToken] = useState(() => localStorage.getItem('viva_access_token') || null)
  const [loading, setLoading] = useState(Boolean(localStorage.getItem('viva_access_token')))

  const logout = () => {
    localStorage.removeItem('viva_access_token')
    localStorage.removeItem('viva_user')
    setToken(null)
    setUser(null)
    setLoading(false)
  }

  useEffect(() => {
    const unauthorized = () => logout()
    window.addEventListener('viva:unauthorized', unauthorized)
    window.addEventListener('auth:unauthorized', unauthorized)

    const storedToken = localStorage.getItem('viva_access_token')
    if (storedToken) {
      setToken(storedToken)
      apiClient
        .get('/api/auth/me')
        .then(({ data }) => {
          setUser(data)
          localStorage.setItem('viva_user', JSON.stringify(data))
        })
        .catch(logout)
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }

    return () => {
      window.removeEventListener('viva:unauthorized', unauthorized)
      window.removeEventListener('auth:unauthorized', unauthorized)
    }
  }, [])

  const login = async (email, password) => {
    const { data } = await apiClient.post('/api/auth/login', { email, password })
    localStorage.setItem('viva_access_token', data.access_token)
    localStorage.setItem('viva_user', JSON.stringify(data.user))
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }

  const register = async ({ full_name, email, password }) => {
    const { data } = await apiClient.post('/api/auth/register', {
      full_name,
      email,
      password,
      role: 'student',
    })
    localStorage.setItem('viva_access_token', data.access_token)
    localStorage.setItem('viva_user', JSON.stringify(data.user))
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }

  const value = useMemo(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(user && token),
      login,
      register,
      logout,
      loading,
    }),
    [user, token, loading]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
