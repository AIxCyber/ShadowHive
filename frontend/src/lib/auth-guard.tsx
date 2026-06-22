"use client"

import { useEffect, type ReactNode } from "react"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "./auth-context"
import LoadingSpinner from "@/components/LoadingSpinner"

const PUBLIC_PATHS = ["/login", "/forgot-password", "/reset-password"]

export function RequireAuth({ children, role }: { children: ReactNode; role?: string }) {
  const { user, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  const isPublic = PUBLIC_PATHS.some(p => pathname.startsWith(p))
  const isChangePassword = pathname === "/change-password"

  useEffect(() => {
    if (loading) return
    if (isPublic) return
    if (user && user.id === "guest") return
    if (!user || !user.id) {
      router.push("/login")
      return
    }
    if (user.must_change_password && !isChangePassword) {
      router.push("/change-password")
    }
  }, [user, loading, router, isPublic, isChangePassword])

  if (loading) {
    return <LoadingSpinner message="Checking authentication..." className="py-32" />
  }

  if (isPublic) {
    return <>{children}</>
  }

  if (user && user.id === "guest") {
    return <>{children}</>
  }

  if (!user || !user.id) {
    return null
  }

  if (user.must_change_password && !isChangePassword) {
    return null
  }

  if (role && user.role !== "admin" && user.role !== role) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="text-center">
          <p className="text-lg text-red-400 font-medium">Access Denied</p>
          <p className="text-sm text-gray-600 mt-1">You do not have permission to view this page.</p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
