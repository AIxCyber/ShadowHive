"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Activity, RefreshCw, AlertTriangle, Shield, Target, TrendingUp } from "lucide-react"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import Navbar from "@/components/Navbar"
import LoadingSpinner from "@/components/LoadingSpinner"
import StatusBadge from "@/components/StatusBadge"
import type { ThreatEvent } from "@/lib/api"
import { fetchThreats } from "@/lib/api"
export default function IntelligencePage() {
  const router = useRouter()

  const [threats, setThreats] = useState<ThreatEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [severityFilter, setSeverityFilter] = useState("")
  const [expandedThreat, setExpandedThreat] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const d = await fetchThreats(severityFilter || undefined)
      setThreats(d)
    } catch {} finally { setLoading(false) }
  }, [severityFilter])

  useEffect(() => { load(); const i = setInterval(load, 30000); return () => clearInterval(i) }, [load])

  const tacticCounts: Record<string, number> = {}
  threats.forEach(t => { if (t.tactic) tacticCounts[t.tactic] = (tacticCounts[t.tactic] || 0) + 1 })
  const tacticData = Object.entries(tacticCounts)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8 animate-in">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Threat Intelligence</h1>
            <p className="text-sm text-gray-600 mt-1">MITRE ATT&CK mapped threat events and adversary tactics</p>
          </div>
          <div className="flex items-center gap-3">
            <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)} className="input-field text-xs py-1.5 px-3">
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <button onClick={load} className="btn-ghost"><RefreshCw className="w-4 h-4" /></button>
          </div>
        </div>

        {loading ? <LoadingSpinner message="Loading intelligence..." className="py-20" /> : (
          <>
            {/* Chart */}
            <div className="card">
              <div className="flex items-center gap-3 mb-5">
                <div className="w-8 h-8 rounded-lg bg-red-500/15 flex items-center justify-center">
                  <TrendingUp className="w-4 h-4 text-red-400" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white">Tactics Breakdown</h2>
                  <p className="text-xs text-gray-600">MITRE ATT&CK tactics by occurrence</p>
                </div>
              </div>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={tacticData} layout="vertical" margin={{ left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
                    <XAxis type="number" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={{ stroke: "#1f2937" }} />
                    <YAxis type="category" dataKey="name" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} width={140} />
                    <Tooltip
                      contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 10, fontSize: 13 }}
                      cursor={{ fill: '#0f172a' }}
                    />
                    <Bar dataKey="value" fill="#0c8ee2" radius={[0, 4, 4, 0]} cursor={{ fill: '#0f172a' }} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Threats Table */}
            <div className="card p-0 overflow-hidden">
              <div className="p-5 pb-0">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-orange-500/15 flex items-center justify-center">
                    <AlertTriangle className="w-4 h-4 text-orange-400" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-white">Threat Events</h2>
                    <p className="text-xs text-gray-600">{threats.length} events detected</p>
                  </div>
                </div>
              </div>
              <div className="mt-5 overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800/40">
                      <th className="table-cell text-left table-header">ID</th>
                      <th className="table-cell text-left table-header">Severity</th>
                      <th className="table-cell text-left table-header">Tactic</th>
                      <th className="table-cell text-left table-header">Technique</th>
                      <th className="table-cell text-left table-header">Confidence</th>
                      <th className="table-cell text-left table-header">Source</th>
                      <th className="table-cell text-left table-header">Detected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {threats.map((t, i) => (
                      <tr key={t.threat_id || i} className="table-row">
                        <td className="table-cell font-mono text-xs text-gray-500">{t.threat_id?.slice(0, 8)}</td>
                        <td className="table-cell"><StatusBadge severity={t.severity} /></td>
                        <td className="table-cell text-gray-400">{t.tactic}</td>
                        <td className="table-cell text-gray-400">{t.technique}</td>
                        <td className="table-cell">
                          <div className="flex items-center gap-2">
                            <div className="w-20 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                              <div className="h-full rounded-full bg-gradient-to-r from-hive-600 to-hive-400" style={{ width: `${(t.confidence || 0) * 100}%` }} />
                            </div>
                            <span className="text-xs text-gray-600">{((t.confidence || 0) * 100).toFixed(0)}%</span>
                          </div>
                        </td>
                        <td className="table-cell text-gray-500 text-xs">{t.source_ip}</td>
                        <td className="table-cell text-gray-500 text-xs">{t.detected_at ? new Date(t.detected_at).toLocaleString() : "-"}</td>
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
