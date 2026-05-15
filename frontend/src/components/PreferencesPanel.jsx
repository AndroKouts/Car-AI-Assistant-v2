import { useState, useEffect } from 'react'
import { getPreferences, updatePreferences } from '../api'

const VOICES = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
const MODELS = ['openai:gpt-4.1-mini', 'openai:gpt-4o-mini', 'openai:gpt-4o']

export default function PreferencesPanel() {
  const [form, setForm] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  // Inputs for adding senders
  const [newPriority, setNewPriority] = useState('')
  const [newBlocked, setNewBlocked] = useState('')

  useEffect(() => {
    getPreferences()
      .then(({ data }) => setForm(data))
      .catch(() => setError('Could not load preferences'))
      .finally(() => setLoading(false))
  }, [])

  const set = (key, value) => setForm(f => ({ ...f, [key]: value }))

  const addSender = (type) => {
    const val = type === 'priority' ? newPriority.trim() : newBlocked.trim()
    if (!val) return
    const key = type === 'priority' ? 'priority_senders' : 'blocked_senders'
    if (!form[key].includes(val)) set(key, [...form[key], val])
    type === 'priority' ? setNewPriority('') : setNewBlocked('')
  }

  const removeSender = (type, addr) => {
    const key = type === 'priority' ? 'priority_senders' : 'blocked_senders'
    set(key, form[key].filter(s => s !== addr))
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const { data } = await updatePreferences(form)
      setForm(data)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch {
      setError('Failed to save preferences')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="page"><p className="dim">Loading preferences…</p></div>
  if (!form)   return <div className="page"><p style={{ color: 'var(--red)' }}>{error}</p></div>

  return (
    <div className="page">
      <h1 className="page-title">Preferences</h1>

      <div style={styles.grid}>

        {/* ── Email ── */}
        <Section title="📧 Email">
          <Field label="Microsoft account email">
            <input
              value={form.microsoft_email}
              onChange={e => set('microsoft_email', e.target.value)}
              placeholder="you@outlook.com"
            />
          </Field>

          <Field label="Priority senders" hint="These will be flagged as important">
            <TagInput
              items={form.priority_senders}
              value={newPriority}
              onChange={setNewPriority}
              onAdd={() => addSender('priority')}
              onRemove={addr => removeSender('priority', addr)}
              placeholder="email@example.com"
            />
          </Field>

          <Field label="Blocked senders" hint="Emails from these will be ignored">
            <TagInput
              items={form.blocked_senders}
              value={newBlocked}
              onChange={setNewBlocked}
              onAdd={() => addSender('blocked')}
              onRemove={addr => removeSender('blocked', addr)}
              placeholder="spam@example.com"
            />
          </Field>
        </Section>

        {/* ── Spotify ── */}
        <Section title="🎵 Spotify">
          <Field label="Default volume" hint={`${form.default_volume}%`}>
            <input
              type="range"
              min={0}
              max={100}
              value={form.default_volume}
              onChange={e => set('default_volume', Number(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--accent)' }}
            />
          </Field>

          <Field label="Startup playlist / mood" hint="Played automatically when a session starts">
            <input
              value={form.startup_playlist}
              onChange={e => set('startup_playlist', e.target.value)}
              placeholder="e.g. 90s rock, morning commute…"
            />
          </Field>

          <Field label="Preferred device" hint="Target device name from Spotify">
            <input
              value={form.preferred_device}
              onChange={e => set('preferred_device', e.target.value)}
              placeholder="e.g. My Car, iPhone…"
            />
          </Field>
        </Section>

        {/* ── Assistant ── */}
        <Section title="🤖 Assistant">
          <Field label="Voice">
            <select value={form.assistant_voice} onChange={e => set('assistant_voice', e.target.value)}>
              {VOICES.map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </Field>

          <Field label="Sub-agent model">
            <select value={form.sub_agent_model} onChange={e => set('sub_agent_model', e.target.value)}>
              {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </Field>

          <Field label="Driving mode" hint="Keeps responses concise and safe for driving">
            <label style={styles.toggle}>
              <input
                type="checkbox"
                checked={form.driving_mode}
                onChange={e => set('driving_mode', e.target.checked)}
                style={{ accentColor: 'var(--accent)', width: 16, height: 16 }}
              />
              <span>{form.driving_mode ? 'Enabled' : 'Disabled'}</span>
            </label>
          </Field>
        </Section>
      </div>

      {/* Save bar */}
      <div style={styles.saveBar}>
        {error && <span style={{ color: 'var(--red)', fontSize: 13 }}>{error}</span>}
        {saved && <span style={{ color: 'var(--green)', fontSize: 13 }}>✓ Saved</span>}
        <button className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save preferences'}
        </button>
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h2 style={{ fontSize: 16, fontWeight: 700 }}>{title}</h2>
      {children}
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <label style={{ fontSize: 13, fontWeight: 500 }}>{label}</label>
        {hint && <span className="dim">{hint}</span>}
      </div>
      {children}
    </div>
  )
}

function TagInput({ items, value, onChange, onAdd, onRemove, placeholder }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          onKeyDown={e => e.key === 'Enter' && onAdd()}
        />
        <button className="btn-ghost" onClick={onAdd} style={{ whiteSpace: 'nowrap', width: 'auto' }}>
          Add
        </button>
      </div>
      {items.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {items.map(addr => (
            <span key={addr} style={styles.tag}>
              {addr}
              <button onClick={() => onRemove(addr)} style={styles.tagRemove}>×</button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

const styles = {
  grid: { display: 'flex', flexDirection: 'column', gap: 16 },
  saveBar: {
    marginTop: 24,
    display: 'flex',
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: 16,
  },
  toggle: { display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 14 },
  tag: {
    background: 'var(--surface2)',
    border: '1px solid var(--border)',
    borderRadius: 20,
    padding: '3px 10px',
    fontSize: 12,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  tagRemove: {
    background: 'none',
    border: 'none',
    color: 'var(--text-dim)',
    padding: 0,
    fontSize: 14,
    lineHeight: 1,
    cursor: 'pointer',
    borderRadius: 0,
  },
}
