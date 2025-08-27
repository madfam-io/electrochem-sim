'use client'

import { useState, Suspense } from 'react'
import dynamic from 'next/dynamic'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { useSimulationData } from '@/hooks/useSimulationData'

// Dynamically import 3D components to avoid SSR issues
const LabCanvas = dynamic(
  () => import('@/components/visualization/LabCanvas').then(mod => mod.LabCanvas),
  { 
    ssr: false,
    loading: () => <div className="w-full h-full flex items-center justify-center bg-gray-900">
      <div className="text-white">Loading 3D Environment...</div>
    </div>
  }
)

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

export default function VisualizationPage() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [quality, setQuality] = useState<'low' | 'medium' | 'high'>('medium')
  const [showStats, setShowStats] = useState(false)
  const [showControls, setShowControls] = useState(true)
  
  // Fetch available runs
  const { data: runs } = useQuery({
    queryKey: ['runs'],
    queryFn: async () => {
      const res = await axios.get(`${API_URL}/api/v1/runs`)
      return res.data
    },
    refetchInterval: 5000,
  })
  
  // Get data for selected run
  const { data: simulationData, isStreaming, history } = useSimulationData(selectedRunId || '')
  
  return (
    <div className="flex h-screen bg-gray-900">
      {/* Control Panel */}
      {showControls && (
        <div className="w-80 bg-gray-800 p-4 overflow-y-auto">
          <h2 className="text-xl font-bold text-white mb-4">Laboratory Control</h2>
          
          {/* Run Selection */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Active Experiment
            </label>
            <select
              value={selectedRunId || ''}
              onChange={(e) => setSelectedRunId(e.target.value || null)}
              className="w-full px-3 py-2 bg-gray-700 text-white rounded border border-gray-600 focus:border-blue-500 focus:outline-none"
            >
              <option value="">No active experiment</option>
              {runs?.map((run: any) => (
                <option key={run.id} value={run.id}>
                  {run.id} - {run.status}
                </option>
              ))}
            </select>
          </div>
          
          {/* Quality Settings */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Render Quality
            </label>
            <div className="flex gap-2">
              {(['low', 'medium', 'high'] as const).map((q) => (
                <button
                  key={q}
                  onClick={() => setQuality(q)}
                  className={`flex-1 px-3 py-2 rounded ${
                    quality === q
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {q.charAt(0).toUpperCase() + q.slice(1)}
                </button>
              ))}
            </div>
          </div>
          
          {/* Display Options */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Display Options
            </label>
            <div className="space-y-2">
              <label className="flex items-center text-gray-300">
                <input
                  type="checkbox"
                  checked={showStats}
                  onChange={(e) => setShowStats(e.target.checked)}
                  className="mr-2 rounded bg-gray-700 border-gray-600"
                />
                Show Performance Stats
              </label>
            </div>
          </div>
          
          {/* Current Data */}
          {selectedRunId && simulationData && (
            <div className="mb-6">
              <h3 className="text-sm font-medium text-gray-300 mb-2">
                Live Data {isStreaming && <span className="text-green-400">● Streaming</span>}
              </h3>
              <div className="bg-gray-700 rounded p-3 space-y-1 text-sm">
                <div className="flex justify-between text-gray-300">
                  <span>Time:</span>
                  <span className="text-white font-mono">
                    {simulationData.time.toFixed(2)} s
                  </span>
                </div>
                <div className="flex justify-between text-gray-300">
                  <span>Current Density:</span>
                  <span className="text-white font-mono">
                    {simulationData.current_density.toFixed(3)} A/m²
                  </span>
                </div>
                <div className="flex justify-between text-gray-300">
                  <span>Surface Conc.:</span>
                  <span className="text-white font-mono">
                    {(simulationData.concentration[0] || 0).toFixed(2)} mol/m³
                  </span>
                </div>
                {simulationData.deposition_thickness && (
                  <div className="flex justify-between text-gray-300">
                    <span>Deposition:</span>
                    <span className="text-white font-mono">
                      {(simulationData.deposition_thickness * 1000).toFixed(3)} μm
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
          
          {/* History Chart */}
          {history.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-medium text-gray-300 mb-2">
                Current History
              </h3>
              <div className="bg-gray-700 rounded p-3 h-32">
                <svg className="w-full h-full">
                  <polyline
                    fill="none"
                    stroke="#60a5fa"
                    strokeWidth="2"
                    points={history
                      .map((frame, i) => {
                        const x = (i / (history.length - 1)) * 100
                        const y = 50 - (frame.current_density / 5) * 40
                        return `${x},${y}`
                      })
                      .join(' ')}
                  />
                </svg>
              </div>
            </div>
          )}
          
          {/* Instructions */}
          <div className="text-xs text-gray-400">
            <p className="mb-2">
              <strong>Controls:</strong>
            </p>
            <ul className="space-y-1">
              <li>• Left Mouse: Rotate camera</li>
              <li>• Right Mouse: Pan camera</li>
              <li>• Scroll: Zoom in/out</li>
              <li>• Click instruments to interact</li>
            </ul>
          </div>
        </div>
      )}
      
      {/* 3D Visualization */}
      <div className="flex-1 relative">
        <LabCanvas
          runId={selectedRunId || undefined}
          quality={quality}
          showStats={showStats}
        />
        
        {/* Toggle Controls Button */}
        <button
          onClick={() => setShowControls(!showControls)}
          className="absolute top-4 left-4 px-3 py-2 bg-gray-800 text-white rounded hover:bg-gray-700 transition-colors"
        >
          {showControls ? '← Hide' : 'Show →'} Controls
        </button>
        
        {/* Quick Actions */}
        <div className="absolute bottom-4 right-4 flex gap-2">
          <button
            onClick={() => {
              // Reset camera position
              window.location.reload()
            }}
            className="px-3 py-2 bg-gray-800 text-white rounded hover:bg-gray-700"
          >
            Reset View
          </button>
          
          {selectedRunId && (
            <button
              onClick={() => setSelectedRunId(null)}
              className="px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700"
            >
              Stop Visualization
            </button>
          )}
        </div>
      </div>
    </div>
  )
}