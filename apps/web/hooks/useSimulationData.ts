import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

interface SimulationFrame {
  time: number
  timestep: number
  current_density: number
  concentration: number[]
  potential: number[]
  deposition_thickness?: number
}

interface UseSimulationDataReturn {
  data: SimulationFrame | null
  isStreaming: boolean
  isLoading: boolean
  error: Error | null
  history: SimulationFrame[]
}

export function useSimulationData(runId: string): UseSimulationDataReturn {
  const [currentFrame, setCurrentFrame] = useState<SimulationFrame | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [history, setHistory] = useState<SimulationFrame[]>([])
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()
  
  // Fetch initial run data
  const { data: runData, isLoading, error } = useQuery({
    queryKey: ['run', runId],
    queryFn: async () => {
      const res = await axios.get(`${API_URL}/api/v1/runs/${runId}`)
      return res.data
    },
    enabled: !!runId,
  })
  
  // Connect to SSE stream for real-time updates
  useEffect(() => {
    if (!runId) return
    
    const connectToStream = () => {
      // Clean up existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
      
      const eventSource = new EventSource(`${API_URL}/api/v1/runs/${runId}/stream`)
      eventSourceRef.current = eventSource
      
      eventSource.onopen = () => {
        console.log('Connected to simulation stream')
        setIsStreaming(true)
      }
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          if (data.type === 'frame') {
            const frame: SimulationFrame = {
              time: data.time || 0,
              timestep: data.timestep || 0,
              current_density: data.current_density || 0,
              concentration: data.concentration || [],
              potential: data.potential || [],
              deposition_thickness: data.deposition_thickness,
            }
            
            setCurrentFrame(frame)
            setHistory(prev => [...prev.slice(-99), frame]) // Keep last 100 frames
          } else if (data.type === 'status') {
            console.log('Run status:', data.status)
            if (data.status === 'completed' || data.status === 'failed') {
              setIsStreaming(false)
            }
          }
        } catch (err) {
          console.error('Error parsing stream data:', err)
        }
      }
      
      eventSource.onerror = (error) => {
        console.error('Stream error:', error)
        setIsStreaming(false)
        eventSource.close()
        
        // Attempt to reconnect after 5 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log('Attempting to reconnect...')
          connectToStream()
        }, 5000)
      }
    }
    
    // For demo purposes, simulate data if no real stream is available
    const simulateData = () => {
      let timestep = 0
      const interval = setInterval(() => {
        const time = timestep * 0.1
        const frame: SimulationFrame = {
          time,
          timestep,
          current_density: -2.5 * Math.exp(-time / 10) * (1 + 0.1 * Math.sin(time)),
          concentration: Array.from({ length: 100 }, (_, i) => 
            100 * Math.exp(-i / 50) * (1 - time / 100)
          ),
          potential: Array.from({ length: 100 }, (_, i) => 
            -0.8 * (1 - i / 100)
          ),
          deposition_thickness: time * 0.0001,
        }
        
        setCurrentFrame(frame)
        setHistory(prev => [...prev.slice(-99), frame])
        timestep++
        
        if (timestep > 600) { // Stop after 60 seconds simulation time
          clearInterval(interval)
          setIsStreaming(false)
        }
      }, 100) // Update every 100ms
      
      setIsStreaming(true)
      
      return () => clearInterval(interval)
    }
    
    // Try to connect to real stream, fall back to simulation
    fetch(`${API_URL}/api/v1/runs/${runId}/stream`, { method: 'HEAD' })
      .then(() => connectToStream())
      .catch(() => {
        console.log('Stream not available, using simulated data')
        return simulateData()
      })
    
    // Cleanup
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [runId])
  
  return {
    data: currentFrame,
    isStreaming,
    isLoading,
    error: error as Error | null,
    history,
  }
}

// Hook for batch fetching volume data
export function useVolumeData(runId: string, timestep?: number) {
  return useQuery({
    queryKey: ['volume', runId, timestep],
    queryFn: async () => {
      const params = timestep !== undefined ? `?timestep=${timestep}` : ''
      const res = await axios.get(
        `${API_URL}/api/v1/visualization/volumes/${runId}${params}`,
        { responseType: 'arraybuffer' }
      )
      
      // Parse binary volume data
      const buffer = res.data as ArrayBuffer
      const floatArray = new Float32Array(buffer)
      
      // First 3 values are dimensions
      const dimensions = {
        x: floatArray[0],
        y: floatArray[1],
        z: floatArray[2],
      }
      
      // Rest is volume data
      const volumeData = floatArray.slice(3)
      
      return { dimensions, data: volumeData }
    },
    enabled: !!runId,
    staleTime: 60000, // Cache for 1 minute
  })
}