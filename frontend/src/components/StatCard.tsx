import Link from "next/link"
import type { LucideIcon } from "lucide-react"

interface StatCardProps {
  title: string
  value: string | number
  icon: LucideIcon
  subtitle?: string
  color?: "hive" | "red" | "yellow" | "green" | "purple"
  href?: string
}

const colorMap: Record<string, { bg: string; icon: string; glow: string }> = {
  hive:   { bg: "from-hive-600/20 via-hive-700/10 to-transparent", icon: "bg-hive-500/20 text-hive-400 border-hive-500/20", glow: "shadow-hive-600/10" },
  red:    { bg: "from-red-600/20 via-red-700/10 to-transparent",   icon: "bg-red-500/20 text-red-400 border-red-500/20",   glow: "shadow-red-600/10" },
  yellow: { bg: "from-yellow-600/20 via-yellow-700/10 to-transparent", icon: "bg-yellow-500/20 text-yellow-400 border-yellow-500/20", glow: "shadow-yellow-600/10" },
  green:  { bg: "from-green-600/20 via-green-700/10 to-transparent", icon: "bg-green-500/20 text-green-400 border-green-500/20", glow: "shadow-green-600/10" },
  purple: { bg: "from-purple-600/20 via-purple-700/10 to-transparent", icon: "bg-purple-500/20 text-purple-400 border-purple-500/20", glow: "shadow-purple-600/10" },
}

export default function StatCard({ title, value, icon: Icon, subtitle, color = "hive", href }: StatCardProps) {
  const c = colorMap[color] || colorMap.hive

  const inner = (
    <div className={`group relative overflow-hidden rounded-2xl bg-gray-900/60 backdrop-blur-xl border border-gray-800/50 p-5 hover:border-gray-700/50 transition-all duration-300 hover:shadow-lg ${c.glow}`}>
      <div className={`absolute inset-0 bg-gradient-to-br ${c.bg} opacity-0 group-hover:opacity-100 transition-opacity duration-500`} />
      <div className="relative flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-xs font-medium text-gray-500 tracking-wide">{title}</p>
          <p className="text-2xl font-bold text-white tracking-tight">{value}</p>
          {subtitle && <p className="text-xs text-gray-600">{subtitle}</p>}
        </div>
        <div className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center border ${c.icon}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  )

  if (href) {
    return <Link href={href}>{inner}</Link>
  }

  return inner
}
