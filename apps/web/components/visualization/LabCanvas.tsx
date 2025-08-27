'use client'

import { Canvas } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera, Environment, Stats } from '@react-three/drei'
import { EffectComposer, Bloom, SSAO } from '@react-three/postprocessing'
import { Suspense } from 'react'
import { Laboratory } from './Laboratory'
import { ElectrochemicalCell } from './ElectrochemicalCell'
import { VolumeField } from './VolumeField'
import { Instruments } from './Instruments'
import { LoadingScreen } from './LoadingScreen'

interface LabCanvasProps {
  runId?: string
  showStats?: boolean
  quality?: 'low' | 'medium' | 'high'
}

export function LabCanvas({ runId, showStats = false, quality = 'medium' }: LabCanvasProps) {
  const getPixelRatio = () => {
    switch (quality) {
      case 'low': return 0.5
      case 'medium': return 1
      case 'high': return window.devicePixelRatio
      default: return 1
    }
  }
  
  return (
    <div className="w-full h-full relative">
      <Canvas
        dpr={getPixelRatio()}
        shadows
        gl={{
          antialias: quality !== 'low',
          powerPreference: quality === 'high' ? 'high-performance' : 'default',
          alpha: false,
          stencil: false,
          depth: true,
        }}
      >
        <Suspense fallback={<LoadingScreen />}>
          {/* Camera */}
          <PerspectiveCamera
            makeDefault
            position={[5, 3, 5]}
            fov={45}
            near={0.1}
            far={100}
          />
          
          {/* Controls */}
          <OrbitControls
            enableDamping
            dampingFactor={0.05}
            minDistance={1}
            maxDistance={20}
            maxPolarAngle={Math.PI / 2.1}
            target={[0, 1, 0]}
          />
          
          {/* Lighting */}
          <ambientLight intensity={0.4} />
          <directionalLight
            position={[5, 5, 5]}
            intensity={1}
            castShadow
            shadow-mapSize={[2048, 2048]}
            shadow-camera-far={20}
            shadow-camera-left={-10}
            shadow-camera-right={10}
            shadow-camera-top={10}
            shadow-camera-bottom={-10}
          />
          
          {/* Environment */}
          <Environment preset="warehouse" background blur={0.5} />
          
          {/* Lab Components */}
          <Laboratory />
          <Instruments />
          
          {/* Active Experiment */}
          {runId && (
            <>
              <ElectrochemicalCell runId={runId} position={[0, 1.1, 0]} />
              <VolumeField runId={runId} />
            </>
          )}
          
          {/* Post-processing */}
          {quality !== 'low' && (
            <EffectComposer>
              <SSAO
                samples={quality === 'high' ? 31 : 15}
                radius={0.5}
                intensity={quality === 'high' ? 50 : 30}
                luminanceInfluence={0.1}
                color="black"
              />
              <Bloom
                intensity={0.5}
                luminanceThreshold={0.9}
                luminanceSmoothing={0.025}
              />
            </EffectComposer>
          )}
        </Suspense>
        
        {/* Performance stats */}
        {showStats && <Stats />}
      </Canvas>
    </div>
  )
}