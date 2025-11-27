# Visualization Implementation Roadmap

## Quick Start Implementation

### Phase 1: Basic 3D Lab Environment (Week 1-2)

```typescript
// Minimal implementation to get started
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls'

export class SimpleLabScene {
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  renderer: THREE.WebGLRenderer
  
  constructor(container: HTMLElement) {
    // Basic Three.js setup
    this.scene = new THREE.Scene()
    this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000)
    this.renderer = new THREE.WebGLRenderer()
    
    this.renderer.setSize(window.innerWidth, window.innerHeight)
    container.appendChild(this.renderer.domElement)
    
    // Add basic lab elements
    this.addWorkbench()
    this.addBeaker()
    this.addLighting()
    
    // Start render loop
    this.animate()
  }
  
  addWorkbench() {
    const geometry = new THREE.BoxGeometry(3, 0.1, 2)
    const material = new THREE.MeshPhongMaterial({ color: 0x8B4513 })
    const bench = new THREE.Mesh(geometry, material)
    bench.position.y = 1
    this.scene.add(bench)
  }
  
  addBeaker() {
    const geometry = new THREE.CylinderGeometry(0.2, 0.2, 0.4, 32)
    const material = new THREE.MeshPhongMaterial({ 
      color: 0x88CCFF,
      transparent: true,
      opacity: 0.7
    })
    const beaker = new THREE.Mesh(geometry, material)
    beaker.position.set(0, 1.3, 0)
    this.scene.add(beaker)
  }
  
  animate = () => {
    requestAnimationFrame(this.animate)
    this.renderer.render(this.scene, this.camera)
  }
}
```

### Phase 2: Volumetric Concentration Visualization (Week 3-4)

```glsl
// Simple volume rendering shader
uniform sampler3D concentrationField;
uniform float threshold;

void main() {
  vec3 rayDir = normalize(vRayDirection);
  vec4 accum = vec4(0.0);
  
  // Simple ray marching
  for(int i = 0; i < 100; i++) {
    float density = texture(concentrationField, rayPos).r;
    vec4 color = vec4(density, 0.0, 1.0 - density, density * 0.1);
    accum += (1.0 - accum.a) * color;
    rayPos += rayDir * 0.01;
  }
  
  gl_FragColor = accum;
}
```

### Phase 3: Real-time Data Streaming (Week 5-6)

```typescript
class DataStreamer {
  private eventSource: EventSource
  private scene: LabScene
  
  connect(runId: string) {
    this.eventSource = new EventSource(`/api/viz/stream/${runId}`)
    
    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      this.updateVisualization(data)
    }
  }
  
  updateVisualization(data: any) {
    // Update concentration field
    if (data.concentration) {
      this.scene.volumeRenderer.update(data.concentration)
    }
    
    // Update particle positions
    if (data.particles) {
      this.scene.particleSystem.update(data.particles)
    }
  }
}
```

## Technology Stack

### Essential Dependencies

```json
{
  "dependencies": {
    "three": "^0.160.0",
    "@react-three/fiber": "^8.15.0",
    "@react-three/drei": "^9.88.0",
    "@react-three/postprocessing": "^2.15.0",
    "leva": "^0.9.35",
    "zustand": "^4.4.0"
  }
}
```

### React Three Fiber Implementation

```tsx
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Environment } from '@react-three/drei'
import { EffectComposer, Bloom, SSAO } from '@react-three/postprocessing'

export function LabVisualization({ runId }: { runId: string }) {
  return (
    <Canvas camera={{ position: [5, 3, 5] }}>
      <Environment preset="warehouse" />
      
      <Laboratory />
      <Workbench position={[0, 0, 0]} />
      <ElectrochemicalCell runId={runId} />
      <VolumeField runId={runId} />
      
      <OrbitControls />
      
      <EffectComposer>
        <Bloom intensity={0.5} />
        <SSAO />
      </EffectComposer>
    </Canvas>
  )
}

function ElectrochemicalCell({ runId }: { runId: string }) {
  const { concentration, current } = useSimulationData(runId)
  
  return (
    <group>
      <Glass />
      <Electrodes current={current} />
      <Electrolyte concentration={concentration} />
      <Bubbles />
    </group>
  )
}
```

## Implementation Phases

### Phase 1: Foundation (Weeks 1-2)
- [x] Basic Three.js scene setup
- [x] Lab environment geometry
- [x] Camera controls
- [x] Basic lighting

### Phase 2: Equipment Models (Weeks 3-4)
- [ ] Beaker and glassware models
- [ ] Basic instrument models (potentiostat)
- [ ] Workbench with slots
- [ ] Safety equipment

### Phase 3: Volumetric Rendering (Weeks 5-6)
- [ ] Volume texture setup
- [ ] Ray marching shader
- [ ] Transfer functions
- [ ] Color maps

### Phase 4: Real-time Integration (Weeks 7-8)
- [ ] WebSocket connection
- [ ] Data streaming
- [ ] Frame interpolation
- [ ] Update synchronization

### Phase 5: Advanced Effects (Weeks 9-10)
- [ ] Fluid simulation
- [ ] Particle systems
- [ ] Surface reconstruction
- [ ] Caustics and reflections

### Phase 6: Digital Twins (Weeks 11-12)
- [ ] Instrument state sync
- [ ] Real-time sensor data
- [ ] Predictive visualization
- [ ] Calibration overlay

## Performance Optimization

### Level of Detail (LOD)

```typescript
class LODManager {
  updateLOD(camera: THREE.Camera, objects: THREE.Object3D[]) {
    objects.forEach(obj => {
      const distance = camera.position.distanceTo(obj.position)
      
      if (distance < 5) {
        obj.userData.setLOD('high')
      } else if (distance < 15) {
        obj.userData.setLOD('medium')
      } else {
        obj.userData.setLOD('low')
      }
    })
  }
}
```

### GPU Instancing

```typescript
class ParticleInstancer {
  mesh: THREE.InstancedMesh
  
  constructor(count: number) {
    const geometry = new THREE.SphereGeometry(0.01)
    const material = new THREE.MeshBasicMaterial()
    this.mesh = new THREE.InstancedMesh(geometry, material, count)
    
    // Initialize positions
    const matrix = new THREE.Matrix4()
    for (let i = 0; i < count; i++) {
      matrix.setPosition(Math.random(), Math.random(), Math.random())
      this.mesh.setMatrixAt(i, matrix)
    }
  }
  
  update(positions: Float32Array) {
    const matrix = new THREE.Matrix4()
    for (let i = 0; i < positions.length / 3; i++) {
      matrix.setPosition(
        positions[i * 3],
        positions[i * 3 + 1],
        positions[i * 3 + 2]
      )
      this.mesh.setMatrixAt(i, matrix)
    }
    this.mesh.instanceMatrix.needsUpdate = true
  }
}
```

## Asset Pipeline

### 3D Model Workflow

1. **Modeling** (Blender)
   - Create low-poly lab equipment
   - UV unwrapping
   - LOD versions

2. **Texturing** (Substance Painter)
   - PBR materials
   - Bake normal maps
   - Export texture atlases

3. **Optimization**
   - GLTF export with Draco compression
   - Texture compression (KTX2)
   - Mesh decimation

### Asset Loading

```typescript
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader'

class AssetLoader {
  private gltfLoader: GLTFLoader
  
  constructor() {
    const dracoLoader = new DRACOLoader()
    dracoLoader.setDecoderPath('/draco/')
    
    this.gltfLoader = new GLTFLoader()
    this.gltfLoader.setDRACOLoader(dracoLoader)
  }
  
  async loadModel(url: string): Promise<THREE.Object3D> {
    const gltf = await this.gltfLoader.loadAsync(url)
    return gltf.scene
  }
  
  async loadLaboratory(): Promise<Laboratory> {
    const [workbench, fumeHood, instruments] = await Promise.all([
      this.loadModel('/models/workbench.glb'),
      this.loadModel('/models/fume_hood.glb'),
      this.loadModel('/models/instruments.glb')
    ])
    
    return new Laboratory(workbench, fumeHood, instruments)
  }
}
```

## Testing Strategy

### Visual Testing

```typescript
import { render } from '@testing-library/react'
import { act } from 'react-dom/test-utils'

describe('3D Visualization', () => {
  it('renders lab environment', async () => {
    const { container } = render(<LabVisualization runId="test" />)
    
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 100))
    })
    
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeTruthy()
    
    // Take screenshot for visual regression testing
    const screenshot = canvas.toDataURL()
    expect(screenshot).toMatchSnapshot()
  })
})
```

### Performance Testing

```typescript
class PerformanceMonitor {
  private stats: Stats
  
  constructor() {
    this.stats = new Stats()
    document.body.appendChild(this.stats.dom)
  }
  
  measure(callback: () => void): PerformanceMetrics {
    const start = performance.now()
    
    callback()
    
    const end = performance.now()
    const frameTime = end - start
    
    return {
      fps: 1000 / frameTime,
      frameTime,
      drawCalls: this.renderer.info.render.calls,
      triangles: this.renderer.info.render.triangles,
      memory: performance.memory?.usedJSHeapSize
    }
  }
}
```

## Deployment

### CDN Setup

```nginx
# Serve 3D assets from CDN
location /models/ {
  proxy_pass https://cdn.galvana.com/3d/;
  add_header Cache-Control "public, max-age=31536000";
  add_header X-Content-Type-Options nosniff;
}

# Compress GLTF files
location ~ \.glb$ {
  gzip on;
  gzip_types model/gltf-binary;
}
```

### Progressive Loading

```typescript
class ProgressiveLoader {
  async loadScene(quality: 'low' | 'medium' | 'high') {
    // Load essential geometry first
    const essential = await this.loadEssential()
    this.scene.add(essential)
    
    // Progressive enhancement
    if (quality === 'medium' || quality === 'high') {
      const details = await this.loadDetails()
      this.scene.add(details)
    }
    
    if (quality === 'high') {
      const advanced = await this.loadAdvanced()
      this.scene.add(advanced)
    }
  }
}
```

## Success Metrics

- **Performance**: 60 FPS on mid-range devices
- **Load Time**: < 3s for initial scene
- **Memory**: < 500MB for typical session
- **Quality**: Photorealistic materials and lighting
- **Accuracy**: Scientifically accurate visualization
- **Interactivity**: < 50ms response to user input

## Next Steps

1. **Immediate** (Week 1)
   - Set up Three.js in existing Next.js app
   - Create basic lab scene
   - Implement camera controls

2. **Short Term** (Weeks 2-4)
   - Add beaker with fluid simulation
   - Implement concentration visualization
   - Connect to real-time data

3. **Medium Term** (Weeks 5-8)
   - Full volumetric rendering
   - Digital twin integration
   - Advanced materials

4. **Long Term** (Weeks 9-12)
   - XR support (VR/AR)
   - Collaborative features
   - AI-assisted visualization