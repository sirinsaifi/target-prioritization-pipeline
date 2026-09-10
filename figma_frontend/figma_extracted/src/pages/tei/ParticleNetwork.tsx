import { useEffect, useRef } from 'react'

/* ─── Animated particle network (landing page background) ───────────────────
 *
 * A lightweight, dependency-free canvas animation inspired by the structure
 * of Open Targets Platform's landing background (a field of connected dots)
 * but with our OWN pink palette and our OWN motion characteristics — not a
 * copy. Uses requestAnimationFrame for 60fps performance with no heavy
 * library (no particles.js / tsparticles / three.js import needed).
 *
 * Visual design decisions:
 * - Deep rose background (#2a0a1a) — clearly NOT OTP's blue.
 * - ~70 small particles that drift slowly and wrap around screen edges.
 * - Thin, soft-opacity pink lines connect particles within ~110px of each
 *   other; line opacity fades with distance so the network feels alive but
 *   never busy. Movement speed is deliberately gentle (max 0.35 px/frame).
 * - Particle size varies slightly (0.5–1.7px radius) for organic texture.
 * - Full viewport, fixed position, z-index 0 (behind all content).
 */

const PARTICLE_COUNT = 70
const MAX_CONNECTION_DIST = 110
const MAX_SPEED = 0.35       // px per frame — slow, gentle drift
const NODE_BASE_ALPHA = 0.45 // base opacity for particle dots

export default function ParticleNetwork() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    /* Resize canvas to fill the viewport (also handles devicePixelRatio for
       crispness on retina screens without changing the visual density). */
    const resize = () => {
      const dpr = window.devicePixelRatio || 1
      canvas.width = window.innerWidth * dpr
      canvas.height = window.innerHeight * dpr
      canvas.style.width = `${window.innerWidth}px`
      canvas.style.height = `${window.innerHeight}px`
      ctx.scale(dpr, dpr)
    }
    resize()
    window.addEventListener('resize', resize)

    type Particle = {
      x: number
      y: number
      vx: number
      vy: number
      radius: number
    }

    const particles: Particle[] = []
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        vx: (Math.random() - 0.5) * MAX_SPEED * 2,
        vy: (Math.random() - 0.5) * MAX_SPEED * 2,
        radius: Math.random() * 1.2 + 0.5,
      })
    }

    /* RGB values for our pink palette (parsed once, used per-frame via
       rgba() strings). */
    const NODE_RGB = '244, 114, 182'   // pink-400
    const LINE_RGB = '219, 39, 119'    // pink-600 — slightly deeper for contrast

    /* The canvas 2D context cannot resolve CSS variables, so the deep-rose
       background color is read once from the stylesheet rather than
       hardcoting the hex in two places. */
    const root = getComputedStyle(document.documentElement)
    const bgHex = root.getPropertyValue('--landing-bg').trim() || '#2a0a1a'

    let rafId: number

    function animate() {
      const w = window.innerWidth
      const h = window.innerHeight

      /* Full-opaque deep-rose fill each frame — no motion trails, keeping
         the background subtle and non-distracting. */
      ctx.fillStyle = bgHex
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      /* --- Update positions (slow drift with screen-edge wrap) --- */
      for (const p of particles) {
        p.x += p.vx
        p.y += p.vy

        /* Wrap around — gives the "infinite space" feel without particles
           ever leaving the visible area. */
        if (p.x < 0) p.x = w
        if (p.x > w) p.x = 0
        if (p.y < 0) p.y = h
        if (p.y > h) p.y = 0
      }

      /* --- Draw connecting lines (faded with distance) --- */
      ctx.lineWidth = 0.8
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < MAX_CONNECTION_DIST) {
            /* Opacity ramps from ~0.20 at the far edge to ~0.0 at the
               max distance — keeps lines barely perceptible unless you
               look for them. */
            const alpha = (1 - dist / MAX_CONNECTION_DIST) * 0.2
            ctx.strokeStyle = `rgba(${LINE_RGB}, ${alpha})`
            ctx.beginPath()
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.stroke()
          }
        }
      }

      /* --- Draw particle nodes --- */
      for (const p of particles) {
        const alpha = NODE_BASE_ALPHA + p.radius * 0.15
        ctx.fillStyle = `rgba(${NODE_RGB}, ${alpha})`
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
        ctx.fill()
      }

      rafId = requestAnimationFrame(animate)
    }

    animate()

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 0,
        pointerEvents: 'none',
      }}
      aria-hidden="true"
    />
  )
}
