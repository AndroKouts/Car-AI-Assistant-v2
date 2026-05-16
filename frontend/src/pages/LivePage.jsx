import AssistantVisualiser from '../components/AssistantVisualiser'

export default function LivePage({ sessionActive }) {
  return (
    <div className="page">
      <h1 className="page-title">Live Session</h1>
      <AssistantVisualiser sessionActive={sessionActive} />
    </div>
  )
}
