import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getSessions } from '../api'

function formatDuration(start, end) {
  if (!end) return 'In progress'
  const ms = new Date(end) - new Date(start)
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
}

function formatDate(iso) {
  return new Date(iso).toLocaleString()
}

export default function SessionList() {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getSessions(30)
      .then(({ data }) => setSessions(data))
      .catch(() => setError('Could not load sessions'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="page"><p className="dim">Loading sessions…</p></div>
  if (error)   return <div className="page"><p style={{ color: 'var(--red)' }}>{error}</p></div>

  return (
    <div className="page">
      <h1 className="page-title">Drive Sessions</h1>

      {sessions.length === 0 && (
        <div className="card">
          <p className="dim">No sessions yet. Start the assistant and go for a drive.</p>
        </div>
      )}

      <div className="gap">
        {sessions.map(s => (
          <Link key={s.id} to={`/sessions/${s.id}`} style={{ textDecoration: 'none' }}>
            <div className="card" style={styles.row}>
              <div style={styles.left}>
                <div style={styles.date}>{formatDate(s.started_at)}</div>
                <div className="dim">{s.user_email}</div>
              </div>
              <div style={styles.stats}>
                <Stat label="Duration" value={formatDuration(s.started_at, s.ended_at)} />
                <Stat label="Requests" value={s.turn_count} />
                <div style={{
                  ...styles.statusBadge,
                  background: s.ended_at ? 'var(--surface2)' : '#1a3d2b',
                  color: s.ended_at ? 'var(--text-dim)' : 'var(--green)',
                }}>
                  {s.ended_at ? 'Completed' : 'Live'}
                </div>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 18, fontWeight: 600 }}>{value}</div>
      <div className="dim">{label}</div>
    </div>
  )
}

const styles = {
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    cursor: 'pointer',
    transition: 'border-color 0.15s',
  },
  left: { display: 'flex', flexDirection: 'column', gap: 4 },
  date: { fontSize: 15, fontWeight: 600 },
  stats: { display: 'flex', alignItems: 'center', gap: 32 },
  statusBadge: {
    padding: '3px 12px',
    borderRadius: 20,
    fontSize: 12,
    fontWeight: 600,
  },
}
