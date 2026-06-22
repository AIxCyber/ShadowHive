export default function LoadingSpinner({ className = "", message }: { className?: string; message?: string }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 ${className}`}>
      <div className="relative w-10 h-10">
        <div className="absolute inset-0 rounded-full border-2 border-hive-500/20" />
        <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-hive-400 animate-spin" />
      </div>
      {message && <p className="text-sm text-gray-500 animate-pulse">{message}</p>}
    </div>
  )
}
