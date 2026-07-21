import * as THREE from "three"
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js"
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js"

interface LoupeFieldOptions {
  reducedMotion: boolean
}

function makeRandom(seed: number) {
  let value = seed >>> 0
  return () => {
    value += 0x6d2b79f5
    let next = value
    next = Math.imul(next ^ (next >>> 15), next | 1)
    next ^= next + Math.imul(next ^ (next >>> 7), next | 61)
    return ((next ^ (next >>> 14)) >>> 0) / 4294967296
  }
}

function damp(current: number, target: number, lambda: number, delta: number) {
  return THREE.MathUtils.lerp(current, target, 1 - Math.exp(-lambda * delta))
}

export class LoupeField {
  private readonly canvas: HTMLCanvasElement
  private readonly renderer: THREE.WebGLRenderer
  private readonly scene = new THREE.Scene()
  private readonly camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100)
  private readonly timer = new THREE.Timer()
  private readonly root = new THREE.Group()
  private readonly assembly = new THREE.Group()
  private readonly lens = new THREE.Group()
  private readonly network = new THREE.Group()
  private readonly reducedMotion: boolean
  private readonly edgeMaterial: THREE.LineBasicMaterial
  private readonly nodeMaterial: THREE.MeshBasicMaterial
  private readonly dustMaterial: THREE.PointsMaterial
  private core: THREE.Mesh | null = null
  private coreMaterial: THREE.MeshStandardMaterial | null = null
  private environmentTexture: THREE.Texture | null = null
  private frameId = 0
  private running = false
  private destroyed = false
  private pointerTarget = new THREE.Vector2()
  private pointer = new THREE.Vector2()
  private scrollTarget = 0
  private scroll = 0
  private baseScale = 1
  private animationElapsed = 2.4

  constructor(canvas: HTMLCanvasElement, options: LoupeFieldOptions) {
    this.canvas = canvas
    this.reducedMotion = options.reducedMotion
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    })
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.2
    this.timer.connect(document)
    this.scene.fog = new THREE.FogExp2(0x06151c, 0.042)
    this.camera.position.set(0, 0, 11.4)
    this.createEnvironment()

    this.scene.add(this.root)
    this.root.add(this.assembly)
    this.assembly.add(this.network, this.lens)

    this.edgeMaterial = new THREE.LineBasicMaterial({
      color: 0x2da9ad,
      transparent: true,
      opacity: 0.23,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    this.nodeMaterial = new THREE.MeshBasicMaterial({
      color: 0xdffcf8,
      transparent: true,
      opacity: 0.92,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    this.dustMaterial = new THREE.PointsMaterial({
      color: 0x8adbd8,
      size: 0.018,
      transparent: true,
      opacity: 0.38,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    })

    this.loadHeroModel()
    this.createNetwork()
    this.createDust()
    this.createLights()
    this.resize()

    if (this.reducedMotion) this.render(this.animationElapsed)
  }

  private createEnvironment() {
    const environment = new RoomEnvironment()
    const generator = new THREE.PMREMGenerator(this.renderer)
    this.environmentTexture = generator.fromScene(environment, 0.032).texture
    this.scene.environment = this.environmentTexture
    environment.dispose()
    generator.dispose()
  }

  private loadHeroModel() {
    const loader = new GLTFLoader()
    const url = `${import.meta.env.BASE_URL}models/loupe-hero.glb`

    loader.load(
      url,
      ({ scene: importedScene }) => {
        if (this.destroyed) {
          importedScene.traverse((object) => {
            if (!(object instanceof THREE.Mesh)) return
            object.geometry.dispose()
            const materials = Array.isArray(object.material) ? object.material : [object.material]
            materials.forEach((material) => material.dispose())
          })
          return
        }

        importedScene.rotation.x = Math.PI / 2
        importedScene.updateMatrixWorld(true)
        const bounds = new THREE.Box3().setFromObject(importedScene)
        const center = bounds.getCenter(new THREE.Vector3())
        importedScene.position.sub(center)
        importedScene.updateMatrixWorld(true)

        const centeredBounds = new THREE.Box3().setFromObject(importedScene)
        const size = centeredBounds.getSize(new THREE.Vector3())
        const normalized = new THREE.Group()
        normalized.name = "Loupe_Blender_Asset"
        normalized.scale.setScalar(5.55 / Math.max(size.x, size.y))
        normalized.add(importedScene)

        importedScene.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return
          const materials = Array.isArray(object.material) ? object.material : [object.material]
          materials.forEach((material) => {
            if (material instanceof THREE.MeshStandardMaterial) {
              material.envMapIntensity = 0.92
              material.needsUpdate = true
            }
          })
        })

        const opticalCore = importedScene.getObjectByName("Optical_Core")
        if (opticalCore instanceof THREE.Mesh) {
          this.core = opticalCore
          const material = Array.isArray(opticalCore.material)
            ? opticalCore.material.find((entry) => entry instanceof THREE.MeshStandardMaterial)
            : opticalCore.material
          if (material instanceof THREE.MeshStandardMaterial) this.coreMaterial = material
        }

        this.lens.add(normalized)
        this.canvas.dataset.model = "loaded"
        this.render(this.animationElapsed)
      },
      undefined,
      () => {
        this.canvas.dataset.model = "unavailable"
      }
    )
  }

  private createNetwork() {
    const random = makeRandom(0x10a9e)
    const nodes: THREE.Vector3[] = []
    const count = 44
    for (let index = 0; index < count; index += 1) {
      const radius = 2.2 + random() * 2.8
      const theta = random() * Math.PI * 2
      const phi = Math.acos(2 * random() - 1)
      nodes.push(
        new THREE.Vector3(
          Math.sin(phi) * Math.cos(theta) * radius,
          Math.cos(phi) * radius * 0.72,
          Math.sin(phi) * Math.sin(theta) * radius * 0.58 - 1.5
        )
      )
    }

    const nodeGeometry = new THREE.IcosahedronGeometry(0.045, 1)
    const nodeMesh = new THREE.InstancedMesh(nodeGeometry, this.nodeMaterial, count)
    const matrix = new THREE.Matrix4()
    nodes.forEach((node, index) => {
      matrix.makeTranslation(node.x, node.y, node.z)
      nodeMesh.setMatrixAt(index, matrix)
      nodeMesh.setColorAt(index, new THREE.Color(index % 7 === 0 ? 0x16c4bd : 0xc9eeec))
    })
    nodeMesh.instanceMatrix.needsUpdate = true
    this.network.add(nodeMesh)

    const positions: number[] = []
    const edgeKeys = new Set<string>()
    nodes.forEach((node, index) => {
      const nearest = nodes
        .map((candidate, candidateIndex) => ({
          candidateIndex,
          distance: candidate.distanceToSquared(node),
        }))
        .filter(({ candidateIndex }) => candidateIndex !== index)
        .sort((a, b) => a.distance - b.distance)
        .slice(0, index % 5 === 0 ? 3 : 2)

      nearest.forEach(({ candidateIndex }) => {
        const key = index < candidateIndex ? `${index}-${candidateIndex}` : `${candidateIndex}-${index}`
        if (edgeKeys.has(key)) return
        edgeKeys.add(key)
        const target = nodes[candidateIndex]
        positions.push(node.x, node.y, node.z, target.x, target.y, target.z)
      })
    })
    const edgeGeometry = new THREE.BufferGeometry()
    edgeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3))
    this.network.add(new THREE.LineSegments(edgeGeometry, this.edgeMaterial))
    this.network.position.set(0.7, 0.1, -0.7)
  }

  private createDust() {
    const random = makeRandom(0x51a7)
    const positions = new Float32Array(380 * 3)
    for (let index = 0; index < 380; index += 1) {
      positions[index * 3] = (random() - 0.5) * 17
      positions[index * 3 + 1] = (random() - 0.5) * 10
      positions[index * 3 + 2] = (random() - 0.5) * 9 - 2
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3))
    this.root.add(new THREE.Points(geometry, this.dustMaterial))
  }

  private createLights() {
    this.scene.add(new THREE.AmbientLight(0x7ca9b2, 1.5))
    const tealLight = new THREE.PointLight(0x18d8cf, 20, 18, 1.8)
    tealLight.position.set(2.4, 2.2, 5)
    this.scene.add(tealLight)
    const rimLight = new THREE.DirectionalLight(0xe8fbff, 2.6)
    rimLight.position.set(-4, 3, 6)
    this.scene.add(rimLight)
  }

  start() {
    if (this.running || this.destroyed || this.reducedMotion) return
    this.running = true
    this.timer.reset()
    this.frameId = requestAnimationFrame(this.frame)
  }

  stop() {
    this.running = false
    cancelAnimationFrame(this.frameId)
  }

  setPointer(x: number, y: number) {
    this.pointerTarget.set(x, y)
  }

  setScroll(progress: number) {
    this.scrollTarget = THREE.MathUtils.clamp(progress, 0, 1)
    if (this.reducedMotion) this.render(2.4)
  }

  resize() {
    const parent = this.canvas.parentElement
    if (!parent) return
    const rect = parent.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return

    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75))
    this.renderer.setSize(rect.width, rect.height, false)
    this.camera.aspect = rect.width / rect.height
    this.camera.updateProjectionMatrix()

    const narrow = rect.width < 760
    this.root.position.set(narrow ? 0.25 : 2.85, narrow ? -1.52 : -0.1, 0)
    const scale = narrow ? Math.min(0.72, rect.width / 660) : Math.min(1, rect.width / 1320)
    this.baseScale = scale
    this.render(this.animationElapsed)
  }

  private frame = (timestamp: DOMHighResTimeStamp) => {
    if (!this.running || this.destroyed) return
    this.timer.update(timestamp)
    const delta = Math.min(this.timer.getDelta(), 0.05)
    this.animationElapsed += delta
    this.pointer.x = damp(this.pointer.x, this.pointerTarget.x, 3.4, delta)
    this.pointer.y = damp(this.pointer.y, this.pointerTarget.y, 3.4, delta)
    this.scroll = damp(this.scroll, this.scrollTarget, 2.8, delta)
    this.render(this.animationElapsed)
    this.frameId = requestAnimationFrame(this.frame)
  }

  private render(elapsed: number) {
    const breathe = 1 + Math.sin(elapsed * 1.15) * 0.032
    const scalePulse = 1 + Math.sin(elapsed * 0.18 + 0.35) * 0.012 + Math.sin(elapsed * 0.073) * 0.005
    const pitch = Math.sin(elapsed * 0.17 + 0.8) * 0.11 + Math.sin(elapsed * 0.053) * 0.035
    const yaw = Math.sin(elapsed * 0.23) * 0.22 + Math.sin(elapsed * 0.071 + 1.3) * 0.07
    const roll = Math.sin(elapsed * 0.13 + 2.1) * 0.035
    this.core?.scale.setScalar(breathe)
    if (this.coreMaterial) {
      this.coreMaterial.emissiveIntensity = 0.72 + Math.sin(elapsed * 1.3) * 0.16
    }
    this.lens.rotation.z = Math.sin(elapsed * 0.11) * 0.045 - this.scroll * 0.18
    this.lens.rotation.x = this.pointer.y * 0.1 + this.scroll * 0.12
    this.lens.rotation.y = this.pointer.x * 0.12 - this.scroll * 0.2
    this.network.rotation.y = Math.sin(elapsed * 0.12 + 0.5) * 0.12 + this.pointer.x * 0.08
    this.network.rotation.x = Math.sin(elapsed * 0.08) * 0.08 + this.pointer.y * 0.05
    this.network.rotation.z = Math.sin(elapsed * 0.16 + 1.1) * 0.025
    this.assembly.rotation.set(pitch, yaw, roll)
    this.assembly.position.y = Math.sin(elapsed * 0.13 + 1.9) * 0.045
    this.assembly.position.z = Math.sin(elapsed * 0.19 + 0.7) * 0.16
    this.root.scale.setScalar(this.baseScale * scalePulse)
    this.root.rotation.z = -this.scroll * 0.08
    this.edgeMaterial.opacity = 0.19 + Math.sin(elapsed * 0.72) * 0.035
    this.dustMaterial.opacity = 0.3 + Math.sin(elapsed * 0.31) * 0.05
    this.camera.position.x = this.pointer.x * 0.18
    this.camera.position.y = this.pointer.y * 0.12 - this.scroll * 0.16
    this.camera.position.z = 11.4 + this.scroll * 0.7
    this.camera.lookAt(0.4, -0.1, 0)
    this.renderer.render(this.scene, this.camera)
  }

  destroy() {
    this.stop()
    this.destroyed = true
    this.scene.traverse((object) => {
      const renderable = object as THREE.Object3D & {
        geometry?: THREE.BufferGeometry
        material?: THREE.Material | THREE.Material[]
      }
      renderable.geometry?.dispose()
      if (renderable.material) {
        const material = renderable.material
        if (Array.isArray(material)) material.forEach((entry) => entry.dispose())
        else material.dispose()
      }
    })
    this.timer.dispose()
    this.environmentTexture?.dispose()
    this.renderer.dispose()
  }
}
