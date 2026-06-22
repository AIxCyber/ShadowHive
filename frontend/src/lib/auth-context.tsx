"use client"

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react"
import { refreshTokens } from "./api"

interface User {
  id: string
  email: string
  display_name: string
  role: string
  must_change_password: boolean
  is_active: boolean
  created_at?: string
  last_login?: string
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
  isAdmin: boolean
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  login: async () => {},
  logout: () => {},
  refreshUser: async () => {},
  isAdmin: false,
})

function getToken() {
  if (typeof window === "undefined") return null
  return localStorage.getItem("access_token")
}

function getRefreshToken() {
  if (typeof window === "undefined") return null
  return localStorage.getItem("refresh_token")
}

function setTokens(access: string, refresh: string) {
  localStorage.setItem("access_token", access)
  localStorage.setItem("refresh_token", refresh)
}

function clearTokens() {
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    const token = getToken()
    try {
      let res = await fetch("/api/auth/me", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (res.ok) {
        const u = await res.json()
        setUser(u)
      } else if (res.status === 401) {
        const refreshed = await refreshTokens()
        if (refreshed) {
          const newToken = getToken()
          const meRes = await fetch("/api/auth/me", {
            headers: newToken ? { Authorization: `Bearer ${newToken}` } : {},
          })
          if (meRes.ok) {
            const u = await meRes.json()
            setUser(u)
        } else if (meRes.status === 401) {
          clearTokens()
          setUser(null)
        } else {
          setUser(null)
        }
      } else {
        if (!getRefreshToken()) clearTokens()
        setUser(null)
      }
    } else {
      const body = await res.text().catch(() => "")
      if (body.includes("Auth is disabled")) {
        setUser({ id: "guest", email: "", display_name: "Guest", role: "admin", must_change_password: false, is_active: true })
      } else if (res.status >= 500) {
        setUser(null)
      } else {
        clearTokens()
        setUser(null)
      }
    }
  } catch {
    setUser(null)
  } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refreshUser() }, [refreshUser])

  const login = async (email: string, password: string) => {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => "")
      throw new Error(body || "Login failed")
    }
    const data = await res.json()
    setTokens(data.access_token, data.refresh_token)
    setUser(data.user)
  }

  const logout = () => {
    clearTokens()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser, isAdmin: user?.role === "admin" }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
