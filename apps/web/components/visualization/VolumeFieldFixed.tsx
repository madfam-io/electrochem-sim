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
      float t0 = max(max(tmin.x, tmin.y), tmin.z);
      float t1 = min(min(tmax.x, tmax.y), tmax.z);
      return vec2(t0, t1);
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
      float accum_alpha = 0.0;
      
      for (float t = bounds.x; t < bounds.y; t += delta) {
        vec3 samplePos = vOrigin + t * rayDir;
        vec3 texCoord = samplePos + vec3(0.5);
        
        if (texCoord.x < 0.0 || texCoord.x > 1.0 ||
            texCoord.y < 0.0 || texCoord.y > 1.0 ||
            texCoord.z < 0.0 || texCoord.z > 1.0) continue;
        
        float density = texture(volumeTexture, texCoord).r;
        
        if (density > threshold) {
          vec4 color = texture(colorMap, vec2(density, 0.5));
          
          float alpha = density * opacity * alphaCorrection;
          alpha *= (1.0 - accum_alpha);
          
          accum += vec4(color.rgb * alpha, alpha);
          accum_alpha += alpha;
          
          if (accum_alpha >= 0.95) break;
        }
      }
      
      gl_FragColor = accum;
      
      if (gl_FragColor.a < 0.01) discard;
    }
  `
)

extend({ VolumeShaderMaterial })

interface VolumeFieldProps {
  runId?: string
  visible?: boolean
  opacity?: number
  threshold?: number
}

export default function VolumeField({
  runId = 'demo',
  visible = true,
  opacity = 0.5,
  threshold = 0.01,
}: VolumeFieldProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const materialRef = useRef<any>(null)
  const textureRef = useRef<THREE.Data3DTexture | null>(null)
  const colorMapRef = useRef<THREE.DataTexture | null>(null)
  const { camera } = useThree()
  const { data: simData } = useSimulationData(runId)
  
  // Create volume texture - properly dispose of old texture
  const volumeTexture = useMemo(() => {
    // Dispose of previous texture
    if (textureRef.current) {
      textureRef.current.dispose()
    }
    
    // Generate demo volume data
    const size = 64
    const data = new Float32Array(size * size * size)
    
    for (let z = 0; z < size; z++) {
      for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
          const i = x + y * size + z * size * size
          
          // Create concentration gradient
          const cx = (x - size / 2) / size
          const cy = (y - size / 2) / size
          const cz = (z - size / 2) / size
          const r = Math.sqrt(cx * cx + cy * cy + cz * cz)
          
          data[i] = Math.exp(-r * 4) * (1 + 0.5 * Math.sin(x * 0.2) * Math.cos(y * 0.2))
        }
      }
    }
    
    const texture = new THREE.Data3DTexture(data, size, size, size)
    texture.format = THREE.RedFormat
    texture.type = THREE.FloatType
    texture.minFilter = THREE.LinearFilter
    texture.magFilter = THREE.LinearFilter
    texture.needsUpdate = true
    
    textureRef.current = texture
    return texture
  }, [])
  
  // Create color map texture - properly dispose of old texture
  const colorMapTexture = useMemo(() => {
    // Dispose of previous color map
    if (colorMapRef.current) {
      colorMapRef.current.dispose()
    }
    
    const width = 256
    const height = 1
    const data = new Uint8Array(width * height * 4)
    
    for (let i = 0; i < width; i++) {
      const t = i / (width - 1)
      const idx = i * 4
      
      // Gradient from blue to red
      data[idx] = Math.floor(t * 255)     // R
      data[idx + 1] = Math.floor((1 - Math.abs(t - 0.5) * 2) * 255) // G
      data[idx + 2] = Math.floor((1 - t) * 255) // B
      data[idx + 3] = 255 // A
    }
    
    const texture = new THREE.DataTexture(data, width, height, THREE.RGBAFormat)
    texture.needsUpdate = true
    
    colorMapRef.current = texture
    return texture
  }, [])
  
  // Update shader uniforms
  useFrame(() => {
    if (materialRef.current) {
      materialRef.current.uniforms.cameraPos.value.copy(camera.position)
      materialRef.current.uniforms.opacity.value = opacity
      materialRef.current.uniforms.threshold.value = threshold
    }
  })
  
  // Update volume data from simulation
  useEffect(() => {
    if (simData?.concentration && textureRef.current) {
      const size = 64
      const data = new Float32Array(size * size * size)
      
      // Map 1D concentration to 3D volume
      const concentrationData = simData.concentration
      const nPoints = concentrationData.length
      
      for (let z = 0; z < size; z++) {
        for (let y = 0; y < size; y++) {
          for (let x = 0; x < size; x++) {
            const i = x + y * size + z * size * size
            
            // Map to concentration data
            const concIdx = Math.floor((x / size) * nPoints)
            const concentration = concentrationData[concIdx] || 0
            
            // Add some 3D variation
            const cy = (y - size / 2) / size
            const cz = (z - size / 2) / size
            const r = Math.sqrt(cy * cy + cz * cz)
            
            data[i] = (concentration / 100) * Math.exp(-r * 2)
          }
        }
      }
      
      textureRef.current.image.data.set(data)
      textureRef.current.needsUpdate = true
    }
  }, [simData])
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (textureRef.current) {
        textureRef.current.dispose()
        textureRef.current = null
      }
      if (colorMapRef.current) {
        colorMapRef.current.dispose()
        colorMapRef.current = null
      }
      if (materialRef.current) {
        materialRef.current.dispose()
        materialRef.current = null
      }
      if (meshRef.current) {
        meshRef.current.geometry.dispose()
      }
    }
  }, [])
  
  if (!visible) return null
  
  return (
    <mesh ref={meshRef} position={[0, 0.5, 0]} scale={[2, 1, 2]}>
      <boxGeometry args={[1, 1, 1]} />
      <volumeShaderMaterial
        ref={materialRef}
        volumeTexture={volumeTexture}
        colorMap={colorMapTexture}
        transparent
        side={THREE.BackSide}
        depthWrite={false}
      />
    </mesh>
  )
}