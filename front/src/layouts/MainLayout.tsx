import { useEffect, useState } from 'react'
import { Outlet, Navigate } from 'react-router-dom'
import Sidebar from '../components/layout/Sidebar'
import { useUserStore } from '../stores/useUserStore'
import { restoreSession } from '../api/client'

export default function MainLayout() {
  const isLogin = useUserStore((s) => s.isLogin)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [restoring, setRestoring] = useState(!isLogin)

  useEffect(() => {
    if (!restoring) return
    let mounted = true
    void restoreSession().finally(() => { if (mounted) setRestoring(false) })
    return () => { mounted = false }
  }, [restoring])

  if (restoring) return <p role="status" className="p-6">正在恢复登录状态…</p>

  if (!isLogin) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-bg)]">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
      />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
