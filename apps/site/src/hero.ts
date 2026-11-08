import * as THREE from 'three'

/** The hero: an endless production line. Raw footage (the app's own looping clips, still playing) flows in from the
 *  left as a wide film strip; a lime playhead cuts each frame as it passes, wiping it into a finished post (a real
 *  render from the design engine); the post turns upright, lifts out of the strip and drifts off into depth. Tiles
 *  recycle, so it never stops. Scroll speed feeds the line, the pointer tilts it, and it pauses off-screen. Under
 *  reduced motion it draws one still frame. Rounded corners, shadows and the wipe are drawn in the shaders. */

const M = 18                         // tiles on the line at once
const D = 1.78                       // distance between tile centres
const L = M * D                      // length of the line
const RAW = new THREE.Vector2(1.6, 0.9)
const POST = new THREE.Vector2(1.1, 1.375)
const CUT_X = -0.6                   // where the playhead stands
const CELL = 240                     // footage atlas cell
const ACCENT = new THREE.Color('#c6f432')

const vertex = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`

const sdf = /* glsl */ `
  float sdRound(vec2 p, vec2 b, float r) { vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
  vec2 cover(vec2 uv, vec2 size) {            // square source, any frame shape
    float a = size.x / size.y;
    return a > 1.0 ? vec2(uv.x, (uv.y - 0.5) / a + 0.5) : vec2((uv.x - 0.5) * a + 0.5, uv.y);
  }`

const tileFragment = /* glsl */ `
  varying vec2 vUv;
  uniform sampler2D atlas; uniform vec2 cell; uniform sampler2D post;
  uniform vec2 size; uniform float wipe; uniform float morph; uniform float alpha;
  uniform vec3 accent;
  ${sdf}
  void main() {
    float d = sdRound((vUv - 0.5) * size, size * 0.5, mix(0.05, 0.09, morph));
    float aa = fwidth(d);
    // raw: the footage frame, washed out like a source file; post: the finished render in full colour
    vec2 fuv = (cell + clamp(cover(vUv, size), 0.002, 0.998)) / vec2(4.0, 3.0);
    vec3 raw = texture2D(atlas, vec2(fuv.x, 1.0 - fuv.y)).rgb;
    raw = mix(vec3(dot(raw, vec3(0.299, 0.587, 0.114))), raw, 0.35) * 0.92 + 0.04;
    vec3 fin = texture2D(post, cover(vUv, size)).rgb;
    float edge = 1.0 - wipe;                    // the playhead crosses right to left in tile space
    float isPost = smoothstep(edge - 0.004, edge + 0.004, vUv.x);
    vec3 col = mix(raw, fin, isPost);
    // the cut itself: a lime seam riding the wipe, gone once the frame is through
    float seam = (1.0 - smoothstep(0.0, 0.012, abs(vUv.x - edge))) * step(0.001, wipe) * step(wipe, 0.999);
    col = mix(col, accent, seam);
    gl_FragColor = vec4(col, alpha * (1.0 - smoothstep(-aa, aa, d)));
    #include <colorspace_fragment>
  }`

const shadowFragment = /* glsl */ `
  varying vec2 vUv;
  uniform vec2 size; uniform float strength; uniform vec3 tint;
  ${sdf}
  void main() {
    vec2 s = size + 0.8;
    float d = sdRound((vUv - 0.5) * s, size * 0.5 - 0.1, 0.12);
    gl_FragColor = vec4(tint, (1.0 - smoothstep(-0.18, 0.3, d)) * strength);
  }`

const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const ease = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)
const smooth = (a: number, b: number, x: number) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t) }

type Decoder = { decode(o: { frameIndex: number }): Promise<{ image: CanvasImageSource & { close(): void } }>; tracks: { ready: Promise<void>; selectedTrack?: { frameCount: number } } }

/** The footage atlas: twelve looping clips drawn into one 4x3 canvas that is re-uploaded about 15 times a second.
 *  WebCodecs' ImageDecoder pulls frames straight from the animated WebP files; without it (Safari) the clips play as
 *  hidden <img> elements and their current frame is copied. */
function footageAtlas(urls: string[], onFrame: () => void) {
  const canvas = document.createElement('canvas')
  canvas.width = CELL * 4
  canvas.height = CELL * 3
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = '#2a2c30'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  const cellAt = (i: number) => [(i % 4) * CELL, Math.floor(i / 4) * CELL] as const
  const ID = (window as unknown as { ImageDecoder?: new (o: object) => Decoder }).ImageDecoder
  let tick: () => void

  if (ID) {
    const clips = urls.map((url) => {
      const clip = { decoder: undefined as Decoder | undefined, count: 1, frame: 0, busy: false }
      fetch(url).then((r) => r.arrayBuffer()).then(async (data) => {
        const decoder = new ID({ data, type: 'image/webp' })
        await decoder.tracks.ready
        clip.count = decoder.tracks.selectedTrack?.frameCount || 1
        clip.decoder = decoder
      }).catch(() => {})
      return clip
    })
    tick = () => clips.forEach((c, i) => {
      if (!c.decoder || c.busy) return
      c.busy = true
      c.decoder.decode({ frameIndex: c.frame }).then(({ image }) => {
        ctx.drawImage(image, ...cellAt(i), CELL, CELL)
        image.close()
        c.frame = (c.frame + 1) % c.count
        onFrame()
      }).catch(() => {}).finally(() => { c.busy = false })
    })
  } else {
    const holder = document.createElement('div')
    holder.style.cssText = 'position:fixed;left:0;top:0;width:4px;height:4px;overflow:hidden;opacity:0.01;pointer-events:none'
    const imgs = urls.map((u) => { const im = new Image(); im.src = u; im.width = im.height = 4; holder.append(im); return im })
    document.body.append(holder)
    tick = () => { imgs.forEach((im, i) => im.complete && ctx.drawImage(im, ...cellAt(i), CELL, CELL)); onFrame() }
  }
  return { canvas, tick }
}

export function mountHero(canvas: HTMLCanvasElement, renders: string[], footage: string[]) {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2))

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 80)
  const rig = new THREE.Group()
  scene.add(rig)

  const atlasTex = new THREE.CanvasTexture(document.createElement('canvas'))
  const atlas = footageAtlas(footage, () => { atlasTex.needsUpdate = true })
  atlasTex.image = atlas.canvas
  atlasTex.colorSpace = THREE.SRGBColorSpace
  atlasTex.needsUpdate = true

  const manager = new THREE.LoadingManager()
  const loader = new THREE.TextureLoader(manager)
  const posts = renders.map((u) => loader.load(u, (t) => { t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8 }))

  const plane = new THREE.PlaneGeometry(1, 1)
  const shadowTint = new THREE.Color('#1b2a10')
  const tiles = Array.from({ length: M }, (_, i) => {
    const size = new THREE.Vector2().copy(RAW)
    const material = new THREE.ShaderMaterial({
      uniforms: {
        atlas: { value: atlasTex }, cell: { value: new THREE.Vector2(i % 4, Math.floor(i / 4) % 3) },
        post: { value: posts[i % posts.length] }, size: { value: size }, wipe: { value: 0 }, morph: { value: 0 },
        alpha: { value: 1 }, accent: { value: ACCENT },
      },
      vertexShader: vertex, fragmentShader: tileFragment, transparent: true, depthWrite: false,
    })
    const shadow = new THREE.ShaderMaterial({
      uniforms: { size: { value: size }, strength: { value: 0 }, tint: { value: shadowTint } },
      vertexShader: vertex, fragmentShader: shadowFragment, transparent: true, depthWrite: false,
    })
    const card = new THREE.Mesh(plane, material)
    const shade = new THREE.Mesh(plane, shadow)
    shade.position.set(0.05, -0.14, -0.04)
    const holder = new THREE.Group()
    holder.add(shade, card)
    rig.add(holder)
    return { holder, card, shade, material, shadow, size, lap: 0 }
  })

  // the playhead: a lime bar with a round head, and a faint track the strip runs along
  const playhead = new THREE.Group()
  const lime = new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true })
  playhead.add(new THREE.Mesh(new THREE.PlaneGeometry(0.03, 1.5), lime))
  const head = new THREE.Mesh(new THREE.CircleGeometry(0.07, 40), lime)
  head.position.y = 0.75
  playhead.add(head)
  playhead.position.set(CUT_X, -0.25, 0.3)
  rig.add(playhead)

  /** One tile at path position s (0 enters at the far left, 1 leaves at the far right). Pure function of s and time,
   *  so a still frame and the live loop agree. */
  function place(tile: (typeof tiles)[number], s: number, time: number, index: number) {
    const x = (s - 0.5) * L + 2
    const half = RAW.x / 2
    const wipe = clamp01((x + half - CUT_X) / RAW.x)
    const after = x - CUT_X - half                       // distance past the cut once fully through
    const morph = ease(clamp01(after / 1.9))
    const out = clamp01(after / (L * 0.5))               // how far down the exit run

    tile.size.set(THREE.MathUtils.lerp(RAW.x, POST.x, morph), THREE.MathUtils.lerp(RAW.y, POST.y, morph))
    const bob = Math.sin(time * 1.2 + index * 1.7) * 0.06 * morph
    const sway = (index % 2 ? 1 : -1)
    tile.holder.position.set(
      x,
      THREE.MathUtils.lerp(-0.25, 0.32 + sway * 0.12, morph) + bob + out * out * 1.4,
      THREE.MathUtils.lerp(-Math.pow(Math.min(0, x - CUT_X) * 0.32, 2), 0.55, morph) - out * out * 7,
    )
    tile.holder.rotation.set(
      THREE.MathUtils.lerp(-0.18, 0, morph),
      THREE.MathUtils.lerp(0.32, -0.12, morph) - out * 0.5,
      sway * 0.06 * morph + Math.sin(time * 0.8 + index) * 0.02 * morph,
    )
    tile.card.scale.set(tile.size.x, tile.size.y, 1)
    tile.shade.scale.set(tile.size.x + 0.8, tile.size.y + 0.8, 1)
    tile.material.uniforms.wipe.value = wipe
    tile.material.uniforms.morph.value = morph
    const fade = smooth(0, 0.07, s) * (1 - smooth(0.9, 1, s))
    tile.material.uniforms.alpha.value = fade
    tile.shadow.uniforms.strength.value = (0.1 + 0.26 * morph) * fade
    tile.card.renderOrder = tile.shade.renderOrder = Math.round(tile.holder.position.z * 100)
  }

  const fit = () => {
    const { clientWidth: w, clientHeight: h } = canvas
    if (!w || !h) return
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    // frame about 12 units of the line across the widest screens, never fewer than ~6 on a phone
    const want = THREE.MathUtils.clamp(12 * Math.min(1, camera.aspect / 1.6) + 2, 6.5, 12.5)
    const hfov = 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect)
    camera.position.set(0.4, 0.55, (want / 2) / Math.tan(hfov / 2) + 0.6)
    camera.lookAt(0.4, 0.05, 0)
    camera.updateProjectionMatrix()
  }

  const pointer = { x: 0, y: 0, tx: 0, ty: 0 }
  const onPointer = (e: PointerEvent) => {
    pointer.tx = (e.clientX / innerWidth) * 2 - 1
    pointer.ty = (e.clientY / innerHeight) * 2 - 1
  }

  let progress = 0.31          // line position, in tiles
  let boost = 0
  let atlasClock = 0
  const timer = new THREE.Timer()
  timer.connect(document)

  function draw(time: number) {
    tiles.forEach((tile, i) => {
      const raw = (i + progress) / M
      const lap = Math.floor(raw)
      const s = raw - lap
      if (lap !== tile.lap) {      // a recycled tile enters with fresh footage and a fresh render
        tile.lap = lap
        const k = i + lap * M
        tile.material.uniforms.cell.value.set(((k * 5) % 12) % 4, Math.floor(((k * 5) % 12) / 4))
        tile.material.uniforms.post.value = posts[((k % posts.length) + posts.length) % posts.length]
      }
      place(tile, s, time, i)
    })
    rig.rotation.set(pointer.y * 0.06, pointer.x * 0.12, 0)
    lime.opacity = 0.85 + Math.sin(time * 3) * 0.15
    renderer.render(scene, camera)
  }

  function frame() {
    timer.update()
    const dt = Math.min(timer.getDelta(), 0.05)
    boost = THREE.MathUtils.damp(boost, 0, 2.5, dt)
    progress += dt * (0.32 + boost)
    pointer.x = THREE.MathUtils.damp(pointer.x, pointer.tx, 3, dt)
    pointer.y = THREE.MathUtils.damp(pointer.y, pointer.ty, 3, dt)
    atlasClock += dt
    if (atlasClock > 1 / 15) { atlasClock = 0; atlas.tick() }
    draw(timer.getElapsed())
  }

  const resizer = new ResizeObserver(() => { fit(); if (reduce) draw(0) })
  resizer.observe(canvas)
  fit()
  let visible = true
  const watcher = new IntersectionObserver(([e]) => {
    visible = e.isIntersecting
    if (!reduce) renderer.setAnimationLoop(visible ? frame : null)
  })

  manager.onLoad = () => {
    canvas.classList.add('ready')
    if (reduce) { atlas.tick(); setTimeout(() => draw(0), 400); return }
    addEventListener('pointermove', onPointer, { passive: true })
    watcher.observe(canvas)
    if (visible) renderer.setAnimationLoop(frame)
  }

  return {
    /** scroll velocity in px per frame-ish; fast scrolling runs the line faster */
    push(v: number) { boost = Math.min(4, boost + Math.abs(v) * 0.004) },
  }
}
