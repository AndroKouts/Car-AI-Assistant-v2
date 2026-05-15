import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getSession, getSessionTurns, getSessionSpotify, getSessionEmail } from '../api'

function formatDate(iso) {
  return new Date(iso).toLocaleString()
}

export default function SessionDetail() {
  const { id } = useParams()
  const [session, setSession] = useState(null)
  const [turns, setTurns] = useState([])
  const [spotify, setSpotify] = useState([])
  const [email, setEmail] = useState([])
  const [tab, setTab] = useState('turns')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getSession(id),
      getSessionTurns(id),
      getSessionSpotify(id),
      getSessionEmail(id),
    ]).then(([s, t, sp, em]) => {
      setSession(s.data)
      setTurns(t.data)
      setSpotify(sp.data)
      setEmail(em.data)
    }).finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="page"><p className="dim">Loading…</p></div>
  if (!session) return <div className="page"><p className="dim">Session not found.</p></div>

  return (
    <div className="page">
      <Link to="/" style={{ fontSize: 13, color: 'var(--text-dim)' }}>← Back to sessions</Link>

      <div style={styles.header}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700 }}>{formatDate(session.started_at)}</h1>
          <p className="dim">{session.user_email} · {turns.length} requests</p>
        </div>
      </div>

      {/* Tabs */}
      <div style={styles.tabs}>
        {[
          { key: 'turns',   label: `All Requests (${turns.length})` },
          { key: 'spotify', label: `Spotify (${spotify.length})` },
          { key: 'email',   label: `Email (${email.length})` },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              ...styles.tab,
              color: tab === t.key ? 'var(--accent)' : 'var(--text-dim)',
              borderBottom: tab === t.key ? '2px solid var(--accent)' : '2px solid transparent',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Turns tab */}
      {tab === 'turns' && (
        <div className="gap">
          {turns.length === 0 && <p className="dim">No requests recorded.</p>}
          {turns.map(turn => (
            <div key={turn.id} className="card" style={styles.turn}>
              <div style={styles.turnTop}>
                <span className={`badge badge-${turn.intent || 'unknown'}`}>
                  {turn.intent || 'unknown'}
                </span>
                <span className="dim" style={{ fontSize: 12 }}>{formatDate(turn.timestamp)}</span>
                {turn.duration_ms && (
                  <span className="dim" style={{ fontSize: 12 }}>{turn.duration_ms}ms</span>
                )}
              </div>
              {turn.transcript && (
                <div style={styles.transcript}>"{turn.transcript}"</div>
              )}
              <div style={styles.instruction}>
                <span className="dim">Instruction: </span>{turn.instruction}
              </div>
              <div style={styles.result}>
                <span className="dim">Result: </span>{turn.result}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Spotify tab */}
      {tab === 'spotify' && (
        <div className="gap">
          {spotify.length === 0 && <p className="dim">No Spotify actions recorded.</p>}
          {spotify.map(a => (
            <div key={a.id} className="card" style={styles.action}>
              <div style={styles.actionLeft}>
                <span className="badge badge-spotify">{a.action}</span>
                {a.track_name && (
                  <span style={{ fontWeight: 600 }}>{a.track_name}</span>
                )}
                {a.artist && <span className="dim">by {a.artist}</span>}
                {!a.track_name && a.query && <span className="dim">{a.query}</span>}
              </div>
              <span className="dim" style={{ fontSize: 12 }}>{formatDate(a.timestamp)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Email tab */}
      {tab === 'email' && (
        <div className="gap">
          {email.length === 0 && <p className="dim">No email actions recorded.</p>}
          {email.map(a => (
            <div key={a.id} className="card" style={styles.action}>
              <div style={styles.actionLeft}>
                <span className="badge badge-email">{a.action}</span>
                {a.subject && <span style={{ fontWeight: 600 }}>{a.subject}</span>}
                {a.sender_email && <span className="dim">from {a.sender_email}</span>}
                {a.recipient && <span className="dim">to {a.recipient}</span>}
              </div>
              <span className="dim" style={{ fontSize: 12 }}>{formatDate(a.timestamp)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const styles = {
  header: { margin: '20px 0 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  tabs: { display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid var(--border)' },
  tab: { background: 'none', borderRadius: 0, padding: '10px 20px', fontSize: 14, color: 'var(--text-dim)' },
  turn: { display: 'flex', flexDirection: 'column', gap: 8 },
  turnTop: { display: 'flex', alignItems: 'center', gap: 10 },
  transcript: { fontStyle: 'italic', color: 'var(--text)', fontSize: 15, padding: '4px 0' },
  instruction: { fontSize: 13 },
  result: { fontSize: 13 },
  action: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  actionLeft: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
}
