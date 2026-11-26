"""Design system "soft frosted glass" della piattaforma.

Un solo modulo per tutto il CSS: ``TOKENS`` definisce i valori, ``BASE_CSS`` i
componenti comuni (vetro, campi, bottoni, tabelle, badge), poi ogni superficie
aggiunge le proprie regole e viene servita gia' completa. Le pagine non hanno
piu' fogli di stile inline: importano ``DASHBOARD_CSS``, ``LOGIN_CSS``,
``REPORT_CSS``, ``VERIFY_CSS`` o ``EXPIRED_CSS``.
"""

import html
import re
from urllib.parse import urlsplit

TOKENS = """
  :root {
    /* Giorno: Glass Amber su Warm Fog. */
    --text:#1A1512; --muted:rgba(52,42,34,.74);
    --line:rgba(120,72,40,.16); --glass-line:rgba(120,72,40,.14);
    --accent:#B4501A; --accent-2:#FF9A4D; --accent-ink:#FFFFFF;
    --accent-soft:rgba(255,154,77,.16); --accent-line:rgba(180,80,26,.32);
    --warm-line:rgba(255,190,130,.55);
    --glass-edge:rgba(180,80,26,.2);
    --ok:#0F7A4E; --warn:#B25000; --bad:#D70015;
    --surface:rgba(255,252,247,.42); --surface-hover:rgba(255,252,247,.62);
    --surface-solid:rgba(255,253,250,.96);
    --surface-flat:#FFFDFA; --surface-flat-hover:#FFF1E4;
    --field:rgba(255,255,255,.82); --field-line:rgba(120,72,40,.18);
    --control:rgba(255,255,255,.8); --control-hover:rgba(255,255,255,.94);
    --shadow:0 20px 45px rgba(64,36,18,.1), inset 0 1px 1px rgba(255,255,255,.95);
    --shadow-float:0 24px 54px rgba(64,36,18,.12), inset 0 1px 1px rgba(255,255,255,.98);
    --blur:blur(24px) saturate(180%);
    /* Vetro pieno (dashboard) e vetro leggero (sezioni operative). */
    --glass-blur:blur(20px) saturate(150%);
    --glass-blur-soft:blur(6px) saturate(110%);
    --glass-shadow:0 18px 44px rgba(64,36,18,.12), inset 0 1px 0 rgba(255,255,255,.9);
    --glass-shadow-soft:0 6px 18px rgba(64,36,18,.08);
  }
"""

# Tema e feedback tattile: un solo blocco JS per dashboard, login e controllo.
# Va inserito dentro un <script> dopo il markup: applica la preferenza salvata
# e aggancia il ripple a tutti i pulsanti.
THEME_JS = """
function applyTheme(dark, persist) {
  document.body.classList.toggle('dark', !!dark);
  const button = document.getElementById('theme-toggle');
  if (button) {
    button.textContent = dark ? '☀️' : '🌙';
    button.title = dark ? 'Tema chiaro' : 'Tema notturno';
    button.setAttribute('aria-label', dark ? 'Passa al tema chiaro' : 'Passa al tema notturno');
  }
  if (typeof Chart !== 'undefined') {
    const styles = getComputedStyle(document.body);
    Chart.defaults.color = styles.getPropertyValue('--muted').trim()
      || (dark ? '#C7D1E0' : '#103429');
    Chart.defaults.borderColor = styles.getPropertyValue('--line').trim()
      || (dark ? 'rgba(255,154,77,.18)' : 'rgba(120,72,40,.16)');
  }
  // I grafici si ridisegnano con l'accento appena applicato.
  document.dispatchEvent(new CustomEvent('dh:theme', { detail: { dark: !!dark } }));
  if (persist !== false) {
    try { localStorage.setItem('dh_theme', dark ? 'dark' : 'light'); } catch (error) {}
  }
}

function toggleTheme() { applyTheme(!document.body.classList.contains('dark')); }

// Conferma visiva dell'invio di un comando critico: 2 secondi di spunta.
function triggerActionFeedback(button) {
  if (!button) return;
  const original = button.textContent;
  button.textContent = '\u2713 Completato';
  button.classList.add('action-done');
  button.disabled = true;
  setTimeout(function () {
    button.textContent = original;
    button.classList.remove('action-done');
    button.disabled = false;
  }, 2000);
}

function initRipple() {
  document.addEventListener('pointerdown', function (event) {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    const rect = button.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2;
    const ripple = document.createElement('span');
    ripple.className = 'ripple';
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = (event.clientX - rect.left - size / 2) + 'px';
    ripple.style.top = (event.clientY - rect.top - size / 2) + 'px';
    button.appendChild(ripple);
    setTimeout(function () { ripple.remove(); }, 620);
  }, { passive: true });
}

// Live AI Canvas: al primo ingresso la UI si assembla in ~1,3 s con riquadri
// di selezione e tre cursori agente. Tutto l'overlay e' pointer-events:none,
// quindi i comandi restano cliccabili da subito.
function initCanvasBuild() {
  const root = document.documentElement;
  if (root.classList.contains('canvas-done')) return;
  root.classList.add('canvas-done');
  if (!window.Element || !Element.prototype.animate) return;
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  // Una sola volta per vista nella sessione: ricaricare non rilancia l'animazione.
  const seenKey = 'dh_canvas:' + window.location.pathname;
  try {
    if (window.sessionStorage.getItem(seenKey)) return;
    window.sessionStorage.setItem(seenKey, '1');
  } catch (error) {}

  const candidates = document.querySelectorAll('.topbar, .card, .kpi, main > .panel');
  const targets = [];
  for (let i = 0; i < candidates.length && targets.length < 4; i += 1) {
    const rect = candidates[i].getBoundingClientRect();
    if (rect.width > 60 && rect.height > 30) targets.push(candidates[i]);
  }
  if (!targets.length) return;

  const overlay = document.createElement('div');
  overlay.className = 'canvas-overlay';
  overlay.setAttribute('aria-hidden', 'true');
  document.body.appendChild(overlay);

  const boxes = targets.map(function (target) {
    target.classList.add('canvas-assemble');
    const box = document.createElement('span');
    box.className = 'canvas-box';
    for (let c = 0; c < 4; c += 1) box.appendChild(document.createElement('i'));
    overlay.appendChild(box);
    return box;
  });

  const route = targets.map(function (target) {
    const rect = target.getBoundingClientRect();
    return { x: rect.left + rect.width * 0.5, y: rect.top + rect.height * 0.42 };
  });
  const last = route.length - 1;
  const agents = [
    { label: 'UI-Glass', color: '#FF9A4D', start: [-70, 130], path: [0, Math.min(1, last)] },
    { label: 'SOC-Core', color: '#7DD3FC', start: [window.innerWidth + 30, window.innerHeight * 0.5], path: [Math.min(1, last), 0] },
    { label: 'Telemetry', color: '#86EFAC', start: [window.innerWidth * 0.6, window.innerHeight + 40], path: [Math.min(2, last), Math.min(1, last)] }
  ];

  agents.forEach(function (agent, index) {
    const cursor = document.createElement('div');
    cursor.className = 'canvas-cursor';
    cursor.style.setProperty('--tag', agent.color);
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 14 18');
    svg.setAttribute('aria-hidden', 'true');
    const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    arrow.setAttribute('d', 'M1 1 L1 15 L5 11.5 L7.5 17 L10 15.8 L7.6 10.5 L12.5 10.2 Z');
    arrow.setAttribute('fill', agent.color);
    arrow.setAttribute('stroke', '#0E1016');
    arrow.setAttribute('stroke-width', '1');
    svg.appendChild(arrow);
    const tag = document.createElement('span');
    tag.textContent = agent.label;
    cursor.appendChild(svg);
    cursor.appendChild(tag);
    overlay.appendChild(cursor);

    const from = route[agent.path[0]];
    const to = route[agent.path[1]];
    cursor.animate([
      { transform: 'translate(' + agent.start[0] + 'px,' + agent.start[1] + 'px) scale(.8)', opacity: 0 },
      { transform: 'translate(' + from.x + 'px,' + from.y + 'px) scale(1)', opacity: 1, offset: 0.38 },
      { transform: 'translate(' + to.x + 'px,' + to.y + 'px) scale(1)', opacity: 1, offset: 0.78 },
      { transform: 'translate(' + (to.x + 48) + 'px,' + (to.y + 28) + 'px) scale(.9)', opacity: 0 }
    ], {
      duration: 1180, delay: 80 + index * 90,
      easing: 'cubic-bezier(.32,.72,.24,1)', fill: 'both'
    });
  });

  const started = Date.now();
  function followTargets() {
    targets.forEach(function (target, index) {
      const rect = target.getBoundingClientRect();
      const box = boxes[index];
      box.style.left = rect.left + 'px';
      box.style.top = rect.top + 'px';
      box.style.width = rect.width + 'px';
      box.style.height = rect.height + 'px';
    });
    if (Date.now() - started < 1300) requestAnimationFrame(followTargets);
  }
  followTargets();

  setTimeout(function () {
    overlay.classList.add('out');
    targets.forEach(function (target) { target.classList.remove('canvas-assemble'); });
    setTimeout(function () { overlay.remove(); }, 260);
  }, 1300);
}

applyTheme(document.body.classList.contains('dark'), false);
initRipple();
initCanvasBuild();
"""

BASE_CSS = TOKENS + """
  * { box-sizing:border-box; }
  html { background:#FBF7F2; }
  body {
    /* Sfondo aziendale (white-label): imposta solo
         style="--custom-bg-image:url('/static/sfondo.jpg')"
       Il velo --custom-bg-veil, del colore del tema, copre la foto quanto basta
       perche' il contrasto dei testi non dipenda dall'immagine scelta. */
    --custom-bg-image:none; --custom-bg-veil:rgba(251,247,242,.84);
    margin:0; min-height:100vh; color:var(--text);
    /* Contesto di stacking: lo sfondo aziendale (::before, z-index:-1) sta
       sopra il gradiente del tema ma sotto ogni contenuto. */
    position:relative; isolation:isolate;
    font:14px/1.55 -apple-system,BlinkMacSystemFont,'SF Pro Display','SF Pro Text','Segoe UI',Roboto,sans-serif;
    -webkit-font-smoothing:antialiased;
    background:radial-gradient(900px 620px at 6% -10%, rgba(255,154,77,.14), transparent 62%),
               linear-gradient(150deg,#FBF7F2 0%,#FFFCF8 52%,#F4EBE2 100%) fixed;
    background-color:#FBF7F2;
  }
  /* Il livello dipinge solo quando c'e' un'immagine: senza, il tema resta intatto. */
  body.has-custom-bg::before {
    content:""; position:fixed; inset:0; z-index:-1; pointer-events:none;
    background-image:
      linear-gradient(var(--custom-bg-veil), var(--custom-bg-veil)),
      var(--custom-bg-image);
    background-position:center, center;
    background-size:cover, cover;
    background-repeat:no-repeat, no-repeat;
    filter:saturate(.96);
  }
  h1, h2, h3 {
    font-family:inherit; color:var(--text); letter-spacing:-.02em;
  }
  h1 { font-size:18px; font-weight:700; margin:0; }
  h2 {
    font-size:12px; font-weight:600; text-transform:uppercase;
    letter-spacing:.09em; color:var(--muted); margin:0 0 14px;
  }
  .sub, .muted { color:var(--muted); }
  a { color:var(--accent); }
  header {
    display:flex; justify-content:space-between; align-items:center;
    gap:16px; flex-wrap:wrap;
    margin:14px 16px 0; padding:14px 20px; border-radius:18px;
    background:var(--surface); border:1px solid var(--glass-line);
    box-shadow:var(--shadow-float);
    backdrop-filter:var(--blur); -webkit-backdrop-filter:var(--blur);
    position:sticky; top:12px; z-index:50;
  }
  /* Base pulita: le sezioni operative leggono dati densi, quindi superficie
     quasi piena e blur minimo. La dashboard riaccende il vetro pieno sotto. */
  .panel, .card, .kpi {
    backdrop-filter:var(--glass-blur-soft); -webkit-backdrop-filter:var(--glass-blur-soft);
  }
  .panel, .card {
    background:var(--surface-solid); color:var(--text);
    border:1px solid var(--glass-line); border-radius:22px; padding:24px;
    box-shadow:var(--glass-shadow-soft);
    transition:background .25s ease, box-shadow .25s ease, border-color .25s ease;
  }
  .panel:hover, .card:hover, .kpi:hover {
    box-shadow:var(--shadow);
  }
  table, .kpi .value, .badge, .count, .status-pill, .vehicle-grid strong,
  .playback-kpis strong, .map-count, .emergency-kpis strong {
    font-variant-numeric:tabular-nums;
    font-feature-settings:"tnum";
  }
  .card button {
    background:var(--accent); color:var(--accent-ink); font-weight:700;
    border-color:var(--accent-line);
    box-shadow:0 10px 24px var(--accent-line);
  }
  .card button:hover { background:var(--accent); filter:brightness(1.08); }
  .card input, .card textarea {
    background:var(--field); border-color:var(--field-line);
  }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:14px; }
  .kpi {
    padding:16px; border-radius:18px;
    background:var(--surface-solid);
    border:1px solid var(--glass-line);
    box-shadow:var(--glass-shadow-soft);
    color:var(--text);
    transition:transform .2s ease, box-shadow .2s ease;
  }
  .kpi .label {
    font-size:10.5px; font-weight:600; text-transform:uppercase;
    letter-spacing:.06em; color:var(--muted);
  }
  .kpi .value {
    font-size:25px; font-weight:700; margin-top:6px;
    letter-spacing:-.03em; color:var(--text);
  }
  input, select, textarea {
    padding:8px 14px; font-size:13px;
    background:var(--field); color:var(--text);
    border:1px solid var(--field-line); border-radius:14px;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.9);
    backdrop-filter:blur(10px) saturate(140%);
  }
  input:focus, select:focus, textarea:focus {
    outline:none; border-color:var(--accent);
  }
  input::placeholder, textarea::placeholder { color:rgba(16,52,42,.7); }
  input[type=file]::file-selector-button {
    margin-right:10px; padding:7px 12px; border-radius:10px;
    border:1px solid rgba(255,255,255,.8); background:rgba(255,255,255,.8);
    color:var(--text); font-weight:600; cursor:pointer;
  }
  input[type=file]::file-selector-button:hover { background:#fff; }
  input[type=color] {
    padding:3px; width:52px; height:34px; border-radius:10px;
    background:rgba(255,255,255,.55); border:1px solid rgba(255,255,255,.8);
  }
  button {
    padding:8px 15px; font-size:12.5px;
    background:var(--control); color:var(--text);
    border:1px solid var(--glass-line); border-radius:14px;
    font-weight:600; cursor:pointer;
    box-shadow:0 8px 22px rgba(4,42,31,.1), inset 0 1px 0 rgba(255,255,255,.95);
    backdrop-filter:blur(10px) saturate(140%);
    transition:transform .15s ease, box-shadow .15s ease, background .15s ease;
  }
  button:hover { background:var(--control-hover); transform:translateY(-1px); }
  button:disabled { opacity:.5; cursor:not-allowed; transform:none; }
  button.ok {
    background:var(--accent); color:var(--accent-ink);
    border-color:var(--accent-line); font-weight:700;
    box-shadow:0 10px 24px var(--accent-line);
  }
  button.danger {
    background:rgba(255,69,58,.12); color:#c31d10;
    border-color:rgba(255,69,58,.32);
  }
  button.tiny { padding:5px 10px; font-size:11px; }
  table { width:100%; border-collapse:collapse; }
  th {
    text-align:left; color:var(--muted); font-size:10.5px; font-weight:600;
    text-transform:uppercase; letter-spacing:.07em;
    padding:8px; border-bottom:1px solid rgba(120,72,40,.14);
  }
  td { padding:10px 8px; border-bottom:1px solid rgba(120,72,40,.1); }
  tbody tr:hover { background:rgba(255,255,255,.35); }
  code { color:var(--accent); }
  .badge {
    display:inline-block; padding:2px 9px; border-radius:999px;
    font-size:10.5px; font-weight:700; border:1px solid transparent;
  }
  .badge.on, .badge.ok, .badge.active {
    background:rgba(52,199,89,.16); color:#1c7c34; border-color:rgba(52,199,89,.3);
    box-shadow:0 0 14px rgba(52,199,89,.28);
  }
  .badge.off, .badge.pending, .badge.offline {
    background:rgba(120,120,128,.12); color:#5a5a5f; border-color:rgba(120,120,128,.2);
  }
  .badge.warn {
    background:rgba(255,159,10,.16); color:#9a5b00; border-color:rgba(255,159,10,.32);
    box-shadow:0 0 14px rgba(255,159,10,.24);
  }
  .badge.bad {
    background:rgba(255,69,58,.14); color:#c31d10; border-color:rgba(255,69,58,.3);
    box-shadow:0 0 14px rgba(255,69,58,.3);
  }
  .row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
  .empty { color:var(--muted); padding:14px 0; }
  #log {
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11.5px;
    white-space:pre-wrap; max-height:230px; overflow:auto; color:var(--muted);
  }
  pre#prov {
    display:none; margin:12px 0 0; padding:14px; border-radius:14px;
    background:var(--field); border:1px solid var(--glass-line);
    font-size:11.5px; white-space:pre-wrap; overflow:auto; color:var(--text);
  }
  .err { color:var(--bad); }
  .okv { color:var(--ok); }

  /* Ripple tattile sui pulsanti */
  button { position:relative; overflow:hidden; }
  .ripple {
    position:absolute; border-radius:50%; pointer-events:none;
    transform:scale(0); background:rgba(255,255,255,.55);
    animation:rippleOut .6s ease-out forwards;
  }
  body.dark .ripple { background:var(--accent-soft); }
  @keyframes rippleOut { to { transform:scale(1); opacity:0; } }


  /* Segnaposto in attesa di telemetria. */
  .skeleton-glass {
    height:14px; border-radius:16px;
    background-image:linear-gradient(90deg,
      rgba(255,255,255,.34) 0%, rgba(255,255,255,.72) 50%, rgba(255,255,255,.34) 100%);
    background-size:200% 100%;
    backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px);
    animation:shimmerGlass 1.4s linear infinite;
  }
  body.dark .skeleton-glass {
    background-image:linear-gradient(90deg,
      rgba(255,255,255,.06) 0%, rgba(255,255,255,.18) 50%, rgba(255,255,255,.06) 100%);
  }
  @keyframes shimmerGlass {
    from { background-position:200% 0; }
    to { background-position:-200% 0; }
  }

  .theme-toggle {
    width:36px; height:36px; padding:0; border-radius:12px;
    font-size:15px; line-height:1; flex:0 0 auto;
    background:var(--control-hover); border-color:var(--field-line);
  }
  body.dark .theme-toggle {
    background:var(--control-hover); border-color:rgba(255,255,255,.2);
  }
  .table-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .table-wrap table { min-width:900px; }
  .table-wrap td .row {
    display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px;
  }
  .table-wrap td .row button { padding:5px 8px; font-size:11px; }
  .theme-fab {
    position:fixed; top:16px; right:16px; z-index:60;
    width:42px; height:42px; padding:0; border-radius:14px; font-size:16px;
  }

  /* ===== Tema notturno (Night Shift + Laser Lemon) ===== */
  body.dark {
    color-scheme:dark;
    --text:#F3EEE8; --muted:rgba(232,222,212,.72);
    --line:rgba(255,190,130,.18); --glass-line:rgba(255,255,255,.18);
    --accent:#FF9A4D; --accent-2:#FFB173; --accent-ink:#1A1207;
    --accent-soft:rgba(255,154,77,.12); --accent-line:rgba(255,154,77,.32);
    --ok:#34D399; --warn:#FBBF24; --bad:#FB7185;
    --surface:rgba(32,35,44,.52);
    --surface-hover:rgba(44,48,58,.64);
    --surface-solid:rgba(26,29,37,.9);
    --surface-flat:#1A1D25; --surface-flat-hover:#2A2F3B;
    --custom-bg-veil:rgba(12,14,20,.7);
    --field:rgba(20,23,31,.78); --field-line:rgba(255,190,130,.2);
    --control:rgba(30,34,44,.74); --control-hover:rgba(40,45,57,.86);
    --shadow:0 20px 45px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.08);
    --shadow-float:0 24px 54px rgba(0,0,0,.52), inset 0 1px 0 rgba(255,255,255,.1);
    --glass-edge:rgba(255,190,130,.3);
    --glass-shadow:0 18px 44px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.1);
    --glass-shadow-soft:0 6px 18px rgba(0,0,0,.32), inset 0 1px 0 rgba(255,255,255,.06);
    background:radial-gradient(1100px 640px at 10% -12%, rgba(255,154,77,.08), transparent 62%),
               linear-gradient(160deg,#0E1016 0%,#14161E 55%,#090A0F 100%) fixed;
    background-color:#0E1016;
  }
  /* Con lo sfondo aziendale la foto si vede di piu' (velo leggero), quindi il
     vetro diventa piu' denso: il testo dei pannelli resta sopra AA qualunque
     immagine venga caricata. Senza immagine questi valori non si applicano. */
  body.has-custom-bg {
    --custom-bg-veil:rgba(251,247,242,.6);
    --surface:rgba(255,252,247,.6);
    --surface-hover:rgba(255,252,247,.74);
    --surface-solid:rgba(255,253,250,.96);
    --surface-flat:#FFFDFA; --surface-flat-hover:#FFF1E4;
  }
  body.dark.has-custom-bg {
    --custom-bg-veil:rgba(12,14,20,.58);
    --surface:rgba(18,20,28,.72);
    --surface-hover:rgba(26,29,38,.82);
    --surface-solid:rgba(16,18,25,.94);
    --surface-flat:#101219; --surface-flat-hover:#242936;
  }
  body.dark header, body.dark .topbar {
    background:var(--surface); border-color:var(--glass-line);
  }
  body.dark input, body.dark select, body.dark textarea {
    background:var(--field); color:var(--text);
    border-color:var(--field-line);
    box-shadow:inset 0 1px 0 rgba(255,154,77,.05);
  }
  body.dark input::placeholder, body.dark textarea::placeholder { color:rgba(199,209,224,.64); }
  body.dark button {
    background:var(--control); color:var(--text);
    border-color:rgba(255,154,77,.14);
    box-shadow:0 8px 22px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,154,77,.06);
  }
  body.dark button:hover { background:var(--control-hover); }
  body.dark button.ok {
    background:var(--accent); color:var(--accent-ink);
    border-color:var(--accent-line); font-weight:700;
    box-shadow:0 10px 26px rgba(255,154,77,.24);
  }
  body.dark .card button {
    background:var(--accent); color:var(--accent-ink);
    border-color:var(--accent-line); font-weight:700;
    box-shadow:0 10px 26px rgba(255,154,77,.22);
  }
  body.dark button.danger {
    background:rgba(248,113,113,.16); color:#fda4af;
    border-color:rgba(255,69,58,.32);
  }
  body.dark table th { border-color:rgba(255,154,77,.14); }
  body.dark table td { border-color:rgba(255,255,255,.07); }
  body.dark tbody tr:hover { background:rgba(255,255,255,.05); }
  body.dark a, body.dark code { color:var(--accent); }
  body.dark .leaflet-bar a {
    background:var(--control-hover); color:var(--text); border-color:rgba(255,255,255,.16);
  }
  body.dark .leaflet-bar a:hover { background:var(--control-hover); }
  body.dark .leaflet-control-attribution {
    background:var(--surface-hover); color:var(--muted);
  }
  body.dark .badge.on, body.dark .badge.ok, body.dark .badge.active {
    color:#6ee7a0; background:rgba(52,199,89,.18); border-color:rgba(52,199,89,.36);
  }
  body.dark .badge.off, body.dark .badge.pending, body.dark .badge.offline {
    color:var(--muted); background:rgba(148,163,184,.16);
    border-color:rgba(148,163,184,.24);
  }
  body.dark .badge.warn { color:#fcd34d; background:rgba(251,191,36,.16); }
  body.dark .badge.bad { color:#fda4af; background:rgba(251,113,133,.18); }
  /* Chip e stati: senza override il vetro bianco restava sotto testo chiaro. */
  body.dark .chip {
    background:rgba(255,154,77,.06); border-color:rgba(255,154,77,.16); color:var(--muted);
  }
  body.dark .chip.live { border-color:rgba(52,199,89,.5); color:#6EE7A0; }
  body.dark .chip.partial { border-color:rgba(251,191,36,.5); color:#FCD34D; }
  body.dark .chip.hardware { border-color:rgba(255,154,77,.4); color:var(--accent); }
  body.dark .status-text.moving, body.dark .status-pill.moving { color:#6EE7A0; }
  body.dark .status-text.stopped, body.dark .status-pill.stopped { color:#FCD34D; }
  body.dark .status-text.alarm, body.dark .status-pill.alarm { color:#FDA4AF; }
  body.dark .emergency-kicker { color:#FDA4AF; }
  body.dark .side-group-title { color:rgba(199,209,224,.55); }
  body.dark .map-search-panel input::placeholder { color:rgba(199,209,224,.64); }
  body.dark .leaflet-popup-content-wrapper, body.dark .leaflet-popup-tip {
    background:rgba(16,18,25,.97); color:var(--text);
    border-color:var(--glass-line);
  }
  body.dark pre#prov, body.dark .drop {
    background:var(--field); border-color:rgba(255,255,255,.16);
  }
  body.dark .side-results { background:rgba(16,18,25,.97); }
  body.dark .side-results button { color:var(--text); }

  /* Conferma di invio per i comandi critici (blocco motore, ecc.).
     In coda al foglio: deve vincere sulle regole .danger del tema notturno. */
  button.action-done, button.action-done:hover, body button.action-done:disabled {
    background:rgba(16,185,129,.9); color:#fff;
    border-color:rgba(16,185,129,.65); opacity:1; cursor:default;
    transform:none;
    box-shadow:0 0 0 3px rgba(16,185,129,.22), 0 10px 24px rgba(16,185,129,.32);
  }

  /* ===== Live AI Canvas: assemblaggio delle viste all'apertura ===== */
  @keyframes canvasAssemble {
    from { opacity:0; transform:scale(.95); }
    55% { opacity:1; }
    to { opacity:1; transform:scale(1); }
  }
  .canvas-assemble {
    animation:canvasAssemble 1.28s cubic-bezier(.2,.8,.2,1) both;
    transform-origin:center center;
  }
  /* Overlay decorativo: mai sopra i click dell'operatore. */
  .canvas-overlay {
    position:fixed; inset:0; z-index:2100; pointer-events:none;
    overflow:hidden; transition:opacity .24s ease;
  }
  .canvas-overlay.out { opacity:0; }
  .canvas-box {
    position:absolute; display:block; box-sizing:border-box;
    border:1px solid rgba(120,72,40,.55); border-radius:14px;
    box-shadow:0 0 0 1px rgba(255,255,255,.5) inset;
    animation:canvasBox 1.32s ease forwards;
  }
  body.dark .canvas-box {
    border-color:rgba(255,154,77,.6);
    box-shadow:0 0 0 1px rgba(255,154,77,.14) inset;
  }
  .canvas-box i {
    position:absolute; width:6px; height:6px; border-radius:1px;
    background:var(--accent); box-shadow:0 0 0 1.5px #fff;
  }
  .canvas-box i:nth-child(1) { top:-3px; left:-3px; }
  .canvas-box i:nth-child(2) { top:-3px; right:-3px; }
  .canvas-box i:nth-child(3) { bottom:-3px; left:-3px; }
  .canvas-box i:nth-child(4) { bottom:-3px; right:-3px; }
  body.dark .canvas-box i { box-shadow:0 0 0 1.5px #0E1016; }
  @keyframes canvasBox {
    0% { opacity:0; transform:scale(.95); }
    16% { opacity:1; transform:scale(1); }
    74% { opacity:1; }
    100% { opacity:0; }
  }
  .canvas-cursor {
    position:absolute; top:0; left:0; display:flex; align-items:center; gap:4px;
    opacity:0; will-change:transform, opacity;
  }
  .canvas-cursor svg { width:13px; height:17px; display:block; }
  .canvas-cursor span {
    font-size:9.5px; font-weight:700; letter-spacing:.02em; white-space:nowrap;
    padding:2px 6px; border-radius:999px; color:#0E1016;
    background:var(--tag, #FF9A4D);
    box-shadow:0 4px 12px rgba(0,0,0,.25);
  }
  @media (prefers-reduced-motion:reduce) {
    .canvas-assemble { animation:none; }
    .canvas-overlay { display:none; }
  }

  /* ===== Gerarchia del vetro ===== */
  /* Dashboard: vetro pieno, blur ampio, bordi luminosi sul bordo attivo. */
  [data-view="dashboard"] .panel, [data-view="dashboard"] .card {
    background:var(--surface);
    border-color:var(--glass-edge);
    border-radius:24px;
    box-shadow:var(--glass-shadow);
    backdrop-filter:var(--glass-blur); -webkit-backdrop-filter:var(--glass-blur);
  }
  [data-view="dashboard"] .kpi {
    background:linear-gradient(155deg,var(--surface-hover),var(--surface));
    border-color:var(--glass-edge);
    box-shadow:var(--glass-shadow);
    backdrop-filter:var(--glass-blur); -webkit-backdrop-filter:var(--glass-blur);
  }
  [data-view="dashboard"] .panel:hover, [data-view="dashboard"] .card:hover, [data-view="dashboard"] .kpi:hover {
    background:var(--surface-hover);
    box-shadow:var(--shadow-float);
  }
  [data-view="dashboard"] .panel:focus-within, [data-view="dashboard"] .card:focus-within {
    border-color:var(--warm-line);
  }

  /* Sezioni operative: nessun blur sui dati densi, righe leggibili, hover caldo. */
  .tab:not([data-view="dashboard"]) th { border-bottom:1px solid var(--line); }
  .tab:not([data-view="dashboard"]) td { border-bottom:1px solid var(--line); }
  .tab:not([data-view="dashboard"]) tbody tr:hover { background:var(--accent-soft); }
  .tab:not([data-view="dashboard"]) input,
  .tab:not([data-view="dashboard"]) select,
  .tab:not([data-view="dashboard"]) textarea,
  .tab:not([data-view="dashboard"]) button {
    backdrop-filter:none; -webkit-backdrop-filter:none;
  }
  .tab:not([data-view="dashboard"]) .kpi { border-radius:16px; }

  /* Fallback: senza backdrop-filter il vetro diventa superficie piena. */
  @supports not ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))) {
    .panel, .card, .kpi, .topbar, .sidebar, .dock, .map-glass,
    .modal-card, #toast, .playback-panel, .side-results {
      background:var(--surface-solid);
    }
  }
  /* Trasparenza ridotta: preferenza dell'utente, vince su ogni vetro decorativo
     anche quando regole successive (mobile compreso) riaccendono il blur. */
  @media (prefers-reduced-transparency:reduce) {
    .panel, .card, .kpi, .topbar, .sidebar, .dock, .map-glass,
    .modal-card, #toast, .playback-panel, .side-results,
    [data-view="dashboard"] .panel, [data-view="dashboard"] .card, [data-view="dashboard"] .kpi {
      background:var(--surface-flat) !important;
      backdrop-filter:none !important; -webkit-backdrop-filter:none !important;
    }
    /* Opache ma reattive: hover e focus restano distinguibili senza tornare
       translucidi. Il gradiente dei KPI lascia il posto a una tinta piatta. */
    .panel:hover, .card:hover, .kpi:hover,
    [data-view="dashboard"] .panel:hover, [data-view="dashboard"] .card:hover, [data-view="dashboard"] .kpi:hover {
      background:var(--surface-flat-hover) !important;
    }
    /* Veli e scrim restano traslucidi: si toglie solo la sfocatura. */
    #side-scrim, .bg-preview-chip {
      backdrop-filter:none !important; -webkit-backdrop-filter:none !important;
    }
  }
  /* Anello di focus unico: pulsanti e campi condividono stile e colore,
     così la navigazione da tastiera resta coerente in tutta la piattaforma. */
  button:focus-visible, a:focus-visible, .side-nav button:focus-visible,
  input:focus-visible, select:focus-visible, textarea:focus-visible {
    outline:2px solid var(--accent); outline-offset:2px;
  }
  /* I pulsanti a riempimento accento hanno lo stesso colore dell'anello (1:1):
     l'indicatore si fonderebbe col fondo del pulsante. Solo su quelli l'anello
     diventa a due toni, con una linea del colore "ink" aderente al riempimento
     (bianca nel tema giorno, 5,1:1; quasi nera in quello notte, 8,8:1) e
     l'accento esterno sul fondo della pagina. Negli altri casi resta l'anello
     unico qui sopra. */
  body button.ok:focus-visible,
  body .card button:not(.danger):focus-visible,
  body .vehicle-actions button.ok:focus-visible,
  body .playback-play:focus-visible {
    outline:2px solid transparent; outline-offset:2px;
    box-shadow:0 0 0 2px var(--accent-ink), 0 0 0 4px var(--accent);
  }

  @media print {
    html { background:#fff; }
    body { background:#fff; color:var(--text); }
    body::before, body::after { display:none; }
    .panel, .card, .kpi {
      background:#fff; box-shadow:none; border:1px solid #dfe4ea;
      backdrop-filter:none; -webkit-backdrop-filter:none;
    }
  }
"""


DASHBOARD_CSS = BASE_CSS + """
  /* ===== Anteprima dello sfondo nelle impostazioni del cliente ===== */
  .bg-preview {
    --preview-veil:rgba(251,247,242,.62);
    margin-top:12px; height:132px; border-radius:18px; overflow:hidden;
    border:1px solid var(--glass-line); background-color:var(--surface);
    background-image:
      linear-gradient(var(--preview-veil), var(--preview-veil)),
      var(--bg-preview-image, none);
    background-size:cover; background-position:center;
    display:flex; align-items:flex-end; padding:10px 12px;
  }
  body.dark .bg-preview { --preview-veil:rgba(14,16,22,.6); }
  .bg-preview-chip {
    padding:6px 12px; border-radius:12px; font-size:11.5px;
    background:var(--surface); border:1px solid var(--glass-line);
    color:var(--text); backdrop-filter:blur(10px);
  }

  /* ===== Shell: sidebar fluttuante + area di lavoro ===== */
  .app-shell { display:flex; align-items:stretch; min-height:100vh; }
  .workspace { flex:1; min-width:0; display:flex; flex-direction:column; }
  main, .tab-inner, .panel, .kpis, .grid2 { min-width:0; }
  main {
    width:100%; max-width:1320px; margin:22px auto;
    padding:0 24px 32px; display:flex; flex-direction:column; gap:18px;
  }
  /* La dock fluttua sempre su spazio vuoto: 100px riservati in fondo. */
  body { padding-bottom:100px; }

  /* Barra superiore */
  .topbar {
    display:flex; justify-content:space-between; align-items:center;
    gap:14px; flex-wrap:wrap;
    margin:14px 16px 0; padding:12px 20px;
    background:var(--surface);
    border:1px solid var(--glass-line); border-radius:24px;
    box-shadow:var(--shadow-float);
    backdrop-filter:var(--blur); -webkit-backdrop-filter:var(--blur);
    position:sticky; top:12px; z-index:900;
  }
  .brand { display:flex; align-items:center; gap:10px; min-width:0; }
  .brand-mark {
    width:28px; height:28px; flex:0 0 28px; border-radius:10px;
    background:linear-gradient(135deg,var(--accent),var(--accent-2));
    box-shadow:0 8px 20px var(--accent-line);
  }
  body.dark .brand-mark {
    background:linear-gradient(135deg,#FF9A4D,#FFB173);
    box-shadow:0 0 18px rgba(255,154,77,.35);
  }
  .brand h1 { font-size:15px; margin:0; color:var(--text); }
  .brand .sub { font-size:11.5px; }
  .brand-badge {
    padding:5px 12px; border-radius:999px; white-space:nowrap;
    background:var(--accent-soft); color:var(--accent);
    border:1px solid var(--accent-line);
    font-size:10.5px; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
  }
  .tools { display:flex; align-items:center; gap:8px; flex-wrap:wrap; min-width:0; }
  .topbar .badge, .topbar .sub { white-space:nowrap; }

  /* Sidebar */
  .sidebar {
    position:fixed; top:0; bottom:0; left:0; width:min(88vw,300px); height:100vh;
    z-index:1300; display:flex; flex-direction:column; gap:7px; padding:18px 14px;
    overflow-y:auto; margin:0; transform:translateX(-102%);
    transition:transform .24s cubic-bezier(.2,.8,.2,1);
    background:var(--surface-solid);
    border-right:1px solid var(--glass-line); border-radius:0 24px 24px 0;
    box-shadow:var(--shadow-float), inset 0 1px 0 rgba(255,255,255,.9);
    backdrop-filter:var(--blur); -webkit-backdrop-filter:var(--blur);
    scrollbar-width:thin; scrollbar-color:rgba(120,72,40,.26) transparent;
  }
  .sidebar.open { transform:none; }
  .sidebar::-webkit-scrollbar { width:6px; }
  .sidebar::-webkit-scrollbar-thumb { background:rgba(120,72,40,.22); border-radius:999px; }
  .sidebar::-webkit-scrollbar-track { background:transparent; }
  .sidebar .brand { padding:2px 6px 8px; }
  .sidebar-search { position:relative; margin-bottom:2px; }
  .sidebar-search input { width:100%; padding:10px 13px; font-size:12.5px; }
  .side-results {
    position:absolute; top:calc(100% + 6px); left:0; right:0; z-index:400;
    display:none; overflow:hidden;
    background:var(--surface-solid);
    border:1px solid rgba(255,255,255,.6); border-radius:16px;
    box-shadow:var(--shadow-float);
    backdrop-filter:blur(16px) saturate(150%);
    -webkit-backdrop-filter:blur(16px) saturate(150%);
  }
  .side-results.open { display:block; }
  .side-results button {
    display:block; width:100%; text-align:left;
    padding:9px 12px; font-size:12px; font-weight:500;
    background:transparent; border:0; border-radius:0; box-shadow:none;
    color:var(--text); backdrop-filter:none; -webkit-backdrop-filter:none;
  }
  .side-results button:hover { background:var(--accent-soft); transform:none; }
  .side-results small { display:block; color:var(--muted); font-size:10.5px; margin-top:1px; }
  .side-results .side-empty { padding:9px 12px; font-size:12px; color:var(--muted); }
  .side-user {
    display:flex; align-items:center; gap:12px; padding:12px 14px;
    background:var(--surface);
    border:1px solid var(--glass-line); border-radius:18px;
  }
  .side-avatar {
    width:38px; height:38px; flex:0 0 38px; border-radius:50%;
    display:flex; align-items:center; justify-content:center;
    font-size:13px; font-weight:700; color:var(--accent-ink);
    background:linear-gradient(135deg,var(--accent),var(--accent-2));
    box-shadow:0 8px 18px var(--accent-line);
  }
  body.dark .side-avatar {
    background:linear-gradient(135deg,#FF9A4D,#FFB173); color:#0E1016;
  }
  .side-user h4 { margin:0; font-size:13.5px; color:var(--text); }
  .side-user p { margin:2px 0 0; font-size:11px; color:var(--muted); }
  .side-group-title {
    padding:9px 10px 1px; font-size:10.5px; font-weight:600;
    text-transform:uppercase; letter-spacing:.12em; color:rgba(120,72,40,.55);
  }
  .side-nav { display:flex; flex-direction:column; gap:2px; }
  .side-nav button, .side-status {
    display:flex; align-items:center; gap:9px; width:100%;
    padding:8px 10px; border-radius:11px;
    background:transparent; border:1px solid transparent; box-shadow:none;
    text-align:left; font-size:12.5px; font-weight:500; color:#4a4a4d;
    backdrop-filter:none; -webkit-backdrop-filter:none;
  }
  .side-nav button:hover {
    background:rgba(255,255,255,.62);
    border-color:rgba(255,255,255,.8); color:var(--text);
  }
  .side-nav button.active {
    background:var(--accent-soft);
    border-color:var(--accent-line); color:var(--accent);
  }
  .side-nav .ico { width:18px; text-align:center; }
  .side-nav .count {
    margin-left:auto; padding:1px 8px; border-radius:999px;
    background:var(--accent-soft); color:var(--muted); font-size:10.5px;
  }
  .side-nav button.active .count { background:var(--accent-soft); color:var(--accent); }
  .side-status { justify-content:space-between; cursor:default; }
  .side-status .badge { margin-left:auto; }
  .side-toggle-row {
    display:flex; align-items:center; justify-content:space-between; gap:10px;
    padding:9px 11px; border-radius:16px;
    background:var(--surface); border:1px solid var(--glass-line);
    font-size:12.5px; font-weight:500; color:var(--text);
  }
  .side-toggle-row small {
    display:block; margin-top:2px; font-size:10.5px;
    font-weight:400; color:var(--muted);
  }
  .switch { position:relative; width:40px; height:22px; flex:0 0 40px; }
  .switch input {
    position:absolute; inset:0; z-index:1; width:100%; height:100%;
    margin:0; opacity:0; cursor:pointer;
  }
  .switch .slider {
    position:absolute; inset:0; border-radius:999px; cursor:pointer;
    background:rgba(120,120,128,.3); border:1px solid rgba(255,255,255,.6);
    transition:background .18s ease;
  }
  .switch .slider::before {
    content:""; position:absolute; top:50%; left:2px; width:16px; height:16px;
    border-radius:50%; background:#fff; transform:translateY(-50%);
    box-shadow:0 1px 3px rgba(0,0,0,.35); transition:transform .18s ease;
  }
  .switch input:checked + .slider {
    background:linear-gradient(180deg,#34c759,#248a3d);
    border-color:rgba(255,255,255,.55);
  }
  .switch input:checked + .slider::before { transform:translate(18px,-50%); }
  .switch input:disabled + .slider { opacity:.55; cursor:not-allowed; }
  .switch input:focus-visible { outline:none; }
  .switch input:focus-visible + .slider { outline:2px solid var(--accent); outline-offset:2px; }
  .menu-toggle { display:inline-flex; align-items:center; padding:6px 11px; font-size:15px; line-height:1; }
  .side-close {
    display:inline-flex; margin-left:auto; padding:0 4px; font-size:22px; line-height:1;
    background:transparent; border:0; box-shadow:none; color:var(--muted);
  }
  #side-scrim {
    position:fixed; inset:0; z-index:1290; display:none;
    background:rgba(9,10,12,.32);
    backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
  }
  #side-scrim.open { display:block; }
  body.side-lock { overflow:hidden; }

  /* Dock inferiore */
  .dock {
    position:fixed; bottom:16px; left:50%; transform:translateX(-50%);
    display:flex; gap:2px; padding:7px 10px; overflow-x:auto; overflow-y:hidden;
    max-width:96vw; z-index:1000; scrollbar-width:none; scroll-behavior:smooth;
    background:var(--surface);
    border:1px solid var(--glass-line); border-radius:28px;
    box-shadow:0 24px 54px rgba(0,0,0,.08), inset 0 1px 1px rgba(255,255,255,.98);
    backdrop-filter:var(--blur); -webkit-backdrop-filter:var(--blur);
    -webkit-mask-image:linear-gradient(to right, transparent 0, #000 16px, #000 calc(100% - 16px), transparent 100%);
    mask-image:linear-gradient(to right, transparent 0, #000 16px, #000 calc(100% - 16px), transparent 100%);
  }
  .dock::-webkit-scrollbar { display:none; }
  .dock { scroll-snap-type:x proximity; }
  .dock button {
    flex:0 0 auto; scroll-snap-align:center;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    gap:2px; min-width:58px; white-space:nowrap; padding:6px 8px;
    font-size:9.5px; font-weight:600; letter-spacing:.01em;
    border-radius:18px; background:transparent; border-color:transparent;
    box-shadow:none; color:var(--muted);
    backdrop-filter:none; -webkit-backdrop-filter:none;
    transition:background .18s ease, color .18s ease, transform .18s ease;
  }
  .dock .ico { font-size:17px; line-height:1.15; filter:saturate(.9); }
  .dock button:hover {
    background:var(--control); color:var(--text); transform:translateY(-2px);
  }
  .dock button.active {
    background:var(--accent-soft); color:var(--accent);
    border-color:var(--accent-line);
    box-shadow:0 0 18px var(--accent-soft);
  }
  .dock button.active .ico { filter:none; }

  /* Widget magnetici: opacità a distanza */
  .map-glass.glass-dim { opacity:.76; }
  .map-glass.glass-dim:hover, .map-glass.glass-dim:focus-within { opacity:1; }
  @media (min-width:901px) {
    .vehicle-card { transition:width .28s ease, opacity .3s ease, background .25s ease, box-shadow .25s ease; }
    .vehicle-card:hover { width:360px; }
    .device-sidebar { transition:width .28s ease, opacity .3s ease; }
    .device-sidebar:hover { width:300px; }
    .map-search-panel { transition:width .28s ease; }
    .map-search-panel:focus-within { width:min(430px, calc(100% - 400px)); }
  }

  /* Dark Liquid Glass: superfici specifiche della dashboard */
  body.dark .sidebar {
    background:rgba(16,18,25,.96); border-color:var(--glass-line);
  }
  /* Il fondo generico body.dark button aggiungerebbe bordo e ombra anche alle
     voci piatte: qui si ridichiara lo stile della base, non i colori. */
  body.dark .side-nav button, body.dark .side-status {
    background:transparent; border-color:transparent; box-shadow:none;
    color:var(--muted);
  }
  body.dark .side-nav button:hover {
    background:rgba(255,255,255,.08); border-color:rgba(255,255,255,.14);
  }
  body.dark .side-nav button.active {
    background:var(--accent-soft); color:var(--accent); border-color:var(--accent-line);
  }
  body.dark .side-user, body.dark .side-toggle-row {
    background:rgba(255,255,255,.06); border-color:rgba(255,255,255,.12);
  }
  body.dark .dock {
    background:var(--surface); border-color:var(--glass-line);
    box-shadow:0 24px 54px rgba(0,0,0,.55), inset 0 1px 0 rgba(255,154,77,.1);
  }
  body.dark .dock button {
    background:transparent; border-color:transparent; box-shadow:none;
    color:var(--muted);
  }
  body.dark .dock button:hover { background:rgba(255,154,77,.08); color:var(--text); }
  body.dark .dock button.active {
    background:var(--accent-soft); color:var(--accent);
    border-color:var(--accent-line);
    box-shadow:0 0 22px rgba(255,154,77,.18);
  }
  /* Stessa ragione per le chiusure icona: restano senza fondo né bordo. */
  body.dark .side-close, body.dark .eh-close {
    background:transparent; border-color:transparent; box-shadow:none;
    color:var(--muted);
  }
  body.dark .map-glass {
    background:var(--surface); border-color:var(--glass-line);
  }
  body.dark .map-glass:hover { background:var(--surface-hover); }
  body.dark .map-search-panel input { background:transparent; border:0; box-shadow:none; }
  body.dark .vehicle-grid div, body.dark .vehicle-address, body.dark .device-item {
    background:rgba(255,255,255,.06); border-color:rgba(255,255,255,.1);
  }
  body.dark .device-item:hover { background:rgba(255,255,255,.1); }
  body.dark .device-item.selected {
    background:var(--accent-soft); border-color:var(--accent-line);
  }
  body.dark .vehicle-actions button {
    background:var(--control); color:var(--accent);
    border-color:var(--accent-line); box-shadow:none;
  }
  body.dark .vehicle-actions button.ok {
    background:var(--accent); color:var(--accent-ink);
    box-shadow:0 8px 24px rgba(255,154,77,.24);
  }
  body.dark .status-pill.offline { color:var(--muted); }
  body.dark .map-controls button { background:var(--control); color:var(--text); border-color:rgba(255,255,255,.16); }
  body.dark .map-controls button:hover { background:var(--control-hover); }
  body.dark .map-controls a { color:var(--accent); }
  body.dark .map-shell { background:#0B0E14; border-color:rgba(255,255,255,.12); }
  body.dark .leaflet-container { background:#0B0E14; }
  body.dark .leaflet-tile-pane {
    filter:invert(1) hue-rotate(180deg) brightness(.95) contrast(.9) saturate(.6);
  }
  body.dark .emergency-hud {
    background:rgba(16,18,25,.9); border-color:rgba(255,255,255,.2);
    box-shadow:0 28px 70px rgba(0,0,0,.55), 0 0 0 1px rgba(251,113,133,.16);
  }
  body.dark .modal-card { background:rgba(16,18,25,.97); border-color:rgba(255,255,255,.16); }
  body.dark #toast { background:rgba(16,18,25,.96); border-color:rgba(255,255,255,.16); }
  body.dark .playback-kpis div, body.dark .playback-speed {
    background:rgba(255,255,255,.06); border-color:rgba(255,255,255,.12);
  }
  body.dark .playback-dates input[type="date"] {
    background:var(--field); color:var(--text); border-color:rgba(255,255,255,.16);
  }

  /* Contenuto delle schede */
  .tab { display:none; }
  .tab.active { display:block; }
  .tab-inner { display:flex; flex-direction:column; gap:18px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
  .kpi:hover {
    transform:translateY(-2px);
    box-shadow:0 26px 54px rgba(4,42,31,.16);
  }
  /* Card con allarmi aperti: priorita' visiva senza leggere il numero. */
  .kpi.card-alert-active {
    background:linear-gradient(155deg,rgba(239,68,68,.18),rgba(239,68,68,.07));
    border-color:rgba(239,68,68,.45);
    animation:pulseGlow 2.4s ease-in-out infinite;
  }
  .kpi.card-alert-active .label { color:#b42318; }
  body.dark .kpi.card-alert-active {
    background:linear-gradient(155deg,rgba(239,68,68,.24),var(--surface-hover));
    border-color:rgba(251,113,133,.52);
  }
  body.dark .kpi.card-alert-active .label { color:#fda4af; }
  @keyframes pulseGlow {
    0%, 100% { box-shadow:0 0 0 1px rgba(239,68,68,.2), 0 14px 34px rgba(239,68,68,.16); }
    50% { box-shadow:0 0 0 1px rgba(239,68,68,.32), 0 18px 46px rgba(239,68,68,.3); }
  }
  .scroll { max-height:430px; overflow:auto; border-radius:18px; -webkit-overflow-scrolling:touch; }
  .chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
  .chip {
    font-size:12px; padding:6px 10px; border-radius:999px;
    background:var(--surface);
    border:1px solid var(--glass-line); color:var(--muted);
  }
  .chip.live { border-color:rgba(52,199,89,.5); color:#1c7c34; }
  .chip.partial { border-color:rgba(255,159,10,.5); color:#9a5b00; }
  .chip.hardware { border-color:var(--accent-line); color:var(--accent); }
  .chip.planned { opacity:.62; }
  #kpi-moving { color:var(--accent); }
  .pending-note {
    border-left:3px solid #ff9f0a; padding-left:12px;
    color:var(--muted); font-size:12.5px;
  }

  /* Dialoghi e messaggi */
  .modal {
    position:fixed; inset:0; display:none; align-items:center; justify-content:center;
    padding:20px; z-index:1400; background:rgba(9,10,12,.3);
    backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
  }
  .modal.open { display:flex; }
  .modal-card {
    width:100%; max-width:420px; padding:20px; border-radius:20px;
    background:var(--surface-solid); border:1px solid var(--glass-line);
    box-shadow:0 24px 60px rgba(4,42,31,.22),
               inset 0 1px 0 rgba(255,255,255,.95);
    backdrop-filter:var(--blur); -webkit-backdrop-filter:var(--blur);
    color:var(--text);
  }
  .modal-card h3 { margin:0 0 8px; font-size:15px; color:var(--text); }
  #toast {
    position:fixed; left:50%; bottom:112px;
    transform:translateX(-50%) translateY(18px);
    background:var(--surface-solid); color:var(--text);
    border:1px solid var(--glass-line); border-radius:14px;
    padding:11px 16px; font-size:12.5px; max-width:72vw;
    opacity:0; pointer-events:none; transition:.22s; z-index:1350;
    box-shadow:var(--shadow-float);
    backdrop-filter:blur(16px) saturate(150%);
    -webkit-backdrop-filter:blur(16px) saturate(150%);
  }
  #toast.show { opacity:1; transform:translateX(-50%) translateY(0); }
  #toast.bad { border-color:rgba(215,0,21,.35); color:#b00015; }
  #toast.okv { border-color:rgba(28,138,60,.35); color:#137a32; }
  #offline-banner {
    background:rgba(255,159,10,.16); color:#7a4a00;
    border:1px solid rgba(255,159,10,.35); border-radius:16px;
  }

  /* Mappa */
  .map-shell {
    position:relative; height:calc(100vh - 220px); min-height:520px;
    margin:0 18px 8px; border-radius:24px; overflow:hidden;
    background:#e8eef8; border:1px solid rgba(255,255,255,.5);
    box-shadow:var(--shadow-float);
  }
  body.map-mode main { max-width:none; padding-left:10px; padding-right:10px; }
  body.map-mode .map-shell { height:calc(100vh - 148px); }
  #map { position:absolute; inset:0; width:100%; height:100%; background:#e8eef8; }
  /* Sfumature fluide sui bordi, sotto marker e pannelli: il centro della
     mappa resta pulito, altrimenti le tile chiare perdono contrasto. */
  .map-shell::after {
    content:""; position:absolute; inset:0; z-index:350; pointer-events:none;
    background:
      radial-gradient(130% 96% at 50% 50%, transparent 58%, rgba(120,170,230,.12) 100%),
      radial-gradient(620px 420px at 6% 0%, rgba(140,190,255,.16), transparent 56%),
      radial-gradient(560px 400px at 100% 100%, rgba(150,225,220,.14), transparent 56%);
  }
  .leaflet-container { background:#e8eef8; font:inherit; }
  .leaflet-tile-pane { filter:none; }
  /* Mappa: i contenitori Leaflet restano opachi. Un backdrop-filter sopra un
     canvas di tile produce artefatti e sgranature in iOS/Safari, oltre a un
     composito per ogni pan. */
  .map-shell, #map, .leaflet-container, .leaflet-tile-pane,
  .leaflet-pane, .gmaps-frame {
    backdrop-filter:none !important;
    -webkit-backdrop-filter:none !important;
  }
  .map-shell, #map, .leaflet-container, .leaflet-tile-pane { background:#e8eef8; }
  body.dark .map-shell, body.dark #map, body.dark .leaflet-container,
  body.dark .leaflet-tile-pane { background:#0B0E14; }
  .map-glass {
    position:absolute; z-index:600;
    background:var(--surface);
    border:1px solid var(--glass-line);
    border-radius:20px;
    box-shadow:var(--shadow-float);
    backdrop-filter:var(--blur); -webkit-backdrop-filter:var(--blur);
    color:var(--text); animation:panelIn .35s ease both;
    transition:opacity .3s ease, background .25s ease, box-shadow .25s ease, border-color .25s ease;
  }
  .map-glass:hover {
    background:var(--surface-hover);
    box-shadow:0 28px 60px rgba(4,42,31,.14);
  }

  /* HUD di emergenza: vetro liquido sopra la mappa, senza oscurarla */
  .emergency-hud {
    position:fixed; top:84px; left:50%; transform:translateX(-50%);
    z-index:1250; width:min(560px, calc(100vw - 32px)); padding:16px 18px;
    border:1px solid rgba(255,255,255,.98); border-left:3px solid #ff453a;
    border-radius:22px; background:rgba(255,255,255,.78);
    box-shadow:0 28px 70px rgba(180,20,30,.18), 0 0 0 1px rgba(255,69,58,.12);
    backdrop-filter:blur(28px) saturate(170%);
    -webkit-backdrop-filter:blur(28px) saturate(170%);
    animation:hudIn .3s cubic-bezier(.2,.8,.2,1) both;
  }
  .emergency-hud[hidden] { display:none; }
  @keyframes hudIn {
    from { opacity:0; transform:translate(-50%,-12px) scale(.98); }
    to { opacity:1; transform:translate(-50%,0) scale(1); }
  }
  .emergency-head { display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .emergency-kicker {
    font-size:9.5px; font-weight:800; letter-spacing:.14em;
    text-transform:uppercase; color:#c31d10;
  }
  .emergency-hud strong { display:block; margin-top:6px; font-size:20px; letter-spacing:-.02em; }
  .emergency-detail { display:block; margin-top:2px; font-size:12px; color:var(--muted); }
  .eh-close {
    background:transparent; border:0; box-shadow:none; padding:0 4px;
    font-size:20px; line-height:1; color:var(--muted);
  }
  .emergency-actions { margin-top:12px; }
  .emergency-actions button { border-radius:14px; }
  @keyframes panelIn {
    from { opacity:0; transform:translateY(10px) scale(.985); }
    to { opacity:1; transform:translateY(0) scale(1); }
  }
  .map-search-panel {
    top:18px; left:20px; width:min(360px, calc(100% - 400px));
    display:flex; align-items:center; gap:10px; padding:8px 14px;
  }
  .map-search-panel input {
    width:100%; padding:6px 0; font-size:13px;
    background:transparent; border:0; box-shadow:none;
    color:var(--text); backdrop-filter:none; -webkit-backdrop-filter:none;
  }
  .map-search-panel input:focus { background:transparent; border:0; box-shadow:none; outline:none; }
  .map-search-panel input::placeholder { color:rgba(16,52,42,.7); }
  .search-icon {
    width:11px; height:11px; flex:0 0 auto; position:relative;
    border:2px solid var(--accent); border-radius:50%; box-shadow:none;
  }
  .search-icon::after {
    content:''; position:absolute; width:2px; height:6px; right:-3px; bottom:-4px;
    background:var(--accent); transform:rotate(-45deg); border-radius:2px;
  }
  .map-count {
    font-size:11px; font-weight:700; color:var(--accent);
    background:var(--accent-soft); border-radius:999px; padding:3px 8px;
    white-space:nowrap;
  }
  .device-sidebar {
    top:82px; left:20px; bottom:82px; width:280px; padding:14px;
    display:flex; flex-direction:column;
  }
  .map-side-head {
    display:flex; justify-content:space-between; align-items:center;
    padding:2px 6px 10px; font-size:10.5px; letter-spacing:.12em;
    text-transform:uppercase; color:var(--muted);
  }
  .device-list {
    overflow:auto; display:flex; flex-direction:column; gap:6px;
    padding-right:2px; scrollbar-width:thin;
    scrollbar-color:rgba(120,72,40,.26) transparent;
  }
  .device-list::-webkit-scrollbar { width:6px; }
  .device-list::-webkit-scrollbar-thumb { background:rgba(120,72,40,.22); border-radius:999px; }
  .device-item {
    display:flex; align-items:center; gap:10px; width:100%; text-align:left;
    padding:9px 10px; border-radius:16px;
    background:rgba(255,255,255,.62); color:var(--text);
    border:1px solid transparent; box-shadow:none;
    font-size:inherit; font-weight:400;
    transition:background .18s ease, border-color .18s ease, transform .18s ease;
  }
  .device-item:hover { background:rgba(255,255,255,.8); transform:translateX(2px); }
  .device-item.selected {
    background:var(--accent-soft); border-color:var(--accent-line);
    box-shadow:0 6px 18px var(--accent-soft);
  }
  .device-main { display:flex; flex-direction:column; gap:2px; min-width:0; flex:1; }
  .device-main strong { font-size:13px; letter-spacing:-.01em; color:var(--text); }
  .device-main small {
    font-size:10px; color:var(--muted); overflow:hidden;
    text-overflow:ellipsis; white-space:nowrap;
  }
  .status-dot { width:9px; height:9px; border-radius:50%; flex:0 0 auto; }
  .status-dot.moving { background:#34c759; box-shadow:0 0 10px rgba(52,199,89,.7); }
  .status-dot.stopped { background:#ff9f0a; box-shadow:0 0 10px rgba(255,159,10,.6); }
  .status-dot.alarm { background:#ff453a; box-shadow:0 0 12px rgba(255,69,58,.7); }
  .status-dot.offline { background:#8e8e93; }
  .status-text { font-size:9.5px; font-weight:800; text-transform:uppercase; letter-spacing:.05em; }
  .status-text.moving { color:#1c7c34; }
  .status-text.stopped { color:#9a5b00; }
  .status-text.alarm { color:#c31d10; }
  .status-text.offline { color:var(--muted); }
  .map-empty { color:var(--muted); font-size:12px; padding:14px 6px; }
  .vehicle-card {
    top:auto; bottom:96px; right:20px; width:340px;
    max-height:calc(100% - 120px); overflow:auto; padding:18px;
    scrollbar-width:thin; scrollbar-color:rgba(120,72,40,.26) transparent;
  }
  .vehicle-card::-webkit-scrollbar { width:6px; }
  .vehicle-card::-webkit-scrollbar-thumb { background:rgba(120,72,40,.22); border-radius:999px; }
  .vehicle-head { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
  .vehicle-plate {
    font-size:24px; font-weight:800; letter-spacing:-.03em; color:var(--text);
  }
  .vehicle-model { font-size:11px; color:var(--muted); margin-top:4px; }
  .status-pill {
    font-size:9.5px; font-weight:800; text-transform:uppercase;
    letter-spacing:.06em; padding:6px 9px; border-radius:999px;
    background:rgba(120,120,128,.12); color:#5a5a5f;
    border:1px solid rgba(120,120,128,.2); white-space:nowrap;
  }
  .status-pill.moving { color:#1c7c34; border-color:rgba(52,199,89,.4); }
  .status-pill.stopped { color:#9a5b00; border-color:rgba(255,159,10,.4); }
  .status-pill.alarm { color:#c31d10; border-color:rgba(255,69,58,.45); }
  .status-pill.offline { color:var(--muted); border-color:rgba(120,120,128,.25); }
  .vehicle-grid {
    display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:14px;
  }
  .vehicle-grid div {
    padding:9px 10px; border-radius:14px;
    background:var(--surface); border:1px solid var(--glass-line);
  }
  .vehicle-grid span {
    display:block; font-size:8.5px; text-transform:uppercase;
    letter-spacing:.08em; color:var(--muted);
  }
  .vehicle-grid strong {
    display:block; margin-top:3px; font-size:11.5px; color:var(--text);
  }
  .vehicle-address {
    margin-top:10px; padding:10px 12px; border-radius:14px;
    background:var(--surface);
    border:1px solid var(--glass-line);
  }
  .vehicle-address > span {
    display:block; font-size:8.5px; text-transform:uppercase;
    letter-spacing:.08em; color:var(--muted);
  }
  .vehicle-address strong {
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
    overflow:hidden; margin-top:4px; font-size:11px; line-height:1.45;
    color:var(--text); font-weight:500;
  }
  .vehicle-actions { margin-top:12px; flex-wrap:nowrap; }
  .vehicle-actions button {
    flex:1; min-height:38px; padding:6px 8px; border-radius:12px;
    font-size:11px; font-weight:700;
    background:var(--control); color:var(--accent);
    border:1px solid var(--accent-line); box-shadow:none;
  }
  .vehicle-actions button:hover {
    background:#fff; color:var(--accent); border-color:var(--accent-line);
  }
  .vehicle-actions button.ok {
    background:var(--accent);
    color:var(--accent-ink); border-color:var(--accent-line); font-weight:700;
    box-shadow:0 8px 24px var(--accent-line);
  }
  .vehicle-actions button.active {
    background:var(--accent-soft); color:var(--accent);
    border-color:var(--accent-line);
  }
  /* L'eliminazione resta rossa: la regola sta dopo .vehicle-actions button,
     che ha la stessa specificita' e altrimenti vince. */
  .vehicle-actions button.danger {
    background:rgba(255,69,58,.12); color:#b42318;
    border-color:rgba(255,69,58,.42);
    box-shadow:none;
  }
  .vehicle-actions button.danger:hover {
    background:rgba(255,69,58,.2); color:#8f1710;
    border-color:rgba(255,69,58,.58);
  }
  body.dark .vehicle-actions button.danger {
    background:rgba(248,113,113,.16); color:#fda4af;
    border-color:rgba(251,113,133,.45);
  }
  body.dark .vehicle-actions button.danger:hover {
    background:rgba(248,113,113,.26); color:#fecdd3;
    border-color:rgba(251,113,133,.62);
  }
  .map-controls {
    bottom:18px; left:20px; display:flex; flex-wrap:wrap; align-items:center;
    gap:8px; padding:9px 12px; max-width:calc(100% - 390px);
    color:var(--muted);
  }
  .map-controls button {
    padding:6px 11px; font-size:11.5px; border-radius:10px;
    background:var(--control); color:var(--text);
    border:1px solid rgba(255,255,255,.5);
  }
  .map-controls button:hover { background:#fff; }
  .map-controls a { font-size:11px; color:var(--accent); text-decoration:none; }
  .map-controls #map-note { font-size:10.5px; color:var(--muted); }
  .map-hint { display:none; }
  .gmaps-frame {
    position:absolute; inset:0; width:100%; height:100%;
    border:0; border-radius:0; z-index:450; display:none;
  }
  .maps-google .gmaps-frame { display:block; }
  .maps-google #map { display:none; }
  .map-under { max-width:1320px; margin:0 auto; padding:0 18px 16px; }
  .fleet-marker { filter:drop-shadow(0 2px 6px rgba(4,42,31,.38)); }
  .gps-route {
    filter:drop-shadow(0 0 6px var(--accent-line))
           drop-shadow(0 0 14px var(--accent-line));
  }
  .gps-marker-host { background:none; border:0; }
  .gps-marker {
    position:relative; width:38px; height:38px; border-radius:50%;
    display:grid; place-items:center; background:#fff;
    border:2.5px solid var(--state, #B4501A);
    box-shadow:0 0 16px var(--state, #B4501A), 0 5px 16px rgba(4,42,31,.38);
    transition:border-color .25s ease, box-shadow .25s ease, transform .2s ease;
  }
  .gps-marker:hover { transform:scale(1.08); }
  .gps-marker svg.gps-arrow {
    width:17px; height:17px; fill:var(--state, #B4501A);
    transition:transform .55s cubic-bezier(.2,.8,.2,1);
  }
  .gps-marker.selected {
    box-shadow:0 0 24px var(--accent-line), 0 5px 18px rgba(4,42,31,.38);
  }
  .gps-ping {
    position:absolute; inset:-9px; border-radius:50%;
    border:2px solid var(--accent); opacity:0; pointer-events:none;
  }
  .gps-marker.selected .gps-ping {
    animation:gpsPing 1.9s cubic-bezier(.2,.7,.2,1) infinite;
  }
  @keyframes gpsPing {
    0% { transform:scale(.55); opacity:.95; }
    70% { transform:scale(1.55); opacity:0; }
    100% { transform:scale(1.55); opacity:0; }
  }
  .history-stop { filter:drop-shadow(0 0 6px rgba(255,159,10,.75)); }
  .leaflet-popup-content-wrapper, .leaflet-popup-tip {
    background:var(--surface-solid); color:var(--text);
    border:1px solid var(--glass-line); border-radius:14px;
    box-shadow:var(--shadow-float);
    backdrop-filter:blur(16px) saturate(150%);
  }
  .leaflet-popup-content { margin:12px 14px; font-size:12px; }
  .leaflet-popup-content a { color:var(--accent); }
  .leaflet-container a.leaflet-popup-close-button { color:var(--muted); }
  .leaflet-bar a {
    background:var(--control); color:var(--text);
    border-color:rgba(120,72,40,.14);
  }
  .leaflet-bar a:hover { background:#fff; }
  .leaflet-control-attribution {
    background:var(--surface-solid); color:var(--muted);
    border-radius:8px 0 0 0; padding:2px 6px;
  }
  .leaflet-control-attribution a { color:var(--accent); }
  .photo { overflow:hidden; border-radius:18px; }
  .photo img {
    display:block; width:100%; border-radius:18px; transition:transform .35s ease;
  }
  .photo:hover img { transform:scale(1.04); }

  /* Storico percorsi: player in vetro chiaro */
  body.history-mode .vehicle-card { display:none; }
  body.history-mode .map-controls { display:none; }
  body.history-mode .device-sidebar .device-item:not(.selected) { display:none; }
  .playback-panel {
    left:50%; bottom:20px; transform:translateX(-50%);
    width:min(820px, calc(100% - 120px)); padding:16px 18px 13px;
    z-index:680; animation:none;
    background:var(--surface);
    border:1px solid rgba(255,255,255,.6);
    border-top-color:rgba(255,255,255,.95);
    border-radius:20px;
    box-shadow:var(--shadow-float),
               inset 0 1px 0 rgba(255,255,255,.95);
    backdrop-filter:blur(16px) saturate(150%);
    -webkit-backdrop-filter:blur(16px) saturate(150%);
    color:var(--text);
  }
  .playback-panel[hidden] { display:none; }
  .playback-head { display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
  .playback-ident { min-width:120px; }
  .playback-ident > span {
    display:block; font-size:8.5px; font-weight:800; text-transform:uppercase;
    letter-spacing:.12em; color:var(--accent);
  }
  .playback-ident > strong {
    display:block; margin-top:2px; font-size:20px; line-height:1.1;
    font-weight:800; letter-spacing:-.02em; color:var(--text);
  }
  .playback-kpis {
    display:grid; grid-template-columns:repeat(3, minmax(88px, 1fr));
    gap:8px; flex:1; min-width:280px;
  }
  .playback-kpis div {
    padding:7px 10px; border-radius:12px;
    background:var(--surface); border:1px solid var(--glass-line);
  }
  .playback-kpis span {
    display:block; font-size:8px; text-transform:uppercase;
    letter-spacing:.08em; color:var(--muted);
  }
  .playback-kpis strong {
    display:block; margin-top:2px; font-size:14px; font-weight:800;
    color:var(--text);
  }
  .playback-exit {
    min-height:34px; padding:7px 12px; border-radius:11px;
    font-size:10.5px; font-weight:700;
    background:var(--control); color:var(--accent);
    border:1px solid var(--accent-line);
  }
  .playback-exit:hover {
    background:rgba(255,69,58,.12); color:#c31d10;
    border-color:rgba(255,69,58,.3);
  }
  /* Di notte body.dark button impone testo e bordo neutri: l'uscita resta
     accento, con l'hover rosso leggibile sul fondo scuro. */
  body.dark .playback-exit {
    color:var(--accent); border-color:var(--accent-line);
  }
  body.dark .playback-exit:hover {
    background:rgba(255,69,58,.12); color:#fda4af;
    border-color:rgba(255,69,58,.3);
  }
  .playback-main { display:flex; align-items:center; gap:10px; margin-top:13px; }
  /* body.dark button (0,1,2) vince su .playback-play (0,1,0) e di notte
     spegne il riempimento accento. Due classi (0,2,0) bastano a superarlo e
     restano sotto la regola di focus (0,2,1), che così conserva l'anello.
     Vale anche per hover, che altrimenti tornerebbe al fondo "control". */
  .playback-panel .playback-play {
    flex:0 0 auto; width:44px; height:44px; border-radius:50%; padding:0;
    display:grid; place-items:center; font-size:15px; font-weight:900; line-height:1;
    background:var(--accent);
    border:1px solid var(--accent-line); color:var(--accent-ink);
    box-shadow:0 8px 22px var(--accent-line);
  }
  .playback-panel .playback-play:hover { background:var(--accent); filter:brightness(1.1); }
  .playback-speed {
    display:flex; gap:3px; padding:3px; border-radius:10px;
    background:rgba(255,255,255,.4); border:1px solid rgba(255,255,255,.65);
  }
  .playback-speed button {
    min-width:31px; min-height:28px; padding:3px 6px;
    border:0; border-radius:8px; background:transparent; box-shadow:none;
    color:var(--muted); font-size:10px; font-weight:800;
  }
  .playback-speed button:hover { color:var(--text); transform:none; }
  .playback-speed button.active {
    background:var(--accent-soft); color:var(--accent);
    box-shadow:inset 0 0 0 1px var(--accent-line);
  }
  /* Dentro la pastiglia velocità i tasti restano trasparenti anche di notte:
     il fondo generico li trasformerebbe in pillole annidate. */
  body.dark .playback-speed button:not(.active) {
    background:transparent; border-color:transparent; box-shadow:none;
    color:var(--muted);
  }
  body.dark .playback-speed button:not(.active):hover {
    background:transparent; color:var(--text); transform:none;
  }
  body.dark .playback-speed button.active:hover {
    background:var(--accent-soft); color:var(--accent); transform:none;
  }
  .playback-live {
    margin-left:auto; display:flex; flex-direction:column; gap:1px; text-align:right;
  }
  .playback-live strong {
    font-size:17px; color:var(--text); font-variant-numeric:tabular-nums;
  }
  .playback-live span { font-size:10px; font-weight:700; color:var(--accent); }
  .playback-slider {
    -webkit-appearance:none; appearance:none; width:100%; height:6px;
    margin:14px 0 8px; border-radius:999px; padding:0; outline:none; cursor:pointer;
    border:0; box-shadow:none;
    background:linear-gradient(90deg,var(--accent) var(--progress,0%),var(--field-line) var(--progress,0%));
  }
  .playback-slider::-webkit-slider-thumb {
    -webkit-appearance:none; appearance:none; width:16px; height:16px;
    border-radius:50%; background:#fff; border:2px solid var(--accent);
    box-shadow:0 2px 8px var(--accent-line);
  }
  .playback-slider::-moz-range-thumb {
    width:14px; height:14px; border-radius:50%; background:#fff;
    border:2px solid var(--accent); box-shadow:0 2px 8px var(--accent-line);
  }
  .playback-foot {
    display:flex; align-items:center; justify-content:space-between; gap:10px;
  }
  .playback-dates { display:flex; align-items:center; gap:5px; }
  .playback-dates button {
    min-height:27px; padding:4px 10px; border-radius:8px;
    font-size:10px; font-weight:700;
    background:rgba(255,255,255,.66); color:var(--muted);
    border:1px solid rgba(255,255,255,.7); box-shadow:none;
  }
  .playback-dates button:hover { color:var(--text); transform:none; }
  .playback-dates button.active {
    background:var(--accent-soft); color:var(--accent);
    border-color:var(--accent-line);
  }
  /* L'hover generico di notte spegnerebbe il chip attivo: si tiene l'accento. */
  body.dark .playback-dates button.active:hover {
    background:var(--accent-soft); color:var(--accent);
  }
  .playback-dates label {
    display:flex; align-items:center; gap:5px; font-size:9px; font-weight:700;
    text-transform:uppercase; letter-spacing:.05em; color:var(--muted);
  }
  .playback-dates input[type="date"] {
    width:120px; min-height:27px; padding:3px 6px; font-size:10px;
    background:var(--field); color:var(--text);
    border:1px solid rgba(255,255,255,.75); border-radius:8px;
    color-scheme:light;
  }
  .playback-foot > span { font-size:9px; color:var(--muted); white-space:nowrap; }

  /* Adattamenti */
  @media (min-width:1200px) {
    /* Sette card in 4+3: niente ultima riga con due card e spazio vuoto. */
    .kpis { grid-template-columns:repeat(4, minmax(0, 1fr)); }
    /* I gruppi da tre restano a piena larghezza invece di lasciare una cella vuota. */
    .kpis:has(> .kpi:nth-child(3):last-child) {
      grid-template-columns:repeat(3, minmax(0, 1fr));
    }
  }
  @media (min-width:1101px) {
    .topbar { justify-content:space-between; }
  }
  @media (max-width:1100px) {
    .menu-toggle { display:inline-flex; align-items:center; }
    .sidebar {
      position:fixed; top:0; bottom:0; left:0; height:100vh; margin:0;
      width:min(88vw,320px); z-index:1300;
      background:var(--surface-solid);
      border-right:1px solid var(--glass-line); border-radius:0 24px 24px 0;
      box-shadow:var(--shadow-float);
      transform:translateX(-102%); transition:transform .22s ease;
    }
    .sidebar.open { transform:none; }
    .side-close { display:inline-flex; }
    #side-scrim {
      position:fixed; inset:0; z-index:1290; background:rgba(9,10,12,.32);
      backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
    }
    #side-scrim.open { display:block; }
  }
  @media (max-width:900px) {
    .grid2 { grid-template-columns:1fr; }
    /* Schermi stretti: il vetro pieno costa frame durante lo scroll. */
    [data-view="dashboard"] .panel,
    [data-view="dashboard"] .card,
    [data-view="dashboard"] .kpi {
      backdrop-filter:blur(10px) saturate(130%);
      -webkit-backdrop-filter:blur(10px) saturate(130%);
    }
    .topbar, .dock, .sidebar, .map-glass, .modal-card, #toast {
      backdrop-filter:blur(12px) saturate(130%);
      -webkit-backdrop-filter:blur(12px) saturate(130%);
    }
    .tab:not([data-view="dashboard"]) .panel,
    .tab:not([data-view="dashboard"]) .card,
    .tab:not([data-view="dashboard"]) .kpi {
      backdrop-filter:none; -webkit-backdrop-filter:none;
    }
    /* Topbar compatta: una riga di comandi invece di tre. */
    .topbar { padding:10px 14px; gap:10px; }
    .topbar .brand-badge, .topbar #who { display:none; }
    .topbar #token { width:110px; }
    .map-shell { height:calc(100dvh - 235px); min-height:430px; margin:0 10px; }
    body.map-mode .map-shell { height:calc(100dvh - 235px); }
    .map-search-panel { left:12px; right:12px; top:12px; width:auto; }
    /* Elenco dispositivi come striscia orizzontale: libera la mappa. */
    .device-sidebar {
      left:12px; right:12px; top:70px; bottom:auto; width:auto;
      padding:8px 10px; border-radius:16px;
    }
    .device-sidebar .map-side-head { display:none; }
    .device-sidebar .device-list {
      flex-direction:row; overflow-x:auto; overflow-y:hidden; gap:6px;
      scrollbar-width:none;
    }
    .device-sidebar .device-list::-webkit-scrollbar { display:none; }
    .device-sidebar .device-item {
      flex:0 0 auto; width:auto; min-width:168px; padding:7px 9px;
    }
    .device-sidebar .device-item:hover { transform:none; }
    .vehicle-card {
      display:block; top:auto; left:12px; right:12px; bottom:124px;
      width:auto; max-height:50%; padding:12px 14px; border-radius:20px;
    }
    .vehicle-plate { font-size:20px; }
    /* L'indirizzo resta nella scheda desktop: qui la mappa lo mostra gia'. */
    .vehicle-address { display:none; }
    .vehicle-grid { gap:6px; margin-top:8px; }
    .vehicle-grid div { padding:6px 7px; }
    .vehicle-grid strong { font-size:11px; }
    /* Azioni su una riga scorrevole: la scheda resta bassa sulla mappa. */
    .vehicle-actions {
      flex-wrap:nowrap; overflow-x:auto; gap:6px; scrollbar-width:none;
    }
    .vehicle-actions::-webkit-scrollbar { display:none; }
    .vehicle-actions button {
      flex:0 0 auto; min-height:34px; padding:5px 12px;
      font-size:10.5px; white-space:nowrap;
    }
    .map-controls {
      left:12px; right:12px; bottom:74px; max-width:none;
      padding:6px 8px; gap:6px;
    }
    .map-controls #map-note { display:none; }
    .map-under { padding:0 10px 110px; }
    body.history-mode .device-sidebar,
    body.history-mode .map-search-panel { display:none; }
    body.history-mode .leaflet-control-zoom { display:none; }
    .playback-panel {
      left:8px; right:8px; bottom:78px; transform:none;
      width:auto; padding:12px 12px 9px; border-radius:20px;
    }
    .playback-head {
      display:grid; grid-template-columns:minmax(0, 1fr) auto;
      gap:7px 8px; align-items:center;
    }
    .playback-ident { min-width:0; }
    .playback-ident > strong {
      font-size:17px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
    }
    .playback-kpis {
      grid-column:1 / -1; grid-row:2; width:100%;
      grid-template-columns:repeat(3, minmax(0, 1fr)); min-width:0; gap:5px;
    }
    .playback-kpis div { padding:5px 6px; min-width:0; }
    .playback-kpis span {
      font-size:7px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
    }
    .playback-kpis strong {
      font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
    }
    .playback-exit {
      grid-column:2; grid-row:1; margin-left:0; padding:6px 8px;
      font-size:9px; white-space:nowrap;
    }
    .playback-main {
      display:grid; grid-template-columns:auto minmax(0, 1fr) auto;
      gap:6px; margin-top:10px; align-items:center;
    }
    .playback-play { width:40px; height:40px; }
    .playback-speed { justify-self:start; }
    .playback-speed button { min-width:22px; min-height:24px; padding:2px 3px; font-size:8.5px; }
    .playback-live { margin-left:0; min-width:0; }
    .playback-live strong { font-size:13px; white-space:nowrap; }
    .playback-live span { font-size:8px; white-space:nowrap; }
    .playback-slider { margin:10px 0 7px; }
    .playback-foot { display:block; }
    .playback-foot > span { display:none; }
    .playback-dates { flex-wrap:wrap; gap:4px; }
    .playback-dates button { padding:3px 8px; font-size:9px; }
    .playback-dates label { font-size:0; gap:0; }
    .playback-dates input[type="date"] { width:108px; font-size:9px; }
  }
  @media (max-width:720px) {
    .emergency-hud { top:auto; bottom:98px; padding:13px 14px; }
    [data-view="dashboard"] .panel,
    [data-view="dashboard"] .card,
    [data-view="dashboard"] .kpi {
      backdrop-filter:blur(6px) saturate(120%);
      -webkit-backdrop-filter:blur(6px) saturate(120%);
    }
    .emergency-hud strong { font-size:17px; }
    .emergency-actions button { font-size:11px; padding:7px 10px; }
    .topbar { margin:10px 10px 0; padding:10px 12px; top:8px; }
    main { margin:14px auto; padding:0 12px 32px; }
    .panel { padding:14px; border-radius:24px; }
    .kpis { grid-template-columns:repeat(2, minmax(0, 1fr)); }
    .kpi { padding:13px 14px; }
    .kpi .value { font-size:21px; }
    .dock { bottom:8px; max-width:98vw; padding:6px 8px; }
    .dock button { padding:6px 10px; font-size:11px; }
  }
  @media (prefers-reduced-motion:reduce) {
    .map-glass, .kpi, button, .photo img, .device-item { transition:none; animation:none; }
    .gps-marker.selected .gps-ping { animation:none; opacity:.7; }
    .gps-marker svg.gps-arrow { transition:none; }
  }
"""


LOGIN_CSS = BASE_CSS + """
  body {
    display:grid; place-items:center; padding:24px;
  }
  .card { width:100%; max-width:390px; padding:30px; }
  .card h1 { font-size:24px; margin:0 0 4px; font-weight:600; }
  .card .sub { font-size:12px; margin-bottom:18px; }
  label {
    display:block; margin:14px 0 6px; font-size:10px; font-weight:600;
    text-transform:uppercase; letter-spacing:.1em; color:var(--muted);
  }
  .card input { width:100%; padding:11px 12px; font-size:14px; }
  .card button { width:100%; margin-top:20px; padding:12px; font-weight:700; }
  #error { color:#b00015; font-size:12.5px; margin-top:12px; min-height:18px; }
  body.dark #error { color:#fda4af; }
  body.dark label { color:var(--muted); }
"""


REPORT_CSS = BASE_CSS + """
  main {
    display:flex; flex-direction:column; gap:16px;
    max-width:1040px; margin:22px auto 60px; padding:0 20px;
  }
  .kpis { grid-template-columns:repeat(4, 1fr); gap:12px; }
  .kpi { padding:16px; }
  .kpi .value { font-size:24px; }
  code { word-break:break-all; font-size:11.5px; }
  #status { color:var(--muted); }
  @media (max-width:720px) {
    .kpis { grid-template-columns:repeat(2, 1fr); }
    main { padding:0 12px; }
    .panel table { display:block; overflow-x:auto; white-space:nowrap; }
    .panel th, .panel td { padding:8px 6px; font-size:11px; }
    .panel td code { font-size:10.5px; word-break:normal; }
  }
  @media print {
    header, button, a { display:none; }
    main { margin:0; max-width:none; padding:0; gap:12px; }
    .kpis { grid-template-columns:repeat(4, 1fr); }
    .panel, .card, .kpi {
      background:#fff; box-shadow:none; border:1px solid #dfe4ea;
      padding:0 0 14px; border-radius:0; backdrop-filter:none;
    }
    .kpi { padding:12px; border-radius:8px; }
  }
"""


VERIFY_CSS = BASE_CSS + """
  main {
    display:flex; flex-direction:column; gap:16px;
    max-width:860px; margin:22px auto 60px; padding:0 20px;
  }
  label {
    display:block; margin:12px 0 6px; font-size:11px;
    text-transform:uppercase; letter-spacing:.4px; color:var(--muted);
  }
  input[type=file] {
    width:100%; padding:14px; font-size:13px; cursor:pointer;
    background:rgba(255,255,255,.7); border:1px dashed rgba(120,72,40,.3);
  }
  input[type=file]:hover { border-color:var(--accent); }
  .drop {
    margin-top:10px; padding:22px; border-radius:16px; text-align:center;
    color:var(--muted); background:rgba(255,255,255,.62);
    border:2px dashed rgba(120,72,40,.2);
  }
  .drop.on { border-color:var(--accent); color:var(--accent); background:var(--accent-soft); }
  th { width:34%; }
  td { word-break:break-word; }
  tr:last-child td, tr:last-child th { border-bottom:none; }
  .note { border-left:3px solid rgba(120,72,40,.2); padding:6px 0 6px 12px; margin-top:14px; }
  #error { color:#b00015; min-height:18px; }
  ul { margin:6px 0 0 18px; padding:0; }
  li { margin:3px 0; }
"""


EXPIRED_CSS = BASE_CSS + """
  body { display:grid; place-items:center; padding:24px; }
  .card { width:100%; max-width:420px; padding:28px; }
  .card h1 { font-size:17px; margin:0 0 8px; }
  .card p { color:var(--muted); font-size:13px; margin:6px 0; }
"""


_CUSTOM_BG_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def custom_bg_url(raw: str) -> str:
    """URL utilizzabile in ``url("...")``, oppure vuoto se non e' un'immagine.

    Accetta URL assoluti (http/https), protocollo-relativi (//cdn/...),
    percorsi assoluti (/statici/...), relativi (statici/sfondo.jpg) e
    ``data:image/...``. Rifiuta gli altri schemi e i caratteri di controllo.
    Le virgolette e la barra rovesciata vengono protette, perche' chiuderebbero
    la stringa CSS; il valore resta comunque confinato dentro ``url()``.
    """
    value = raw.strip()
    if not value or _CUSTOM_BG_CONTROL.search(value):
        return ""
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in ("", "http", "https", "data"):
        return ""
    if scheme in ("http", "https") and not parts.netloc:
        return ""
    is_data = value[:11].lower().startswith("data:image/")
    if scheme == "data" and not is_data:
        return ""
    # Parentesi e punti e virgola non servono in un URL vero: senza questa
    # regola un valore come "url(x);background:red" passerebbe per un percorso.
    if not is_data and any(ch in value for ch in "();"):
        return ""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def custom_bg_attrs(raw: str) -> str:
    """Attributi del <body> per lo sfondo aziendale gia' risolto lato server.

    La classe ``has-custom-bg`` viaggia nell'HTML: il primo paint ha gia' foto
    e velo (niente lampo senza sfondo) e il livello funziona anche sulle pagine
    pubbliche che non caricano lo script del tema. ``raw`` e' l'URL scelto per
    il tenant attivo (o il valore predefinito del server).
    """
    url = custom_bg_url(raw)
    if not url:
        return ""
    return (
        ' class="has-custom-bg" style="--custom-bg-image:url(&quot;'
        + html.escape(url, quote=True)
        + '&quot;)"'
    )


def with_custom_bg(page: str, bg_url: str = "") -> str:
    """Inserisce gli attributi dello sfondo nel primo <body> della pagina."""
    attrs = custom_bg_attrs(bg_url)
    if not attrs:
        return page
    return page.replace("<body>", "<body" + attrs + ">", 1)
