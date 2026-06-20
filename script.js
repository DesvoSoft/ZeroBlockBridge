/* ZeroBlockBridge — Site Script
   Particle network hero + Vitra init
*/

// ── Particle Network ───────────────────────────────────────────
(function () {
  const canvas = document.getElementById('particle-canvas');
  const ctx    = canvas.getContext('2d');

  // Emerald palette
  const COLOR_NODE = 'rgba(52, 211, 153, 0.75)';   // bright green node
  const COLOR_LINE = 'rgba(52, 211, 153, {a})';     // template for line
  const COLOR_GLOW = 'rgba(16, 185, 129, 0.18)';    // glow under node

  const CONNECT_DIST = 160;   // max distance to draw a line
  const NODE_COUNT_DESKTOP = 80;
  const NODE_COUNT_MOBILE  = 40;
  const SPEED = 0.35;

  let W, H, nodes, animId;

  function resize() {
    W = canvas.width  = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
  }

  function makeNode() {
    const angle = Math.random() * Math.PI * 2;
    const speed = SPEED * (0.5 + Math.random() * 0.8);
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

  function draw() {
    ctx.clearRect(0, 0, W, H);

    // Update positions + bounce
    for (const n of nodes) {
      n.x += n.vx;
      n.y += n.vy;
      if (n.x < 0 || n.x > W) n.vx *= -1;
      if (n.y < 0 || n.y > H) n.vy *= -1;
    }

    // Draw lines
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > CONNECT_DIST) continue;

        const alpha = (1 - dist / CONNECT_DIST) * 0.55;
        ctx.beginPath();
        ctx.strokeStyle = COLOR_LINE.replace('{a}', alpha);
        ctx.lineWidth = 0.8;
        ctx.moveTo(nodes[i].x, nodes[i].y);
        ctx.lineTo(nodes[j].x, nodes[j].y);
        ctx.stroke();
      }
    }

    // Draw nodes
    for (const n of nodes) {
      // Glow
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r * 3, 0, Math.PI * 2);
      ctx.fillStyle = COLOR_GLOW;
      ctx.fill();
      // Core
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = COLOR_NODE;
      ctx.fill();
    }

    animId = requestAnimationFrame(draw);
  }

  // Mouse interaction — attract nearby nodes
  let mouse = { x: -9999, y: -9999 };
  canvas.addEventListener('mousemove', e => {
    const rect = canvas.getBoundingClientRect();
    mouse.x = e.clientX - rect.left;
    mouse.y = e.clientY - rect.top;
  });
  canvas.addEventListener('mouseleave', () => {
    mouse.x = -9999;
    mouse.y = -9999;
  });

  // Mouse-attract pass runs after node update inside draw()
  // Override draw to inject attraction
  const _drawOrig = draw;

  function drawWithAttract() {
    ctx.clearRect(0, 0, W, H);

    for (const n of nodes) {
      // Attraction to mouse
      const dx = mouse.x - n.x;
      const dy = mouse.y - n.y;
      const d  = Math.sqrt(dx * dx + dy * dy);
      if (d < 120) {
        n.vx += (dx / d) * 0.04;
        n.vy += (dy / d) * 0.04;
        // Speed cap
        const sp = Math.sqrt(n.vx * n.vx + n.vy * n.vy);
        if (sp > SPEED * 3) { n.vx = (n.vx / sp) * SPEED * 3; n.vy = (n.vy / sp) * SPEED * 3; }
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
        const alpha = (1 - dist / CONNECT_DIST) * 0.55;
        ctx.beginPath();
        ctx.strokeStyle = COLOR_LINE.replace('{a}', alpha);
        ctx.lineWidth = 0.8;
        ctx.moveTo(nodes[i].x, nodes[i].y);
        ctx.lineTo(nodes[j].x, nodes[j].y);
        ctx.stroke();
      }
    }

    // Nodes
    for (const n of nodes) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r * 3, 0, Math.PI * 2);
      ctx.fillStyle = COLOR_GLOW;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = COLOR_NODE;
      ctx.fill();
    }

    animId = requestAnimationFrame(drawWithAttract);
  }

  window.addEventListener('resize', () => {
    cancelAnimationFrame(animId);
    resize();
    drawWithAttract();
  });

  init();
  drawWithAttract();
})();

// ── Console cursor blink ───────────────────────────────────────
(function () {
  const cursor = document.querySelector('.mc-tag-cursor');
  if (!cursor) return;
  setInterval(() => cursor.style.opacity = cursor.style.opacity === '0' ? '1' : '0', 530);
})();

// ── Vitra init ─────────────────────────────────────────────────
window.addEventListener('load', () => {
  if (typeof Vitra === 'undefined') return;
  Vitra.theme.init({ defaultTheme: 'emerald', persist: false });
  Vitra.reveal.init({ threshold: 0.1, stagger: 80 });
  Vitra.spotlight.init();
  Vitra.tooltip.init();
});
