import * as THREE from "three"
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js"
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js"

interface LoupeFieldOptions {
  reducedMotion: boolean
}

function damp(current: number, target: number, lambda: number, delta: number) {
  return THREE.MathUtils.lerp(current, target, 1 - Math.exp(-lambda * delta))
}

export class LoupeField {
  private readonly canvas: HTMLCanvasElement
  private readonly renderer: THREE.WebGLRenderer
  private readonly scene = new THREE.Scene()
  private readonly camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100)
  private readonly timer = new THREE.Timer()
  private readonly root = new THREE.Group()
  private readonly reducedMotion: boolean
  private environmentTexture: THREE.Texture | null = null
  private lensTexture: THREE.CanvasTexture | null = null
  private frameId = 0
  private running = false
  private destroyed = false
  private pointerTarget = new THREE.Vector2()
  private pointer = new THREE.Vector2()
  private scrollTarget = 0
  private scroll = 0
  private animationElapsed = 1.8

  constructor(canvas: HTMLCanvasElement, options: LoupeFieldOptions) {
    this.canvas = canvas
    this.reducedMotion = options.reducedMotion
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    })
    this.renderer.setClearColor(0x000000, 0)
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 0.94
    this.timer.connect(document)
    this.camera.position.set(0, 0, 9.8)

    this.createEnvironment()
    this.createLights()
    this.scene.add(this.root)
    this.loadHeroModel()
    this.resize()

    if (this.reducedMotion) this.render(this.animationElapsed)
  }

  private createEnvironment() {
    const environment = new RoomEnvironment()
    const generator = new THREE.PMREMGenerator(this.renderer)
    this.environmentTexture = generator.fromScene(environment, 0.035).texture
    this.scene.environment = this.environmentTexture
    environment.dispose()
    generator.dispose()
  }

  private createLights() {
    this.scene.add(new THREE.AmbientLight(0xf7f7f8, 1.05))

    const keyLight = new THREE.DirectionalLight(0xf7f7f8, 2.15)
    keyLight.position.set(-3.8, 4.5, 7)
    this.scene.add(keyLight)

    const redRim = new THREE.PointLight(0xe33b4c, 12, 16, 1.7)
    redRim.position.set(4.6, 2.8, 4.5)
    this.scene.add(redRim)

    const softFill = new THREE.PointLight(0xd7a1a8, 5, 15, 1.8)
    softFill.position.set(-4.2, -3.6, 3.2)
    this.scene.add(softFill)
  }

  private createLensTexture() {
    const surface = document.createElement("canvas")
    surface.width = 512
    surface.height = 512
    const context = surface.getContext("2d")
    if (!context) return null

    const base = context.createRadialGradient(176, 152, 22, 270, 270, 340)
    base.addColorStop(0, "#2b151c")
    base.addColorStop(0.32, "#180d11")
    base.addColorStop(0.72, "#0b080a")
    base.addColorStop(1, "#050607")
    context.fillStyle = base
    context.fillRect(0, 0, surface.width, surface.height)

    const sheen = context.createRadialGradient(146, 118, 0, 146, 118, 185)
    sheen.addColorStop(0, "rgba(247, 247, 248, 0.12)")
    sheen.addColorStop(0.36, "rgba(227, 59, 76, 0.045)")
    sheen.addColorStop(1, "rgba(7, 8, 10, 0)")
    context.fillStyle = sheen
    context.fillRect(0, 0, surface.width, surface.height)

    const texture = new THREE.CanvasTexture(surface)
    texture.colorSpace = THREE.SRGBColorSpace
    texture.anisotropy = Math.min(this.renderer.capabilities.getMaxAnisotropy(), 8)
    texture.needsUpdate = true
    this.lensTexture = texture
    return texture
  }

  private loadHeroModel() {
    const loader = new GLTFLoader()
    const url = `${import.meta.env.BASE_URL}models/loupe-magnifier-v2.glb`

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

        const opticalAnchor =
          importedScene.getObjectByName("Frame_Graphite") ??
          importedScene.getObjectByName("Optical_Bezel_Ivory") ??
          importedScene.getObjectByName("Optical_Glass")
        const opticalBounds = new THREE.Box3().setFromObject(opticalAnchor ?? importedScene)
        const opticalCenter = opticalBounds.getCenter(new THREE.Vector3())
        importedScene.position.sub(opticalCenter)
        importedScene.updateMatrixWorld(true)

        const centeredBounds = new THREE.Box3().setFromObject(importedScene)
        const size = centeredBounds.getSize(new THREE.Vector3())
        const normalized = new THREE.Group()
        normalized.name = "Loupe_Blender_Asset"
        normalized.scale.setScalar(4.15 / Math.max(size.x, size.y))
        normalized.add(importedScene)

        importedScene.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return
          object.castShadow = false
          object.receiveShadow = false

          if (object.name.includes("Optical_Glass")) {
            const previous = Array.isArray(object.material) ? object.material : [object.material]
            const texture = this.lensTexture ?? this.createLensTexture()
            object.material = new THREE.MeshBasicMaterial({
              color: 0xffffff,
              map: texture,
              toneMapped: true,
            })
            previous.forEach((material) => material.dispose())
            return
          }

          const materials = Array.isArray(object.material) ? object.material : [object.material]
          materials.forEach((material) => {
            if (material instanceof THREE.MeshStandardMaterial) {
              if (material.name.includes("Ivory")) {
                material.envMapIntensity = 0.62
                material.roughness = Math.max(material.roughness, 0.2)
              } else {
                material.envMapIntensity = 0.8
              }
              material.needsUpdate = true
            }
          })
        })

        this.root.add(normalized)
        this.canvas.dataset.model = "loaded"
        this.render(this.animationElapsed)
      },
      undefined,
      () => {
        this.canvas.dataset.model = "unavailable"
      }
    )
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
    if (this.reducedMotion) this.render(this.animationElapsed)
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return

    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.65))
    this.renderer.setSize(rect.width, rect.height, false)
    this.camera.aspect = rect.width / rect.height
    this.camera.updateProjectionMatrix()
    this.render(this.animationElapsed)
  }

  private frame = (timestamp: DOMHighResTimeStamp) => {
    if (!this.running || this.destroyed) return
    this.timer.update(timestamp)
    const delta = Math.min(this.timer.getDelta(), 0.05)
    this.animationElapsed += delta
    this.pointer.x = damp(this.pointer.x, this.pointerTarget.x, 3.8, delta)
    this.pointer.y = damp(this.pointer.y, this.pointerTarget.y, 3.8, delta)
    this.scroll = damp(this.scroll, this.scrollTarget, 2.8, delta)
    this.render(this.animationElapsed)
    this.frameId = requestAnimationFrame(this.frame)
  }

  private render(elapsed: number) {
    const idlePitch = Math.sin(elapsed * 0.29 + 0.8) * 0.028
    const idleYaw = Math.sin(elapsed * 0.23) * 0.052
    const idleRoll = Math.sin(elapsed * 0.17 + 1.4) * 0.012

    this.root.rotation.x = -0.035 + idlePitch + this.pointer.y * 0.105 + this.scroll * 0.045
    this.root.rotation.y = 0.065 + idleYaw + this.pointer.x * 0.135 - this.scroll * 0.075
    this.root.rotation.z =
      -0.012 + idleRoll + (this.pointer.x - this.pointer.y) * 0.012 - this.scroll * 0.055
    this.root.position.y = 0
    this.root.position.z = Math.sin(elapsed * 0.18 + 1.1) * 0.055

    this.camera.position.x = this.pointer.x * 0.055
    this.camera.position.y = this.pointer.y * 0.04 - this.scroll * 0.08
    this.camera.position.z = 9.8 + this.scroll * 0.28
    this.camera.lookAt(0, 0, 0)
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
    this.lensTexture?.dispose()
    this.environmentTexture?.dispose()
    this.renderer.dispose()
  }
}
