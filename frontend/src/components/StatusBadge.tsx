interface BadgeProps {
  severity?: string
  status?: string
  className?: string
}

const severityClasses: Record<string, string> = {
  critical: "badge-critical",
  high: "badge-high",
  medium: "badge-medium",
  low: "badge-low",
}

const statusClasses: Record<string, string> = {
  completed: "badge-success",
  running: "badge-info",
  paused: "badge-warning",
  pending: "badge",
  failed: "badge-critical",
  cancelled: "badge-low",
}

export default function StatusBadge({ severity, status, className = "" }: BadgeProps) {
  let cls = "badge"
  let label = severity || status || ""

  if (severity) cls = severityClasses[severity] || cls
  if (status) cls = statusClasses[status] || cls

  return <span className={`${cls} ${className}`}>{label}</span>
}
