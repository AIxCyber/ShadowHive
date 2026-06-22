"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { Building2, Skull, Activity, Hexagon, LayoutDashboard, ScrollText, ArrowLeft, User as UserIcon, LogOut, Shield } from "lucide-react"
import { useAuth } from "@/lib/auth-context"

const links = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/attackers", label: "Attackers", icon: Skull },
  { href: "/intelligence", label: "Intel", icon: Activity },
  { href: "/logs", label: "Logs", icon: ScrollText },
]

export default function Navbar() {
  const pathname = usePathname()
  const router = useRouter()
  const isHome = pathname === "/"
  const { user, logout, isAdmin } = useAuth()

  const handleLogout = () => {
    logout()
    router.push("/login")
  }

  return (
    <header className="sticky top-0 z-50 border-b border-gray-800/60 bg-gray-950/70 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {!isHome && (
            <button onClick={() => router.back()} className="flex items-center justify-center w-8 h-8 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-gray-800/40 transition-all duration-200" title="Go back">
              <ArrowLeft className="w-4 h-4" />
            </button>
          )}
          <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-hive-400 to-hive-700 flex items-center justify-center shadow-lg shadow-hive-600/20 group-hover:shadow-hive-500/30 transition-shadow">
            <Hexagon className="w-4 h-4 text-white" />
          </div>
          <span className="text-lg font-bold text-white tracking-tight">Shadow<span className="text-gradient">Hive</span></span>
        </Link>
        </div>
        <nav className="flex items-center gap-1">
          {links.map(({ href, label, icon: Icon }) => {
            const active = pathname === href
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
                  active
                    ? "bg-hive-500/10 text-hive-300 border border-hive-500/20 shadow-sm"
                    : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/40"
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            )
          })}
          {user && user.id === "guest" ? (
            <div className="flex items-center gap-1 ml-2 pl-2 border-l border-gray-800/60">
              <Link href="/login"
                className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-medium text-gray-500 hover:text-gray-300 hover:bg-gray-800/40 transition-all duration-200"
              >
                <UserIcon className="w-4 h-4" />
                Sign In
              </Link>
            </div>
          ) : user && user.id && (
            <div className="flex items-center gap-1 ml-2 pl-2 border-l border-gray-800/60">
              {isAdmin && (
                <Link href="/admin/users"
                  className={`flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
                    pathname.startsWith("/admin")
                      ? "bg-hive-500/10 text-hive-300 border border-hive-500/20"
                      : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/40"
                  }`}
                  title="Admin Panel"
                >
                  <Shield className="w-4 h-4" />
                  Admin
                </Link>
              )}
              <div className="relative group">
                <button className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm text-gray-500 hover:text-gray-300 hover:bg-gray-800/40 transition-all">
                  <UserIcon className="w-4 h-4" />
                  <span className="max-w-[100px] truncate">{user.display_name}</span>
                </button>
                <div className="absolute right-0 top-full mt-1 w-48 bg-gray-900 border border-gray-800 rounded-xl shadow-xl z-10 hidden group-hover:block overflow-hidden">
                  <div className="px-3 py-2 border-b border-gray-800/60">
                    <p className="text-xs text-gray-400 truncate">{user.email}</p>
                    <p className="text-[10px] text-gray-600 capitalize">{user.role}</p>
                  </div>
                  <button onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 transition-colors">
                    <LogOut className="w-4 h-4" />
                    Sign Out
                  </button>
                </div>
              </div>
            </div>
          )}
        </nav>
      </div>
    </header>
  )
}
