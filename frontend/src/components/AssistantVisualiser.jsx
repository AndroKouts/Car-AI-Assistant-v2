import { useState, useEffect, useRef } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'

// ── State config ──────────────────────────────────────────────────────────────

const STATE_CONFIG = {
  idle: {
    label: 'Idle',
    color: '#3a3f5c',
    glow: 'rgba(108, 142, 245, 0.1)',
    pulse: 'pulse-slow',
    dot: '#8b90a8',
  },
  listening: {
    label: 'Listening…',
    color: '#4c7aaf',
    glow: 'rgba(76, 122, 175, 0.4)',
    pulse: 'pulse-medium',
    dot: '#6ab0ff',
  },
  processing: {
    label: 'Thinking…',
    color: '#7c5cbf',
    glow: 'rgba(124, 92, 191, 0.45)',
    pulse: 'pulse-fast',
    dot: '#b48fff',
  },
  speaking: {
    label: 'Speaking…',
    color: '#4caf82',
    glow: 'rgba(76, 175, 130, 0.45)',
    pulse: 'pulse-speaking',
    dot: '#4caf82',
  },
}

const MAX_TRANSCRIPT_ITEMS = 30

// ── Main component ────────────────────────────────────────────────────────────

export default function AssistantVisualiser({ sessionActive }) {
  const { lastEvent, connected } = useWebSocket()

  const [state, setState] = useState('idle')
  const [transcript, setTranscript] = useState([])   // [{role, text, id}]
  const [action, setAction] = useState(null)          // {intent, text}
  const [actionVisible, setActionVisible] = useState(false)
  const actionTimer = useRef(null)
  const transcriptEnd = useRef(null)
  const assistantBuffer = useRef('')  // accumulates streaming assistant text
  const assistantIdRef = useRef(null)

  // Process incoming WebSocket events
  useEffect(() => {
    if (!lastEvent) return

    switch (lastEvent.type) {

      case 'state':
        setState(lastEvent.state)
        break

      case 'transcript': {
        const { role, text, final } = lastEvent

        if (role === 'user' && final) {
          // User transcript — add as a complete item
          setTranscript(prev => [
            ...prev.slice(-MAX_TRANSCRIPT_ITEMS + 1),
            { role: 'user', text, id: Date.now() },
          ])
          // Reset assistant buffer for next turn
          assistantBuffer.current = ''
          assistantIdRef.current = null
        }

        if (role === 'assistant' && !final) {
          // Streaming delta — accumulate and update the last assistant item
          assistantBuffer.current += text
          const buffered = assistantBuffer.current

          if (assistantIdRef.current === null) {
            // First delta — create new item
            const id = Date.now()
            assistantIdRef.current = id
            setTranscript(prev => [
              ...prev.slice(-MAX_TRANSCRIPT_ITEMS + 1),
              { role: 'assistant', text: buffered, id },
            ])
          } else {
            // Subsequent delta — update existing item
            const id = assistantIdRef.current
            setTranscript(prev =>
              prev.map(item => item.id === id ? { ...item, text: buffered } : item)
            )
          }
        }

        if (role === 'assistant' && final) {
          // Final transcript — replace streamed item with clean final text
          const id = assistantIdRef.current
          if (id !== null) {
            setTranscript(prev =>
              prev.map(item => item.id === id ? { ...item, text } : item)
            )
          }
          assistantBuffer.current = ''
          assistantIdRef.current = null
        }
        break
      }

      case 'action': {
        // Show action card for 6 seconds then fade
        clearTimeout(actionTimer.current)
        setAction({ intent: lastEvent.intent, text: lastEvent.text })
        setActionVisible(true)
        actionTimer.current = setTimeout(() => setActionVisible(false), 6000)
        break
      }

      default:
        break
    }
  }, [lastEvent])

  // Auto-scroll transcript to bottom
  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcript])

  // Clear transcript when session stops
  useEffect(() => {
    if (!sessionActive) {
      setState('idle')
      setAction(null)
      setActionVisible(false)
    }
  }, [sessionActive])

  const cfg = STATE_CONFIG[state] || STATE_CONFIG.idle

  return (
    <div style={styles.container}>

      {/* ── Orb ── */}
      <div style={styles.orbSection}>
        <div
          className={`orb ${cfg.pulse}`}
          style={{
            '--orb-color': cfg.color,
            '--orb-glow': cfg.glow,
          }}
        >
          <div className="orb-inner" />
        </div>

        <div style={styles.stateRow}>
          <span style={{ ...styles.stateDot, background: cfg.dot }} />
          <span style={styles.stateLabel}>{sessionActive ? cfg.label : 'Session stopped'}</span>
          {!connected && (
            <span style={styles.wsWarning}>⚠ disconnected</span>
          )}
        </div>
      </div>

      {/* ── Action card ── */}
      <div style={{
        ...styles.actionCard,
        opacity: actionVisible ? 1 : 0,
        transform: actionVisible ? 'translateY(0)' : 'translateY(6px)',
      }}>
        {action && (
          <>
            <span style={styles.actionIcon}>
              {action.intent === 'spotify' ? '🎵' : action.intent === 'email' ? '📧' : '💬'}
            </span>
            <span style={styles.actionText}>{action.text}</span>
          </>
        )}
      </div>

      {/* ── Transcript feed ── */}
      <div style={styles.transcriptBox}>
        {transcript.length === 0 ? (
          <p style={styles.transcriptEmpty}>
            {sessionActive ? 'Waiting for speech…' : 'Start a session to see the conversation.'}
          </p>
        ) : (
          transcript.map(item => (
            <div
              key={item.id}
              style={{
                ...styles.transcriptItem,
                alignSelf: item.role === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              <div style={{
                ...styles.bubble,
                background: item.role === 'user' ? 'var(--accent)' : 'var(--surface2)',
                color: item.role === 'user' ? '#fff' : 'var(--text)',
                borderRadius: item.role === 'user'
                  ? '18px 18px 4px 18px'
                  : '18px 18px 18px 4px',
              }}>
                {item.text}
              </div>
              <div style={{
                ...styles.bubbleRole,
                textAlign: item.role === 'user' ? 'right' : 'left',
              }}>
                {item.role === 'user' ? 'You' : 'Assistant'}
              </div>
            </div>
          ))
        )}
        <div ref={transcriptEnd} />
      </div>
    </div>
  )
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 24,
    padding: '32px 0',
  },
  orbSection: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 16,
  },
  stateRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  stateDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    display: 'inline-block',
    transition: 'background 0.4s',
  },
  stateLabel: {
    fontSize: 14,
    fontWeight: 500,
    color: 'var(--text-dim)',
    transition: 'color 0.3s',
  },
  wsWarning: {
    fontSize: 12,
    color: 'var(--red)',
    marginLeft: 8,
  },
  actionCard: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: '12px 20px',
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    maxWidth: 480,
    width: '100%',
    transition: 'opacity 0.4s, transform 0.4s',
    minHeight: 48,
  },
  actionIcon: { fontSize: 18 },
  actionText: { fontSize: 14, color: 'var(--text)', lineHeight: 1.4 },
  transcriptBox: {
    width: '100%',
    maxWidth: 520,
    maxHeight: 380,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    padding: '4px 0',
    scrollbarWidth: 'thin',
    scrollbarColor: 'var(--border) transparent',
  },
  transcriptEmpty: {
    color: 'var(--text-dim)',
    fontSize: 13,
    textAlign: 'center',
    padding: '40px 0',
  },
  transcriptItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    maxWidth: '80%',
  },
  bubble: {
    padding: '10px 14px',
    fontSize: 14,
    lineHeight: 1.5,
    wordBreak: 'break-word',
  },
  bubbleRole: {
    fontSize: 11,
    color: 'var(--text-dim)',
    padding: '0 4px',
  },
}
