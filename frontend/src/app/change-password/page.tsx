"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Hexagon, Eye, EyeOff, Loader2, Shield } from "lucide-react"
import { useAuth } from "@/lib/auth-context"

export default function ChangePasswordPage() {
  const [current, setCurrent] = useState("")
  const [newPw, setNewPw] = useState("")
  const [confirm, setConfirm] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const { refreshUser, logout } = useAuth()
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    if (newPw !== confirm) {
      setError("Passwords do not match")
      return
    }
    if (newPw.length < 6) {
      setError("Password must be at least 6 characters")
      return
    }
    setBusy(true)
    try {
      const token = localStorage.getItem("access_token")
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ current_password: current, new_password: newPw }),
      })
      if (!res.ok) {
        const body = await res.text().catch(() => "")
        throw new Error(body || "Change failed")
      }
      await refreshUser()
      router.push("/")
    } catch (err: any) {
      setError(err.message || "Change failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-yellow-500/15 flex items-center justify-center mx-auto shadow-lg shadow-yellow-600/10 mb-4">
            <Shield className="w-7 h-7 text-yellow-400" />
          </div>
          <h1 className="text-xl font-bold text-white tracking-tight">Change Password Required</h1>
          <p className="text-sm text-gray-600 mt-1">You must change your password before continuing.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400 text-center">
              {error}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs text-gray-600 font-medium">Current Password</label>
            <input
              type="password"
              value={current}
              onChange={e => setCurrent(e.target.value)}
              required
              className="w-full px-4 py-2.5 rounded-xl text-sm bg-gray-900/80 border border-gray-800 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-gray-600 font-medium">New Password</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={newPw}
                onChange={e => setNewPw(e.target.value)}
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
            <label className="text-xs text-gray-600 font-medium">Confirm New Password</label>
            <input
              type="password"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              placeholder="Repeat new password"
              required
              className="w-full px-4 py-2.5 rounded-xl text-sm bg-gray-900/80 border border-gray-800 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors"
            />
          </div>

          <button type="submit" disabled={busy || !current || !newPw || !confirm} className="btn-primary w-full justify-center">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            {busy ? "Changing..." : "Change Password"}
          </button>

          <div className="text-center">
            <button onClick={logout} className="text-xs text-gray-600 hover:text-red-400 transition-colors">
              Sign out
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
