import type { Metadata } from "next"
import "./globals.css"
import { AuthProvider } from "@/lib/auth-context"
import { RequireAuth } from "@/lib/auth-guard"

export const metadata: Metadata = {
  title: "ShadowHive — Deception & Adversary Intelligence",
  description: "AI-Powered Adaptive Honeypot Personalities Platform",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-950 text-gray-100 antialiased">
        <AuthProvider>
          <RequireAuth>
            {children}
          </RequireAuth>
        </AuthProvider>
      </body>
    </html>
  )
}
