"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Building2, Skull, Activity, ShieldAlert, RefreshCw, TrendingUp, AlertTriangle, Radio } from "lucide-react"
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import Navbar from "@/components/Navbar"
import StatCard from "@/components/StatCard"
import LoadingSpinner from "@/components/LoadingSpinner"
import StatusBadge from "@/components/StatusBadge"
import type { DashboardStats } from "@/lib/api"
import { fetchStats } from "@/lib/api"

const RANGE_OPTIONS = [
  { key: "24h", label: "24h" },
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
  { key: "all", label: "All time" },
] as const

export default function Dashboard() {
  const router = useRouter()
  const [range, setRange] = useState<typeof RANGE_OPTIONS[number]["key"]>("24h")
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (r: string) => {
    try {
      const d = await fetchStats(r)
      setStats(d)
      setError(null)
    } catch {
      setError("Failed to load stats")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(range); const i = setInterval(() => load(range), 30000); return () => clearInterval(i) }, [load, range])

  const handleRangeChange = (r: typeof RANGE_OPTIONS[number]["key"]) => {
    setRange(r)
    setLoading(true)
    load(r)
  }

  const rangeLabel = RANGE_OPTIONS.find(o => o.key === range)?.label ?? "24h"

  const cards = [
    { title: "Active Companies", value: stats?.active_companies ?? 0, icon: Building2, color: "hive" as const, subtitle: "Protected entities", href: "/companies" },
    { title: "Threat Events", value: stats?.threat_events_total ?? 0, icon: Activity, color: "red" as const, subtitle: `${stats?.threat_events_new_hour ?? 0} in last hour`, href: "/intelligence" },
    { title: "Active Sessions", value: stats?.active_sessions ?? 0, icon: Radio, color: "yellow" as const, subtitle: `${stats?.high_risk_sessions ?? 0} high risk`, href: "/attackers" },
    { title: "MITRE Coverage", value: `${stats?.mitre_coverage_pct ?? 0}%`, icon: ShieldAlert, color: "purple" as const, subtitle: `${stats?.techniques_identified ?? 0} techniques detected`, href: "/intelligence" },
  ]

  const timelineEmpty = stats?.threat_timeline?.every(t => t.threats === 0 && t.critical === 0) ?? true

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {loading ? (
          <div className="flex items-center justify-center py-32">
            <LoadingSpinner message="Loading dashboard..." />
          </div>
        ) : (<>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Dashboard</h1>
            <p className="text-sm text-gray-600 mt-1">Real-time threat intelligence overview</p>
          </div>
          <button onClick={() => load(range)} className="btn-ghost" title="Refresh">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {cards.map((c, i) => (
            <div key={c.title} className="animate-in-up" style={{ animationDelay: `${i * 80}ms` }}>
              <StatCard {...c} />
            </div>
          ))}
        </div>

        {/* Threat Timeline */}
        <div className="card">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-red-500/15 flex items-center justify-center">
                <TrendingUp className="w-4 h-4 text-red-400" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-white">Threat Timeline</h2>
                <p className="text-xs text-gray-600">{rangeLabel}</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex gap-1 bg-gray-900 rounded-lg p-0.5 border border-gray-800">
                {RANGE_OPTIONS.map(o => (
                  <button
                    key={o.key}
                    onClick={() => handleRangeChange(o.key)}
                    className={`px-3 py-1 text-xs rounded-md transition-colors ${
                      range === o.key
                        ? "bg-hive-600 text-white"
                        : "text-gray-500 hover:text-gray-300"
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
              <div className="flex gap-3 text-xs text-gray-600">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-hive-500" /> Threats
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-red-500" /> Critical
                </span>
              </div>
            </div>
          </div>
          <div className="h-64 relative">
            {timelineEmpty ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <p className="text-sm text-gray-600">No threats in this period</p>
              </div>
            ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stats?.threat_timeline ?? []}>
                <defs>
                  <linearGradient id="threatGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0c8ee2" stopOpacity={0.3}/><stop offset="100%" stopColor="#0c8ee2" stopOpacity={0}/></linearGradient>
                  <linearGradient id="criticalGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ef4444" stopOpacity={0.3}/><stop offset="100%" stopColor="#ef4444" stopOpacity={0}/></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="hour" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={{ stroke: "#1f2937" }} />
                <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={{ stroke: "#1f2937" }} />
                <Tooltip
                  contentStyle={{ background: "#111827", border: "1px solid #1f2937", borderRadius: 10, fontSize: 13 }}
                  labelStyle={{ color: "#9ca3af" }}
                />
                <Area type="monotone" dataKey="threats" stroke="#0c8ee2" strokeWidth={2} fill="url(#threatGrad)" />
                <Area type="monotone" dataKey="critical" stroke="#ef4444" strokeWidth={2} fill="url(#criticalGrad)" />
              </AreaChart>
            </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Quick Action Cards */}
        <div>
          <h3 className="section-title mb-4">Quick Actions</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { title: "Generate Company", desc: "Deploy a new honeypot organization", color: "from-hive-600/20 to-transparent", border: "border-hive-500/20", icon: Building2, href: "/companies" },
              { title: "View Threats", desc: "Analyze recent threat intelligence", color: "from-red-600/20 to-transparent", border: "border-red-500/20", icon: AlertTriangle, href: "/intelligence" },
              { title: "Monitor Sessions", desc: "Track active attack sessions", color: "from-yellow-600/20 to-transparent", border: "border-yellow-500/20", icon: Radio, href: "/attackers" },
            ].map((item, i) => (
              <a key={item.title} href={item.href} className="animate-in-up group relative overflow-hidden rounded-2xl bg-gray-900/60 backdrop-blur-xl border border-gray-800/50 p-5 hover:border-gray-700/50 transition-all duration-300 hover:shadow-lg" style={{ animationDelay: `${(i + 4) * 80}ms` }}>
                <div className={`absolute inset-0 bg-gradient-to-br ${item.color} opacity-0 group-hover:opacity-100 transition-opacity duration-500`} />
                <div className="relative flex items-start justify-between">
                  <div className="space-y-1.5">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center border ${item.border} bg-gray-900/50`}>
                      <item.icon className="w-4.5 h-4.5" />
                    </div>
                    <p className="text-sm font-semibold text-white mt-3">{item.title}</p>
                    <p className="text-xs text-gray-600">{item.desc}</p>
                  </div>
                </div>
              </a>
            ))}
          </div>
        </div>
        </>)}
      </main>
    </div>
  )
}
