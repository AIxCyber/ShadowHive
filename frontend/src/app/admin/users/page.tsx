"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Users, Plus, Trash2, Shield, RefreshCw, Loader2, X, Check } from "lucide-react"
import Navbar from "@/components/Navbar"
import { useAuth } from "@/lib/auth-context"

interface UserInfo {
  id: string
  email: string
  display_name: string
  role: string
  must_change_password: boolean
  is_active: boolean
  created_at?: string
  last_login?: string
}

const ROLE_LEVEL = { admin: 3, user: 2, viewer: 1 }

export default function AdminUsersPage() {
  const { user, loading: authLoading, isAdmin } = useAuth()
  const router = useRouter()
  const [users, setUsers] = useState<UserInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  // Create form
  const [showCreate, setShowCreate] = useState(false)
  const [newEmail, setNewEmail] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [newName, setNewName] = useState("")
  const [newRole, setNewRole] = useState("user")
  const [creating, setCreating] = useState(false)

  // Reset password
  const [resettingId, setResettingId] = useState<string | null>(null)
  const [tempPassword, setTempPassword] = useState("")

  useEffect(() => {
    if (!authLoading && (!user || !isAdmin)) {
      router.push("/")
    }
  }, [user, authLoading, isAdmin, router])

  const loadUsers = useCallback(async () => {
    const token = localStorage.getItem("access_token")
    setLoading(true)
    try {
      const res = await fetch("/api/admin/users", {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        setUsers(await res.json())
      }
    } catch {} finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { if (isAdmin) loadUsers() }, [isAdmin, loadUsers])

  const doCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setCreating(true)
    const token = localStorage.getItem("access_token")
    try {
      const res = await fetch("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ email: newEmail, password: newPassword, display_name: newName, role: newRole }),
      })
      if (!res.ok) {
        const body = await res.text().catch(() => "")
        throw new Error(body || "Create failed")
      }
      setShowCreate(false)
      setNewEmail("")
      setNewPassword("")
      setNewName("")
      setNewRole("user")
      loadUsers()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  const doDelete = async (userId: string) => {
    if (!confirm("Delete this user?")) return
    const token = localStorage.getItem("access_token")
    try {
      await fetch(`/api/admin/users/${userId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      })
      loadUsers()
    } catch {}
  }

  const doResetPassword = async (userId: string) => {
    const token = localStorage.getItem("access_token")
    setResettingId(userId)
    setTempPassword("")
    try {
      const res = await fetch(`/api/admin/users/${userId}/reset-password`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data = await res.json()
        setTempPassword(data.temporary_password)
      }
    } catch {} finally {
      setResettingId(null)
    }
  }

  const doToggleActive = async (userId: string, currentActive: boolean) => {
    const token = localStorage.getItem("access_token")
    try {
      await fetch(`/api/admin/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ is_active: !currentActive }),
      })
      loadUsers()
    } catch {}
  }

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-hive-400" />
      </div>
    )
  }

  if (!user || !isAdmin) return null

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8 animate-in">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-hive-500/15 flex items-center justify-center">
              <Shield className="w-5 h-5 text-hive-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">User Management</h1>
              <p className="text-sm text-gray-600 mt-1">Manage users, roles, and permissions</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={loadUsers} className="btn-ghost"><RefreshCw className="w-4 h-4" /></button>
            <button onClick={() => setShowCreate(true)} className="btn-primary">
              <Plus className="w-4 h-4" /> Create User
            </button>
          </div>
        </div>

        {showCreate && (
          <div className="card border-hive-500/20">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-white">Create New User</h3>
              <button onClick={() => setShowCreate(false)} className="text-gray-600 hover:text-gray-400">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={doCreate} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {error && <div className="sm:col-span-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400">{error}</div>}
              <div className="space-y-1.5">
                <label className="text-xs text-gray-600 font-medium">Email</label>
                <input value={newEmail} onChange={e => setNewEmail(e.target.value)} required
                  className="w-full px-3 py-2 rounded-xl text-sm bg-gray-900/60 border border-gray-800/50 text-gray-300 focus:outline-none focus:border-hive-500/30" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-gray-600 font-medium">Password</label>
                <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required
                  className="w-full px-3 py-2 rounded-xl text-sm bg-gray-900/60 border border-gray-800/50 text-gray-300 focus:outline-none focus:border-hive-500/30" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-gray-600 font-medium">Display Name</label>
                <input value={newName} onChange={e => setNewName(e.target.value)} required
                  className="w-full px-3 py-2 rounded-xl text-sm bg-gray-900/60 border border-gray-800/50 text-gray-300 focus:outline-none focus:border-hive-500/30" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-gray-600 font-medium">Role</label>
                <select value={newRole} onChange={e => setNewRole(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl text-sm bg-gray-900/60 border border-gray-800/50 text-gray-300 focus:outline-none focus:border-hive-500/30">
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
              <div className="sm:col-span-2 flex justify-end gap-2">
                <button type="button" onClick={() => setShowCreate(false)} className="btn-ghost">Cancel</button>
                <button type="submit" disabled={creating} className="btn-primary">
                  {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  {creating ? "Creating..." : "Create"}
                </button>
              </div>
            </form>
          </div>
        )}

        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800/40">
                  <th className="table-cell text-left table-header">Email</th>
                  <th className="table-cell text-left table-header">Name</th>
                  <th className="table-cell text-left table-header">Role</th>
                  <th className="table-cell text-left table-header">Status</th>
                  <th className="table-cell text-left table-header">Force Change</th>
                  <th className="table-cell text-left table-header">Last Login</th>
                  <th className="table-cell text-left table-header">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className="table-row">
                    <td className="table-cell font-mono text-xs text-white">{u.email}</td>
                    <td className="table-cell text-gray-400">{u.display_name}</td>
                    <td className="table-cell">
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        u.role === "admin" ? "bg-hive-500/10 text-hive-400" :
                        u.role === "viewer" ? "bg-gray-700 text-gray-400" :
                        "bg-blue-500/10 text-blue-400"
                      }`}>{u.role}</span>
                    </td>
                    <td className="table-cell">
                      <span className={`text-xs px-2 py-0.5 rounded ${u.is_active ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="table-cell">
                      {u.must_change_password ? (
                        <Check className="w-4 h-4 text-yellow-400" />
                      ) : (
                        <X className="w-4 h-4 text-gray-600" />
                      )}
                    </td>
                    <td className="table-cell text-gray-500 text-xs">
                      {u.last_login ? new Date(u.last_login).toLocaleString() : "Never"}
                    </td>
                    <td className="table-cell">
                      <div className="flex items-center gap-1">
                        <button onClick={() => doResetPassword(u.id)} disabled={resettingId === u.id}
                          className="p-1.5 rounded-lg text-gray-600 hover:text-hive-400 hover:bg-hive-500/10"
                          title="Reset password">
                          {resettingId === u.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                        </button>
                        <button onClick={() => doToggleActive(u.id, u.is_active)}
                          className="p-1.5 rounded-lg text-gray-600 hover:text-yellow-400 hover:bg-yellow-500/10"
                          title={u.is_active ? "Disable" : "Enable"}>
                          <Shield className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => doDelete(u.id)}
                          className="p-1.5 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-500/10"
                          title="Delete user">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {tempPassword && (
          <div className="card border-green-500/20 bg-green-500/5">
            <p className="text-sm text-green-400 font-medium mb-2">Temporary Password</p>
            <code className="text-lg font-mono text-white bg-gray-900/60 px-3 py-2 rounded-xl block select-all">{tempPassword}</code>
            <p className="text-xs text-gray-600 mt-2">User must change this on next login.</p>
            <button onClick={() => setTempPassword("")} className="btn-ghost text-xs mt-2">Dismiss</button>
          </div>
        )}
      </main>
    </div>
  )
}
