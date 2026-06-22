"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Skull, RefreshCw, Terminal, Shield, Activity } from "lucide-react"
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import Navbar from "@/components/Navbar"
import LoadingSpinner from "@/components/LoadingSpinner"
import StatusBadge from "@/components/StatusBadge"
import type { Session } from "@/lib/api"
import { fetchSessions } from "@/lib/api"
const PIE_COLORS: Record<string, string> = {
  Low: "#38bdf8",
  Medium: "#eab308",
  High: "#fca5a5",
  Critical: "#ef4444",
  Unknown: "#a855f7",
}

const RISK_LABELS: Record<number, string> = { 1: "Low", 2: "Medium", 3: "High", 4: "Critical", 5: "Unknown" }

export default function AttackersPage() {
  const router = useRouter()

  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [minRisk, setMinRisk] = useState(1)

  const load = useCallback(async () => {
    try {
      const d = await fetchSessions(minRisk)
      setSessions(d)
    } catch {} finally { setLoading(false) }
  }, [minRisk])

  useEffect(() => { load(); const i = setInterval(load, 15000); return () => clearInterval(i) }, [load])

  const riskDist = [1, 2, 3, 4].map(r => ({
    name: RISK_LABELS[r as keyof typeof RISK_LABELS],
    value: sessions.filter(s => Math.round(s.risk_score) === r).length,
  })).filter(d => d.value > 0)

  const commandsBySession = sessions.slice(0, 10).map(s => ({
    name: s.source_ip?.slice(0, 12) || "unknown",
    commands: s.commands_executed || 0,
  }))

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8 animate-in">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Attackers</h1>
            <p className="text-sm text-gray-600 mt-1">Active attack sessions and adversary behavior</p>
          </div>
          <div className="flex items-center gap-3">
            <select value={minRisk} onChange={e => setMinRisk(Number(e.target.value))} className="input-field text-xs py-1.5 px-3">
              <option value={1}>All Risk Levels</option>
              <option value={2}>Medium+</option>
              <option value={3}>High+</option>
              <option value={4}>Critical Only</option>
            </select>
            <button onClick={load} className="btn-ghost"><RefreshCw className="w-4 h-4" /></button>
          </div>
        </div>

        {loading ? <LoadingSpinner message="Loading sessions..." className="py-20" /> : (
          <>
            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="card">
                <div className="flex items-center gap-3 mb-5">
                  <div className="w-8 h-8 rounded-lg bg-yellow-500/15 flex items-center justify-center">
                    <Shield className="w-4 h-4 text-yellow-400" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-white">Risk Distribution</h2>
                    <p className="text-xs text-gray-600">Session risk score breakdown</p>
                  </div>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={riskDist} cx="50%" cy="50%" innerRadius={60} outerRadius={90} dataKey="value" nameKey="name" stroke="none" label={({ name, value }: { name: string; value: number }) => `${name}: ${value}`}>
                        {riskDist.map((d, i) => <Cell key={i} fill={PIE_COLORS[d.name] || "#38bdf8"} />)}
                      </Pie>
                      <Tooltip
                        content={({ active, payload }: { active?: boolean; payload?: Array<{ name: string; value: number }> }) => {
                          if (!active || !payload || !payload.length) return null
                          const d = payload[0]
                          return (
                            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 10, fontSize: 13, padding: "8px 12px" }}>
                              <p style={{ color: "#e5e7eb", margin: 0 }}>{d.name}</p>
                              <p style={{ color: "#9ca3af", margin: 0 }}>{d.value} sessions</p>
                            </div>
                          )
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex justify-center gap-4 text-xs text-gray-600">
                  {riskDist.map(d => (
                    <span key={d.name} className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: PIE_COLORS[d.name] || "#38bdf8" }} /> {d.name} ({d.value})
                    </span>
                  ))}
                </div>
              </div>
              <div className="card">
                <div className="flex items-center gap-3 mb-5">
                  <div className="w-8 h-8 rounded-lg bg-purple-500/15 flex items-center justify-center">
                    <Terminal className="w-4 h-4 text-purple-400" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-white">Commands Executed</h2>
                    <p className="text-xs text-gray-600">Top sessions by activity</p>
                  </div>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={commandsBySession} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
                      <XAxis type="number" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={{ stroke: "#1f2937" }} />
                      <YAxis type="category" dataKey="name" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} width={90} />
                      <Tooltip
                        contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 10, fontSize: 13 }}
                        cursor={{ fill: '#0f172a' }}
                      />
                      <Bar dataKey="commands" fill="#0c8ee2" radius={[0, 4, 4, 0]} cursor={{ fill: '#0f172a' }} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>

            {/* Sessions Table */}
            <div className="card p-0 overflow-hidden">
              <div className="p-5 pb-0">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-red-500/15 flex items-center justify-center">
                    <Activity className="w-4 h-4 text-red-400" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-white">Active Sessions</h2>
                    <p className="text-xs text-gray-600">{sessions.length} total sessions</p>
                  </div>
                </div>
              </div>
              <div className="mt-5 overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800/40">
                      <th className="table-cell text-left table-header">Source IP</th>
                      <th className="table-cell text-left table-header">Protocol</th>
                      <th className="table-cell text-left table-header">Risk</th>
                      <th className="table-cell text-left table-header">Commands</th>
                      <th className="table-cell text-left table-header">Duration</th>
                      <th className="table-cell text-left table-header">Last Seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((s, i) => (
                      <tr key={s.session_id || i} className="table-row">
                        <td className="table-cell font-mono text-xs text-white">{s.source_ip}</td>
                        <td className="table-cell text-gray-400">{s.protocol?.toUpperCase()}</td>
                        <td className="table-cell">
                          <StatusBadge severity={
                            Math.round(s.risk_score) >= 4 ? "critical" :
                            Math.round(s.risk_score) >= 3 ? "high" : "medium"
                          } />
                        </td>
                        <td className="table-cell text-gray-400">{s.commands_executed}</td>
                        <td className="table-cell text-gray-400">{s.duration_minutes ? `${Math.round(s.duration_minutes)}m` : "-"}</td>
                        <td className="table-cell text-gray-500 text-xs">{s.last_seen ? new Date(s.last_seen).toLocaleString() : "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
