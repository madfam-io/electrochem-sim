import * as THREE from 'three'

/**
 * Volumetric rendering for concentration fields and other 3D scalar data
 */
export class VolumeRenderer {
  private scene: THREE.Scene
  private volumeMesh: THREE.Mesh | null = null
  private volumeTexture: THREE.DataTexture3D | null = null
  private transferFunction: THREE.DataTexture
  private material: THREE.ShaderMaterial
  private colorMaps: Map<string, Float32Array>
  
  constructor(scene: THREE.Scene) {
    this.scene = scene
    this.colorMaps = this.initColorMaps()
    this.transferFunction = this.createTransferFunction('viridis')
    this.material = this.createVolumeMaterial()
  }
  
  /**
   * Update the volume field with new data
   */
  updateField(
    data: Float32Array,
    dimensions: THREE.Vector3,
    colorMap: string = 'viridis'
  ): void {
    // Create or update 3D texture
    if (!this.volumeTexture || 
        this.volumeTexture.image.width !== dimensions.x ||
        this.volumeTexture.image.height !== dimensions.y ||
        this.volumeTexture.image.depth !== dimensions.z) {
      
      this.volumeTexture = new THREE.DataTexture3D(
        data,
        dimensions.x,
        dimensions.y,
        dimensions.z
      )
      this.volumeTexture.format = THREE.RedFormat
      this.volumeTexture.type = THREE.FloatType
      this.volumeTexture.minFilter = THREE.LinearFilter
      this.volumeTexture.magFilter = THREE.LinearFilter
      this.volumeTexture.needsUpdate = true
      
      this.material.uniforms.volumeTexture.value = this.volumeTexture
    } else {
      this.volumeTexture.image.data = data
      this.volumeTexture.needsUpdate = true
    }
    
    // Update transfer function if color map changed
    if (this.colorMaps.has(colorMap)) {
      this.transferFunction = this.createTransferFunction(colorMap)
      this.material.uniforms.transferFunction.value = this.transferFunction
    }
    
    // Create or update mesh
    if (!this.volumeMesh) {
      const geometry = new THREE.BoxGeometry(2, 2, 2)
      this.volumeMesh = new THREE.Mesh(geometry, this.material)
      this.volumeMesh.position.set(0, 1, 0)
      this.scene.add(this.volumeMesh)
    }
  }
  
  /**
   * Create the volume rendering shader material
   */
  private createVolumeMaterial(): THREE.ShaderMaterial {
    return new THREE.ShaderMaterial({
      uniforms: {
        volumeTexture: { value: null },
        transferFunction: { value: this.transferFunction },
        cameraPos: { value: new THREE.Vector3() },
        volumeScale: { value: new THREE.Vector3(1, 1, 1) },
        stepSize: { value: 0.01 },
        alphaCorrection: { value: 1.0 },
        threshold: { value: 0.01 }
      },
      
      vertexShader: `
        varying vec3 vRayDirection;
        varying vec3 vPosition;
        uniform vec3 cameraPos;
        
        void main() {
          vPosition = position;
          vRayDirection = position - cameraPos;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      
      fragmentShader: `
        uniform sampler3D volumeTexture;
        uniform sampler2D transferFunction;
        uniform vec3 cameraPos;
        uniform vec3 volumeScale;
        uniform float stepSize;
        uniform float alphaCorrection;
        uniform float threshold;
        
        varying vec3 vRayDirection;
        varying vec3 vPosition;
        
        // Ray-box intersection
        vec2 intersectBox(vec3 orig, vec3 dir) {
          vec3 box_min = vec3(-0.5);
          vec3 box_max = vec3(0.5);
          vec3 inv_dir = 1.0 / dir;
          vec3 tmin_tmp = (box_min - orig) * inv_dir;
          vec3 tmax_tmp = (box_max - orig) * inv_dir;
          vec3 tmin = min(tmin_tmp, tmax_tmp);
          vec3 tmax = max(tmin_tmp, tmax_tmp);
          float t0 = max(tmin.x, max(tmin.y, tmin.z));
          float t1 = min(tmax.x, min(tmax.y, tmax.z));
          return vec2(t0, t1);
        }
        
        // Sample volume at position
        float sampleVolume(vec3 pos) {
          vec3 texCoord = pos * volumeScale + 0.5;
          if (any(lessThan(texCoord, vec3(0.0))) || any(greaterThan(texCoord, vec3(1.0)))) {
            return 0.0;
          }
          return texture(volumeTexture, texCoord).r;
        }
        
        // Apply transfer function
        vec4 applyTransferFunction(float density) {
          if (density < threshold) return vec4(0.0);
          return texture(transferFunction, vec2(density, 0.5));
        }
        
        void main() {
          vec3 rayOrigin = cameraPos;
          vec3 rayDir = normalize(vRayDirection);
          
          // Find intersection with bounding box
          vec2 t = intersectBox(rayOrigin, rayDir);
          
          if (t.x > t.y) {
            discard;
          }
          
          t.x = max(t.x, 0.0);
          
          // Ray marching
          vec3 rayPos = rayOrigin + rayDir * t.x;
          vec3 step = rayDir * stepSize;
          vec4 accum = vec4(0.0);
          
          for (float t = t.x; t < t.y; t += stepSize) {
            float density = sampleVolume(rayPos);
            
            if (density > threshold) {
              vec4 colorSample = applyTransferFunction(density);
              
              // Alpha correction for step size
              colorSample.a = 1.0 - pow(1.0 - colorSample.a, alphaCorrection);
              
              // Front-to-back compositing
              colorSample.rgb *= colorSample.a;
              accum += (1.0 - accum.a) * colorSample;
              
              // Early ray termination
              if (accum.a >= 0.95) break;
            }
            
            rayPos += step;
          }
          
          gl_FragColor = accum;
        }
      `,
      
      transparent: true,
      side: THREE.DoubleSide,
      depthWrite: false
    })
  }
  
  /**
   * Create transfer function texture for color mapping
   */
  private createTransferFunction(colorMap: string): THREE.DataTexture {
    const width = 256
    const data = new Float32Array(width * 4)
    const colors = this.colorMaps.get(colorMap) || this.colorMaps.get('viridis')!
    
    for (let i = 0; i < width; i++) {
      const idx = i * 4
      const colorIdx = Math.floor((i / width) * (colors.length / 4)) * 4
      
      data[idx] = colors[colorIdx]
      data[idx + 1] = colors[colorIdx + 1]
      data[idx + 2] = colors[colorIdx + 2]
      data[idx + 3] = i / width // Linear alpha ramp
    }
    
    const texture = new THREE.DataTexture(data, width, 1, THREE.RGBAFormat, THREE.FloatType)
    texture.needsUpdate = true
    return texture
  }
  
  /**
   * Initialize color maps
   */
  private initColorMaps(): Map<string, Float32Array> {
    const maps = new Map<string, Float32Array>()
    
    // Viridis color map
    maps.set('viridis', new Float32Array([
      0.267, 0.005, 0.329, 1.0,
      0.283, 0.141, 0.458, 1.0,
      0.254, 0.265, 0.530, 1.0,
      0.207, 0.372, 0.553, 1.0,
      0.164, 0.471, 0.558, 1.0,
      0.128, 0.567, 0.551, 1.0,
      0.135, 0.659, 0.518, 1.0,
      0.267, 0.749, 0.441, 1.0,
      0.478, 0.821, 0.318, 1.0,
      0.741, 0.873, 0.150, 1.0,
      0.993, 0.906, 0.144, 1.0
    ]))
    
    // Plasma color map
    maps.set('plasma', new Float32Array([
      0.050, 0.030, 0.528, 1.0,
      0.295, 0.020, 0.632, 1.0,
      0.493, 0.011, 0.658, 1.0,
      0.665, 0.136, 0.565, 1.0,
      0.787, 0.267, 0.441, 1.0,
      0.866, 0.397, 0.325, 1.0,
      0.914, 0.530, 0.217, 1.0,
      0.944, 0.667, 0.128, 1.0,
      0.961, 0.805, 0.106, 1.0,
      0.965, 0.938, 0.316, 1.0,
      0.940, 0.975, 0.131, 1.0
    ]))
    
    // Cool-warm diverging
    maps.set('coolwarm', new Float32Array([
      0.230, 0.299, 0.754, 1.0,
      0.347, 0.451, 0.811, 1.0,
      0.468, 0.599, 0.858, 1.0,
      0.596, 0.737, 0.898, 1.0,
      0.737, 0.857, 0.933, 1.0,
      0.865, 0.865, 0.865, 1.0,
      0.933, 0.737, 0.737, 1.0,
      0.898, 0.596, 0.596, 1.0,
      0.858, 0.468, 0.468, 1.0,
      0.811, 0.347, 0.347, 1.0,
      0.754, 0.230, 0.230, 1.0
    ]))
    
    return maps
  }
  
  /**
   * Create isosurface mesh using marching cubes
   */
  createIsosurface(
    data: Float32Array,
    dimensions: THREE.Vector3,
    threshold: number
  ): THREE.Mesh {
    const geometry = new MarchingCubes(dimensions, data, threshold).generate()
    
    const material = new THREE.MeshPhongMaterial({
      color: 0x44aa88,
      transparent: true,
      opacity: 0.7,
      side: THREE.DoubleSide,
      shininess: 100
    })
    
    return new THREE.Mesh(geometry, material)
  }
  
  /**
   * Update camera position for proper ray marching
   */
  update(deltaTime: number): void {
    if (this.material && this.scene.userData.camera) {
      this.material.uniforms.cameraPos.value = this.scene.userData.camera.position
    }
  }
  
  /**
   * Dispose of resources
   */
  dispose(): void {
    if (this.volumeMesh) {
      this.scene.remove(this.volumeMesh)
      this.volumeMesh.geometry.dispose()
    }
    
    if (this.volumeTexture) {
      this.volumeTexture.dispose()
    }
    
    this.transferFunction.dispose()
    this.material.dispose()
  }
}

/**
 * Marching cubes algorithm for isosurface extraction
 */
class MarchingCubes {
  private dimensions: THREE.Vector3
  private data: Float32Array
  private threshold: number
  
  constructor(dimensions: THREE.Vector3, data: Float32Array, threshold: number) {
    this.dimensions = dimensions
    this.data = data
    this.threshold = threshold
  }
  
  generate(): THREE.BufferGeometry {
    const vertices: number[] = []
    const normals: number[] = []
    
    // Iterate through all voxels
    for (let z = 0; z < this.dimensions.z - 1; z++) {
      for (let y = 0; y < this.dimensions.y - 1; y++) {
        for (let x = 0; x < this.dimensions.x - 1; x++) {
          this.processVoxel(x, y, z, vertices, normals)
        }
      }
    }
    
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
    geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3))
    
    return geometry
  }
  
  private processVoxel(
    x: number, y: number, z: number,
    vertices: number[], normals: number[]
  ): void {
    // Get corner values
    const corners = [
      this.getValue(x, y, z),
      this.getValue(x + 1, y, z),
      this.getValue(x + 1, y + 1, z),
      this.getValue(x, y + 1, z),
      this.getValue(x, y, z + 1),
      this.getValue(x + 1, y, z + 1),
      this.getValue(x + 1, y + 1, z + 1),
      this.getValue(x, y + 1, z + 1)
    ]
    
    // Calculate cube index
    let cubeIndex = 0
    for (let i = 0; i < 8; i++) {
      if (corners[i] < this.threshold) {
        cubeIndex |= (1 << i)
      }
    }
    
    // Skip if entirely inside or outside
    if (EDGE_TABLE[cubeIndex] === 0) return
    
    // Find edge intersections
    const vertList: THREE.Vector3[] = new Array(12)
    
    if (EDGE_TABLE[cubeIndex] & 1) {
      vertList[0] = this.interpolate(x, y, z, x + 1, y, z, corners[0], corners[1])
    }
    // ... continue for all 12 edges
    
    // Generate triangles from lookup table
    for (let i = 0; TRI_TABLE[cubeIndex][i] !== -1; i += 3) {
      const v1 = vertList[TRI_TABLE[cubeIndex][i]]
      const v2 = vertList[TRI_TABLE[cubeIndex][i + 1]]
      const v3 = vertList[TRI_TABLE[cubeIndex][i + 2]]
      
      // Add vertices
      vertices.push(v1.x, v1.y, v1.z)
      vertices.push(v2.x, v2.y, v2.z)
      vertices.push(v3.x, v3.y, v3.z)
      
      // Calculate normal
      const normal = new THREE.Vector3()
      normal.crossVectors(
        v2.clone().sub(v1),
        v3.clone().sub(v1)
      ).normalize()
      
      normals.push(normal.x, normal.y, normal.z)
      normals.push(normal.x, normal.y, normal.z)
      normals.push(normal.x, normal.y, normal.z)
    }
  }
  
  private getValue(x: number, y: number, z: number): number {
    const index = x + y * this.dimensions.x + z * this.dimensions.x * this.dimensions.y
    return this.data[index]
  }
  
  private interpolate(
    x1: number, y1: number, z1: number,
    x2: number, y2: number, z2: number,
    v1: number, v2: number
  ): THREE.Vector3 {
    const t = (this.threshold - v1) / (v2 - v1)
    return new THREE.Vector3(
      x1 + t * (x2 - x1),
      y1 + t * (y2 - y1),
      z1 + t * (z2 - z1)
    )
  }
}

// Marching cubes lookup tables
const EDGE_TABLE = new Uint16Array(256)
const TRI_TABLE: number[][] = []

// Initialize lookup tables (abbreviated for brevity)
// In production, these would contain the full 256 entries
EDGE_TABLE[0] = 0x0
EDGE_TABLE[1] = 0x109
// ... etc