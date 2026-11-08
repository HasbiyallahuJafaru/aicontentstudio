import * as THREE from 'three'

/** The hero's story in one loop (about 10 s): the app's real renders sit edge to edge as one long film strip (the
 *  long video), a lime playhead sweeps across and cuts it, the pieces lift into a fan of finished posts, rest, and
 *  fold back. Rounded corners and soft shadows are drawn in the shaders so the strip can start square and round off
 *  as it is cut. Pauses off-screen; under reduced motion it renders the fan once, still. */

const N = 5
const W = 1, H = 1.25                     // the renders are 4:5
const GAP = 0.12                          // space a cut opens between two pieces
const LOOP = 10.4
const ACCENT = new THREE.Color('#c6f432')

const vertex = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`

const sdf = /* glsl */ `
  float sdRound(vec2 p, vec2 b, float r) { vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }`

const cardFragment = /* glsl */ `
  varying vec2 vUv;
  uniform sampler2D map; uniform vec2 size; uniform float radius; uniform float shade; uniform float rim;
  ${sdf}
  void main() {
    float d = sdRound((vUv - 0.5) * size, size * 0.5, radius);
    float aa = fwidth(d);
    vec4 c = texture2D(map, vUv);
    // rim: a hairline of light at the edge so dark cards separate from a dark page
    vec3 col = mix(c.rgb * shade, vec3(1.0), rim * (1.0 - smoothstep(0.0, 0.012, -d)));
    gl_FragColor = vec4(col, 1.0 - smoothstep(-aa, aa, d));
    #include <colorspace_fragment>
  }`

const shadowFragment = /* glsl */ `
  varying vec2 vUv;
  uniform vec2 size; uniform float strength; uniform vec3 tint;
  ${sdf}
  void main() {
    float d = sdRound((vUv - 0.5) * size, size * 0.5 - 0.22, 0.12);
    gl_FragColor = vec4(tint, (1.0 - smoothstep(-0.2, 0.22, d)) * strength);
  }`

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const easeInOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)
const easeOut = (x: number) => 1 - Math.pow(1 - x, 4)
const span = (t: number, a: number, b: number) => clamp01((t - a) / (b - a))

export function mountHero(canvas: HTMLCanvasElement, urls: string[]): () => void {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
  const dark = matchMedia('(prefers-color-scheme: dark)')
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2))

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 60)
  const rig = new THREE.Group()
  scene.add(rig)

  const manager = new THREE.LoadingManager()
  const loader = new THREE.TextureLoader(manager)
  const cardGeo = new THREE.PlaneGeometry(W, H)
  const shadowGeo = new THREE.PlaneGeometry(W + 0.9, H + 0.9)
  const shadowTint = new THREE.Color()
  let cards: { holder: THREE.Group; material: THREE.ShaderMaterial; shadow: THREE.ShaderMaterial }[] = []
  const paintShadow = () => {
    shadowTint.set(dark.matches ? '#000000' : '#1b2a10')
    cards.forEach(({ material }) => { material.uniforms.rim.value = dark.matches ? 0.22 : 0 })
  }

  cards = Array.from({ length: N }, (_, i) => {
    const map = loader.load(urls[i % urls.length], (t) => { t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8 })
    const material = new THREE.ShaderMaterial({
      uniforms: { map: { value: map }, size: { value: new THREE.Vector2(W, H) }, radius: { value: 0 }, shade: { value: 1 }, rim: { value: 0 } },
      vertexShader: vertex, fragmentShader: cardFragment, transparent: true,
    })
    const shadow = new THREE.Mesh(shadowGeo, new THREE.ShaderMaterial({
      uniforms: { size: { value: new THREE.Vector2(W + 0.9, H + 0.9) }, strength: { value: 0 }, tint: { value: shadowTint } },
      vertexShader: vertex, fragmentShader: shadowFragment, transparent: true, depthWrite: false,
    }))
    const card = new THREE.Mesh(cardGeo, material)
    const holder = new THREE.Group()
    shadow.position.set(0.04, -0.12, -0.06)
    holder.add(shadow, card)
    rig.add(holder)
    return { holder, material, shadow: shadow.material as THREE.ShaderMaterial }
  })

  paintShadow()

  // the playhead: a lime bar with a round head, riding just in front of the strip
  const playhead = new THREE.Group()
  const lineMat = new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0 })
  playhead.add(new THREE.Mesh(new THREE.PlaneGeometry(0.035, H + 0.3), lineMat))
  const head = new THREE.Mesh(new THREE.CircleGeometry(0.075, 32), lineMat)
  head.position.y = (H + 0.3) / 2
  playhead.add(head)
  playhead.position.z = 0.02
  rig.add(playhead)

  /** Fit by measurement: pose the loop's widest moments, project every card corner from a reference distance, and
   *  move the camera so the largest extent fills the canvas with a small margin. Works for any canvas shape. */
  const corner = new THREE.Vector3()
  function resize() {
    const { clientWidth: w, clientHeight: h } = canvas
    if (!w || !h) return
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.position.set(0, 0, 10)
    camera.updateProjectionMatrix()
    camera.updateMatrixWorld()
    const [px, py] = [pointer.x, pointer.y]
    pointer.x = pointer.y = 0
    let ex = 0, ey = 0
    for (const at of [0.4, 2.2, 3.8, 6]) {
      pose(at, 0)
      rig.updateMatrixWorld(true)
      for (const { holder } of cards) {
        const mesh = holder.children[1]
        for (const [cx, cy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
          corner.set((cx * W) / 2, (cy * H) / 2, 0).applyMatrix4(mesh.matrixWorld).project(camera)
          ex = Math.max(ex, Math.abs(corner.x))
          ey = Math.max(ey, Math.abs(corner.y))
        }
      }
    }
    pointer.x = px; pointer.y = py
    camera.position.z = 10 * Math.max(ex / 0.92, ey / 0.8)
  }

  const pointer = { x: 0, y: 0, tx: 0, ty: 0 }
  const onPointer = (e: PointerEvent) => {
    pointer.tx = (e.clientX / innerWidth) * 2 - 1
    pointer.ty = (e.clientY / innerHeight) * 2 - 1
  }

  /** Every transform is a pure function of time t in the loop, so frames never drift and reduced motion can pose
   *  any moment. */
  function pose(t: number, elapsed: number) {
    const sweep = easeInOut(span(t, 1.1, 3.1))
    const back = easeInOut(span(t, 8.9, 10.2))
    const px = (-N / 2 - 0.15 + sweep * (N + 0.3)) * W
    const cut = Array.from({ length: N - 1 }, (_, j) => easeOut(span(px, (j - (N - 1) / 2 + 0.5) * W, (j - (N - 1) / 2 + 0.5) * W + 0.45)) * (1 - back))
    const total = cut.reduce((a, b) => a + b, 0)
    let before = 0
    let lifted = 0
    cards.forEach(({ holder, material, shadow }, i) => {
      const c = i - (N - 1) / 2
      const lift = easeInOut(span(t, 3.0 + i * 0.09, 4.5 + i * 0.09)) * (1 - easeInOut(span(t, 8.9 + (N - 1 - i) * 0.05, 10.1 + (N - 1 - i) * 0.05)))
      lifted += lift / N
      const stripX = c * W + (before - total / 2) * GAP
      before += cut[i] ?? 0
      const bob = Math.sin(elapsed * 1.1 + i * 0.9) * 0.035 * lift
      holder.position.set(
        THREE.MathUtils.lerp(stripX, c * 1.08, lift),
        THREE.MathUtils.lerp(0, -c * c * 0.05 + 0.12, lift) + bob,
        THREE.MathUtils.lerp(0, -Math.abs(c) * 0.42 + 0.3, lift),
      )
      holder.rotation.set(0, THREE.MathUtils.lerp(0, -c * 0.1, lift), THREE.MathUtils.lerp(0, -c * 0.075, lift))
      const edge = Math.max(cut[i - 1] ?? 0, cut[i] ?? 0)
      material.uniforms.radius.value = 0.075 * Math.max(edge, lift)
      material.uniforms.shade.value = 1 - 0.07 * Math.abs(c) * lift
      shadow.uniforms.strength.value = 0.16 + 0.22 * lift
    })
    playhead.position.x = px
    lineMat.opacity = span(t, 0.8, 1.15) * (1 - span(t, 3.0, 3.4))
    // the strip lies in perspective; the fan faces the viewer and follows the pointer
    rig.rotation.set(
      THREE.MathUtils.lerp(-0.16, 0, lifted) + pointer.y * 0.12,
      THREE.MathUtils.lerp(-0.5, 0, lifted) + pointer.x * 0.22,
      THREE.MathUtils.lerp(0.2, 0, lifted),
    )
    rig.position.y = THREE.MathUtils.lerp(0.05, -0.05, lifted)
  }

  const timer = new THREE.Timer()
  timer.connect(document)
  let t = 0.3
  function frame() {
    timer.update()
    const delta = Math.min(timer.getDelta(), 0.05)
    t = (t + delta) % LOOP
    pointer.x = THREE.MathUtils.damp(pointer.x, pointer.tx, 3, delta)
    pointer.y = THREE.MathUtils.damp(pointer.y, pointer.ty, 3, delta)
    pose(t, timer.getElapsed())
    renderer.render(scene, camera)
  }
  const still = () => { pose(6, 0); renderer.render(scene, camera) }

  const resizer = new ResizeObserver(() => { resize(); if (reduce) still() })
  resizer.observe(canvas)
  resize()
  let visible = true
  const watcher = new IntersectionObserver(([e]) => {
    visible = e.isIntersecting
    if (!reduce) renderer.setAnimationLoop(visible ? frame : null)
  })
  const onScheme = () => { paintShadow(); if (reduce) still() }
  dark.addEventListener('change', onScheme)

  manager.onLoad = () => {
    canvas.classList.add('ready')
    if (reduce) { still(); return }
    addEventListener('pointermove', onPointer, { passive: true })
    watcher.observe(canvas)
    if (visible) renderer.setAnimationLoop(frame)
  }

  return () => {
    renderer.setAnimationLoop(null)
    resizer.disconnect()
    watcher.disconnect()
    removeEventListener('pointermove', onPointer)
    dark.removeEventListener('change', onScheme)
    timer.dispose()
    cards.forEach(({ material, shadow }) => { material.uniforms.map.value.dispose(); material.dispose(); shadow.dispose() })
    cardGeo.dispose(); shadowGeo.dispose(); lineMat.dispose()
    renderer.dispose()
  }
}
