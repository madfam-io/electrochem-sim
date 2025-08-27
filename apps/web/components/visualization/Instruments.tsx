'use client'

import { useRef, useState } from 'react'
import { Group } from 'three'
import { useFrame } from '@react-three/fiber'
import { Box, Cylinder, Text } from '@react-three/drei'
import { Html } from '@react-three/drei'

export function Instruments() {
  return (
    <group>
      <Potentiostat position={[2, 1, 0]} />
      <AnalyticalBalance position={[-2, 1, 1]} />
      <PeristalticPump position={[1, 1, -2]} />
    </group>
  )
}

function Potentiostat({ position }: { position: [number, number, number] }) {
  const [isOn, setIsOn] = useState(false)
  const [current, setCurrent] = useState(0)
  const displayRef = useRef<Group>(null)
  
  useFrame((state) => {
    if (isOn) {
      // Simulate current reading
      setCurrent(Math.sin(state.clock.elapsedTime) * 2.5)
    }
  })
  
  return (
    <group position={position}>
      {/* Main unit */}
      <Box args={[0.5, 0.3, 0.4]} position={[0, 0.15, 0]} castShadow receiveShadow>
        <meshStandardMaterial color="#2a2a2a" roughness={0.8} metalness={0.3} />
      </Box>
      
      {/* Display screen */}
      <Box args={[0.3, 0.15, 0.01]} position={[0, 0.2, 0.201]} ref={displayRef}>
        <meshStandardMaterial
          color={isOn ? "#00ff00" : "#001100"}
          emissive={isOn ? "#00ff00" : "#000000"}
          emissiveIntensity={isOn ? 0.2 : 0}
        />
      </Box>
      
      {/* Display content */}
      {isOn && (
        <Html
          position={[0, 0.2, 0.21]}
          center
          style={{
            color: '#00ff00',
            fontSize: '10px',
            fontFamily: 'monospace',
            background: 'transparent',
            userSelect: 'none',
          }}
        >
          <div>
            <div>Current: {current.toFixed(2)} mA</div>
            <div>Voltage: -0.80 V</div>
          </div>
        </Html>
      )}
      
      {/* Control knobs */}
      {[-0.15, 0, 0.15].map((x, i) => (
        <Cylinder
          key={i}
          args={[0.02, 0.02, 0.03]}
          position={[x, 0.05, 0.15]}
          rotation={[Math.PI / 2, 0, 0]}
          castShadow
        >
          <meshStandardMaterial color="#666666" roughness={0.5} metalness={0.8} />
        </Cylinder>
      ))}
      
      {/* Power button */}
      <Cylinder
        args={[0.025, 0.025, 0.01]}
        position={[0.2, 0.15, 0.201]}
        rotation={[Math.PI / 2, 0, 0]}
        onClick={() => setIsOn(!isOn)}
        onPointerOver={(e) => e.stopPropagation()}
      >
        <meshStandardMaterial
          color={isOn ? "#00ff00" : "#ff0000"}
          emissive={isOn ? "#00ff00" : "#ff0000"}
          emissiveIntensity={0.3}
        />
      </Cylinder>
      
      {/* Connection ports */}
      <group position={[0, 0.3, 0]}>
        {/* Working electrode (red) */}
        <Cylinder args={[0.01, 0.01, 0.02]} position={[-0.1, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <meshStandardMaterial color="#ff0000" metalness={0.8} />
        </Cylinder>
        
        {/* Counter electrode (black) */}
        <Cylinder args={[0.01, 0.01, 0.02]} position={[0, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <meshStandardMaterial color="#000000" metalness={0.8} />
        </Cylinder>
        
        {/* Reference electrode (blue) */}
        <Cylinder args={[0.01, 0.01, 0.02]} position={[0.1, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <meshStandardMaterial color="#0000ff" metalness={0.8} />
        </Cylinder>
      </group>
      
      {/* Label */}
      <Text
        position={[0, 0.35, 0]}
        fontSize={0.05}
        color="#ffffff"
        anchorX="center"
        anchorY="middle"
      >
        Potentiostat
      </Text>
    </group>
  )
}

function AnalyticalBalance({ position }: { position: [number, number, number] }) {
  const [weight, setWeight] = useState(0)
  const [tared, setTared] = useState(false)
  
  return (
    <group position={position}>
      {/* Base */}
      <Box args={[0.4, 0.1, 0.4]} position={[0, 0.05, 0]} castShadow receiveShadow>
        <meshStandardMaterial color="#e8e8e8" roughness={0.7} metalness={0.2} />
      </Box>
      
      {/* Weighing platform */}
      <Cylinder args={[0.12, 0.12, 0.01]} position={[0, 0.11, 0]} castShadow>
        <meshStandardMaterial color="#aaaaaa" roughness={0.3} metalness={0.8} />
      </Cylinder>
      
      {/* Display */}
      <Box args={[0.2, 0.08, 0.01]} position={[0, 0.05, 0.15]}>
        <meshStandardMaterial color="#001100" />
      </Box>
      
      {/* Display readout */}
      <Html
        position={[0, 0.05, 0.16]}
        center
        style={{
          color: '#00ff00',
          fontSize: '12px',
          fontFamily: 'monospace',
          background: '#001100',
          padding: '2px 5px',
          borderRadius: '2px',
        }}
      >
        {tared ? '0.0000' : weight.toFixed(4)} g
      </Html>
      
      {/* Tare button */}
      <Box
        args={[0.04, 0.02, 0.01]}
        position={[0.08, 0.02, 0.15]}
        onClick={() => setTared(!tared)}
      >
        <meshStandardMaterial color="#0066ff" />
      </Box>
      
      {/* Glass shield (open top) */}
      {[[-0.15, 0, 0], [0.15, 0, 0], [0, 0, -0.15], [0, 0, 0.15]].map((pos, i) => (
        <Box
          key={i}
          args={[i < 2 ? 0.01 : 0.3, 0.25, i < 2 ? 0.3 : 0.01]}
          position={[pos[0], 0.225, pos[2]]}
        >
          <meshPhysicalMaterial
            color="#ffffff"
            transparent
            opacity={0.2}
            roughness={0.1}
            metalness={0.1}
            transmission={0.9}
          />
        </Box>
      ))}
      
      {/* Sample (if weight > 0) */}
      {weight > 0 && (
        <Box args={[0.05, 0.02, 0.05]} position={[0, 0.13, 0]}>
          <meshStandardMaterial color="#8b7355" />
        </Box>
      )}
    </group>
  )
}

function PeristalticPump({ position }: { position: [number, number, number] }) {
  const [isRunning, setIsRunning] = useState(false)
  const rollerRef = useRef<Group>(null)
  
  useFrame((state, delta) => {
    if (rollerRef.current && isRunning) {
      rollerRef.current.rotation.z -= delta * 2
    }
  })
  
  return (
    <group position={position}>
      {/* Pump housing */}
      <Box args={[0.3, 0.25, 0.2]} position={[0, 0.125, 0]} castShadow receiveShadow>
        <meshStandardMaterial color="#4a4a4a" roughness={0.8} metalness={0.3} />
      </Box>
      
      {/* Pump head */}
      <Cylinder args={[0.08, 0.08, 0.05]} position={[0, 0.15, 0.08]} rotation={[Math.PI / 2, 0, 0]}>
        <meshStandardMaterial color="#666666" roughness={0.5} metalness={0.7} />
      </Cylinder>
      
      {/* Rollers */}
      <group ref={rollerRef} position={[0, 0.15, 0.08]}>
        {[0, Math.PI / 3, 2 * Math.PI / 3, Math.PI, 4 * Math.PI / 3, 5 * Math.PI / 3].map((angle, i) => (
          <Cylinder
            key={i}
            args={[0.01, 0.01, 0.04]}
            position={[
              Math.cos(angle) * 0.05,
              Math.sin(angle) * 0.05,
              0
            ]}
            rotation={[Math.PI / 2, 0, 0]}
          >
            <meshStandardMaterial color="#333333" roughness={0.3} metalness={0.9} />
          </Cylinder>
        ))}
      </group>
      
      {/* Tubing */}
      <Cylinder
        args={[0.005, 0.005, 0.5]}
        position={[-0.1, 0.15, 0.08]}
        rotation={[0, 0, Math.PI / 2]}
      >
        <meshStandardMaterial
          color="#ffaa00"
          transparent
          opacity={0.8}
          roughness={0.8}
        />
      </Cylinder>
      
      {/* Control panel */}
      <Box args={[0.15, 0.08, 0.01]} position={[0, 0.2, 0.101]}>
        <meshStandardMaterial color="#222222" />
      </Box>
      
      {/* Start/Stop button */}
      <Cylinder
        args={[0.02, 0.02, 0.01]}
        position={[0, 0.2, 0.11]}
        rotation={[Math.PI / 2, 0, 0]}
        onClick={() => setIsRunning(!isRunning)}
      >
        <meshStandardMaterial
          color={isRunning ? "#00ff00" : "#ff0000"}
          emissive={isRunning ? "#00ff00" : "#ff0000"}
          emissiveIntensity={0.3}
        />
      </Cylinder>
      
      {/* Speed indicator */}
      {isRunning && (
        <Html
          position={[0.05, 0.2, 0.12]}
          center
          style={{
            color: '#00ff00',
            fontSize: '8px',
            fontFamily: 'monospace',
          }}
        >
          50 mL/min
        </Html>
      )}
    </group>
  )
}