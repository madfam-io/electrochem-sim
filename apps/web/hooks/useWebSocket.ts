/**
 * WebSocket Hook for Real-time Simulation Streaming
 *
 * Features:
 * - Exponential backoff reconnection (1s, 2s, 4s, 8s... up to 30s)
 * - Connection quality monitoring (Good, Lagging, Disconnected)
 * - Automatic token refresh support
 * - Frame buffering with memory management
 *
 * RFC-001: Real-time Simulation Streaming with Backpressure Control
 */

import { useState, useEffect, useRef, useCallback } from 'react'

export type ConnectionQuality = 'Good' | 'Lagging' | 'Disconnected'

export interface SimulationFrame {
  type: 'frame' | 'status' | 'log' | 'event'
  run_id?: string
  timestamp: string
  time?: number
  timestep?: number
  save_step?: number
  is_keyframe?: boolean
  final?: boolean
  data?: {
    current_density?: number
    voltage?: number
    concentration_surface?: number
    concentration_bulk?: number
    concentration?: number[]
    potential?: number[]
    x?: number[]
  }
  status?: string
  message?: string
  event?: string
  _latency_ms?: number
}

export interface WebSocketState {
  // Connection state
  connected: boolean
  connecting: boolean
  error: string | null
  connectionQuality: ConnectionQuality

  // Frame data
  frames: SimulationFrame[]
  latestFrame: SimulationFrame | null
  keyframesCount: number
  totalFrames: number

  // Performance metrics
  averageLatency: number
  framesDropped: number

  // Controls
  connect: () => void
  disconnect: () => void
  clearFrames: () => void
}

interface UseWebSocketOptions {
  runId: string
  token: string
  autoConnect?: boolean
  maxFramesBuffer?: number
  reconnect?: boolean
  maxReconnectDelay?: number
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8080'

/**
 * Custom hook for WebSocket connection to simulation streaming endpoint
 *
 * Connection Quality Thresholds:
 * - Good: Latency < 200ms
 * - Lagging: Latency 200-1000ms
 * - Disconnected: No connection
 *
 * Exponential Backoff Strategy:
 * - Attempt 1: 1s delay
 * - Attempt 2: 2s delay
 * - Attempt 3: 4s delay
 * - Attempt 4: 8s delay
 * - Attempt 5: 16s delay
 * - Attempt 6+: 30s delay (max)
 *
 * Example:
 * ```tsx
 * const { connected, frames, connectionQuality } = useWebSocket({
 *   runId: 'run_123',
 *   token: accessToken,
 *   autoConnect: true
 * })
 * ```
 */
export function useWebSocket({
  runId,
  token,
  autoConnect = true,
  maxFramesBuffer = 1000,
  reconnect = true,
  maxReconnectDelay = 30000 // 30 seconds
}: UseWebSocketOptions): WebSocketState {
  // WebSocket reference
  const wsRef = useRef<WebSocket | null>(null)

  // Reconnection state
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttempts = useRef(0)
  const shouldReconnect = useRef(reconnect)

  // Connection state
  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [connectionQuality, setConnectionQuality] = useState<ConnectionQuality>('Disconnected')

  // Frame state
  const [frames, setFrames] = useState<SimulationFrame[]>([])
  const [latestFrame, setLatestFrame] = useState<SimulationFrame | null>(null)
  const [keyframesCount, setKeyframesCount] = useState(0)
  const [totalFrames, setTotalFrames] = useState(0)

  // Performance metrics
  const [averageLatency, setAverageLatency] = useState(0)
  const [framesDropped, setFramesDropped] = useState(0)
  const latencySum = useRef(0)
  const latencyCount = useRef(0)

  /**
   * Calculate exponential backoff delay
   * Formula: min(2^attempt * 1000, maxReconnectDelay)
   */
  const getReconnectDelay = useCallback((attempt: number): number => {
    const delay = Math.min(Math.pow(2, attempt) * 1000, maxReconnectDelay)
    return delay
  }, [maxReconnectDelay])

  /**
   * Update connection quality based on latency
   */
  const updateConnectionQuality = useCallback((latency: number) => {
    if (latency < 200) {
      setConnectionQuality('Good')
    } else if (latency < 1000) {
      setConnectionQuality('Lagging')
    } else {
      setConnectionQuality('Lagging')
    }
  }, [])

  /**
   * Process incoming frame
   */
  const processFrame = useCallback((frame: SimulationFrame) => {
    setTotalFrames(prev => prev + 1)

    // Update keyframe count
    if (frame.is_keyframe) {
      setKeyframesCount(prev => prev + 1)
    }

    // Update latest frame
    setLatestFrame(frame)

    // Update latency metrics
    if (frame._latency_ms !== undefined) {
      latencySum.current += frame._latency_ms
      latencyCount.current += 1
      const avgLatency = latencySum.current / latencyCount.current
      setAverageLatency(avgLatency)
      updateConnectionQuality(avgLatency)
    }

    // Add to frames buffer (limit size to prevent memory overflow)
    setFrames(prev => {
      const newFrames = [...prev, frame]
      if (newFrames.length > maxFramesBuffer) {
        // Keep keyframes + recent frames
        const keyframes = newFrames.filter(f => f.is_keyframe)
        const recentFrames = newFrames.slice(-Math.floor(maxFramesBuffer / 2))
        const merged = [...new Set([...keyframes, ...recentFrames])]
        return merged.slice(-maxFramesBuffer)
      }
      return newFrames
    })
  }, [maxFramesBuffer, updateConnectionQuality])

  /**
   * Connect to WebSocket
   */
  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (wsRef.current && (wsRef.current.readyState === WebSocket.CONNECTING || wsRef.current.readyState === WebSocket.OPEN)) {
      console.log('[WebSocket] Already connected or connecting')
      return
    }

    setConnecting(true)
    setError(null)

    try {
      const wsUrl = `${WS_URL}/ws/runs/${runId}?token=${token}`
      console.log(`[WebSocket] Connecting to ${wsUrl.replace(token, '***')}`)

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('[WebSocket] Connected successfully')
        setConnected(true)
        setConnecting(false)
        setError(null)
        setConnectionQuality('Good')

        // Reset reconnection attempts on successful connection
        reconnectAttempts.current = 0
      }

      ws.onmessage = (event) => {
        try {
          const frame: SimulationFrame = JSON.parse(event.data)
          processFrame(frame)
        } catch (err) {
          console.error('[WebSocket] Failed to parse frame:', err)
        }
      }

      ws.onerror = (event) => {
        console.error('[WebSocket] Error:', event)
        setError('WebSocket connection error')
        setConnectionQuality('Disconnected')
      }

      ws.onclose = (event) => {
        console.log('[WebSocket] Closed:', event.code, event.reason)
        setConnected(false)
        setConnecting(false)
        setConnectionQuality('Disconnected')
        wsRef.current = null

        // Attempt reconnection if enabled
        if (shouldReconnect.current && reconnect) {
          const delay = getReconnectDelay(reconnectAttempts.current)
          console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current + 1})`)

          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttempts.current += 1
            connect()
          }, delay)
        }
      }
    } catch (err) {
      console.error('[WebSocket] Connection failed:', err)
      setConnecting(false)
      setError(err instanceof Error ? err.message : 'Connection failed')
      setConnectionQuality('Disconnected')
    }
  }, [runId, token, reconnect, getReconnectDelay, processFrame])

  /**
   * Disconnect from WebSocket
   */
  const disconnect = useCallback(() => {
    console.log('[WebSocket] Disconnecting...')
    shouldReconnect.current = false

    // Clear reconnection timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect')
      wsRef.current = null
    }

    setConnected(false)
    setConnecting(false)
    setConnectionQuality('Disconnected')
  }, [])

  /**
   * Clear frames buffer
   */
  const clearFrames = useCallback(() => {
    setFrames([])
    setLatestFrame(null)
    setKeyframesCount(0)
    setTotalFrames(0)
    latencySum.current = 0
    latencyCount.current = 0
    setAverageLatency(0)
  }, [])

  /**
   * Auto-connect on mount if enabled
   */
  useEffect(() => {
    if (autoConnect) {
      connect()
    }

    // Cleanup on unmount
    return () => {
      shouldReconnect.current = false
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmount')
      }
    }
  }, [autoConnect, connect])

  return {
    // Connection state
    connected,
    connecting,
    error,
    connectionQuality,

    // Frame data
    frames,
    latestFrame,
    keyframesCount,
    totalFrames,

    // Performance metrics
    averageLatency,
    framesDropped,

    // Controls
    connect,
    disconnect,
    clearFrames
  }
}
