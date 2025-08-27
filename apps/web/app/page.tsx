'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import Link from 'next/link'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080'

interface Run {
  id: string
  type: string
  status: string
  created_at: string
  progress?: {
    percentage: number
    timesteps: number
  }
}

interface CreateRunResponse {
  run_id: string
  status: string
  stream_url: string
}

export default function Home() {
  const queryClient = useQueryClient()
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  
  // Fetch runs
  const { data: runs, isLoading } = useQuery({
    queryKey: ['runs'],
    queryFn: async () => {
      const res = await axios.get<Run[]>(`${API_URL}/api/v1/runs`)
      return res.data
    },
    refetchInterval: 2000, // Poll every 2 seconds
  })
  
  // Create run mutation
  const createRun = useMutation({
    mutationFn: async () => {
      const res = await axios.post<CreateRunResponse>(`${API_URL}/api/v1/runs`, {
        type: 'simulation',
        engine: 'auto',
        tags: ['mvp', 'test']
      })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    }
  })
  
  // Mock data for chart
  const chartData = [
    { time: 0, current: 0 },
    { time: 1, current: -2.5 },
    { time: 2, current: -2.3 },
    { time: 3, current: -2.1 },
    { time: 4, current: -1.9 },
    { time: 5, current: -1.8 },
  ]
  
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold text-gray-900">
              Galvana Platform
            </h1>
            <div className="flex items-center gap-4">
              <Link
                href="/visualization"
                className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 transition-colors"
              >
                3D Laboratory →
              </Link>
              <span className="text-sm text-gray-500">MVP v0.1.0</span>
            </div>
          </div>
        </div>
      </header>
      
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Hero Section */}
        <div className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg p-8 mb-8 text-white">
          <h2 className="text-2xl font-bold mb-4">Welcome to Galvana</h2>
          <p className="mb-4">
            Experience the future of electrochemistry with our phygital platform. 
            Visualize experiments in stunning 3D, control real instruments, and accelerate your research.
          </p>
          <div className="flex gap-4">
            <Link
              href="/visualization"
              className="px-6 py-3 bg-white text-purple-600 rounded-lg font-semibold hover:bg-gray-100 transition-colors"
            >
              Launch 3D Laboratory
            </Link>
            <button
              onClick={() => createRun.mutate()}
              className="px-6 py-3 bg-purple-800 text-white rounded-lg font-semibold hover:bg-purple-900 transition-colors"
            >
              Start Simulation
            </button>
          </div>
        </div>
        
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          
          {/* Run Controls */}
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold">Simulation Runs</h2>
              <button
                onClick={() => createRun.mutate()}
                disabled={createRun.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {createRun.isPending ? 'Starting...' : 'Start New Run'}
              </button>
            </div>
            
            {/* Runs List */}
            <div className="space-y-3">
              {isLoading ? (
                <p className="text-gray-500">Loading runs...</p>
              ) : runs && runs.length > 0 ? (
                runs.map((run) => (
                  <div
                    key={run.id}
                    onClick={() => setSelectedRun(run.id)}
                    className={`p-4 border rounded-lg cursor-pointer transition ${
                      selectedRun === run.id
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium">{run.id}</p>
                        <p className="text-sm text-gray-500">
                          {new Date(run.created_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          run.status === 'completed' ? 'bg-green-100 text-green-800' :
                          run.status === 'running' ? 'bg-blue-100 text-blue-800' :
                          run.status === 'failed' ? 'bg-red-100 text-red-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {run.status}
                        </span>
                        {run.progress && (
                          <p className="text-sm text-gray-500 mt-1">
                            {run.progress.percentage}%
                          </p>
                        )}
                      </div>
                    </div>
                    {selectedRun === run.id && (
                      <div className="mt-3 pt-3 border-t">
                        <Link
                          href={`/visualization?runId=${run.id}`}
                          className="text-sm text-purple-600 hover:text-purple-800"
                        >
                          View in 3D Laboratory →
                        </Link>
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-gray-500">No runs yet. Start a new simulation!</p>
              )}
            </div>
          </div>
          
          {/* Visualization */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-6">Current vs Time</h2>
            
            {selectedRun ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="time" 
                    label={{ value: 'Time (s)', position: 'insideBottom', offset: -5 }}
                  />
                  <YAxis 
                    label={{ value: 'Current (A/m²)', angle: -90, position: 'insideLeft' }}
                  />
                  <Tooltip />
                  <Legend />
                  <Line 
                    type="monotone" 
                    dataKey="current" 
                    stroke="#2563eb" 
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-gray-500">
                Select a run to view results
              </div>
            )}
          </div>
          
        </div>
        
        {/* Features Grid */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white rounded-lg shadow p-6">
            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold mb-2">Real-time Analytics</h3>
            <p className="text-gray-600">Monitor current density, concentration fields, and deposition in real-time.</p>
          </div>
          
          <div className="bg-white rounded-lg shadow p-6">
            <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold mb-2">3D Visualization</h3>
            <p className="text-gray-600">Immersive laboratory environment with interactive instruments and experiments.</p>
          </div>
          
          <div className="bg-white rounded-lg shadow p-6">
            <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold mb-2">Digital Twin</h3>
            <p className="text-gray-600">Connect real instruments for hardware-in-the-loop experiments.</p>
          </div>
        </div>
        
        {/* Scenario Configuration */}
        <div className="mt-8 bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Quick Scenario Setup</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Applied Voltage (V)
              </label>
              <input
                type="number"
                defaultValue="-0.8"
                step="0.1"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Duration (s)
              </label>
              <input
                type="number"
                defaultValue="120"
                step="10"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Mesh Elements
              </label>
              <input
                type="number"
                defaultValue="100"
                step="10"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          
          <div className="mt-4 flex justify-end">
            <button className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700">
              Save Scenario
            </button>
          </div>
        </div>
        
      </main>
    </div>
  )
}