/* ZeroBlockBridge — Site Script */

// ── Particle Network ───────────────────────────────────────────
(function () {
  const canvas = document.getElementById('particle-canvas');
  const ctx    = canvas.getContext('2d');

  const COLOR_NODE = 'rgba(52, 211, 153, {a})';
  const COLOR_LINE = 'rgba(52, 211, 153, {a})';
  const COLOR_GLOW = 'rgba(16, 185, 129, 0.12)';

  const CONNECT_DIST       = 160;
  const NODE_COUNT_DESKTOP = 70;
  const NODE_COUNT_MOBILE  = 35;
  const BASE_SPEED         = 0.08;   // slow, subtle drift

  // Fade-in on load
  let globalAlpha = 0;
  const FADE_DURATION = 1200; // ms
  let fadeStart = null;

  let W, H, nodes, animId;
  let mouse = { x: -9999, y: -9999 };

  function resize() {
    W = canvas.width  = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
  }

  function makeNode() {
    const angle = Math.random() * Math.PI * 2;
    const speed = BASE_SPEED * (0.6 + Math.random() * 0.8);
    return {
      x:  Math.random() * W,
      y:  Math.random() * H,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      r:  1.5 + Math.random() * 1.5,
    };
  }

  function init() {
    resize();
    const count = W > 800 ? NODE_COUNT_DESKTOP : NODE_COUNT_MOBILE;
    nodes = Array.from({ length: count }, makeNode);
  }

  function tick(ts) {
    // Fade-in
    if (!fadeStart) fadeStart = ts;
    globalAlpha = Math.min(1, (ts - fadeStart) / FADE_DURATION);

    ctx.clearRect(0, 0, W, H);

    // Update
    for (const n of nodes) {
      // Gentle mouse attraction
      const dx = mouse.x - n.x;
      const dy = mouse.y - n.y;
      const d  = Math.sqrt(dx * dx + dy * dy);
      if (d < 140 && d > 0) {
        const force = 0.015;
        n.vx += (dx / d) * force;
        n.vy += (dy / d) * force;
        // Soft speed cap — much lower than before
        const sp = Math.sqrt(n.vx * n.vx + n.vy * n.vy);
        const cap = BASE_SPEED * 2.5;
        if (sp > cap) { n.vx = (n.vx / sp) * cap; n.vy = (n.vy / sp) * cap; }
      } else {
        // Gentle drag back to base speed
        const sp = Math.sqrt(n.vx * n.vx + n.vy * n.vy);
        if (sp > BASE_SPEED * 1.2) {
          n.vx *= 0.995;
          n.vy *= 0.995;
        }
      }

      n.x += n.vx;
      n.y += n.vy;
      if (n.x < 0 || n.x > W) n.vx *= -1;
      if (n.y < 0 || n.y > H) n.vy *= -1;
    }

    // Lines
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx   = nodes[i].x - nodes[j].x;
        const dy   = nodes[i].y - nodes[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > CONNECT_DIST) continue;
        const alpha = globalAlpha * (1 - dist / CONNECT_DIST) * 0.45;
        ctx.beginPath();
        ctx.strokeStyle = COLOR_LINE.replace('{a}', alpha);
        ctx.lineWidth = 0.7;
        ctx.moveTo(nodes[i].x, nodes[i].y);
        ctx.lineTo(nodes[j].x, nodes[j].y);
        ctx.stroke();
      }
    }

    // Nodes
    for (const n of nodes) {
      // Soft glow
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r * 4, 0, Math.PI * 2);
      ctx.fillStyle = COLOR_GLOW;
      ctx.fill();
      // Core dot
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = COLOR_NODE.replace('{a}', globalAlpha * 0.8);
      ctx.fill();
    }

    animId = requestAnimationFrame(tick);
  }

  // Mouse tracking on the hero section, not just canvas
  const hero = document.getElementById('hero');
  hero.addEventListener('mousemove', e => {
    const rect = canvas.getBoundingClientRect();
    mouse.x = e.clientX - rect.left;
    mouse.y = e.clientY - rect.top;
  });
  hero.addEventListener('mouseleave', () => { mouse.x = -9999; mouse.y = -9999; });

  window.addEventListener('resize', () => {
    cancelAnimationFrame(animId);
    resize();
    animId = requestAnimationFrame(tick);
  });

  init();
  animId = requestAnimationFrame(tick);
})();

// ── Console cursor blink ───────────────────────────────────────
(function () {
  const cursor = document.querySelector('.mc-tag-cursor');
  if (!cursor) return;
  setInterval(() => { cursor.style.opacity = cursor.style.opacity === '0' ? '1' : '0'; }, 530);
})();

// ── Vitra init ─────────────────────────────────────────────────
window.addEventListener('load', () => {
  if (typeof Vitra === 'undefined') return;
  Vitra.theme.init({ defaultTheme: 'emerald', persist: false });
  Vitra.reveal.init({ threshold: 0.1, stagger: 80 });
  Vitra.spotlight.init();
  Vitra.tooltip.init();
});
