// Living ambient: the app's own background (the `.ambient` studio lamp in index.css) with the ember silk wave over it. The same three
// glows over warm charcoal (ember lamp top right, plum on the left, a warm floor), drifting and breathing through
// slow noise, with embers rising through it. Plain three.js r186, written to the CloudAI-X threejs-skills rules
// (.claude/skills/threejs-*): setAnimationLoop, THREE.Timer, a capped pixel ratio, full disposal on unmount.
// Honest motion: `live` is the only thing that makes it move. The splash is live; the app shell is live only while a
// job really runs, and otherwise holds one still frame, which at intensity 1 is pixel-for-pixel the CSS background.
import { useEffect, useRef } from 'react'
import * as THREE from 'three'

// 3D simplex noise: Ian McEwan and Stefan Gustavson (Ashima Arts / webgl-noise), MIT licence.
const NOISE = /* glsl */ `
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 10.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0))
    + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.5 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 105.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}
`

// A screen-filling quad: the vertex shader ignores the camera, so the glows always cover the whole canvas.
const AMBIENT_VERTEX = /* glsl */ `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`

// Each glow is a CSS radial-gradient: an ellipse (radii as a share of width and height) fading linearly from its
// colour to transparent at 70% of the radius, layered over the ground in CSS order. Blending stays in sRGB, as CSS
// gradients blend, so there is deliberately no colorspace include here: a still frame equals the CSS background.
const AMBIENT_FRAGMENT = /* glsl */ `
uniform float uTime;
uniform float uIntensity;
uniform float uMotion;
varying vec2 vUv;
${NOISE}
vec3 over(vec3 base, vec2 p, vec2 c, vec2 r, vec3 col, float a) {
  float k = clamp(1.0 - length((p - c) / r) / 0.7, 0.0, 1.0);
  return mix(base, col, clamp(a * k * uIntensity, 0.0, 1.0));
}
void main() {
  float t = uTime;
  vec2 p = vec2(vUv.x, 1.0 - vUv.y);  // CSS coordinates: y runs down
  // the light moves like smoke: a slow warp, never a visible pattern
  p += uMotion * 0.045 * vec2(snoise(vec3(p * 1.6, t * 0.05)), snoise(vec3(p * 1.6 + 7.3, t * 0.05)));
  float m = uMotion;
  vec3 col = vec3(13.0, 12.0, 11.0) / 255.0;  // --color-ground
  col = over(col, p, vec2(0.5 + m * 0.08 * sin(t * 0.11), 1.1 - m * 0.05 * sin(t * 0.07)),
             vec2(0.70, 0.60) * (1.0 + m * 0.08 * sin(t * 0.19)), vec3(120.0, 70.0, 40.0) / 255.0, 0.18);
  col = over(col, p, vec2(0.18 + m * 0.07 * sin(t * 0.09 + 1.0), 0.30 + m * 0.08 * sin(t * 0.13)),
             vec2(0.45, 0.50) * (1.0 + m * 0.10 * sin(t * 0.17 + 2.0)), vec3(150.0, 96.0, 120.0) / 255.0, 0.16);
  col = over(col, p, vec2(0.72 + m * 0.07 * sin(t * 0.08 + 3.0), 0.08 + m * 0.07 * sin(t * 0.12 + 1.0)),
             vec2(0.60, 0.55) * (1.0 + m * 0.10 * sin(t * 0.15)), vec3(240.0, 135.0, 58.0) / 255.0,
             0.20 * (1.0 + m * 0.18 * sin(t * 0.21)));
  // a whisper of dither: smooth gradients band on 8-bit displays without it
  col += (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) / 255.0;
  gl_FragColor = vec4(col, 1.0);
}
`

// The ember silk: a lit, slowly folding 3D surface laid over the glows, the app's wave.
const SILK_VERTEX = /* glsl */ `
uniform float uTime;
varying vec3 vWorld;
varying vec3 vNormal;
varying float vHeight;
varying vec2 vUv;
${NOISE}
// Long folds (the silk) over slow noise swells; the fold phase bends with the swell so folds never look ruled.
float height(vec2 p) {
  vec2 q = p * vec2(0.22, 0.38);
  float h = snoise(vec3(q + vec2(uTime * 0.05, 0.0), uTime * 0.06)) * 0.9;
  h += snoise(vec3(q * 2.1 + vec2(0.0, -uTime * 0.04), uTime * 0.09)) * 0.28;
  h += sin(p.x * 0.55 + p.y * 0.35 + uTime * 0.25 + h * 1.6) * 0.35;
  return h;
}
void main() {
  vec2 p = position.xy;
  float h = height(p);
  const float e = 0.05;  // finite differences give the displaced surface's own normal
  vec3 n = normalize(vec3(-(height(p + vec2(e, 0.0)) - h) / e, -(height(p + vec2(0.0, e)) - h) / e, 1.0));
  vec4 world = modelMatrix * vec4(p, h, 1.0);
  vWorld = world.xyz;
  vNormal = normalize(mat3(modelMatrix) * n);  // world space, to match cameraPosition
  vHeight = h;
  vUv = uv;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`

const SILK_FRAGMENT = /* glsl */ `
uniform vec3 uGround;
uniform vec3 uDeep;
uniform vec3 uEmber;
uniform vec3 uGlow;
uniform float uIntensity;
varying vec3 vWorld;
varying vec3 vNormal;
varying float vHeight;
varying vec2 vUv;
void main() {
  vec3 n = normalize(vNormal);
  vec3 v = normalize(cameraPosition - vWorld);
  vec3 l = normalize(vec3(0.55, 0.9, 0.4));  // the warm key from the upper right, where the studio lamp sits
  float diffuse = max(dot(n, l), 0.0);
  float fresnel = pow(1.0 - max(dot(n, v), 0.0), 3.0);
  float spec = pow(max(dot(n, normalize(l + v)), 0.0), 64.0);
  float ridge = smoothstep(-0.2, 1.1, vHeight);
  vec3 col = mix(uGround, uDeep, diffuse * 0.85 + ridge * 0.3);
  col += uEmber * (fresnel * 0.55 + diffuse * ridge * 0.28);
  col += uGlow * spec * 0.6;
  // the cloth dissolves into the glows at its edges, so there is never a visible border
  float edge = smoothstep(0.0, 0.3, vUv.y) * smoothstep(1.0, 0.72, vUv.y)
    * smoothstep(0.0, 0.18, vUv.x) * smoothstep(1.0, 0.82, vUv.x);
  gl_FragColor = vec4(col, edge * uIntensity);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
  #include <premultiplied_alpha_fragment>
}
`

const EMBER_VERTEX = /* glsl */ `
uniform float uTime;
uniform float uPixelRatio;
attribute vec3 aSeed;
varying float vAlpha;
void main() {
  float rise = 0.1 + aSeed.z * 0.16;
  float y = mod(aSeed.y * 6.0 + uTime * rise, 6.0);
  vec3 p = vec3((aSeed.x - 0.5) * 12.0 + sin(uTime * 0.4 + aSeed.x * 40.0) * 0.18, y - 2.2, (aSeed.z - 0.5) * 5.0);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = (2.0 + aSeed.z * 4.0) * uPixelRatio * (6.0 / -mv.z);
  vAlpha = sin(y / 6.0 * 3.14159) * (0.35 + aSeed.x * 0.65);  // fade in low, out near the top
}
`

const EMBER_FRAGMENT = /* glsl */ `
uniform float uGlow;
varying float vAlpha;
void main() {
  float a = smoothstep(0.5, 0.0, length(gl_PointCoord - 0.5)) * vAlpha * uGlow;
  gl_FragColor = vec4(vec3(240.0, 135.0, 58.0) / 255.0, a);
}
`

const EMBERS = 120
const ease = (dt: number) => Math.min(1, dt * 1.8)  // ~1.5 s to settle: motion eases in and out, never snaps

/** `intensity` brightens the glows (1 = exactly the CSS background); `wave` is the silk's strength (0 hides it). */
export default function Ember({ live, intensity = 1, embers = true, wave = 0.8 }: {
  live: boolean; intensity?: number; embers?: boolean; wave?: number
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  // the loop reads the latest props from here, so prop changes never rebuild the renderer
  const props = useRef({ live, intensity, embers, wave })
  const api = useRef<{ wake: () => void }>(undefined)
  props.current = { live, intensity, embers, wave }

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    // a fresh canvas per mount: cleanup force-loses the context, and a lost canvas reused by the next mount (React
    // StrictMode mounts twice in dev) paints white instead of the scene
    const canvas = document.createElement('canvas')
    canvas.className = 'absolute inset-0 size-full'
    host.appendChild(canvas)
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'low-power' })
    } catch {
      canvas.remove()
      return  // no WebGL: the CSS ambient underneath stays, nothing else changes
    }
    // if the GPU drops the context (driver reset, sleep), hide the canvas: the CSS ambient shows, never a blank
    const lost = () => { canvas.style.visibility = 'hidden' }
    const restored = () => { canvas.style.visibility = ''; wake() }
    canvas.addEventListener('webglcontextlost', lost)
    canvas.addEventListener('webglcontextrestored', restored)
    // the silk's fold edges need the display's real resolution plus MSAA to read as clean curves (at 1 CSS pixel they
    // stair-stepped on scaled displays); capped at 2 for fill rate (threejs-performance), and at rest it is one frame
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 50)
    camera.position.set(0, 1.5, 5.5)
    camera.lookAt(0, -0.45, 0)
    const ambient = new THREE.ShaderMaterial({
      vertexShader: AMBIENT_VERTEX, fragmentShader: AMBIENT_FRAGMENT, depthTest: false, depthWrite: false,
      uniforms: { uTime: { value: 14 }, uIntensity: { value: props.current.intensity }, uMotion: { value: 0 } },
    })
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), ambient)
    quad.frustumCulled = false
    quad.renderOrder = -1
    scene.add(quad)

    const sparks = new THREE.ShaderMaterial({
      vertexShader: EMBER_VERTEX, fragmentShader: EMBER_FRAGMENT, transparent: true, depthTest: false,
      depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { uTime: { value: 14 }, uPixelRatio: { value: renderer.getPixelRatio() }, uGlow: { value: 0 } },
    })
    const seeds = new THREE.BufferGeometry()
    seeds.setAttribute('position', new THREE.BufferAttribute(new Float32Array(EMBERS * 3), 3))  // placed in the shader
    seeds.setAttribute('aSeed', new THREE.BufferAttribute(new Float32Array(EMBERS * 3).map(() => Math.random()), 3))
    const points = new THREE.Points(seeds, sparks)
    points.frustumCulled = false
    scene.add(points)

    const silk = new THREE.ShaderMaterial({
      vertexShader: SILK_VERTEX, fragmentShader: SILK_FRAGMENT, transparent: true, premultipliedAlpha: true,
      depthTest: false, depthWrite: false,
      uniforms: {
        uTime: { value: 14 }, uIntensity: { value: props.current.wave },
        uGround: { value: new THREE.Color('#0d0c0b') }, uDeep: { value: new THREE.Color('#3a1e0e') }, uEmber: { value: new THREE.Color('#f0873a') },
        uGlow: { value: new THREE.Color('#ffc896') },
      },
    })
    // fine enough that the fold silhouettes trace curves, not facets
    const cloth = new THREE.Mesh(new THREE.PlaneGeometry(16, 9, 360, 200), silk)
    cloth.rotation.x = -1.12
    cloth.position.set(0, -0.7, 0)
    cloth.frustumCulled = false
    scene.add(cloth)
    points.renderOrder = 1  // embers rise in front of the cloth

    const state = { time: 14, motion: 0, glow: 0, idleFor: 0 }
    const timer = new THREE.Timer()
    timer.connect(document)  // pauses with the page, so a hidden window never jumps ahead on return

    const frame = (timestamp?: number) => {
      timer.update(timestamp)
      const dt = Math.min(timer.getDelta(), 0.1)
      const p = props.current
      const moving = p.live && !reduced.matches
      state.motion += ((moving ? 1 : 0) - state.motion) * ease(dt)
      state.glow += ((moving && p.embers ? p.intensity : 0) - state.glow) * ease(dt)
      state.time += dt * state.motion
      ambient.uniforms.uTime.value = state.time
      ambient.uniforms.uMotion.value = state.motion
      ambient.uniforms.uIntensity.value = p.intensity
      sparks.uniforms.uTime.value = state.time
      sparks.uniforms.uGlow.value = state.glow
      silk.uniforms.uTime.value = state.time
      silk.uniforms.uIntensity.value = p.wave
      cloth.visible = p.wave > 0  // no wave (the splash): skip the cloth's draw entirely
      renderer.render(scene, camera)
      // once settled at rest, stop the loop entirely: the last frame stays on the canvas
      state.idleFor = moving || state.motion > 0.002 || state.glow > 0.002 ? 0 : state.idleFor + dt
      if (state.idleFor > 0.25) renderer.setAnimationLoop(null)
    }
    const wake = () => { state.idleFor = 0; renderer.setAnimationLoop(frame) }
    api.current = { wake }

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = canvas
      if (!w || !h) return
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      frame()  // a still frame at the new size, even while the loop is stopped
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    reduced.addEventListener('change', wake)
    wake()

    return () => {
      canvas.removeEventListener('webglcontextlost', lost)
      canvas.removeEventListener('webglcontextrestored', restored)
      observer.disconnect()
      reduced.removeEventListener('change', wake)
      api.current = undefined
      renderer.setAnimationLoop(null)
      timer.dispose()
      quad.geometry.dispose(); ambient.dispose()
      seeds.dispose(); sparks.dispose()
      cloth.geometry.dispose(); silk.dispose()
      renderer.dispose()
      renderer.forceContextLoss()
      canvas.remove()
    }
  }, [])

  // a prop change (a job starting or ending) restarts the loop so the motion can ease to its new target
  useEffect(() => { api.current?.wake() }, [live, intensity, embers, wave])

  return <div ref={hostRef} aria-hidden className="pointer-events-none absolute inset-0" />
}
