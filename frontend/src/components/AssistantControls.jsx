import { useState } from 'react'
import { startAssistant, stopAssistant } from '../api'

export default function AssistantControls({ status, onStatusChange }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleStart = async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await startAssistant()
      onStatusChange(data)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to start')
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await stopAssistant()
      onStatusChange(data)
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to stop')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.container}>
      {error && <span style={styles.error}>{error}</span>}

      <div style={styles.indicator}>
        <span style={{ ...styles.dot, background: status.running ? 'var(--green)' : 'var(--text-dim)' }} />
        <span style={styles.label}>{status.running ? 'Running' : 'Stopped'}</span>
      </div>

      {status.running ? (
        <button className="btn-red" onClick={handleStop} disabled={loading}>
          {loading ? 'Stopping…' : 'Stop Session'}
        </button>
      ) : (
        <button className="btn-green" onClick={handleStart} disabled={loading}>
          {loading ? 'Starting…' : 'Start Session'}
        </button>
      )}
    </div>
  )
}

const styles = {
  container: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    marginLeft: 'auto',
  },
  indicator: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    display: 'inline-block',
  },
  label: {
    fontSize: 13,
    color: 'var(--text-dim)',
  },
  error: {
    fontSize: 12,
    color: 'var(--red)',
  },
}
