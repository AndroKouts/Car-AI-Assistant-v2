import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = 'ws://localhost:8000/ws/live'
const RECONNECT_DELAY_MS = 2000

/**
 * useWebSocket
 * 
 * Maintains a persistent WebSocket connection to the live endpoint.
 * Automatically reconnects if the connection drops.
 * 
 * Returns:
 *   lastEvent  — the most recent parsed JSON event from the server
 *   connected  — whether the WebSocket is currently open
 */
export function useWebSocket() {
  const [lastEvent, setLastEvent] = useState(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)
  const mountedRef = useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      setConnected(true)
    }

    ws.onmessage = (e) => {
      if (!mountedRef.current) return
      try {
        const event = JSON.parse(e.data)
        if (event.type !== 'ping') {
          setLastEvent(event)
        }
      } catch {}
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnected(false)
      // Reconnect after delay
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  return { lastEvent, connected }
}
