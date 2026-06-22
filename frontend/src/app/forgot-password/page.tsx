"use client"

import { useState } from "react"
import { Hexagon, ArrowLeft, CheckCircle, Loader2 } from "lucide-react"
import Link from "next/link"

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setBusy(true)
    try {
      const res = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      })
      if (!res.ok) {
        const body = await res.text().catch(() => "")
        throw new Error(body || "Request failed")
      }
      setSent(true)
    } catch (err: any) {
      setError(err.message || "Request failed")
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
          <h1 className="text-xl font-bold text-white tracking-tight">Reset Password</h1>
          <p className="text-sm text-gray-600 mt-1">Enter your email to receive a reset link</p>
        </div>

        {sent ? (
          <div className="text-center space-y-4">
            <CheckCircle className="w-12 h-12 text-green-400 mx-auto" />
            <p className="text-sm text-gray-400">
              If the email exists, a reset link has been sent. Check your inbox or server console.
            </p>
            <Link href="/login" className="text-sm text-hive-400 hover:text-hive-300 inline-flex items-center gap-1">
              <ArrowLeft className="w-3 h-3" /> Back to login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400 text-center">
                {error}
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-xs text-gray-600 font-medium">Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="admin@shadowhive.local"
                required
                className="w-full px-4 py-2.5 rounded-xl text-sm bg-gray-900/80 border border-gray-800 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors"
              />
            </div>

            <button type="submit" disabled={busy || !email} className="btn-primary w-full justify-center">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              {busy ? "Sending..." : "Send Reset Link"}
            </button>

            <div className="text-center">
              <Link href="/login" className="text-xs text-gray-600 hover:text-hive-400 inline-flex items-center gap-1">
                <ArrowLeft className="w-3 h-3" /> Back to login
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
