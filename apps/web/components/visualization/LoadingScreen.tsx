'use client'

import { Html } from '@react-three/drei'

export function LoadingScreen() {
  return (
    <Html center>
      <div className="flex flex-col items-center justify-center">
        <div className="w-16 h-16 border-4 border-blue-400 border-t-transparent rounded-full animate-spin"></div>
        <p className="mt-4 text-white text-lg">Loading Laboratory...</p>
      </div>
    </Html>
  )
}