'use client'

import { useRef, useEffect, useState } from 'react'
import { Group, Mesh, BufferGeometry, Float32BufferAttribute } from 'three'
import { useFrame } from '@react-three/fiber'
import { Box, Cylinder, Sphere } from '@react-three/drei'
import { useSimulationData } from '@/hooks/useSimulationData'

interface ElectrochemicalCellProps {
  runId: string
  position: [number, number, number]
}

export function ElectrochemicalCell({ runId, position }: ElectrochemicalCellProps) {
  const groupRef = useRef<Group>(null)
  const electrolyteRef = useRef<Mesh>(null)
  const { data, isStreaming } = useSimulationData(runId)
  const [bubbles, setBubbles] = useState<Bubble[]>([])
  
  // Generate bubbles based on current
  useEffect(() => {
    if (data?.current_density) {
      const rate = Math.abs(data.current_density) * 10
      const newBubbles = Array.from({ length: Math.floor(rate) }, () => ({
        id: Math.random(),
        position: [
          (Math.random() - 0.5) * 0.15,
          0,
          (Math.random() - 0.5) * 0.15
        ] as [number, number, number],
        velocity: 0.01 + Math.random() * 0.02,
        size: 0.005 + Math.random() * 0.01
      }))
      setBubbles(prev => [...prev.slice(-50), ...newBubbles])
    }
  }, [data?.current_density])
  
  // Animate bubbles
  useFrame((state, delta) => {
    setBubbles(prev => prev
      .map(b => ({
        ...b,
        position: [b.position[0], b.position[1] + b.velocity, b.position[2]] as [number, number, number]
      }))
      .filter(b => b.position[1] < 0.3)
    )
    
    // Animate electrolyte color based on concentration
    if (electrolyteRef.current && data?.concentration) {
      const concentration = data.concentration[0] || 1
      const normalizedConc = concentration / 100
      electrolyteRef.current.material.color.setRGB(
        0.3 + normalizedConc * 0.2,
        0.5 + normalizedConc * 0.3,
        0.8 - normalizedConc * 0.3
      )
    }
  })
  
  return (
    <group ref={groupRef} position={position}>
      {/* Glass beaker */}
      <Cylinder
        args={[0.2, 0.18, 0.4, 32, 1, true]}
        position={[0, 0.2, 0]}
        castShadow
        receiveShadow
      >
        <meshPhysicalMaterial
          color="#ffffff"
          transparent
          opacity={0.2}
          roughness={0.1}
          metalness={0.1}
          thickness={0.01}
          transmission={0.9}
          ior={1.5}
        />
      </Cylinder>
      
      {/* Beaker bottom */}
      <Cylinder args={[0.18, 0.18, 0.02, 32]} position={[0, 0.01, 0]}>
        <meshPhysicalMaterial
          color="#ffffff"
          transparent
          opacity={0.3}
          roughness={0.1}
          metalness={0.1}
        />
      </Cylinder>
      
      {/* Electrolyte solution */}
      <Cylinder
        ref={electrolyteRef}
        args={[0.175, 0.175, 0.35, 32]}
        position={[0, 0.175, 0]}
      >
        <meshPhysicalMaterial
          color="#5588cc"
          transparent
          opacity={0.7}
          roughness={0.3}
          metalness={0.0}
          thickness={0.5}
          transmission={0.3}
        />
      </Cylinder>
      
      {/* Working electrode (cathode) */}
      <group position={[-0.1, 0.15, 0]}>
        <Box args={[0.01, 0.3, 0.05]} position={[0, 0.15, 0]} castShadow>
          <meshStandardMaterial color="#444444" roughness={0.3} metalness={0.9} />
        </Box>
        <Box args={[0.02, 0.02, 0.1]} position={[0, 0.35, 0]}>
          <meshStandardMaterial color="#ff0000" />
        </Box>
      </group>
      
      {/* Counter electrode (anode) */}
      <group position={[0.1, 0.15, 0]}>
        <Box args={[0.01, 0.3, 0.05]} position={[0, 0.15, 0]} castShadow>
          <meshStandardMaterial color="#666666" roughness={0.3} metalness={0.9} />
        </Box>
        <Box args={[0.02, 0.02, 0.1]} position={[0, 0.35, 0]}>
          <meshStandardMaterial color="#000000" />
        </Box>
      </group>
      
      {/* Reference electrode */}
      <group position={[0, 0.15, 0.15]}>
        <Cylinder args={[0.005, 0.005, 0.3]} position={[0, 0.15, 0]} rotation={[0, 0, Math.PI / 6]}>
          <meshStandardMaterial color="#ffffff" roughness={0.2} metalness={0.8} />
        </Cylinder>
        <Sphere args={[0.015]} position={[0, 0.05, 0]}>
          <meshStandardMaterial color="#0066ff" roughness={0.3} metalness={0.7} />
        </Sphere>
      </group>
      
      {/* Bubbles */}
      {bubbles.map(bubble => (
        <Sphere
          key={bubble.id}
          args={[bubble.size]}
          position={bubble.position}
        >
          <meshPhysicalMaterial
            color="#ffffff"
            transparent
            opacity={0.4}
            roughness={0.1}
            metalness={0.1}
            clearcoat={1}
            clearcoatRoughness={0}
          />
        </Sphere>
      ))}
      
      {/* Status indicator */}
      {isStreaming && (
        <Sphere args={[0.02]} position={[0, 0.5, 0]}>
          <meshStandardMaterial
            color="#00ff00"
            emissive="#00ff00"
            emissiveIntensity={0.5 + Math.sin(Date.now() * 0.005) * 0.5}
          />
        </Sphere>
      )}
      
      {/* Deposition layer (if visible) */}
      {data?.deposition_thickness && data.deposition_thickness > 0.001 && (
        <Box
          args={[0.01, 0.05, 0.05 + data.deposition_thickness]}
          position={[-0.1, 0.05, 0]}
          castShadow
        >
          <meshStandardMaterial
            color="#887766"
            roughness={0.7}
            metalness={0.6}
            opacity={0.9}
            transparent
          />
        </Box>
      )}
    </group>
  )
}

interface Bubble {
  id: number
  position: [number, number, number]
  velocity: number
  size: number
}