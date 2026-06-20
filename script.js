/* ZeroBlockBridge site — tile grid + Vitra init */

// ── Tile grid (faithful to website/script.js) ──────────────────

const wrapper = document.getElementById('tiles');

let columns = 0;
let rows = 0;
let toggled = false;

const toggle = () => {
  toggled = !toggled;
  document.getElementById('hero').classList.toggle('toggled');
};

const handleOnClick = index => {
  toggle();
  anime({
    targets: '.tile',
    opacity: toggled ? 0 : 1,
    delay: anime.stagger(50, {
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

const createTiles = quantity => {
  const frag = document.createDocumentFragment();
  for (let i = 0; i < quantity; i++) frag.appendChild(createTile(i));
  wrapper.appendChild(frag);
};

const createGrid = () => {
  wrapper.innerHTML = '';
  const size = window.innerWidth > 800 ? 100 : 50;
  columns = Math.floor(window.innerWidth / size);
  rows    = Math.floor(window.innerHeight / size);
  wrapper.style.setProperty('--columns', columns);
  wrapper.style.setProperty('--rows', rows);
  createTiles(columns * rows);
};

createGrid();
window.addEventListener('resize', createGrid);

// ── Vitra init ─────────────────────────────────────────────────
window.addEventListener('load', () => {
  if (typeof Vitra === 'undefined') return;
  Vitra.theme.init({ defaultTheme: 'emerald', persist: false });
  Vitra.reveal.init({ threshold: 0.1, stagger: 80 });
  Vitra.spotlight.init();
  Vitra.tooltip.init();
});
