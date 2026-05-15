import { Routes, Route, NavLink } from 'react-router-dom'
import { useState, useEffect } from 'react'
import SessionList from './components/SessionList'
import SessionDetail from './components/SessionDetail'
import PreferencesPanel from './components/PreferencesPanel'
import AssistantControls from './components/AssistantControls'
import { getStatus } from './api'

export default function App() {
  const [status, setStatus] = useState({ running: false, session_id: null })

  // Poll assistant status every 3 seconds
  useEffect(() => {
    const poll = async () => {
      try {
        const { data } = await getStatus()
        setStatus(data)
      } catch {}
    }
    poll()
    const interval = setInterval(poll, 3000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div>
      <header style={styles.header}>
        <div style={styles.headerInner}>
          <div style={styles.brand}>
            <span style={styles.brandIcon}>🚗</span>
            <span style={styles.brandName}>Car Assistant</span>
          </div>

          <nav style={styles.nav}>
            <NavLink to="/" end style={({ isActive }) => navStyle(isActive)}>
              Sessions
            </NavLink>
            <NavLink to="/preferences" style={({ isActive }) => navStyle(isActive)}>
              Preferences
            </NavLink>
          </nav>

          <AssistantControls status={status} onStatusChange={setStatus} />
        </div>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<SessionList />} />
          <Route path="/sessions/:id" element={<SessionDetail />} />
          <Route path="/preferences" element={<PreferencesPanel />} />
        </Routes>
      </main>
    </div>
  )
}

const navStyle = (isActive) => ({
  color: isActive ? 'var(--accent)' : 'var(--text-dim)',
  fontWeight: isActive ? 600 : 400,
  fontSize: 14,
  padding: '4px 0',
  borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent',
  transition: 'all 0.15s',
})

const styles = {
  header: {
    background: 'var(--surface)',
    borderBottom: '1px solid var(--border)',
    position: 'sticky',
    top: 0,
    zIndex: 100,
  },
  headerInner: {
    maxWidth: 1000,
    margin: '0 auto',
    padding: '0 24px',
    height: 60,
    display: 'flex',
    alignItems: 'center',
    gap: 32,
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginRight: 8,
  },
  brandIcon: { fontSize: 22 },
  brandName: { fontWeight: 700, fontSize: 16 },
  nav: {
    display: 'flex',
    gap: 24,
    flex: 1,
  },
}
