import { useEffect, useRef, useState } from 'react'
import { Progress } from './api'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_URL = API.replace(/^http/, 'ws')

export function useLiveProgress(onUpdate: (p: Progress) => void) {
  const callbackRef = useRef(onUpdate)
  callbackRef.current = onUpdate
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let socket: WebSocket | null = null
    let timer: ReturnType<typeof setInterval> | null = null

    const poll = async () => {
      try {
        const r = await fetch(`${API}/api/runs/current`, { cache: 'no-store' })
        if (r.ok) {
          const p = await r.json()
          callbackRef.current(p)
        }
      } catch {}
    }

    poll()

    try {
      socket = new WebSocket(`${WS_URL}/ws`)
      socket.onopen = () => setConnected(true)
      socket.onclose = () => setConnected(false)
      socket.onerror = () => setConnected(false)
      socket.onmessage = e => {
        try {
          callbackRef.current(JSON.parse(e.data))
        } catch {}
      }
    } catch {
      setConnected(false)
    }

    timer = setInterval(poll, 2000)

    return () => {
      if (timer) clearInterval(timer)
      socket?.close()
    }
  }, [])

  return { connected }
}
