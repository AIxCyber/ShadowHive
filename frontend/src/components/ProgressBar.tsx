export default function ProgressBar({ progress }: { progress: number }) {
  const pct = Math.min(progress, 100)
  return (
    <div className="w-full space-y-1.5">
      <div className="w-full bg-gray-800/60 rounded-full h-2 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-hive-600 via-hive-400 to-hive-300 transition-all duration-700 ease-out relative overflow-hidden"
          style={{ width: `${pct}%` }}
        >
          <div className="absolute inset-0 shimmer" />
        </div>
      </div>
      <p className="text-xs text-gray-600 text-right font-mono">{pct.toFixed(0)}%</p>
    </div>
  )
}
