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
  Vitra.tooltip.init();
});
