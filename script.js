/* ZeroBlockBridge — Site Script */

// ── Hero Tile Grid ─────────────────────────────────────────────
(function () {
  const wrapper = document.getElementById('hero-tiles');
  if (!wrapper) return;

  let columns = 0, rows = 0, toggled = false;

  const handleOnClick = index => {
    toggled = !toggled;
    document.getElementById('hero').classList.toggle('tiles-toggled');
    anime({
      targets: '#hero-tiles .tile',
      opacity: toggled ? 0 : 1,
      delay: anime.stagger(40, {
        grid: [columns, rows],
        from: index,
      }),
    });
  };

  const createTile = index => {
    const tile = document.createElement('div');
    tile.classList.add('tile');
    tile.style.opacity = toggled ? 0 : 1;
    tile.onclick = () => handleOnClick(index);
    return tile;
  };

  const createGrid = () => {
    wrapper.innerHTML = '';
    const size = window.innerWidth > 800 ? 90 : 50;
    columns = Math.floor(window.innerWidth / size);
    rows = Math.floor(window.innerHeight / size);
    wrapper.style.setProperty('--columns', columns);
    wrapper.style.setProperty('--rows', rows);
    const count = columns * rows;
    for (let i = 0; i < count; i++) wrapper.appendChild(createTile(i));
  };

  createGrid();
  window.addEventListener('resize', createGrid);
})();

// ── Section Particle Clusters ──────────────────────────────────
(function () {
  const canvas = document.getElementById('section-particles');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  const COLOR_NODE = 'rgba(52,211,153,{a})';
  const COLOR_LINE = 'rgba(52,211,153,{a})';
  const COLOR_GLOW = 'rgba(16,185,129,0.10)';

  const CONNECT_DIST     = 120;
  const GROUP_SIZE       = 8;
  const GROUP_COUNT_DESK = 5;
  const GROUP_COUNT_MOB  = 3;
  const ORBIT_SPEED      = 0.0004; // rad/ms
  const LEADER_DRIFT     = 0.04;

  let W, H, groups, animId;
  let lastTs = null;

  function resize() {
    W = canvas.width  = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
  }

  function makeGroup(gx, gy) {
    const leaderAngle = Math.random() * Math.PI * 2;
    const leader = {
      x: gx, y: gy,
      vx: Math.cos(leaderAngle) * LEADER_DRIFT,
      vy: Math.sin(leaderAngle) * LEADER_DRIFT,
      r: 2.2,
      isLeader: true,
    };
    const followers = Array.from({ length: GROUP_SIZE - 1 }, (_, i) => ({
      angle: (i / (GROUP_SIZE - 1)) * Math.PI * 2,
      radius: 30 + Math.random() * 50,
      speed: ORBIT_SPEED * (0.7 + Math.random() * 0.6) * (Math.random() < 0.5 ? 1 : -1),
      r: 1.2 + Math.random() * 0.8,
      isLeader: false,
      x: 0, y: 0,
    }));
    return { leader, followers };
  }

  function init() {
    resize();
    const gc = W > 800 ? GROUP_COUNT_DESK : GROUP_COUNT_MOB;
    groups = [];
    for (let i = 0; i < gc; i++) {
      const gx = (0.15 + (i / gc) * 0.7 + (Math.random() - 0.5) * 0.15) * W;
      const gy = (0.2 + Math.random() * 0.6) * H;
      groups.push(makeGroup(gx, gy));
    }
  }

  function tick(ts) {
    const dt = lastTs ? ts - lastTs : 16;
    lastTs = ts;

    ctx.clearRect(0, 0, W, H);

    for (const g of groups) {
      const ldr = g.leader;
      ldr.x += ldr.vx * dt;
      ldr.y += ldr.vy * dt;
      if (ldr.x < 60 || ldr.x > W - 60) ldr.vx *= -1;
      if (ldr.y < 60 || ldr.y > H - 60) ldr.vy *= -1;
      ldr.x = Math.max(0, Math.min(W, ldr.x));
      ldr.y = Math.max(0, Math.min(H, ldr.y));

      for (const f of g.followers) {
        f.angle += f.speed * dt;
        f.x = ldr.x + Math.cos(f.angle) * f.radius;
        f.y = ldr.y + Math.sin(f.angle) * f.radius;
      }

      const all = [ldr, ...g.followers];

      // Lines within cluster
      for (let i = 0; i < all.length; i++) {
        for (let j = i + 1; j < all.length; j++) {
          const dx = all[i].x - all[j].x;
          const dy = all[i].y - all[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist > CONNECT_DIST) continue;
          const alpha = (1 - dist / CONNECT_DIST) * 0.35;
          ctx.beginPath();
          ctx.strokeStyle = COLOR_LINE.replace('{a}', alpha);
          ctx.lineWidth = 0.6;
          ctx.moveTo(all[i].x, all[i].y);
          ctx.lineTo(all[j].x, all[j].y);
          ctx.stroke();
        }
      }

      // Nodes
      for (const n of all) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r * (n.isLeader ? 5 : 3.5), 0, Math.PI * 2);
        ctx.fillStyle = COLOR_GLOW;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = COLOR_NODE.replace('{a}', n.isLeader ? 0.9 : 0.65);
        ctx.fill();
      }
    }

    animId = requestAnimationFrame(tick);
  }

  window.addEventListener('resize', () => {
    cancelAnimationFrame(animId);
    init();
    lastTs = null;
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
