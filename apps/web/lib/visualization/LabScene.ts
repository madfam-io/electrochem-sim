import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass'
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass'
import { VolumeRenderer } from './VolumeRenderer'
import { DigitalTwin } from './DigitalTwin'
import { FluidSimulation } from './FluidSimulation'

/**
 * Main 3D laboratory scene manager
 */
export class LabScene {
  private scene: THREE.Scene
  private camera: THREE.PerspectiveCamera
  private renderer: THREE.WebGLRenderer
  private composer: EffectComposer
  private controls: OrbitControls
  private clock: THREE.Clock
  
  // Lab components
  private laboratory: Laboratory
  private instruments: Map<string, InstrumentDigitalTwin>
  private experiments: Map<string, ExperimentVisualization>
  private volumeRenderer: VolumeRenderer
  private fluidSimulation: FluidSimulation
  
  // Real-time data
  private dataStream: EventSource | null = null
  private updateQueue: UpdateMessage[] = []
  
  constructor(container: HTMLElement) {
    this.clock = new THREE.Clock()
    this.instruments = new Map()
    this.experiments = new Map()
    
    // Initialize Three.js
    this.initScene()
    this.initCamera(container)
    this.initRenderer(container)
    this.initPostProcessing()
    this.initControls()
    this.initLighting()
    
    // Initialize specialized renderers
    this.volumeRenderer = new VolumeRenderer(this.scene)
    this.fluidSimulation = new FluidSimulation(this.scene)
    
    // Load laboratory environment
    this.loadLaboratory()
    
    // Start render loop
    this.animate()
  }
  
  private initScene(): void {
    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0xf0f0f0)
    this.scene.fog = new THREE.Fog(0xf0f0f0, 10, 50)
    
    // Add environment map for reflections
    const pmremGenerator = new THREE.PMREMGenerator(this.renderer)
    new THREE.TextureLoader().load('/hdri/laboratory.hdr', (texture) => {
      const envMap = pmremGenerator.fromEquirectangular(texture).texture
      this.scene.environment = envMap
      texture.dispose()
      pmremGenerator.dispose()
    })
  }
  
  private initCamera(container: HTMLElement): void {
    const aspect = container.clientWidth / container.clientHeight
    this.camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 100)
    this.camera.position.set(5, 3, 5)
    this.camera.lookAt(0, 1, 0)
  }
  
  private initRenderer(container: HTMLElement): void {
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      logarithmicDepthBuffer: true,
      powerPreference: 'high-performance'
    })
    
    this.renderer.setSize(container.clientWidth, container.clientHeight)
    this.renderer.setPixelRatio(window.devicePixelRatio)
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.0
    this.renderer.outputEncoding = THREE.sRGBEncoding
    
    container.appendChild(this.renderer.domElement)
  }
  
  private initPostProcessing(): void {
    this.composer = new EffectComposer(this.renderer)
    
    // Main render pass
    const renderPass = new RenderPass(this.scene, this.camera)
    this.composer.addPass(renderPass)
    
    // Screen-space ambient occlusion
    const ssaoPass = new SSAOPass(
      this.scene,
      this.camera,
      this.renderer.domElement.width,
      this.renderer.domElement.height
    )
    ssaoPass.kernelRadius = 0.5
    ssaoPass.minDistance = 0.001
    ssaoPass.maxDistance = 0.1
    this.composer.addPass(ssaoPass)
    
    // Bloom for emissive materials
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(
        this.renderer.domElement.width,
        this.renderer.domElement.height
      ),
      1.5,  // strength
      0.4,  // radius
      0.85  // threshold
    )
    this.composer.addPass(bloomPass)
  }
  
  private initControls(): void {
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.05
    this.controls.minDistance = 1
    this.controls.maxDistance = 30
    this.controls.maxPolarAngle = Math.PI * 0.45
  }
  
  private initLighting(): void {
    // Ambient light
    const ambient = new THREE.AmbientLight(0xffffff, 0.4)
    this.scene.add(ambient)
    
    // Main overhead lights (fluorescent panels)
    for (let x = -3; x <= 3; x += 3) {
      for (let z = -3; z <= 3; z += 3) {
        const light = new THREE.RectAreaLight(0xffffff, 50, 2, 0.5)
        light.position.set(x, 3.5, z)
        light.lookAt(x, 0, z)
        this.scene.add(light)
      }
    }
    
    // Task lighting for workbenches
    const spotLight = new THREE.SpotLight(0xffffff, 1, 10, Math.PI / 6, 0.5, 2)
    spotLight.position.set(2, 3, 0)
    spotLight.target.position.set(0, 1, 0)
    spotLight.castShadow = true
    spotLight.shadow.mapSize.width = 2048
    spotLight.shadow.mapSize.height = 2048
    this.scene.add(spotLight)
    this.scene.add(spotLight.target)
  }
  
  private async loadLaboratory(): Promise<void> {
    this.laboratory = new Laboratory()
    await this.laboratory.load()
    this.scene.add(this.laboratory.model)
  }
  
  /**
   * Add an instrument to the scene
   */
  async addInstrument(
    type: InstrumentType,
    position: THREE.Vector3,
    options?: InstrumentOptions
  ): Promise<string> {
    const id = `instrument_${Date.now()}`
    const instrument = await InstrumentFactory.create(type, options)
    
    instrument.position.copy(position)
    this.scene.add(instrument.model)
    
    this.instruments.set(id, instrument)
    
    // Connect to real instrument if specified
    if (options?.connectionUrl) {
      await instrument.connectToPhysical(options.connectionUrl)
    }
    
    return id
  }
  
  /**
   * Start an experiment visualization
   */
  async startExperiment(
    runId: string,
    scenario: Scenario
  ): Promise<void> {
    const experiment = new ExperimentVisualization(scenario)
    await experiment.initialize()
    
    this.scene.add(experiment.container)
    this.experiments.set(runId, experiment)
    
    // Connect to data stream
    this.connectToDataStream(runId)
  }
  
  /**
   * Connect to real-time data stream
   */
  private connectToDataStream(runId: string): void {
    const url = `/api/v1/visualization/volumes/${runId}/stream`
    
    this.dataStream = new EventSource(url)
    
    this.dataStream.onmessage = (event) => {
      const data = JSON.parse(event.data)
      this.updateQueue.push(data)
    }
    
    this.dataStream.onerror = (error) => {
      console.error('Data stream error:', error)
      this.reconnectDataStream(runId)
    }
  }
  
  private reconnectDataStream(runId: string): void {
    if (this.dataStream) {
      this.dataStream.close()
    }
    
    setTimeout(() => {
      this.connectToDataStream(runId)
    }, 5000)
  }
  
  /**
   * Process queued updates
   */
  private processUpdates(): void {
    while (this.updateQueue.length > 0) {
      const update = this.updateQueue.shift()!
      
      switch (update.type) {
        case 'volume':
          this.updateVolumeData(update)
          break
        case 'instrument':
          this.updateInstrument(update)
          break
        case 'particles':
          this.updateParticles(update)
          break
      }
    }
  }
  
  private updateVolumeData(update: VolumeUpdate): void {
    const experiment = this.experiments.get(update.runId)
    if (!experiment) return
    
    // Update concentration field
    if (update.concentrationField) {
      this.volumeRenderer.updateField(
        update.concentrationField,
        update.dimensions,
        update.colorMap || 'viridis'
      )
    }
    
    // Update current density visualization
    if (update.currentDensity) {
      experiment.updateCurrentFlow(update.currentDensity)
    }
  }
  
  private updateInstrument(update: InstrumentUpdate): void {
    const instrument = this.instruments.get(update.instrumentId)
    if (!instrument) return
    
    instrument.updateState(update.state)
    
    // Update display
    if (update.display) {
      instrument.updateDisplay(update.display)
    }
    
    // Animate moving parts
    if (update.animation) {
      instrument.animate(update.animation)
    }
  }
  
  private updateParticles(update: ParticleUpdate): void {
    const experiment = this.experiments.get(update.runId)
    if (!experiment) return
    
    experiment.particleSystem.update({
      positions: update.positions,
      velocities: update.velocities,
      colors: update.colors,
      sizes: update.sizes
    })
  }
  
  /**
   * Animation loop
   */
  private animate = (): void => {
    requestAnimationFrame(this.animate)
    
    const deltaTime = this.clock.getDelta()
    
    // Process data updates
    this.processUpdates()
    
    // Update controls
    this.controls.update()
    
    // Update instruments
    this.instruments.forEach(instrument => {
      instrument.update(deltaTime)
    })
    
    // Update experiments
    this.experiments.forEach(experiment => {
      experiment.update(deltaTime)
    })
    
    // Update volume renderer
    this.volumeRenderer.update(deltaTime)
    
    // Update fluid simulation
    this.fluidSimulation.update(deltaTime)
    
    // Render
    this.composer.render()
  }
  
  /**
   * Handle window resize
   */
  onWindowResize(): void {
    const container = this.renderer.domElement.parentElement!
    const width = container.clientWidth
    const height = container.clientHeight
    
    this.camera.aspect = width / height
    this.camera.updateProjectionMatrix()
    
    this.renderer.setSize(width, height)
    this.composer.setSize(width, height)
  }
  
  /**
   * Clean up resources
   */
  dispose(): void {
    if (this.dataStream) {
      this.dataStream.close()
    }
    
    this.instruments.forEach(instrument => {
      instrument.dispose()
    })
    
    this.experiments.forEach(experiment => {
      experiment.dispose()
    })
    
    this.volumeRenderer.dispose()
    this.fluidSimulation.dispose()
    
    this.renderer.dispose()
    this.controls.dispose()
  }
}

/**
 * Laboratory environment model
 */
class Laboratory {
  model: THREE.Group
  workbenches: Workbench[] = []
  
  async load(): Promise<void> {
    this.model = new THREE.Group()
    
    // Floor
    const floorGeometry = new THREE.PlaneGeometry(20, 20)
    const floorMaterial = new THREE.MeshStandardMaterial({
      color: 0xcccccc,
      roughness: 0.8,
      metalness: 0.1
    })
    const floor = new THREE.Mesh(floorGeometry, floorMaterial)
    floor.rotation.x = -Math.PI / 2
    floor.receiveShadow = true
    this.model.add(floor)
    
    // Walls
    this.createWalls()
    
    // Workbenches
    this.createWorkbenches()
    
    // Safety equipment
    this.createSafetyEquipment()
  }
  
  private createWalls(): void {
    const wallMaterial = new THREE.MeshStandardMaterial({
      color: 0xf5f5f5,
      roughness: 0.9,
      metalness: 0.0
    })
    
    // Back wall
    const backWall = new THREE.Mesh(
      new THREE.PlaneGeometry(20, 5),
      wallMaterial
    )
    backWall.position.set(0, 2.5, -10)
    this.model.add(backWall)
    
    // Side walls
    const leftWall = new THREE.Mesh(
      new THREE.PlaneGeometry(20, 5),
      wallMaterial
    )
    leftWall.rotation.y = Math.PI / 2
    leftWall.position.set(-10, 2.5, 0)
    this.model.add(leftWall)
    
    const rightWall = new THREE.Mesh(
      new THREE.PlaneGeometry(20, 5),
      wallMaterial
    )
    rightWall.rotation.y = -Math.PI / 2
    rightWall.position.set(10, 2.5, 0)
    this.model.add(rightWall)
  }
  
  private createWorkbenches(): void {
    // Main workbench
    const workbench = new Workbench({
      dimensions: new THREE.Vector3(3, 0.9, 1.5),
      position: new THREE.Vector3(0, 0, 0)
    })
    
    this.model.add(workbench.model)
    this.workbenches.push(workbench)
    
    // Fume hood
    const fumeHood = new FumeHood({
      position: new THREE.Vector3(-4, 0, -3)
    })
    
    this.model.add(fumeHood.model)
  }
  
  private createSafetyEquipment(): void {
    // Safety shower
    const shower = new SafetyShower()
    shower.model.position.set(8, 0, -8)
    this.model.add(shower.model)
    
    // Eye wash station
    const eyeWash = new EyeWashStation()
    eyeWash.model.position.set(7, 1, -8)
    this.model.add(eyeWash.model)
  }
}

/**
 * Workbench model
 */
class Workbench {
  model: THREE.Group
  slots: EquipmentSlot[] = []
  
  constructor(options: WorkbenchOptions) {
    this.model = new THREE.Group()
    
    // Bench top
    const topGeometry = new THREE.BoxGeometry(
      options.dimensions.x,
      0.05,
      options.dimensions.z
    )
    const topMaterial = new THREE.MeshStandardMaterial({
      color: 0x333333,
      roughness: 0.3,
      metalness: 0.1
    })
    const top = new THREE.Mesh(topGeometry, topMaterial)
    top.position.y = options.dimensions.y
    top.castShadow = true
    top.receiveShadow = true
    
    // Legs
    const legMaterial = new THREE.MeshStandardMaterial({
      color: 0x666666,
      roughness: 0.8,
      metalness: 0.9
    })
    
    const legGeometry = new THREE.CylinderGeometry(0.05, 0.05, options.dimensions.y)
    const legPositions = [
      [-options.dimensions.x / 2 + 0.1, 0, -options.dimensions.z / 2 + 0.1],
      [options.dimensions.x / 2 - 0.1, 0, -options.dimensions.z / 2 + 0.1],
      [-options.dimensions.x / 2 + 0.1, 0, options.dimensions.z / 2 - 0.1],
      [options.dimensions.x / 2 - 0.1, 0, options.dimensions.z / 2 - 0.1]
    ]
    
    legPositions.forEach(pos => {
      const leg = new THREE.Mesh(legGeometry, legMaterial)
      leg.position.set(pos[0], options.dimensions.y / 2, pos[2])
      leg.castShadow = true
      this.model.add(leg)
    })
    
    this.model.add(top)
    this.model.position.copy(options.position)
    
    // Create equipment slots
    this.createSlots(options.dimensions)
  }
  
  private createSlots(dimensions: THREE.Vector3): void {
    const slotSize = 0.3
    const numSlotsX = Math.floor(dimensions.x / slotSize) - 1
    const numSlotsZ = Math.floor(dimensions.z / slotSize) - 1
    
    for (let x = 0; x < numSlotsX; x++) {
      for (let z = 0; z < numSlotsZ; z++) {
        const slot = new EquipmentSlot({
          position: new THREE.Vector3(
            (x - numSlotsX / 2) * slotSize,
            dimensions.y + 0.025,
            (z - numSlotsZ / 2) * slotSize
          ),
          size: slotSize
        })
        
        this.slots.push(slot)
      }
    }
  }
}

// Type definitions
interface UpdateMessage {
  type: 'volume' | 'instrument' | 'particles'
  runId?: string
  instrumentId?: string
  data: any
}

interface VolumeUpdate extends UpdateMessage {
  type: 'volume'
  concentrationField?: Float32Array
  dimensions?: THREE.Vector3
  currentDensity?: Float32Array
  colorMap?: string
}

interface InstrumentUpdate extends UpdateMessage {
  type: 'instrument'
  state?: any
  display?: any
  animation?: any
}

interface ParticleUpdate extends UpdateMessage {
  type: 'particles'
  positions: Float32Array
  velocities?: Float32Array
  colors?: Float32Array
  sizes?: Float32Array
}

interface WorkbenchOptions {
  dimensions: THREE.Vector3
  position: THREE.Vector3
}

interface InstrumentOptions {
  connectionUrl?: string
  calibration?: any
}

enum InstrumentType {
  POTENTIOSTAT = 'potentiostat',
  BALANCE = 'balance',
  PUMP = 'pump',
  SPECTROMETER = 'spectrometer'
}

interface Scenario {
  geometry: any
  physics: any
  materials: any
}