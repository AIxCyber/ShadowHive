"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Hexagon, Eye, EyeOff, Loader2 } from "lucide-react"
import Link from "next/link"
import { useAuth } from "@/lib/auth-context"

export default function LoginPage() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const { login, user } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (user) {
      router.replace("/")
    }
  }, [user, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setBusy(true)
    try {
      await login(email, password)
      router.push("/")
    } catch (err: any) {
      setError(err.message || "Login failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-hive-400 to-hive-700 flex items-center justify-center mx-auto shadow-lg shadow-hive-600/20 mb-4">
            <Hexagon className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-bold text-white tracking-tight">Shadow<span className="text-gradient">Hive</span></h1>
          <p className="text-sm text-gray-600 mt-1">Sign in to your account</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400 text-center">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs text-gray-600 font-medium">Email or Username</label>
            <input
              type="text"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="shadowhive"
              required
              className="w-full px-4 py-2.5 rounded-xl text-sm bg-gray-900/80 border border-gray-800 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-gray-600 font-medium">Password</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="admin123"
                required
                className="w-full px-4 py-2.5 rounded-xl text-sm bg-gray-900/80 border border-gray-800 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button type="submit" disabled={busy || !email || !password} className="btn-primary w-full justify-center">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            {busy ? "Signing in..." : "Sign In"}
          </button>

          <div className="text-center">
            <Link href="/forgot-password" className="text-xs text-gray-600 hover:text-hive-400 transition-colors">
              Forgot password?
            </Link>
          </div>
        </form>

        <p className="text-center text-[10px] text-gray-800 mt-8">
          Default: shadowhive / admin123 (change on first login)
        </p>
      </div>
    </div>
  )
}
