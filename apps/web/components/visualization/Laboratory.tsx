'use client'

import { useRef } from 'react'
import { Group, Mesh } from 'three'
import { useFrame } from '@react-three/fiber'
import { Box, Plane } from '@react-three/drei'

export function Laboratory() {
  const groupRef = useRef<Group>(null)
  
  return (
    <group ref={groupRef}>
      {/* Floor */}
      <Plane
        args={[20, 20]}
        rotation={[-Math.PI / 2, 0, 0]}
        position={[0, 0, 0]}
        receiveShadow
      >
        <meshStandardMaterial color="#cccccc" roughness={0.8} metalness={0.1} />
      </Plane>
      
      {/* Walls */}
      <Plane args={[20, 5]} position={[0, 2.5, -10]} receiveShadow>
        <meshStandardMaterial color="#f5f5f5" roughness={0.9} />
      </Plane>
      
      <Plane args={[20, 5]} position={[-10, 2.5, 0]} rotation={[0, Math.PI / 2, 0]} receiveShadow>
        <meshStandardMaterial color="#f5f5f5" roughness={0.9} />
      </Plane>
      
      <Plane args={[20, 5]} position={[10, 2.5, 0]} rotation={[0, -Math.PI / 2, 0]} receiveShadow>
        <meshStandardMaterial color="#f5f5f5" roughness={0.9} />
      </Plane>
      
      {/* Workbench */}
      <Workbench position={[0, 0, 0]} />
      
      {/* Fume Hood */}
      <FumeHood position={[-4, 0, -3]} />
      
      {/* Safety Equipment */}
      <SafetyShower position={[8, 0, -8]} />
    </group>
  )
}

function Workbench({ position }: { position: [number, number, number] }) {
  const benchRef = useRef<Mesh>(null)
  
  return (
    <group position={position}>
      {/* Bench top */}
      <Box args={[3, 0.1, 2]} position={[0, 1, 0]} castShadow receiveShadow>
        <meshStandardMaterial color="#333333" roughness={0.3} metalness={0.1} />
      </Box>
      
      {/* Legs */}
      {[[-1.4, 0.5, -0.9], [1.4, 0.5, -0.9], [-1.4, 0.5, 0.9], [1.4, 0.5, 0.9]].map((pos, i) => (
        <Box key={i} args={[0.1, 1, 0.1]} position={pos as [number, number, number]} castShadow>
          <meshStandardMaterial color="#666666" roughness={0.8} metalness={0.9} />
        </Box>
      ))}
      
      {/* Shelf */}
      <Box args={[3, 0.05, 0.3]} position={[0, 0.3, -0.85]} castShadow>
        <meshStandardMaterial color="#444444" roughness={0.5} metalness={0.2} />
      </Box>
      
      {/* Power outlets */}
      <group position={[0, 1.05, -0.95]}>
        <Box args={[0.5, 0.15, 0.05]} castShadow>
          <meshStandardMaterial color="#222222" roughness={0.9} />
        </Box>
        {/* Outlet holes */}
        {[-0.15, 0.15].map((x, i) => (
          <Box key={i} args={[0.08, 0.04, 0.06]} position={[x, 0, 0.01]}>
            <meshStandardMaterial color="#000000" />
          </Box>
        ))}
      </group>
    </group>
  )
}

function FumeHood({ position }: { position: [number, number, number] }) {
  const glassRef = useRef<Mesh>(null)
  const [isOpen, setIsOpen] = useState(false)
  
  useFrame((state, delta) => {
    if (glassRef.current) {
      const targetY = isOpen ? 1.8 : 0.3
      glassRef.current.position.y += (targetY - glassRef.current.position.y) * 0.05
    }
  })
  
  return (
    <group position={position}>
      {/* Hood structure */}
      <Box args={[2, 2.5, 1.5]} position={[0, 1.25, 0]} castShadow receiveShadow>
        <meshStandardMaterial color="#e8e8e8" roughness={0.7} metalness={0.3} />
      </Box>
      
      {/* Work surface */}
      <Box args={[1.8, 0.05, 1.3]} position={[0, 0.95, 0]} castShadow>
        <meshStandardMaterial color="#333333" roughness={0.3} metalness={0.1} />
      </Box>
      
      {/* Glass sash (movable) */}
      <Box
        ref={glassRef}
        args={[1.9, 1.2, 0.01]}
        position={[0, 0.3, 0.65]}
        castShadow
        onClick={() => setIsOpen(!isOpen)}
        onPointerOver={(e) => e.stopPropagation()}
      >
        <meshStandardMaterial
          color="#88ccff"
          transparent
          opacity={0.3}
          roughness={0.1}
          metalness={0.1}
        />
      </Box>
      
      {/* Ventilation */}
      <Box args={[0.3, 0.3, 0.1]} position={[0, 2.3, -0.7]} castShadow>
        <meshStandardMaterial color="#666666" roughness={0.9} metalness={0.8} />
      </Box>
    </group>
  )
}

function SafetyShower({ position }: { position: [number, number, number] }) {
  const [isActive, setIsActive] = useState(false)
  const waterRef = useRef<Group>(null)
  
  useFrame((state) => {
    if (waterRef.current && isActive) {
      // Animate water particles
      waterRef.current.children.forEach((child, i) => {
        child.position.y -= 0.05
        if (child.position.y < 0) {
          child.position.y = 2
          child.position.x = (Math.random() - 0.5) * 0.5
          child.position.z = (Math.random() - 0.5) * 0.5
        }
      })
    }
  })
  
  return (
    <group position={position}>
      {/* Shower pole */}
      <Box args={[0.05, 3, 0.05]} position={[0, 1.5, 0]} castShadow>
        <meshStandardMaterial color="#ffff00" roughness={0.3} metalness={0.8} />
      </Box>
      
      {/* Shower head */}
      <Box args={[0.5, 0.1, 0.5]} position={[0, 2.5, 0]} castShadow>
        <meshStandardMaterial color="#ffff00" roughness={0.3} metalness={0.8} />
      </Box>
      
      {/* Pull handle */}
      <Box
        args={[0.15, 0.3, 0.05]}
        position={[0.3, 1.8, 0]}
        castShadow
        onClick={() => setIsActive(!isActive)}
      >
        <meshStandardMaterial color="#ff0000" roughness={0.5} emissive="#ff0000" emissiveIntensity={0.2} />
      </Box>
      
      {/* Water particles (when active) */}
      {isActive && (
        <group ref={waterRef}>
          {Array.from({ length: 50 }).map((_, i) => (
            <Box
              key={i}
              args={[0.02, 0.1, 0.02]}
              position={[
                (Math.random() - 0.5) * 0.5,
                2 - Math.random() * 2,
                (Math.random() - 0.5) * 0.5
              ]}
            >
              <meshStandardMaterial
                color="#4499ff"
                transparent
                opacity={0.6}
                emissive="#4499ff"
                emissiveIntensity={0.1}
              />
            </Box>
          ))}
        </group>
      )}
    </group>
  )
}

import { useState } from 'react'