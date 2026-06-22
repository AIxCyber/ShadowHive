"use client"

import { useState, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Hexagon, Eye, EyeOff, Loader2, CheckCircle } from "lucide-react"
import Link from "next/link"

function ResetForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get("token") || ""

  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    if (password !== confirm) {
      setError("Passwords do not match")
      return
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters")
      return
    }
    setBusy(true)
    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      })
      if (!res.ok) {
        const body = await res.text().catch(() => "")
        throw new Error(body || "Reset failed")
      }
      setDone(true)
    } catch (err: any) {
      setError(err.message || "Reset failed")
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <div className="text-center space-y-4">
        <CheckCircle className="w-12 h-12 text-green-400 mx-auto" />
        <p className="text-sm text-gray-400">Password reset successfully.</p>
        <Link href="/login" className="btn-primary inline-flex">
          Sign In
        </Link>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400 text-center">
          {error}
        </div>
      )}

      <div className="space-y-1.5">
        <label className="text-xs text-gray-600 font-medium">New Password</label>
        <div className="relative">
          <input
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Min 6 characters"
            required
            className="w-full px-4 py-2.5 rounded-xl text-sm bg-gray-900/80 border border-gray-800 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors pr-10"
          />
          <button type="button" onClick={() => setShowPassword(!showPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400">
            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
      </div>

      <div className="space-y-1.5">
        <label className="text-xs text-gray-600 font-medium">Confirm Password</label>
        <input
          type="password"
          value={confirm}
          onChange={e => setConfirm(e.target.value)}
          placeholder="Repeat password"
          required
          className="w-full px-4 py-2.5 rounded-xl text-sm bg-gray-900/80 border border-gray-800 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors"
        />
      </div>

      <button type="submit" disabled={busy || !password || !confirm} className="btn-primary w-full justify-center">
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
        {busy ? "Resetting..." : "Reset Password"}
      </button>
    </form>
  )
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-hive-400 to-hive-700 flex items-center justify-center mx-auto shadow-lg shadow-hive-600/20 mb-4">
            <Hexagon className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-bold text-white tracking-tight">Set New Password</h1>
          <p className="text-sm text-gray-600 mt-1">Enter your new password below</p>
        </div>

        <Suspense fallback={<div className="text-center text-gray-600">Loading...</div>}>
          <ResetForm />
        </Suspense>
      </div>
    </div>
  )
}
