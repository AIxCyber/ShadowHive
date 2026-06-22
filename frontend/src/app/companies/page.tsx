"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import { useRouter } from "next/navigation"
import {
  Building2, Users, Mail, FileText, Server, Shield, Bug, Activity,
  Play, Square, RotateCw, GitBranch,
  ChevronDown, ChevronRight, Pause, Trash2, Settings, Save, FolderOpen, X, AlertTriangle,
  CheckCircle2, Loader,
} from "lucide-react"
import Navbar from "@/components/Navbar"
import TabBar from "@/components/TabBar"
import ProgressBar from "@/components/ProgressBar"
import StatusBadge from "@/components/StatusBadge"
import type { TaskInfo, CompanyProfile } from "@/lib/api"
import {
  generateCompany, cancelTask, pauseTask, resumeTask,
  deleteTask, fetchTask, fetchTasks,
  saveProfile, fetchProfiles, deleteProfile,
  deployCompany, undeployCompany, fetchDeployStatus,
} from "@/lib/api"
import type { DeployStatus } from "@/lib/api"
const INDUSTRIES = ["Technology", "Finance", "Healthcare", "Energy", "Retail", "Manufacturing", "Media"]
const SIZES = [
  { value: "small", label: "Small", desc: "10-50 employees" },
  { value: "medium", label: "Medium", desc: "50-200 employees" },
  { value: "large", label: "Large", desc: "200-1000 employees" },
]
const SECURITY_POSTURES = [
  { value: "default", label: "Default", desc: "Standard mid-market posture" },
  { value: "mature", label: "Mature", desc: "Strong security — minimal weaknesses" },
  { value: "startup", label: "Startup", desc: "Lean security — 1-2 weaknesses" },
  { value: "neglected", label: "Neglected", desc: "Poor security — 2-3 deliberate weaknesses" },
]

export default function CompaniesPage() {
  const router = useRouter()

  const [industry, setIndustry] = useState("Technology")
  const [size, setSize] = useState("small")
  const [generating, setGenerating] = useState(false)
  const [task, setTask] = useState<TaskInfo | null>(null)
  const [viewingTask, setViewingTask] = useState<TaskInfo | null>(null)
  const [tasks, setTasks] = useState<TaskInfo[]>([])
  const [activeTab, setActiveTab] = useState("overview")
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [cancelling, setCancelling] = useState(false)
  const [pausing, setPausing] = useState(false)
  const [deploying, setDeploying] = useState(false)
  const [deployStatus, setDeployStatus] = useState<DeployStatus | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  useEffect(() => {
    fetchDeployStatus().then(setDeployStatus).catch(() => {})
  }, [])

  const doDeploy = async (companyId: string) => {
    setDeploying(true)
    try {
      const result = await deployCompany(companyId)
      setDeployStatus({ active: true, ...result })
    } catch {}
    setDeploying(false)
  }

  const doUndeploy = async () => {
    setDeploying(true)
    try {
      await undeployCompany()
      setDeployStatus(null)
    } catch {}
    setDeploying(false)
  }

  // Advanced options
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [companyName, setCompanyName] = useState("")
  const [description, setDescription] = useState("")
  const [location, setLocation] = useState("")
  const [technologies, setTechnologies] = useState("")
  const [securityPosture, setSecurityPosture] = useState("default")
  const [enrich, setEnrich] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const taskIdRef = useRef<string | null>(null)
  const pollRef = useRef<NodeJS.Timeout | null>(null)
  const cancellingRef = useRef(false)
  const pausingRef = useRef(false)

  // Templates
  const [profiles, setProfiles] = useState<CompanyProfile[]>([])
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [templateName, setTemplateName] = useState("")
  const [showNameInput, setShowNameInput] = useState(false)

  const loadTasks = useCallback(async () => {
    try { setTasks(await fetchTasks()) } catch {}
  }, [])

  useEffect(() => { loadTasks() }, [loadTasks])

  // Recover generation/view after any page refresh
  useEffect(() => {
    let cancelled = false
    const tryRestore = async (id: string, isActive: boolean) => {
      // Show cached data immediately for visual continuity
      let cached: string | null = null
      try { cached = localStorage.getItem("task_cache_" + id) } catch {}
      if (cached && !cancelled) {
        try {
          const p = JSON.parse(cached)
          if (isActive) setTask(p)
          setViewingTask(p)
          if (p.status === "completed") {
            setActiveTab("overview")
          } else if (isActive && (p.status === "running" || p.status === "pending")) {
            setGenerating(true)
            taskIdRef.current = id
            const elapsedFrom = p.started_at || p.created_at
            if (elapsedFrom) {
              const v = Math.floor((Date.now() - new Date(elapsedFrom).getTime()) / 1000)
              setElapsed(v)
            } else {
              const savedElapsed = sessionStorage.getItem("elapsed_" + id)
              if (savedElapsed) setElapsed(parseInt(savedElapsed, 10))
            }
          } else if (isActive && p.status === "paused") {
            setGenerating(true)
            taskIdRef.current = id
          }
        } catch {}
      }
      // Fetch authoritative state from API
      try {
        const t = await fetchTask(id)
        if (cancelled) return true
        if (isActive) setTask(t)
        setViewingTask(t)
        localStorage.setItem("task_cache_" + id, JSON.stringify(t))
        if (isActive) {
          const elapsedFrom = t.started_at || t.created_at
          if (elapsedFrom) {
            const v = Math.floor((Date.now() - new Date(elapsedFrom).getTime()) / 1000)
            setElapsed(v)
          }
          if (t.status === "running" || t.status === "pending") {
            setGenerating(true)
            taskIdRef.current = id
            timerRef.current = setInterval(() => setElapsed(prev => prev + 1), 1000)
            pollTask(id)
          } else if (t.status === "paused") {
            setGenerating(true)
            taskIdRef.current = id
          }
        }
        if (t.status === "completed") {
          setActiveTab("overview")
        }
        return true
      } catch (err) {
        if (cancelled) return false
        // If API is unreachable but cache had a running task, start timer from cache's started_at/created_at
        if (cached && isActive && !cancelled) {
          try {
            if (taskIdRef.current !== id) return true
            const p = JSON.parse(cached)
            if (p.status === "running" || p.status === "pending") {
              const elapsedFrom = p.started_at || p.created_at
              if (elapsedFrom) {
              const v = Math.floor((Date.now() - new Date(elapsedFrom).getTime()) / 1000)
              setElapsed(v)
              } else {
                const savedElapsed = sessionStorage.getItem("elapsed_" + id)
                if (savedElapsed) { setElapsed(parseInt(savedElapsed, 10)) }
              }
          timerRef.current = setInterval(() => setElapsed(prev => prev + 1), 1000)
              pollTask(id)
            } else if (p.status === "paused") {
              setGenerating(true)
              taskIdRef.current = id
            }
          } catch {}
        }
        const is404 = err instanceof Error && (err.message.includes("404") || err.message.includes("Not Found"))
        if (is404) {
          const key = isActive ? "active_task_id" : "viewing_task_id"
          sessionStorage.removeItem(key)
          if (isActive) taskIdRef.current = null
        }
        return false
      }
    }
    ;(async () => {
      const storedId = sessionStorage.getItem("active_task_id")
      if (storedId && await tryRestore(storedId, true)) { return }
      const viewedId = sessionStorage.getItem("viewing_task_id")
      if (viewedId) { taskIdRef.current = viewedId; const ok = await tryRestore(viewedId, true) }
    })()
    return () => {
      cancelled = true
      if (timerRef.current) clearInterval(timerRef.current)
      if (pollRef.current) clearTimeout(pollRef.current)
    }
  }, [])

  const loadProfiles = useCallback(async () => {
    try { setProfiles(await fetchProfiles()) } catch {}
  }, [])

  useEffect(() => { loadProfiles() }, [loadProfiles])

  const getOverrides = () => {
    const o: Record<string, any> = {}
    if (companyName.trim()) o.company_name = companyName.trim()
    if (description.trim()) o.description = description.trim()
    if (location.trim()) o.location = location.trim()
    if (technologies.trim()) o.technologies = technologies.split(",").map(t => t.trim()).filter(Boolean)
    if (securityPosture !== "default") o.security_posture = securityPosture
    return Object.keys(o).length ? o : undefined
  }

  const startGeneration = async () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null }
    taskIdRef.current = null
    // Wipe any stale elapsed_ entries from previous sessions
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const key = sessionStorage.key(i)
      if (key && key.startsWith("elapsed_")) sessionStorage.removeItem(key)
    }
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i)
      if (key && key.startsWith("task_cache_")) localStorage.removeItem(key)
    }
    setGenerating(true)
    setTask(null)
    setViewingTask(null)
    setElapsed(0)
    timerRef.current = setInterval(() => setElapsed(prev => prev + 1), 1000)
    try {
      const overrides = getOverrides()
      const { task_id } = await generateCompany({ industry, size, overrides, enrich })
      taskIdRef.current = task_id
      sessionStorage.setItem("active_task_id", task_id)
      sessionStorage.setItem("viewing_task_id", task_id)
      pollTask(task_id)
    } catch { if (timerRef.current) clearInterval(timerRef.current); sessionStorage.removeItem("active_task_id"); sessionStorage.removeItem("viewing_task_id"); setGenerating(false); taskIdRef.current = null }
  }

  const pollTask = async (id: string) => {
    if (pollRef.current) clearTimeout(pollRef.current)
    const poll = async () => {
      try {
        const t = await fetchTask(id)
        if (taskIdRef.current !== id) { return }
        setTask(t)
        setViewingTask(t)
        sessionStorage.setItem("viewing_task_id", id)
        localStorage.setItem("task_cache_" + id, JSON.stringify(t))
        const elapsedFrom = t.started_at || t.created_at
        if (elapsedFrom) {
          const pollElapsed = Math.floor((Date.now() - new Date(elapsedFrom).getTime()) / 1000)
          sessionStorage.setItem("elapsed_" + id, String(pollElapsed))
        }
        if (t.status === "completed" || t.status === "failed" || t.status === "cancelled") {
          if (timerRef.current) clearInterval(timerRef.current)
          sessionStorage.removeItem("elapsed_" + id)
          setGenerating(false)
          taskIdRef.current = null
          loadTasks()
          return
        }
        pollRef.current = setTimeout(poll, 3000)
      } catch (err) {
        const is404 = err instanceof Error && (err.message.includes("404") || err.message.includes("Not Found"))
        if (is404) {
          if (taskIdRef.current !== id) return
          if (timerRef.current) clearInterval(timerRef.current)
          sessionStorage.removeItem("elapsed_" + id)
          setGenerating(false)
          taskIdRef.current = null
          loadTasks()
          return
        }
        pollRef.current = setTimeout(poll, 3000)
      }
    }
    poll()
  }

  // Recover polling when page becomes visible after screen-lock
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && taskIdRef.current && generating) {
        if (pollRef.current) clearTimeout(pollRef.current)
        pollRef.current = null
        pollTask(taskIdRef.current)
      }
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => document.removeEventListener("visibilitychange", onVisible)
  }, [generating])

  const doCancel = async () => {
    const tid = task?.task_id
    if (!tid || cancellingRef.current) return
    cancellingRef.current = true
    setCancelling(true)
    try { await cancelTask(tid) } catch {}
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    sessionStorage.removeItem("active_task_id")
    sessionStorage.removeItem("viewing_task_id")
    sessionStorage.removeItem("elapsed_" + tid)
    localStorage.removeItem("task_cache_" + tid)
    setGenerating(false)
    taskIdRef.current = null
    loadTasks()
    cancellingRef.current = false
    setCancelling(false)
  }

  const doPause = async () => {
    if (!task?.task_id || pausingRef.current) return
    pausingRef.current = true
    setPausing(true)
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
    if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null }
    try { await pauseTask(task.task_id) } catch {}
    pausingRef.current = false
    setPausing(false)
  }

  const doResume = async () => {
    if (!task?.task_id || pausingRef.current) return
    pausingRef.current = true
    setPausing(true)
    try {
      await resumeTask(task.task_id)
      timerRef.current = setInterval(() => setElapsed(prev => prev + 1), 1000)
      pollTask(task.task_id)
    } finally { pausingRef.current = false; setPausing(false) }
  }

  const doDelete = async (taskId: string) => {
    if (deletingId) return
    setDeletingId(taskId)
    try {
      await deleteTask(taskId)
    } catch (e) {
      // 404 means already gone — still clean up local state
    }
    localStorage.removeItem("task_cache_" + taskId)
    if (sessionStorage.getItem("active_task_id") === taskId) sessionStorage.removeItem("active_task_id")
    if (sessionStorage.getItem("viewing_task_id") === taskId) sessionStorage.removeItem("viewing_task_id")
    sessionStorage.removeItem("elapsed_" + taskId)
    await loadTasks()
    setDeletingId(null)
  }

  const doSaveTemplate = async () => {
    if (!templateName.trim()) return
    setSavingTemplate(true)
    try {
      const overrides = getOverrides()
      await saveProfile({
        name: templateName.trim(),
        industry,
        size,
        company_name: overrides?.company_name,
        description: overrides?.description,
        location: overrides?.location,
        technologies: overrides?.technologies,
        security_posture: overrides?.security_posture,
      })
      setTemplateName("")
      setShowNameInput(false)
      loadProfiles()
    } catch {} finally { setSavingTemplate(false) }
  }

  const doLoadProfile = (p: CompanyProfile) => {
    if (p.industry) setIndustry(p.industry)
    if (p.size) setSize(p.size)
    setCompanyName(p.company_name || "")
    setDescription(p.description || "")
    setLocation(p.location || "")
    setTechnologies(p.technologies?.join(", ") || "")
    setSecurityPosture(p.security_posture || "default")
    setShowAdvanced(true)
  }

  const doDeleteProfile = async (id: string) => {
    try {
      await deleteProfile(id)
      loadProfiles()
    } catch {}
  }

  const company = viewingTask?.status === "completed" ? viewingTask.result
    : task?.status === "completed" ? task.result : null

  const hasInfraEnrichment = company?.infrastructure || company?.security_config || company?.attack_artifacts
  const hasNetworkDepth = company?.network_depth?.active_alerts?.length > 0
  const hasDevops = company?.devops_pipeline?.ci_cd_pipelines?.length > 0

  const tabs = [
    { key: "overview", label: "Overview", icon: Building2 },
    { key: "employees", label: "Employees", icon: Users, count: company?.employees?.length },
    { key: "emails", label: "Emails", icon: Mail, count: company?.emails?.length },
    { key: "documents", label: "Documents", icon: FileText, count: company?.documents?.length },
    ...(hasInfraEnrichment ? [
      { key: "infrastructure", label: "Infrastructure", icon: Server, count: company.infrastructure?.servers?.length },
      { key: "security", label: "Security", icon: Shield },
      ...(hasNetworkDepth ? [{ key: "monitoring", label: "Monitoring", icon: Activity, count: company.network_depth?.active_alerts?.length }] : []),
      ...(hasDevops ? [{ key: "pipeline", label: "Pipeline", icon: GitBranch, count: company.devops_pipeline?.ci_cd_pipelines?.length }] : []),
      { key: "artifacts", label: "Artifacts", icon: Bug, count: company.attack_artifacts?.length },
    ] : []),
  ]

  const hasOverrides = !!getOverrides()

  return (
    <div className="min-h-screen bg-gray-950">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8 animate-in">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Company Generator</h1>
          <p className="text-sm text-gray-600 mt-1">Deploy synthetic organizations for threat deception</p>
        </div>

        {/* Active deployment banner */}
        {deployStatus?.active && (
          <div className="flex items-center justify-between p-4 rounded-xl bg-green-500/5 border border-green-500/20">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-400" />
              <div>
                <p className="text-sm font-medium text-green-300">Active Deployment</p>
                <p className="text-xs text-green-600">
                  {deployStatus.company_name} — {deployStatus.employee_count} employees
                  {deployStatus.deployed_at && ` — deployed ${new Date(deployStatus.deployed_at).toLocaleString()}`}
                </p>
              </div>
            </div>
            <button onClick={doUndeploy} disabled={deploying}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors disabled:opacity-50">
              {deploying ? <Loader className="w-3 h-3 animate-spin" /> : <Square className="w-3 h-3" />}
              {deploying ? "Undeploying..." : "Undeploy"}
            </button>
          </div>
        )}

        {/* Generation Controls */}
        <div className="card">
          <div className="flex flex-wrap gap-6 items-end">
            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600 uppercase tracking-wider">Industry</label>
              <div className="flex gap-1.5 flex-wrap">
                {INDUSTRIES.map(ind => (
                  <button key={ind} onClick={() => setIndustry(ind)}
                    className={`px-3.5 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
                      industry === ind
                        ? "bg-hive-500/15 text-hive-300 border border-hive-500/30 shadow-sm"
                        : "bg-gray-900/60 text-gray-500 border border-gray-800/50 hover:text-gray-300 hover:border-gray-700/50"
                    }`}
                  >{ind}</button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600 uppercase tracking-wider">Size</label>
              <div className="flex gap-1.5">
                {SIZES.map(s => (
                  <button key={s.value} onClick={() => setSize(s.value)}
                    className={`px-3.5 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
                      size === s.value
                        ? "bg-hive-500/15 text-hive-300 border border-hive-500/30 shadow-sm"
                        : "bg-gray-900/60 text-gray-500 border border-gray-800/50 hover:text-gray-300 hover:border-gray-700/50"
                    }`}
                  >{s.label}</button>
                ))}
              </div>
            </div>
            <div className="flex items-end gap-2">
              <button onClick={startGeneration} disabled={generating} className="btn-primary">
                {generating ? <RotateCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                {generating ? "Generating..." : "Generate"}
              </button>
              <button onClick={() => setShowAdvanced(!showAdvanced)}
                className={`p-2 rounded-xl border transition-all ${
                  showAdvanced || hasOverrides
                    ? "bg-hive-500/15 text-hive-300 border-hive-500/30"
                    : "bg-gray-900/60 text-gray-500 border-gray-800/50 hover:text-gray-300 hover:border-gray-700/50"
                }`}
                title="Advanced Options"
              >
                <Settings className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Advanced Options */}
          {showAdvanced && (
            <div className="mt-5 pt-5 border-t border-gray-800/50 space-y-4 animate-in">
              <div className="flex items-center justify-between mb-1">
                <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Settings className="w-4 h-4 text-hive-400" />
                  Advanced Options
                </h4>
                <div className="flex items-center gap-2">
                  {/* Templates dropdown */}
                  {profiles.length > 0 && (
                    <div className="relative" onMouseEnter={() => setShowTemplates(true)} onMouseLeave={() => setShowTemplates(false)}>
                      <button className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-gray-800 text-gray-400 border border-gray-700/50 hover:bg-gray-700 transition-colors">
                        <FolderOpen className="w-3.5 h-3.5" />
                        Load Template
                      </button>
                      {showTemplates && (
                        <div className="absolute right-0 top-full mt-1 w-56 bg-gray-900 border border-gray-800 rounded-xl shadow-xl z-10">
                          {profiles.map(p => (
                            <div key={p.id} className="flex items-center px-3 py-2 hover:bg-gray-800 first:rounded-t-xl last:rounded-b-xl">
                              <button onClick={() => { doLoadProfile(p); setShowTemplates(false) }} className="flex-1 text-left text-sm text-gray-300 truncate">
                                {p.name}
                              </button>
                              <button onClick={() => doDeleteProfile(p.id)} className="p-1 text-gray-600 hover:text-red-400">
                                <Trash2 className="w-3 h-3" />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {/* Save button */}
                  {!showNameInput ? (
                    <button onClick={() => setShowNameInput(true)}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-hive-500/10 text-hive-400 border border-hive-500/20 hover:bg-hive-500/20 transition-colors">
                      <Save className="w-3.5 h-3.5" />
                      Save as Template
                    </button>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <input
                        value={templateName}
                        onChange={e => setTemplateName(e.target.value)}
                        placeholder="Template name..."
                        className="w-36 px-2 py-1.5 rounded-lg text-xs bg-gray-800 border border-gray-700 text-gray-300 placeholder-gray-600 focus:outline-none focus:border-hive-500/50"
                        autoFocus
                        onKeyDown={e => { if (e.key === "Enter") doSaveTemplate(); if (e.key === "Escape") setShowNameInput(false) }}
                      />
                      <button onClick={doSaveTemplate} disabled={!templateName.trim() || savingTemplate}
                        className="px-2 py-1.5 rounded-lg text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 disabled:opacity-50">
                        {savingTemplate ? "..." : "Save"}
                      </button>
                      <button onClick={() => { setShowNameInput(false); setTemplateName("") }}
                        className="p-1.5 rounded-lg text-gray-600 hover:text-gray-400">
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs text-gray-600 font-medium">Company Name</label>
                  <input value={companyName} onChange={e => setCompanyName(e.target.value)}
                    placeholder="Leave blank for AI to generate"
                    className="w-full px-3 py-2 rounded-xl text-sm bg-gray-900/60 border border-gray-800/50 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-gray-600 font-medium">Location</label>
                  <input value={location} onChange={e => setLocation(e.target.value)}
                    placeholder="e.g. London, UK"
                    className="w-full px-3 py-2 rounded-xl text-sm bg-gray-900/60 border border-gray-800/50 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors"
                  />
                </div>
                <div className="sm:col-span-2 space-y-1.5">
                  <label className="text-xs text-gray-600 font-medium">Description</label>
                  <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2}
                    placeholder="Background context for the organization (optional)"
                    className="w-full px-3 py-2 rounded-xl text-sm bg-gray-900/60 border border-gray-800/50 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors resize-none"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-gray-600 font-medium">Technologies</label>
                  <input value={technologies} onChange={e => setTechnologies(e.target.value)}
                    placeholder="e.g. Python, AWS, Kubernetes, PostgreSQL"
                    className="w-full px-3 py-2 rounded-xl text-sm bg-gray-900/60 border border-gray-800/50 text-gray-300 placeholder-gray-700 focus:outline-none focus:border-hive-500/30 transition-colors"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-gray-600 font-medium flex items-center gap-1.5">
                    Security Posture
                    <AlertTriangle className="w-3 h-3 text-yellow-500/70" />
                  </label>
                  <div className="flex gap-1.5">
                    {SECURITY_POSTURES.map(sp => (
                      <button key={sp.value} onClick={() => setSecurityPosture(sp.value)}
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                          securityPosture === sp.value
                            ? "bg-yellow-500/15 text-yellow-400 border border-yellow-500/30"
                            : "bg-gray-900/60 text-gray-500 border border-gray-800/50 hover:text-gray-300 hover:border-gray-700/50"
                        }`}
                        title={sp.desc}
                      >{sp.label}</button>
                    ))}
                  </div>
                  <p className="text-[10px] text-gray-700 mt-0.5">
                    {SECURITY_POSTURES.find(s => s.value === securityPosture)?.desc}
                  </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-2">
                  <input
                    type="checkbox" id="enrich-toggle"
                    checked={enrich} onChange={e => setEnrich(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-700 bg-gray-900 text-hive-500 focus:ring-hive-500/30 focus:ring-offset-0"
                  />
                  <label htmlFor="enrich-toggle" className="text-xs text-gray-500 hover:text-gray-400 cursor-pointer select-none">
                    Infrastructure Enrichment <span className="text-gray-700">(servers, network, CI/CD, security config, attack artifacts)</span>
                  </label>
                </div>
                {enrich && (
                  <p className="text-[10px] text-amber-700 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" />
                    Adds ~3-6 minutes to generation time
                  </p>
                )}
              </div>
          )}

          {/* Progress */}
          {generating && (
            <div className="mt-6 p-4 rounded-xl bg-hive-500/5 border border-hive-500/15 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm" style={{ color: task?.status === "paused" ? "#facc15" : "#5eead4" }}>
                  {task?.status === "paused" ? (
                    <Pause className="w-4 h-4" />
                  ) : (
                    <RotateCw className="w-4 h-4 animate-spin" />
                  )}
                  <span>{task?.message || "Starting generation..."}</span>
                  {task?.status === "paused" && <span className="text-yellow-400 font-medium">(Paused)</span>}
                  <span className="text-gray-600">· {elapsed}s elapsed</span>
                </div>
                <div className="flex items-center gap-2">
                  {task?.status === "paused" ? (
                    <button onClick={doResume} disabled={pausing}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors disabled:opacity-50">
                      <Play className="w-3 h-3" />
                      {pausing ? "Resuming..." : "Resume"}
                    </button>
                  ) : (
                    <button onClick={doPause} disabled={pausing}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 hover:bg-yellow-500/20 transition-colors disabled:opacity-50">
                      <Pause className="w-3 h-3" />
                      {pausing ? "Pausing..." : "Pause"}
                    </button>
                  )}
                  <button onClick={doCancel} disabled={cancelling}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors disabled:opacity-50">
                    {cancelling ? (
                      <RotateCw className="w-3 h-3 animate-spin" />
                    ) : (
                      <Square className="w-3 h-3" />
                    )}
                    {cancelling ? "Stopping..." : "Stop"}
                  </button>
                </div>
              </div>
              <ProgressBar progress={task?.progress ?? 0} />
            </div>
          )}
        </div>

        {/* Generated Company Detail */}
        {company && (
          <div className="card animate-in-scale space-y-6">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-hive-400 to-hive-700 flex items-center justify-center shadow-lg shadow-hive-600/10">
                  <Building2 className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">{company.name}</h2>
                  <p className="text-sm text-gray-500">{company.industry} · {company.size} · {company.location}</p>
                </div>
              </div>
              <StatusBadge status="completed" />
            </div>
            <div className="flex items-center gap-2">
              {company.persisted_id && (
                deployStatus?.company_id === company.persisted_id ? (
                  <button onClick={doUndeploy} disabled={deploying}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors disabled:opacity-50">
                    {deploying ? <Loader className="w-3 h-3 animate-spin" /> : <Square className="w-3 h-3" />}
                    {deploying ? "Undeploying..." : "Undeploy"}
                  </button>
                ) : (
                  <button onClick={() => doDeploy(company.persisted_id)} disabled={deploying}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors disabled:opacity-50">
                    {deploying ? <Loader className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
                    {deploying ? "Deploying..." : "Deploy to Honeypot"}
                  </button>
                )
              )}
            </div>

            <p className="text-sm text-gray-400 leading-relaxed">{company.description}</p>

            <TabBar tabs={tabs} active={activeTab} onChange={setActiveTab} />

            {/* Tab Panels */}
            {activeTab === "overview" && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
                <div className="p-4 rounded-xl bg-gray-900/40 border border-gray-800/40 space-y-1">
                  <p className="text-gray-600 text-xs uppercase tracking-wider font-medium">Founded</p>
                  <p className="text-white font-medium">{company.founded_year}</p>
                </div>
                <div className="p-4 rounded-xl bg-gray-900/40 border border-gray-800/40 space-y-1">
                  <p className="text-gray-600 text-xs uppercase tracking-wider font-medium">Revenue</p>
                  <p className="text-white font-medium">{company.revenue}</p>
                </div>
                <div className="p-4 rounded-xl bg-gray-900/40 border border-gray-800/40 space-y-1">
                  <p className="text-gray-600 text-xs uppercase tracking-wider font-medium">Employees</p>
                  <p className="text-white font-medium">{company.employees?.length ?? 0}</p>
                </div>
              </div>
            )}

            {activeTab === "employees" && (
              <div className="space-y-2">
                {company.employees?.map((emp: any, i: number) => (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-xl bg-gray-900/30 border border-gray-800/30 hover:bg-gray-800/30 transition-colors">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-hive-500/30 to-hive-700/30 flex items-center justify-center text-sm font-bold text-hive-300">
                      {emp.name?.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">{emp.name}</p>
                      <p className="text-xs text-gray-600">{emp.title}</p>
                    </div>
                    <span className="text-xs text-gray-600">{emp.department}</span>
                  </div>
                ))}
              </div>
            )}

            {activeTab === "emails" && (
              <div className="space-y-2">
                {company.emails?.map((email: any, i: number) => (
                  <div key={i} className="rounded-xl bg-gray-900/30 border border-gray-800/30 overflow-hidden">
                    <button onClick={() => setExpandedId(expandedId === `email-${i}` ? null : `email-${i}`)}
                      className="w-full flex items-center justify-between p-4 hover:bg-gray-800/20 transition-colors text-left">
                      <div className="flex items-center gap-3 min-w-0">
                        <Mail className="w-4 h-4 shrink-0 text-gray-600" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-white truncate">{email.subject}</p>
                          <p className="text-xs text-gray-600 truncate">{email.from} → {email.to}</p>
                        </div>
                      </div>
                      {expandedId === `email-${i}` ? <ChevronDown className="w-4 h-4 text-gray-600 shrink-0" /> : <ChevronRight className="w-4 h-4 text-gray-600 shrink-0" />}
                    </button>
                    {expandedId === `email-${i}` && (
                      <div className="px-4 pb-4 pt-0 border-t border-gray-800/30">
                        <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-wrap">{email.body}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {activeTab === "documents" && (
              <div className="space-y-2">
                {company.documents?.map((doc: any, i: number) => (
                  <div key={i} className="rounded-xl bg-gray-900/30 border border-gray-800/30 overflow-hidden">
                    <button onClick={() => setExpandedId(expandedId === `doc-${i}` ? null : `doc-${i}`)}
                      className="w-full flex items-center justify-between p-4 hover:bg-gray-800/20 transition-colors text-left">
                      <div className="flex items-center gap-3 min-w-0">
                        <FileText className="w-4 h-4 shrink-0 text-gray-600" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-white truncate">{doc.title}</p>
                          <p className="text-xs text-gray-600">{doc.type} · {doc.risk_level}</p>
                        </div>
                      </div>
                      {expandedId === `doc-${i}` ? <ChevronDown className="w-4 h-4 text-gray-600 shrink-0" /> : <ChevronRight className="w-4 h-4 text-gray-600 shrink-0" />}
                    </button>
                    {expandedId === `doc-${i}` && (
                      <div className="px-4 pb-4 pt-0 border-t border-gray-800/30">
                        <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-wrap">{doc.content}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {activeTab === "infrastructure" && company.infrastructure && (
              <div className="space-y-6">
                {/* Servers */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Servers ({company.infrastructure.servers?.length || 0})</h4>
                  <div className="space-y-2">
                    {company.infrastructure.servers?.map((s: any, i: number) => (
                      <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-white">{s.hostname}</span>
                          <span className="text-xs text-gray-500">{s.ip}</span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-gray-500">
                          <span className="px-1.5 py-0.5 rounded bg-gray-800/50">{s.role}</span>
                          <span>{s.os}</span>
                        </div>
                        {s.services && <p className="text-xs text-gray-600 mt-1">{s.services.join(", ")}</p>}
                      </div>
                    ))}
                  </div>
                </div>
                {/* Network Devices */}
                {company.infrastructure.network_devices?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Network Devices</h4>
                    <div className="space-y-2">
                      {company.infrastructure.network_devices?.map((d: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30 flex items-center justify-between">
                          <div>
                            <span className="text-sm text-white">{d.hostname}</span>
                            <span className="text-xs text-gray-600 ml-2">{d.type}</span>
                          </div>
                          <span className="text-xs text-gray-500">{d.vendor} · {d.mgmt_ip}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Subnets */}
                {company.infrastructure.subnets?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Subnets</h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {company.infrastructure.subnets?.map((n: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                          <p className="text-sm text-white">{n.name}</p>
                          <p className="text-xs text-gray-500">{n.cidr} · VLAN {n.vlan_id}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Cloud */}
                {company.infrastructure.cloud_infra && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Cloud Infrastructure</h4>
                    <div className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                      <p className="text-sm text-white">{company.infrastructure.cloud_infra.provider}</p>
                      <p className="text-xs text-gray-500">Account: {company.infrastructure.cloud_infra.account_id}</p>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {company.infrastructure.cloud_infra.resources?.map((r: string, i: number) => (
                          <span key={i} className="px-2 py-0.5 rounded text-xs bg-hive-500/10 text-hive-400 border border-hive-500/20">{r}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {/* DNS Records */}
                {company.network_depth?.dns_records?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">DNS Records</h4>
                    <div className="space-y-1.5">
                      {company.network_depth.dns_records?.map((r: any, i: number) => (
                        <div key={i} className="flex items-center gap-3 p-2.5 rounded-xl bg-gray-900/30 border border-gray-800/30 text-sm">
                          <span className="font-mono text-xs text-hive-400 w-8 shrink-0">{r.type}</span>
                          <span className="font-mono text-xs text-white flex-1 truncate">{r.name}</span>
                          <span className="font-mono text-xs text-gray-500 flex-1 truncate text-right">{r.value}</span>
                          <span className="text-[10px] text-gray-700 w-10 text-right">TTL {r.ttl}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Load Balancers */}
                {company.network_depth?.load_balancers?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Load Balancers</h4>
                    <div className="space-y-2">
                      {company.network_depth.load_balancers?.map((lb: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-white">{lb.hostname}</span>
                            <span className="text-xs text-gray-500">{lb.ip}</span>
                          </div>
                          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800/50 text-gray-400">{lb.type}</span>
                          {lb.listeners?.length > 0 && (
                            <div className="mt-2 space-y-1">
                              {lb.listeners.map((l: any, j: number) => (
                                <div key={j} className="flex items-center gap-2 text-xs text-gray-500">
                                  <span className="font-mono">:{l.port}/{l.protocol}</span>
                                  <span>→ {l.backend}</span>
                                </div>
                              ))}
                            </div>
                          )}
                          {lb.upstream_pool?.length > 0 && (
                            <p className="text-xs text-gray-600 mt-1.5">Upstream: {lb.upstream_pool.join(", ")}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* SSL Certs */}
                {company.network_depth?.ssl_certs?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">SSL Certificates</h4>
                    <div className="space-y-2">
                      {company.network_depth.ssl_certs?.map((c: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-white">{c.hostname}</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              c.self_signed ? "bg-yellow-500/10 text-yellow-400" : "bg-green-500/10 text-green-400"
                            }`}>{c.self_signed ? "Self-Signed" : "Trusted"}</span>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-gray-500">
                            <span>Issuer: {c.issuer}</span>
                            {c.weak_cipher && <span className="text-red-400">Weak cipher</span>}
                          </div>
                          <p className="text-xs text-gray-600 mt-0.5">
                            {c.valid_from} → {c.valid_to}
                            {c.san?.length > 0 && ` · SAN: ${c.san.join(", ")}`}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "security" && company.security_config && (
              <div className="space-y-6">
                {/* Firewall Rules */}
                <div>
                  <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Firewall Rules ({company.security_config.firewall_rules?.length || 0})</h4>
                  <div className="space-y-2">
                    {company.security_config.firewall_rules?.map((r: any, i: number) => (
                      <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-white font-mono text-xs">{r.source} → {r.destination}</span>
                          <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                            r.action === "ALLOW" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"
                          }`}>{r.action}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
                          <span>Port {r.port}/{r.protocol}</span>
                          <span>· {r.purpose}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                {/* EDR */}
                <div className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                  <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">EDR</h4>
                  <p className="text-sm text-white">{company.security_config.edr_status || "None"}</p>
                  <p className="text-xs text-gray-500">Coverage: {company.security_config.edr_coverage || "None"}</p>
                </div>
                {/* Patch Gaps */}
                {company.security_config.patch_gaps?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Patch Gaps</h4>
                    <div className="space-y-2">
                      {company.security_config.patch_gaps?.map((p: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30 flex items-center justify-between">
                          <div>
                            <p className="text-sm text-white">{p.hostname}</p>
                            <p className="text-xs text-gray-500">{p.missing_patch}</p>
                          </div>
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            p.severity === "Critical" ? "bg-red-500/10 text-red-400" :
                            p.severity === "High" ? "bg-yellow-500/10 text-yellow-400" :
                            "bg-gray-700 text-gray-400"
                          }`}>{p.severity}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Service Accounts */}
                {company.security_config.service_accounts?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Service Accounts</h4>
                    <div className="space-y-2">
                      {company.security_config.service_accounts?.map((a: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-white font-mono">{a.username}</span>
                            <span className={`text-xs px-2 py-0.5 rounded ${
                              a.privilege_level?.includes("Admin") ? "bg-red-500/10 text-red-400" : "bg-gray-700 text-gray-400"
                            }`}>{a.privilege_level}</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">Used by: {a.used_by}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* VPN */}
                {company.security_config.vpn_config && (
                  <div className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">VPN</h4>
                    <p className="text-sm text-white">{company.security_config.vpn_config.provider} · {company.security_config.vpn_config.endpoint}</p>
                    <p className="text-xs text-gray-500">Auth: {company.security_config.vpn_config.auth_method}</p>
                  </div>
                )}
              </div>
            )}

            {activeTab === "monitoring" && company.network_depth?.active_alerts && (
              <div className="space-y-2">
                {company.network_depth.active_alerts?.map((a: any, i: number) => (
                  <div key={i} className="p-4 rounded-xl bg-gray-900/30 border border-gray-800/30">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Activity className={`w-4 h-4 ${
                          a.severity === "critical" ? "text-red-400" :
                          a.severity === "high" ? "text-orange-400" :
                          a.severity === "medium" ? "text-yellow-400" : "text-gray-500"
                        }`} />
                        <span className="text-sm font-medium text-white">{a.type}</span>
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        a.severity === "critical" ? "bg-red-500/10 text-red-400" :
                        a.severity === "high" ? "bg-orange-500/10 text-orange-400" :
                        a.severity === "medium" ? "bg-yellow-500/10 text-yellow-400" :
                        "bg-gray-700 text-gray-400"
                      }`}>{a.severity}</span>
                    </div>
                    <p className="text-sm text-gray-400 leading-relaxed">{a.message}</p>
                    <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-600">
                      <span>Source: {a.source}</span>
                      {a.affected_host && <span>· Host: {a.affected_host}</span>}
                      {a.timestamp && <span>· {a.timestamp}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === "pipeline" && company.devops_pipeline && (
              <div className="space-y-6">
                {/* CI/CD Pipelines */}
                {company.devops_pipeline.ci_cd_pipelines?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">CI/CD Pipelines</h4>
                    <div className="space-y-2">
                      {company.devops_pipeline.ci_cd_pipelines?.map((p: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium text-white">{p.name}</span>
                            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800/50 text-gray-400">{p.platform}</span>
                          </div>
                          {p.url && <p className="text-xs text-gray-600 font-mono mb-2">{p.url}</p>}
                          {p.misconfigurations?.length > 0 && (
                            <div className="space-y-1 mb-2">
                              {p.misconfigurations.map((m: string, j: number) => (
                                <p key={j} className="text-xs text-red-400 flex items-center gap-1">
                                  <AlertTriangle className="w-3 h-3 shrink-0" />
                                  {m}
                                </p>
                              ))}
                            </div>
                          )}
                          {p.jobs?.length > 0 && (
                            <div className="space-y-1">
                              <p className="text-[10px] text-gray-700 uppercase tracking-wider">Jobs</p>
                              {p.jobs.map((j: any, k: number) => (
                                <div key={k} className="flex items-center gap-2 text-xs text-gray-500 bg-gray-950/30 rounded-lg px-2 py-1">
                                  <span className="text-gray-400 font-medium">{j.name}</span>
                                  <span className="text-gray-700">({j.stage})</span>
                                  <span className="text-gray-600 flex-1 truncate">{j.script_summary}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Source Leaks */}
                {company.devops_pipeline.source_leaks?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-red-500/70 uppercase tracking-wider mb-3">Source Leaks</h4>
                    <div className="space-y-2">
                      {company.devops_pipeline.source_leaks?.map((l: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-red-900/30">
                          <div className="flex items-center justify-between mb-1">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-sm font-medium text-white truncate">{l.repo_name}</span>
                              <span className="text-xs text-gray-600 shrink-0">{l.platform}</span>
                            </div>
                            <span className={`text-xs px-2 py-0.5 rounded shrink-0 ${
                              l.severity === "critical" ? "bg-red-500/10 text-red-400" :
                              l.severity === "high" ? "bg-orange-500/10 text-orange-400" :
                              l.severity === "medium" ? "bg-yellow-500/10 text-yellow-400" :
                              "bg-gray-700 text-gray-400"
                            }`}>{l.severity}</span>
                          </div>
                          {l.url && <p className="text-xs text-gray-600 font-mono mb-1">{l.url}</p>}
                          <p className="text-xs text-gray-500 mb-1">Exposed: {l.exposure_date}</p>
                          {l.leaked_content && (
                            <div className="p-2 rounded-lg bg-gray-950/50 border border-gray-800/30">
                              <code className="text-xs text-yellow-400/80">{l.leaked_content}</code>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Container Registries */}
                {company.devops_pipeline.container_registries?.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Container Registries</h4>
                    <div className="space-y-2">
                      {company.devops_pipeline.container_registries?.map((r: any, i: number) => (
                        <div key={i} className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium text-white">{r.registry_url}</span>
                            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800/50 text-gray-400">{r.provider}</span>
                          </div>
                          {r.repositories?.length > 0 && (
                            <div className="space-y-1.5">
                              {r.repositories.map((repo: any, j: number) => (
                                <div key={j} className="flex items-center justify-between bg-gray-950/30 rounded-lg px-2.5 py-1.5">
                                  <div className="min-w-0">
                                    <span className="text-sm text-white font-mono">{repo.name}</span>
                                    <div className="flex flex-wrap gap-1 mt-0.5">
                                      {repo.tags?.map((t: string, k: number) => (
                                        <span key={k} className="text-[10px] px-1 py-0.5 rounded bg-gray-800 text-gray-500">{t}</span>
                                      ))}
                                    </div>
                                  </div>
                                  <div className="text-right shrink-0">
                                    <p className="text-xs text-gray-500">{repo.vulnerability_count ?? 0} vulns</p>
                                    {(repo.critical_vulns ?? 0) > 0 && (
                                      <p className="text-xs text-red-400">{repo.critical_vulns} critical</p>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Terraform State */}
                {company.devops_pipeline.terraform_state && (
                  <div>
                    <h4 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-3">Terraform State</h4>
                    <div className="p-3 rounded-xl bg-gray-900/30 border border-gray-800/30">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm text-white">{company.devops_pipeline.terraform_state.backend_type}</span>
                        <span className="text-xs text-gray-600 font-mono">{company.devops_pipeline.terraform_state.state_file_url}</span>
                      </div>
                      {company.devops_pipeline.terraform_state.resources?.length > 0 && (
                        <div className="mb-2">
                          <p className="text-[10px] text-gray-700 uppercase tracking-wider mb-1">Resources</p>
                          <div className="flex flex-wrap gap-1">
                            {company.devops_pipeline.terraform_state.resources.map((r: string, i: number) => (
                              <span key={i} className="px-2 py-0.5 rounded text-xs bg-hive-500/10 text-hive-400 border border-hive-500/20">{r}</span>
                            ))}
                          </div>
                        </div>
                      )}
                      {company.devops_pipeline.terraform_state.exposed_secrets?.length > 0 && (
                        <div>
                          <p className="text-[10px] text-red-500/70 uppercase tracking-wider mb-1">Exposed Secrets</p>
                          <div className="flex flex-wrap gap-1">
                            {company.devops_pipeline.terraform_state.exposed_secrets.map((s: string, i: number) => (
                              <span key={i} className="px-2 py-0.5 rounded text-xs bg-red-500/10 text-red-400 border border-red-500/20">{s}</span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "artifacts" && (
              <div className="space-y-2">
                {company.attack_artifacts?.map((a: any, i: number) => (
                  <div key={i} className="rounded-xl bg-gray-900/30 border border-gray-800/30 overflow-hidden">
                    <button onClick={() => setExpandedId(expandedId === `art-${i}` ? null : `art-${i}`)}
                      className="w-full flex items-center justify-between p-4 hover:bg-gray-800/20 transition-colors text-left">
                      <div className="flex items-center gap-3 min-w-0">
                        <Bug className="w-4 h-4 shrink-0 text-gray-600" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-white truncate">{a.name}</p>
                          <p className="text-xs text-gray-600">{a.type} · {a.location}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          a.severity === "critical" ? "bg-red-500/10 text-red-400" :
                          a.severity === "high" ? "bg-orange-500/10 text-orange-400" :
                          "bg-gray-700 text-gray-400"
                        }`}>{a.severity}</span>
                        {expandedId === `art-${i}` ? <ChevronDown className="w-4 h-4 text-gray-600" /> : <ChevronRight className="w-4 h-4 text-gray-600" />}
                      </div>
                    </button>
                    {expandedId === `art-${i}` && (
                      <div className="px-4 pb-4 pt-0 border-t border-gray-800/30 space-y-2">
                        <div className="p-2 rounded-lg bg-gray-950/50 border border-gray-800/30">
                          <code className="text-xs text-yellow-400/80">{a.content_excerpt}</code>
                        </div>
                        <p className="text-sm text-gray-400">{a.description}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Recent Tasks */}
        <div>
          <h3 className="section-title mb-4">Recent Generations</h3>
          {tasks.length === 0 ? (
            <div className="text-center py-12 text-gray-700">
              <Building2 className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No generations yet</p>
            </div>
          ) : (
            <div className="space-y-2">
              {tasks.slice(0, 5).map((t, i) => (
                <div key={t.task_id ?? i} className="flex items-center gap-2 group">
                  <button onClick={() => { setViewingTask(t); setActiveTab("overview"); sessionStorage.setItem("viewing_task_id", t.task_id) }} className="flex-1 flex items-center gap-4 p-3.5 rounded-xl bg-gray-900/30 border border-gray-800/30 hover:bg-gray-800/50 transition-colors text-left cursor-pointer min-w-0">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                      t.status === "completed" ? "bg-green-500/15 text-green-400" :
                      t.status === "failed" ? "bg-red-500/15 text-red-400" :
                      t.status === "paused" ? "bg-yellow-500/15 text-yellow-400" :
                      "bg-hive-500/15 text-hive-400"
                    }`}>
                      {t.status === "completed" ? <Building2 className="w-4 h-4" /> :
                       t.status === "running" ? <RotateCw className="w-4 h-4 animate-spin" /> :
                       t.status === "paused" ? <Pause className="w-4 h-4" /> :
                       <FileText className="w-4 h-4" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">{t.message || t.task_id}</p>
                      <p className="text-xs text-gray-600">{t.progress.toFixed(0)}% complete</p>
                    </div>
                    <StatusBadge status={t.status} />
                  </button>
                  <button onClick={() => doDelete(t.task_id)} disabled={deletingId === t.task_id}
                    className="p-2 rounded-lg text-gray-700 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all disabled:opacity-30 disabled:cursor-not-allowed">
                    {deletingId === t.task_id ? <Loader className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
