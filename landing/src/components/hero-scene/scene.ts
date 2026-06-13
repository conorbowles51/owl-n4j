/**
 * The Reveal — Arclight hero scene.
 *
 * A dark field of drifting evidence fragments. An arc of light sweeps
 * across it; where it passes, hidden structure illuminates — nodes flare,
 * edges draw themselves, and a knowledge graph settles into a quiet,
 * living constellation.
 *
 * Plain canvas 2D, no dependencies. DPR-aware, pausable, with a static
 * composed frame for prefers-reduced-motion.
 */

export interface SceneOptions {
  reducedMotion: boolean;
}

interface GraphNode {
  nx: number; // normalized 0..1
  ny: number;
  depth: number; // 0.4..1, affects size + parallax
  phase: number;
  angle: number; // angle from beam pivot, computed on layout
  discovered: boolean;
  lit: number; // 0..1 steady illumination
  flare: number; // transient burst, decays
}

interface GraphEdge {
  a: number;
  b: number;
  progress: number; // 0..1 draw-in
  active: boolean;
}

interface Fragment {
  nx: number;
  ny: number;
  depth: number;
  text: string;
  baseAlpha: number;
  phase: number;
  flickerSpeed: number;
  angle: number;
}

interface Pulse {
  edge: number;
  p: number;
  forward: boolean;
}

const FRAGMENT_POOL = [
  'WIRE 04-117 — $48,200.00',
  '03:41:07 UTC',
  'EXHIBIT 04-A',
  '+1 (609) 555-0144',
  '40.7357 N  74.1724 W',
  'ACCT ••4417',
  'CALL — 00:06:12',
  'BLUE FINCH LLC — REG. DE',
  'PG 4,217 / 9,880',
  'TOLL REC 14-0092',
  'IMG_2241 — GPS OK',
  'MANIFEST B-77 — 14.2T',
  'TXN REF 9921-AC',
  '▇▇▇▇ ▇▇▇▇▇▇ ▇▇▇',
  'LAT 39.9259  LNG -75.1196',
  'DEP. TR. 112:5-19',
  'CCTV CAM 12 — 02:13:55',
  'INV #20418 — NORTHSTAR',
  'ALPR HIT — RT 130 NB',
  'AUDIO_017.WAV — 41:06',
  'LEASE — CAMDEN YARD 7',
  'SUB. RET. 26-MJ-1187',
  '▇▇▇ ▇▇▇▇ ▇▇▇▇▇',
  'MSG 11,204 OF 12,118',
];

// Narrative timing (seconds)
const FRAG_FADE_START = 0.15;
const FRAG_FADE_DUR = 1.0;
const SWEEP_START = 1.0;
const SWEEP_DUR = 5.4;
const BEAM_FADE_DUR = 1.6;
const RESWEEP_PERIOD = 17;
const RESWEEP_DUR = 7;
const RESWEEP_INTENSITY = 0.32;

const SETTLED_LIT = 0.55;

function easeInOutSine(p: number): number {
  return (1 - Math.cos(Math.PI * p)) / 2;
}

function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}

/** Mulberry32 — deterministic layout per visit keeps QA sane. */
function makeRng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class RevealScene {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private beamCanvas: HTMLCanvasElement;
  private beamCtx: CanvasRenderingContext2D;
  private glowSprite: HTMLCanvasElement;

  private w = 0;
  private h = 0;
  private dpr = 1;

  private nodes: GraphNode[] = [];
  private edges: GraphEdge[] = [];
  private fragments: Fragment[] = [];
  private pulses: Pulse[] = [];

  private pivotX = 0;
  private pivotY = 0;
  private sweepFrom = 0;
  private sweepTo = 0;

  private elapsed = 0;
  private lastFrameTime = 0;
  private raf = 0;
  private running = false;
  private destroyed = false;

  private pointerX = 0;
  private pointerY = 0;
  private parallaxX = 0;
  private parallaxY = 0;

  private nextPulseAt = 0;
  private narrow = false;

  private readonly reducedMotion: boolean;

  constructor(canvas: HTMLCanvasElement, opts: SceneOptions) {
    this.canvas = canvas;
    this.reducedMotion = opts.reducedMotion;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('canvas 2d context unavailable');
    this.ctx = ctx;

    this.beamCanvas = document.createElement('canvas');
    this.beamCtx = this.beamCanvas.getContext('2d')!;
    this.glowSprite = RevealScene.makeGlowSprite();

    this.resize();
  }

  /* ---------------- public api ---------------- */

  resize(): void {
    const parent = this.canvas.parentElement;
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.w = rect.width;
    this.h = rect.height;
    this.canvas.width = Math.round(this.w * this.dpr);
    this.canvas.height = Math.round(this.h * this.dpr);
    this.canvas.style.width = `${this.w}px`;
    this.canvas.style.height = `${this.h}px`;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);

    // beam layer at half resolution — it is pure soft gradient
    this.beamCanvas.width = Math.max(1, Math.round(this.w / 2));
    this.beamCanvas.height = Math.max(1, Math.round(this.h / 2));

    this.narrow = this.w < 760;
    this.pivotX = -0.06 * this.w;
    this.pivotY = 1.14 * this.h;

    if (this.nodes.length === 0) {
      this.generate();
    }
    this.layout();

    if (this.reducedMotion) {
      this.renderStatic();
    }
  }

  start(): void {
    if (this.destroyed || this.running) return;
    if (this.reducedMotion) {
      this.renderStatic();
      return;
    }
    this.running = true;
    this.lastFrameTime = performance.now();
    this.raf = requestAnimationFrame(this.frame);
  }

  stop(): void {
    this.running = false;
    cancelAnimationFrame(this.raf);
  }

  destroy(): void {
    this.stop();
    this.destroyed = true;
  }

  /** Pointer in normalized device coords, -1..1 both axes. */
  setPointer(x: number, y: number): void {
    this.pointerX = x;
    this.pointerY = y;
  }

  /* ---------------- generation ---------------- */

  private generate(): void {
    const rng = makeRng(0x0a4c);
    const area = this.w * this.h;
    const nodeCount = Math.round(clamp(area / 30000, 26, 56));
    const fragCount = Math.round(clamp(area / 34000, 22, 60));

    // Nodes: min-distance rejection sampling, biased right on wide screens
    // so the headline owns the left.
    const placed: GraphNode[] = [];
    const aspect = this.w / this.h;
    // tall narrow screens need tighter packing or sampling starves
    const minDist = this.narrow ? 0.1 : 0.13;
    let guard = 0;
    while (placed.length < nodeCount && guard < 4000) {
      guard++;
      const u = rng();
      const nx = this.narrow ? 0.06 + rng() * 0.88 : 0.18 + Math.pow(u, 0.62) * 0.78;
      const ny = 0.07 + rng() * 0.84;
      let ok = true;
      for (const p of placed) {
        const dx = (nx - p.nx) * aspect;
        const dy = ny - p.ny;
        if (dx * dx + dy * dy < minDist * minDist) {
          ok = false;
          break;
        }
      }
      if (!ok) continue;
      placed.push({
        nx,
        ny,
        depth: 0.4 + rng() * 0.6,
        phase: rng() * Math.PI * 2,
        angle: 0,
        discovered: false,
        lit: 0,
        flare: 0,
      });
    }
    this.nodes = placed;

    // Edges: nearest neighbor plus a few short extras, degree-capped.
    const degree = new Array(placed.length).fill(0);
    const edgeSet = new Set<string>();
    const edges: GraphEdge[] = [];
    const addEdge = (a: number, b: number) => {
      const key = a < b ? `${a}-${b}` : `${b}-${a}`;
      if (a === b || edgeSet.has(key) || degree[a] >= 4 || degree[b] >= 4) return;
      edgeSet.add(key);
      degree[a]++;
      degree[b]++;
      edges.push({ a, b, progress: 0, active: false });
    };
    const distSq = (i: number, j: number) => {
      const dx = (placed[i].nx - placed[j].nx) * aspect;
      const dy = placed[i].ny - placed[j].ny;
      return dx * dx + dy * dy;
    };
    for (let i = 0; i < placed.length; i++) {
      const byDist = placed
        .map((_, j) => j)
        .filter((j) => j !== i)
        .sort((a, b) => distSq(i, a) - distSq(i, b));
      addEdge(i, byDist[0]);
      if (rng() < 0.55 && byDist[1] !== undefined) addEdge(i, byDist[1]);
      if (rng() < 0.18 && byDist[2] !== undefined) addEdge(i, byDist[2]);
    }
    this.edges = edges;

    // Fragments: everywhere, faint, deterministic shuffle of the pool.
    const frags: Fragment[] = [];
    for (let i = 0; i < fragCount; i++) {
      frags.push({
        nx: 0.02 + rng() * 0.96,
        ny: 0.04 + rng() * 0.92,
        depth: 0.3 + rng() * 0.7,
        text: FRAGMENT_POOL[Math.floor(rng() * FRAGMENT_POOL.length)],
        baseAlpha: 0.045 + rng() * 0.065,
        phase: rng() * Math.PI * 2,
        flickerSpeed: 0.15 + rng() * 0.3,
        angle: 0,
      });
    }
    this.fragments = frags;
  }

  /** Recompute pixel-space-dependent values (angles from pivot). */
  private layout(): void {
    let minA = Infinity;
    let maxA = -Infinity;
    for (const n of this.nodes) {
      n.angle = Math.atan2(n.ny * this.h - this.pivotY, n.nx * this.w - this.pivotX);
      if (n.angle < minA) minA = n.angle;
      if (n.angle > maxA) maxA = n.angle;
    }
    for (const f of this.fragments) {
      f.angle = Math.atan2(f.ny * this.h - this.pivotY, f.nx * this.w - this.pivotX);
    }
    this.sweepFrom = minA - 0.22;
    this.sweepTo = maxA + 0.14;
  }

  /* ---------------- frame loop ---------------- */

  private frame = (now: number): void => {
    if (!this.running || this.destroyed) return;
    const dt = clamp((now - this.lastFrameTime) / 1000, 0, 0.05);
    this.lastFrameTime = now;
    this.elapsed += dt;
    this.update(dt);
    this.draw();
    this.raf = requestAnimationFrame(this.frame);
  };

  /** Beam angle + intensity for the current moment, or null when dark. */
  private beamState(): { theta: number; intensity: number } | null {
    const t = this.elapsed;
    const firstEnd = SWEEP_START + SWEEP_DUR;

    if (t >= SWEEP_START && t < firstEnd) {
      const p = (t - SWEEP_START) / SWEEP_DUR;
      const fadeIn = clamp((t - SWEEP_START) / 0.8, 0, 1);
      return {
        theta: this.sweepFrom + (this.sweepTo - this.sweepFrom) * easeInOutSine(p),
        intensity: fadeIn,
      };
    }
    if (t >= firstEnd && t < firstEnd + BEAM_FADE_DUR) {
      const fade = 1 - (t - firstEnd) / BEAM_FADE_DUR;
      return { theta: this.sweepTo, intensity: fade * fade };
    }
    // ambient re-sweeps, much fainter
    if (t >= firstEnd + BEAM_FADE_DUR) {
      const phase = (t - firstEnd - BEAM_FADE_DUR) % RESWEEP_PERIOD;
      if (phase > RESWEEP_PERIOD - RESWEEP_DUR) {
        const p = (phase - (RESWEEP_PERIOD - RESWEEP_DUR)) / RESWEEP_DUR;
        const envelope = Math.sin(Math.PI * p); // fade in and out
        return {
          theta: this.sweepFrom + (this.sweepTo - this.sweepFrom) * easeInOutSine(p),
          intensity: RESWEEP_INTENSITY * envelope,
        };
      }
    }
    return null;
  }

  private update(dt: number): void {
    const beam = this.beamState();
    const ambient = this.elapsed > SWEEP_START + SWEEP_DUR + BEAM_FADE_DUR;

    // parallax easing
    const targetX = this.pointerX * 10;
    const targetY = this.pointerY * 7;
    const k = Math.min(1, dt * 2.5);
    this.parallaxX += (targetX - this.parallaxX) * k;
    this.parallaxY += (targetY - this.parallaxY) * k;

    // node discovery + illumination
    for (const n of this.nodes) {
      if (beam && !n.discovered && beam.intensity > 0.5 && beam.theta >= n.angle) {
        n.discovered = true;
        n.flare = 1;
      }
      // re-sweeps gently re-flare already-discovered nodes
      if (
        beam &&
        n.discovered &&
        beam.intensity <= 0.5 &&
        Math.abs(beam.theta - n.angle) < 0.03 &&
        n.flare < 0.25
      ) {
        n.flare = 0.45;
      }
      if (n.discovered) {
        const target = SETTLED_LIT + 0.09 * Math.sin(this.elapsed * 1.2 + n.phase);
        n.lit += (target - n.lit) * Math.min(1, dt * 3.2);
      }
      n.flare = Math.max(0, n.flare - dt * 1.15);
    }

    // edges draw in once both ends are discovered
    for (const e of this.edges) {
      if (!e.active && this.nodes[e.a].discovered && this.nodes[e.b].discovered) {
        e.active = true;
      }
      if (e.active && e.progress < 1) {
        e.progress = Math.min(1, e.progress + dt / 0.55);
      }
    }

    // ambient pulses traveling along settled edges
    if (ambient) {
      if (this.elapsed >= this.nextPulseAt) {
        const ready = this.edges
          .map((e, i) => ({ e, i }))
          .filter(({ e }) => e.progress >= 1);
        if (ready.length > 0) {
          const pick = ready[Math.floor(Math.random() * ready.length)];
          this.pulses.push({ edge: pick.i, p: 0, forward: Math.random() > 0.5 });
        }
        this.nextPulseAt = this.elapsed + 1.6 + Math.random() * 1.8;
      }
      for (const p of this.pulses) {
        p.p += dt / 0.75;
        if (p.p >= 1) {
          const e = this.edges[p.edge];
          const target = this.nodes[p.forward ? e.b : e.a];
          target.flare = Math.max(target.flare, 0.5);
        }
      }
      this.pulses = this.pulses.filter((p) => p.p < 1);
    }
  }

  /* ---------------- drawing ---------------- */

  private nodeX(n: GraphNode | Fragment): number {
    const drift =
      Math.sin(this.elapsed * 0.07 + n.phase * 3.1) * 5 * n.depth;
    return n.nx * this.w + drift + this.parallaxX * n.depth;
  }

  private nodeY(n: GraphNode | Fragment): number {
    const drift =
      Math.cos(this.elapsed * 0.09 + n.phase * 2.3) * 4 * n.depth;
    return n.ny * this.h + drift + this.parallaxY * n.depth;
  }

  private draw(): void {
    const { ctx, w, h } = this;
    ctx.clearRect(0, 0, w, h);

    const beam = this.beamState();
    const fragGlobal = clamp((this.elapsed - FRAG_FADE_START) / FRAG_FADE_DUR, 0, 1);

    this.drawFragments(ctx, beam, fragGlobal);
    this.drawEdges(ctx);
    this.drawPulses(ctx);
    this.drawNodes(ctx);
    if (beam && beam.intensity > 0.01) {
      this.drawBeam(beam.theta, beam.intensity);
    }
  }

  private drawFragments(
    ctx: CanvasRenderingContext2D,
    beam: { theta: number; intensity: number } | null,
    globalAlpha: number,
  ): void {
    if (globalAlpha <= 0) return;
    for (const f of this.fragments) {
      const flicker = 0.7 + 0.3 * Math.sin(this.elapsed * f.flickerSpeed + f.phase);
      let alpha = f.baseAlpha * flicker * globalAlpha;
      // the beam catches fragments as it passes
      if (beam) {
        const prox = 1 - Math.abs(beam.theta - f.angle) / 0.22;
        if (prox > 0) alpha += prox * 0.16 * beam.intensity;
      }
      if (alpha <= 0.004) continue;
      const size = 9 + f.depth * 2.5;
      ctx.font = `500 ${size}px "IBM Plex Mono", monospace`;
      ctx.fillStyle = `rgba(160, 185, 215, ${alpha})`;
      ctx.fillText(f.text, this.nodeX(f), this.nodeY(f));
    }
  }

  private drawEdges(ctx: CanvasRenderingContext2D): void {
    ctx.lineWidth = 1;
    for (const e of this.edges) {
      if (e.progress <= 0) continue;
      const na = this.nodes[e.a];
      const nb = this.nodes[e.b];
      const ax = this.nodeX(na);
      const ay = this.nodeY(na);
      const bx = this.nodeX(nb);
      const by = this.nodeY(nb);
      const px = ax + (bx - ax) * e.progress;
      const py = ay + (by - ay) * e.progress;
      const litAvg = (na.lit + nb.lit) / 2;
      ctx.strokeStyle = `rgba(120, 190, 255, ${0.10 + litAvg * 0.22})`;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(px, py);
      ctx.stroke();
      // bright drawing head while the edge is still forming
      if (e.progress < 1) {
        ctx.fillStyle = 'rgba(230, 244, 255, 0.9)';
        ctx.beginPath();
        ctx.arc(px, py, 1.4, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  private drawPulses(ctx: CanvasRenderingContext2D): void {
    for (const p of this.pulses) {
      const e = this.edges[p.edge];
      const na = this.nodes[p.forward ? e.a : e.b];
      const nb = this.nodes[p.forward ? e.b : e.a];
      const t = easeInOutSine(p.p);
      const x = this.nodeX(na) + (this.nodeX(nb) - this.nodeX(na)) * t;
      const y = this.nodeY(na) + (this.nodeY(nb) - this.nodeY(na)) * t;
      const fade = Math.sin(Math.PI * p.p);
      this.blitGlow(ctx, x, y, 16, fade * 0.7);
      ctx.fillStyle = `rgba(230, 244, 255, ${fade * 0.9})`;
      ctx.beginPath();
      ctx.arc(x, y, 1.3, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  private drawNodes(ctx: CanvasRenderingContext2D): void {
    for (const n of this.nodes) {
      const vis = n.lit + n.flare;
      if (vis <= 0.01) continue;
      const x = this.nodeX(n);
      const y = this.nodeY(n);
      const glowSize = (14 + 30 * n.lit + 46 * n.flare) * (0.6 + 0.4 * n.depth);
      this.blitGlow(ctx, x, y, glowSize, Math.min(1, n.lit * 0.8 + n.flare));
      const r = (1.4 + 0.8 * n.depth) * (1 + n.flare * 0.7);
      ctx.fillStyle = `rgba(230, 244, 255, ${clamp(0.35 + vis * 0.65, 0, 1)})`;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  private blitGlow(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    size: number,
    alpha: number,
  ): void {
    if (alpha <= 0.01 || size <= 0) return;
    ctx.globalAlpha = clamp(alpha, 0, 1);
    ctx.drawImage(this.glowSprite, x - size / 2, y - size / 2, size, size);
    ctx.globalAlpha = 1;
  }

  private drawBeam(theta: number, intensity: number): void {
    const bw = this.beamCanvas.width;
    const bh = this.beamCanvas.height;
    const bctx = this.beamCtx;
    const px = this.pivotX / 2;
    const py = this.pivotY / 2;

    bctx.clearRect(0, 0, bw, bh);
    bctx.globalCompositeOperation = 'source-over';

    const spread = 0.16; // soft wedge half-width (radians)
    const core = 0.012; // bright blade at the leading line
    const tau = Math.PI * 2;
    const grad = bctx.createConicGradient(theta - spread, px, py);
    const at = (offset: number) => clamp(offset / tau, 0, 1);
    grad.addColorStop(0, 'rgba(140, 200, 255, 0)');
    grad.addColorStop(at(spread - core), `rgba(150, 205, 255, ${0.085 * intensity})`);
    grad.addColorStop(at(spread), `rgba(235, 246, 255, ${0.32 * intensity})`);
    grad.addColorStop(at(spread + core), `rgba(150, 205, 255, ${0.07 * intensity})`);
    grad.addColorStop(at(spread * 2), 'rgba(140, 200, 255, 0)');
    grad.addColorStop(1, 'rgba(140, 200, 255, 0)');
    bctx.fillStyle = grad;
    bctx.fillRect(0, 0, bw, bh);

    // distance falloff from the pivot
    const radial = bctx.createRadialGradient(px, py, 0, px, py, Math.hypot(bw, bh) * 1.05);
    radial.addColorStop(0, 'rgba(255,255,255,1)');
    radial.addColorStop(0.5, 'rgba(255,255,255,0.75)');
    radial.addColorStop(1, 'rgba(255,255,255,0)');
    bctx.globalCompositeOperation = 'destination-in';
    bctx.fillStyle = radial;
    bctx.fillRect(0, 0, bw, bh);

    const { ctx } = this;
    ctx.globalCompositeOperation = 'lighter';
    ctx.drawImage(this.beamCanvas, 0, 0, this.w, this.h);
    ctx.globalCompositeOperation = 'source-over';
  }

  /** One composed frame for prefers-reduced-motion: graph revealed, beam frozen. */
  private renderStatic(): void {
    this.elapsed = SWEEP_START + SWEEP_DUR * 0.72;
    for (const n of this.nodes) {
      if (n.angle <= this.sweepFrom + (this.sweepTo - this.sweepFrom) * 0.72) {
        n.discovered = true;
        n.lit = SETTLED_LIT;
      }
    }
    for (const e of this.edges) {
      if (this.nodes[e.a].discovered && this.nodes[e.b].discovered) {
        e.active = true;
        e.progress = 1;
      }
    }
    this.draw();
  }

  /* ---------------- sprites ---------------- */

  private static makeGlowSprite(): HTMLCanvasElement {
    const size = 128;
    const c = document.createElement('canvas');
    c.width = size;
    c.height = size;
    const g = c.getContext('2d')!;
    const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    grad.addColorStop(0, 'rgba(230, 244, 255, 0.85)');
    grad.addColorStop(0.18, 'rgba(191, 227, 255, 0.5)');
    grad.addColorStop(0.45, 'rgba(96, 170, 255, 0.16)');
    grad.addColorStop(1, 'rgba(96, 170, 255, 0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, size, size);
    return c;
  }
}
