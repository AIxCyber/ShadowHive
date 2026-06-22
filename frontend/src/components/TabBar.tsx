import type { LucideIcon } from "lucide-react"

interface Tab {
  key: string
  label: string
  icon: LucideIcon
  count?: number
}

export default function TabBar({ tabs, active, onChange }: { tabs: Tab[]; active: string; onChange: (key: string) => void }) {
  return (
    <div className="flex gap-1 border-b border-gray-800/60">
      {tabs.map(({ key, label, icon: Icon, count }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all duration-200 -mb-px ${
            active === key
              ? "text-hive-300 border-hive-500 bg-hive-500/5"
              : "text-gray-600 border-transparent hover:text-gray-400 hover:border-gray-700"
          }`}
        >
          <Icon className="w-4 h-4" />
          {label}
          {count !== undefined && (
            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
              active === key ? "bg-hive-500/15 text-hive-400" : "bg-gray-800/60 text-gray-600"
            }`}>
              {count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
