/* ZeroBlockBridge — Site Script
   Tile grid overlay for hero section
   Vitra init runs after vitra.min.js loads (defer)
*/

// ── Tile grid ──────────────────────────────
const tilesEl = document.getElementById('tiles');
const TILE_SIZE = 80;

let cols = 0;
let rows = 0;

function createTile(index) {
  const tile = document.createElement('div');
  tile.classList.add('tile');
  return tile;
}

function buildGrid() {
  tilesEl.innerHTML = '';
  cols = Math.ceil(window.innerWidth / TILE_SIZE);
  rows = Math.ceil(window.innerHeight / TILE_SIZE);
  tilesEl.style.setProperty('--cols', cols);
  tilesEl.style.setProperty('--rows', rows);

  const total = cols * rows;
  const frag = document.createDocumentFragment();
  for (let i = 0; i < total; i++) frag.appendChild(createTile(i));
  tilesEl.appendChild(frag);
}

// Subtle random shimmer on tiles
function shimmerLoop() {
  const tiles = Array.from(tilesEl.querySelectorAll('.tile'));
  if (!tiles.length) return;

  const pick = tiles[Math.floor(Math.random() * tiles.length)];

  anime({
    targets: pick.querySelector('::before') || pick,
    opacity: [0.03, 0.18, 0.03],
    duration: 1200,
    easing: 'easeInOutSine',
  });

  setTimeout(shimmerLoop, 120);
}

buildGrid();
window.addEventListener('resize', buildGrid);

// Start shimmer after a short delay so tiles are in DOM
setTimeout(shimmerLoop, 400);

// ── Vitra init ─────────────────────────────
// vitra.min.js loads with defer — wait for it
window.addEventListener('load', () => {
  if (typeof Vitra === 'undefined') return;

  Vitra.theme.init({ defaultTheme: 'emerald', persist: false });
  Vitra.reveal.init({ threshold: 0.1, stagger: 80 });
  Vitra.spotlight.init();
  Vitra.tooltip.init();
});
