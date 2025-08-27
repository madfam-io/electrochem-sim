'use client'

import { useRef, useMemo, useEffect } from 'react'
import * as THREE from 'three'
import { useFrame, useThree, extend } from '@react-three/fiber'
import { shaderMaterial } from '@react-three/drei'
import { useSimulationData } from '@/hooks/useSimulationData'

// Volume rendering shader material
const VolumeShaderMaterial = shaderMaterial(
  {
    volumeTexture: null,
    colorMap: null,
    cameraPos: new THREE.Vector3(),
    threshold: 0.01,
    opacity: 0.5,
    steps: 100,
    alphaCorrection: 1.0,
  },
  // Vertex shader
  `
    varying vec3 vOrigin;
    varying vec3 vDirection;
    uniform vec3 cameraPos;
    
    void main() {
      vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
      vOrigin = vec3(inverse(modelMatrix) * vec4(cameraPos, 1.0));
      vDirection = position - vOrigin;
      gl_Position = projectionMatrix * mvPosition;
    }
  `,
  // Fragment shader
  `
    precision highp float;
    precision highp sampler3D;
    
    uniform sampler3D volumeTexture;
    uniform sampler2D colorMap;
    uniform vec3 cameraPos;
    uniform float threshold;
    uniform float opacity;
    uniform float steps;
    uniform float alphaCorrection;
    
    varying vec3 vOrigin;
    varying vec3 vDirection;
    
    vec2 hitBox(vec3 orig, vec3 dir) {
      const vec3 box_min = vec3(-0.5);
      const vec3 box_max = vec3(0.5);
      vec3 inv_dir = 1.0 / dir;
      vec3 tmin_tmp = (box_min - orig) * inv_dir;
      vec3 tmax_tmp = (box_max - orig) * inv_dir;
      vec3 tmin = min(tmin_tmp, tmax_tmp);
      vec3 tmax = max(tmin_tmp, tmax_tmp);
      float t0 = max(tmin.x, max(tmin.y, tmin.z));
      float t1 = min(tmax.x, min(tmax.y, tmax.z));
      return vec2(t0, t1);
    }
    
    float sample1(vec3 p) {
      return texture(volumeTexture, p).r;
    }
    
    vec4 applyColorMap(float val) {
      return texture(colorMap, vec2(val, 0.5));
    }
    
    void main() {
      vec3 rayDir = normalize(vDirection);
      vec2 bounds = hitBox(vOrigin, rayDir);
      
      if (bounds.x > bounds.y) discard;
      
      bounds.x = max(bounds.x, 0.0);
      
      vec3 p = vOrigin + bounds.x * rayDir;
      vec3 inc = 1.0 / abs(rayDir);
      float delta = min(inc.x, min(inc.y, inc.z)) / steps;
      
      vec4 accum = vec4(0.0);
      
      for (float t = bounds.x; t < bounds.y; t += delta) {
        float d = sample1(p + 0.5);
        
        if (d > threshold) {
          vec4 col = applyColorMap(d);
          col.a *= opacity;
          col.a = 1.0 - pow(1.0 - col.a, alphaCorrection);
          col.rgb *= col.a;
          accum += col * (1.0 - accum.a);
          
          if (accum.a >= 0.95) break;
        }
        
        p += rayDir * delta;
      }
      
      gl_FragColor = accum;
    }
  `
)

extend({ VolumeShaderMaterial })

interface VolumeFieldProps {
  runId: string
}

export function VolumeField({ runId }: VolumeFieldProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const materialRef = useRef<any>(null)
  const { camera } = useThree()
  const { data } = useSimulationData(runId)
  
  // Create volume texture from concentration data
  const volumeTexture = useMemo(() => {
    if (!data?.concentration || data.concentration.length === 0) {
      // Create default texture
      const size = 32
      const data = new Float32Array(size * size * size)
      for (let i = 0; i < data.length; i++) {
        data[i] = Math.random() * 0.1
      }
      const texture = new THREE.Data3DTexture(data, size, size, size)
      texture.format = THREE.RedFormat
      texture.type = THREE.FloatType
      texture.minFilter = THREE.LinearFilter
      texture.magFilter = THREE.LinearFilter
      texture.needsUpdate = true
      return texture
    }
    
    // Convert 1D concentration array to 3D texture
    const size = Math.ceil(Math.pow(data.concentration.length, 1/3))
    const paddedData = new Float32Array(size * size * size)
    
    for (let i = 0; i < data.concentration.length; i++) {
      paddedData[i] = data.concentration[i] / 100 // Normalize
    }
    
    const texture = new THREE.Data3DTexture(paddedData, size, size, size)
    texture.format = THREE.RedFormat
    texture.type = THREE.FloatType
    texture.minFilter = THREE.LinearFilter
    texture.magFilter = THREE.LinearFilter
    texture.needsUpdate = true
    
    return texture
  }, [data?.concentration])
  
  // Create color map texture
  const colorMapTexture = useMemo(() => {
    const width = 256
    const height = 1
    const size = width * height * 4
    const data = new Uint8Array(size)
    
    // Viridis color map
    for (let i = 0; i < width; i++) {
      const t = i / width
      const idx = i * 4
      
      // Interpolate viridis colors
      if (t < 0.5) {
        const s = t * 2
        data[idx] = Math.floor(68 + s * (35 - 68))
        data[idx + 1] = Math.floor(1 + s * (70 - 1))
        data[idx + 2] = Math.floor(84 + s * (123 - 84))
      } else {
        const s = (t - 0.5) * 2
        data[idx] = Math.floor(35 + s * (253 - 35))
        data[idx + 1] = Math.floor(70 + s * (231 - 70))
        data[idx + 2] = Math.floor(123 + s * (37 - 123))
      }
      data[idx + 3] = 255
    }
    
    const texture = new THREE.DataTexture(data, width, height)
    texture.needsUpdate = true
    return texture
  }, [])
  
  // Update camera position in shader
  useFrame(() => {
    if (materialRef.current) {
      materialRef.current.cameraPos = camera.position
    }
  })
  
  // Update volume data
  useEffect(() => {
    if (materialRef.current && volumeTexture) {
      materialRef.current.volumeTexture = volumeTexture
      materialRef.current.colorMap = colorMapTexture
    }
  }, [volumeTexture, colorMapTexture])
  
  return (
    <mesh ref={meshRef} position={[0, 1.2, 0]}>
      <boxGeometry args={[0.8, 0.8, 0.8]} />
      <volumeShaderMaterial
        ref={materialRef}
        transparent
        depthWrite={false}
        side={THREE.DoubleSide}
        threshold={0.05}
        opacity={0.6}
        steps={50}
        alphaCorrection={1.0}
      />
    </mesh>
  )
}