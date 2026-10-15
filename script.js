/* ZeroBlockBridge — Site Script */

// ── Hero Tile Grid ─────────────────────────────────────────────
(function () {
  const wrapper = document.getElementById('hero-tiles');
  const hero    = document.getElementById('hero');
  if (!wrapper || !hero) return;

  let columns = 0, rows = 0, toggled = false;

  const handleOnClick = index => {
    toggled = !toggled;
    hero.classList.toggle('toggled');

    anime({
      targets: '#hero-tiles .tile',
      opacity: toggled ? 0 : 1,
      delay: anime.stagger(65, {
        grid: [columns, rows],
        from: index,
      }),
      easing: 'easeOutQuad',
      duration: 550,
    });
  };

  const createTile = index => {
    const tile = document.createElement('div');
    tile.classList.add('tile');
    tile.style.opacity = 1;
    tile.onclick = () => handleOnClick(index);
    return tile;
  };

  const createGrid = () => {
    wrapper.innerHTML = '';
    toggled = false;
    hero.classList.remove('toggled');

    const size = window.innerWidth > 800 ? 80 : 50;
    columns = Math.max(4, Math.floor(window.innerWidth / size));
    rows    = Math.max(4, Math.floor(window.innerHeight / size));

    wrapper.style.setProperty('--columns', columns);
    wrapper.style.setProperty('--rows', rows);

    for (let i = 0; i < columns * rows; i++) wrapper.appendChild(createTile(i));
  };

  createGrid();
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(createGrid, 150);
  });

  // ── Scroll-out: hero fades as user scrolls (no slide) ───────
  const FADE_RANGE = 220;
  let rafId;

  window.addEventListener('scroll', () => {
    if (rafId !== undefined) return;
    rafId = requestAnimationFrame(() => {
      rafId = undefined;
      const progress = Math.max(0, Math.min(1, window.scrollY / FADE_RANGE));
      hero.style.opacity       = String(1 - progress);
      hero.style.pointerEvents = progress > 0.95 ? 'none' : 'auto';
    });
  });
})();

// ── Section Particle Clusters ──────────────────────────────────
(function () {
  const canvas = document.getElementById('section-particles');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  const COLOR_NODE = 'rgba(52,211,153,{a})';
  const COLOR_LINE = 'rgba(52,211,153,{a})';
  const COLOR_GLOW = 'rgba(16,185,129,0.08)';

  const CONNECT_DIST     = 180;  // farther → lines between spread-out followers
  const GROUP_SIZE       = 8;
  const GROUP_COUNT_DESK = 5;
  const GROUP_COUNT_MOB  = 3;
  const ORBIT_SPEED      = 0.00018; // very slow orbit
  const LEADER_DRIFT     = 0.018;   // very slow leader drift

  let W, H, groups, animId, lastTs = null;

  function resize() {
    W = canvas.width  = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
  }

  function makeGroup(gx, gy) {
    const a = Math.random() * Math.PI * 2;
    const leader = {
      x: gx, y: gy,
      vx: Math.cos(a) * LEADER_DRIFT,
      vy: Math.sin(a) * LEADER_DRIFT,
      r: 2.5, isLeader: true,
    };
    // Followers spread wide — radius 60-130px
    const followers = Array.from({ length: GROUP_SIZE - 1 }, (_, i) => ({
      angle:  (i / (GROUP_SIZE - 1)) * Math.PI * 2,
      radius: 60 + Math.random() * 70,
      speed:  ORBIT_SPEED * (0.6 + Math.random() * 0.8) * (Math.random() < 0.5 ? 1 : -1),
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
      const gx = (0.12 + (i / gc) * 0.76 + (Math.random() - 0.5) * 0.1) * W;
      const gy = (0.15 + Math.random() * 0.7) * H;
      groups.push(makeGroup(gx, gy));
    }
  }

  function tick(ts) {
    const dt = lastTs ? Math.min(ts - lastTs, 32) : 16;
    lastTs = ts;
    ctx.clearRect(0, 0, W, H);

    for (const g of groups) {
      const ldr = g.leader;
      ldr.x += ldr.vx * dt;
      ldr.y += ldr.vy * dt;
      if (ldr.x < 80 || ldr.x > W - 80) ldr.vx *= -1;
      if (ldr.y < 80 || ldr.y > H - 80) ldr.vy *= -1;
      ldr.x = Math.max(0, Math.min(W, ldr.x));
      ldr.y = Math.max(0, Math.min(H, ldr.y));

      for (const f of g.followers) {
        f.angle += f.speed * dt;
        f.x = ldr.x + Math.cos(f.angle) * f.radius;
        f.y = ldr.y + Math.sin(f.angle) * f.radius;
      }

      const all = [ldr, ...g.followers];

      for (let i = 0; i < all.length; i++) {
        for (let j = i + 1; j < all.length; j++) {
          const dx = all[i].x - all[j].x;
          const dy = all[i].y - all[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist > CONNECT_DIST) continue;
          const alpha = (1 - dist / CONNECT_DIST) * 0.3;
          ctx.beginPath();
          ctx.strokeStyle = COLOR_LINE.replace('{a}', alpha);
          ctx.lineWidth = 0.55;
          ctx.moveTo(all[i].x, all[i].y);
          ctx.lineTo(all[j].x, all[j].y);
          ctx.stroke();
        }
      }

      for (const n of all) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r * (n.isLeader ? 6 : 4), 0, Math.PI * 2);
        ctx.fillStyle = COLOR_GLOW;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = COLOR_NODE.replace('{a}', n.isLeader ? 0.9 : 0.6);
        ctx.fill();
      }
    }

    if (!reduceMotion) animId = requestAnimationFrame(tick);
  }

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      cancelAnimationFrame(animId);
      init();
      lastTs = null;
      if (!reduceMotion) animId = requestAnimationFrame(tick);
    }, 150);
  });

  init();
  if (reduceMotion) {
    tick(0); // draw one static frame, no loop
  } else {
    animId = requestAnimationFrame(tick);
  }
})();

// ── Latest release ─────────────────────────────────────────────
// The download links already point at /releases/latest/download/<asset>,
// which GitHub redirects to the newest release. This only refines them to
// the exact asset of that release and shows its version; if the API is
// unreachable or rate-limited the static links keep working.
(function () {
  const API = 'https://api.github.com/repos/DesvoSoft/ZeroBlockBridge/releases/latest';
  const CACHE_KEY = 'zbb-latest-release';
  const CACHE_MS = 30 * 60 * 1000;

  const pickAsset = (assets, platform) => assets.find(a => {
    const n = a.name.toLowerCase();
    if (n.endsWith('.sha256')) return false;
    return platform === 'windows' ? n.endsWith('.exe') : n.includes('linux');
  });

  const formatSize = bytes => (bytes / (1024 * 1024)).toFixed(0) + ' MB';

  const apply = release => {
    const assets = release.assets || [];
    document.querySelectorAll('[data-release-asset]').forEach(link => {
      const asset = pickAsset(assets, link.dataset.releaseAsset);
      if (!asset) return;
      link.href = asset.browser_download_url;
      link.title = `${asset.name} · ${formatSize(asset.size)}`;
    });

    document.querySelectorAll('[data-release-version]').forEach(el => {
      el.textContent = release.tag_name;
      el.hidden = false;
    });

    const info = document.querySelector('[data-release-info]');
    if (info) {
      const date = new Date(release.published_at).toLocaleDateString('en', {
        year: 'numeric', month: 'short', day: 'numeric',
      });
      const link = document.createElement('a');
      link.href = release.html_url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = `${release.tag_name} · released ${date} · changelog →`;
      info.replaceChildren(link);
    }
  };

  const readCache = () => {
    try {
      const cached = JSON.parse(sessionStorage.getItem(CACHE_KEY));
      if (cached && Date.now() - cached.at < CACHE_MS) return cached.release;
    } catch (_) { /* storage unavailable */ }
    return null;
  };

  const writeCache = release => {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ at: Date.now(), release }));
    } catch (_) { /* storage unavailable */ }
  };

  const cached = readCache();
  if (cached) { apply(cached); return; }

  fetch(API, { headers: { Accept: 'application/vnd.github+json' } })
    .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(data => {
      const release = {
        tag_name: data.tag_name,
        html_url: data.html_url,
        published_at: data.published_at,
        assets: (data.assets || []).map(a => ({
          name: a.name, size: a.size, browser_download_url: a.browser_download_url,
        })),
      };
      writeCache(release);
      apply(release);
    })
    .catch(() => { /* keep the static /releases/latest links */ });
})();

// ── Vitra init ─────────────────────────────────────────────────
window.addEventListener('load', () => {
  if (typeof Vitra === 'undefined') return;
  Vitra.theme.init({ defaultTheme: 'emerald', persist: false });
  Vitra.reveal.init({ threshold: 0.1, stagger: 80 });
  Vitra.spotlight.init();
  Vitra.tooltip.init();
});
