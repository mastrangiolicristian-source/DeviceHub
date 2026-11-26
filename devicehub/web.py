"""Pagina di controllo flotta, servita dalla stessa API.

HTML autosufficiente (nessuna build, nessuna CDN): la pagina parla con gli
endpoint JSON del servizio. Il token dell'API si inserisce una volta e resta
in localStorage; il rendering dei dati dei dispositivi usa textContent, mai
innerHTML, cosi' un campo targa/IMEI non puo' iniettare markup.
"""

from __future__ import annotations

import html

from .config import Settings
from .theme import BASE_CSS, LOGIN_CSS, THEME_JS, with_custom_bg

PAGE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DeviceHub - Controllo flotta</title>
</head>
<body>
<script>try{if(localStorage.getItem('dh_theme')!=='light')document.body.classList.add('dark');}catch(e){}</script>
<header>
  <div>
    <h1>DeviceHub &middot; Controllo flotta</h1>
    <div class="sub">ingestione TCP __TCP_PORT__ &middot; API __API_PORT__ &middot; __DOUTS__ uscite digitali</div>
  </div>
  <div class="row">
    <button class="theme-toggle" id="theme-toggle" onclick="toggleTheme()" title="Tema notturno" aria-label="Cambia tema">🌙</button>
    <span class="sub">token API</span>
    <input id="token" type="password" placeholder="X-Api-Key" style="width:210px">
    <button onclick="saveToken()">Salva</button>
    <button onclick="refresh()">Aggiorna</button>
  </div>
</header>

<main>
  <section class="panel">
    <div class="spread">
      <h2 style="margin:0">Dispositivi</h2>
      <label class="sub"><input type="checkbox" id="auto" checked onchange="toggleAuto()">
        aggiorna ogni 10 s</label>
    </div>
    <div id="devices" class="empty">caricamento...</div>
  </section>

  <section class="panel">
    <h2>Provisioning</h2>
    <div class="sub" style="margin-bottom:10px">
      Comandi da inviare via SMS alla SIM del tracker, dopo aver inserito la SIM.
    </div>
    <div class="row">
      <input id="p_imei" placeholder="IMEI" style="width:190px">
      <input id="p_host" value="__PUBLIC_HOST__" placeholder="host" style="width:210px">
      <input id="p_port" value="__PUBLIC_PORT__" placeholder="porta" style="width:80px">
      <input id="p_apn" value="__APN__" placeholder="APN" style="width:190px">
      <button onclick="loadProvisioning()">Genera comandi</button>
      <button onclick="copyProvisioning()">Copia</button>
    </div>
    <pre id="prov"></pre>
  </section>

  <section class="panel">
    <h2>Log</h2>
    <div id="log" class="muted">pronto.</div>
  </section>
</main>

<script>
const TOKEN_KEY = 'devicehub_token';
const IMEI_RE = /^\\d{14,16}$/;
let timer = null;
let provisioningText = '';

__THEME_JS__
function el(tag, props, children) {
  const node = document.createElement(tag);
  Object.entries(props || {}).forEach(function (entry) {
    const key = entry[0], value = entry[1];
    if (key === 'text') node.textContent = value;
    else if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  });
  [].concat(children || []).forEach(function (child) { if (child) node.appendChild(child); });
  return node;
}

function log(message, kind) {
  const box = document.getElementById('log');
  if (box.classList.contains('muted')) { box.textContent = ''; box.classList.remove('muted'); }
  box.appendChild(el('div', { class: kind || '', text: '[' + new Date().toLocaleTimeString('it-IT') + '] ' + message }));
  box.scrollTop = box.scrollHeight;
}

function saveToken() {
  const value = document.getElementById('token').value.trim();
  if (value) { localStorage.setItem(TOKEN_KEY, value); log('token salvato nel browser', 'okv'); }
  else { localStorage.removeItem(TOKEN_KEY); log('token rimosso', ''); }
  document.getElementById('token').value = '';
  refresh();
}

async function api(path, options) {
  const opts = options || {};
  const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers['X-Api-Key'] = token;
  const response = await fetch(path, Object.assign({}, opts, { headers: headers }));
  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('accesso richiesto');
  }
  if (!response.ok) {
    let detail = 'HTTP ' + response.status;
    try { const body = await response.json(); if (body.detail) detail = body.detail; } catch (e) { /* testo */ }
    throw new Error(detail);
  }
  return response;
}

function fmt(value, digits) {
  if (value === null || value === undefined) return '\\u2014';
  return Number(value).toFixed(digits === undefined ? 5 : digits);
}

function statusBadge(device) {
  if (device.status !== 'active') return el('span', { class: 'badge pending', text: 'da abilitare' });
  return el('span', { class: 'badge active', text: 'abilitato' });
}

async function refresh() {
  try {
    const response = await api('/devices');
    renderDevices(await response.json());
  } catch (error) {
    log('lettura dispositivi: ' + error.message, 'err');
  }
}

function renderDevices(data) {
  const box = document.getElementById('devices');
  box.textContent = '';
  if (!data.count) {
    box.className = 'empty';
    box.textContent = 'Nessun dispositivo ha ancora inviato dati.';
    return;
  }
  box.className = '';

  const head = el('tr', {}, ['IMEI', 'Stato', 'Connessione', 'Ultima posizione', 'Velocita', 'Quadro', 'Ultimo contatto', 'Azioni']
    .map(function (label) { return el('th', { text: label }); }));
  const body = el('tbody');

  data.devices.forEach(function (device) {
    const position = (device.latitude === null || device.latitude === undefined)
      ? el('span', { class: 'muted', text: 'nessuna posizione' })
      : el('a', {
          href: 'https://www.openstreetmap.org/?mlat=' + device.latitude + '&mlon=' + device.longitude +
                '#map=16/' + device.latitude + '/' + device.longitude,
          target: '_blank', rel: 'noopener',
          text: fmt(device.latitude) + ', ' + fmt(device.longitude)
        });

    const actions = el('div', { class: 'row' });
    if (device.status !== 'active') {
      actions.appendChild(el('button', { class: 'ok', text: 'Abilita', onclick: function () { activate(device.imei); } }));
    }
    actions.appendChild(el('button', { class: 'danger', text: 'Blocca', onclick: function () { engineBlock(device.imei, true, this); } }));
    actions.appendChild(el('button', { text: 'Sblocca', onclick: function () { engineBlock(device.imei, false, this); } }));
    actions.appendChild(el('button', { text: 'SMS', onclick: function () {
      document.getElementById('p_imei').value = device.imei;
      loadProvisioning();
    } }));
    actions.appendChild(el('button', { text: 'Audit', onclick: function () { audit(device.imei); } }));

    body.appendChild(el('tr', {}, [
      el('td', {}, [el('code', { text: device.imei })]),
      el('td', {}, [statusBadge(device)]),
      el('td', {}, [el('span', { class: 'badge ' + (device.connected ? 'active' : 'offline'),
                            text: device.connected ? 'online' : 'offline' })]),
      el('td', {}, [position]),
      el('td', { text: device.speed === null || device.speed === undefined ? '\\u2014' : fmt(device.speed, 1) + ' km/h' }),
      el('td', { text: device.ignition === null || device.ignition === undefined ? '\\u2014' : (device.ignition ? 'acceso' : 'spento') }),
      el('td', { class: 'muted', text: device.last_seen ? String(device.last_seen).replace('T', ' ') : '\\u2014' }),
      el('td', {}, [actions])
    ]));
  });

  const table = el('table');
  table.appendChild(el('thead', {}, [head]));
  table.appendChild(body);
  box.appendChild(el('div', { class: 'table-wrap' }, [table]));
  box.appendChild(el('div', { class: 'sub', style: 'margin-top:10px' },
    [el('span', { text: data.count + ' dispositivi' })]));
}

async function activate(imei) {
  const plate = prompt('Targa del mezzo per ' + imei + ':', '');
  if (plate === null) return;
  const model = prompt('Modello del dispositivo:', 'FMC150');
  if (model === null) return;
  try {
    await api('/devices/' + encodeURIComponent(imei) + '/activate?plate=' +
              encodeURIComponent(plate) + '&model=' + encodeURIComponent(model), { method: 'POST' });
    log('dispositivo ' + imei + ' abilitato', 'okv');
    refresh();
  } catch (error) {
    log('abilitazione ' + imei + ': ' + error.message, 'err');
  }
}

async function engineBlock(imei, block, button) {
  const question = block
    ? 'Bloccare il motore di ' + imei + '?\\n\\nIl comando viene rifiutato se il mezzo risulta in movimento.'
    : 'Sbloccare il motore di ' + imei + '?';
  if (!confirm(question)) return;
  try {
    const response = await api('/devices/' + encodeURIComponent(imei) +
      '/engine_block?block=' + block + '&requested_by=ui', { method: 'POST' });
    const data = await response.json();
    log((block ? 'BLOCCO ' : 'SBLOCCO ') + imei + ': ' + data.command + ' -> ' + data.device_response, 'okv');
    if (button) { triggerActionFeedback(button); setTimeout(refresh, 2000); }
    else { refresh(); }
  } catch (error) {
    log((block ? 'BLOCCO ' : 'SBLOCCO ') + imei + ' rifiutato: ' + error.message, 'err');
  }
}

async function audit(imei) {
  try {
    const response = await api('/devices/' + encodeURIComponent(imei) + '/commands');
    const data = await response.json();
    if (!data.count) { log('audit ' + imei + ': nessun comando'); return; }
    const lines = data.commands.map(function (item) {
      return '  ' + item.created_at + '  ' + item.action + '  ' + item.command +
             '  [' + (item.accepted ? 'ok' : 'rifiutato') + ']  ' + (item.detail || '');
    });
    log('audit ' + imei + ':\\n' + lines.join('\\n'));
  } catch (error) {
    log('audit ' + imei + ': ' + error.message, 'err');
  }
}

async function loadProvisioning() {
  const imei = document.getElementById('p_imei').value.trim();
  if (!IMEI_RE.test(imei)) { log('IMEI non valido: attese 14-16 cifre', 'err'); return; }
  const query = new URLSearchParams({
    host: document.getElementById('p_host').value.trim(),
    port: document.getElementById('p_port').value.trim(),
    apn: document.getElementById('p_apn').value.trim()
  });
  try {
    const response = await api('/provisioning/' + encodeURIComponent(imei) + '/sms.txt?' + query.toString());
    provisioningText = await response.text();
    const pre = document.getElementById('prov');
    pre.textContent = provisioningText;
    pre.style.display = 'block';
    log('comandi generati per ' + imei);
  } catch (error) {
    log('provisioning ' + imei + ': ' + error.message, 'err');
  }
}

async function copyProvisioning() {
  if (!provisioningText) { log('nessun comando da copiare', 'err'); return; }
  try {
    await navigator.clipboard.writeText(provisioningText);
    log('comandi copiati negli appunti', 'okv');
  } catch (error) {
    log('copia non riuscita: selezionare il testo e copiarlo a mano', 'err');
  }
}

function toggleAuto() {
  if (document.getElementById('auto').checked) {
    timer = setInterval(refresh, 10000);
  } else if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

window.addEventListener('load', function () {
  document.getElementById('token').value = '';
  refresh();
  toggleAuto();
});
</script>
</body>
</html>
"""


def render_control_page(settings: Settings, bg_url: str = "") -> str:
    page = (
        PAGE.replace("__TCP_PORT__", str(settings.tcp_port))
        .replace("__API_PORT__", str(settings.api_port))
        .replace("__DOUTS__", str(settings.douts))
        .replace("__PUBLIC_HOST__", html.escape(settings.public_host))
        .replace("__PUBLIC_PORT__", str(settings.public_port))
        .replace("__APN__", html.escape(settings.apn))
    )
    return with_custom_bg(page, bg_url)


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__COMPANY__ &middot; Accesso</title>
</head>
<body>
<script>try{if(localStorage.getItem('dh_theme')!=='light')document.body.classList.add('dark');}catch(e){}</script>
<button type="button" class="theme-fab" id="theme-toggle" onclick="toggleTheme()" title="Tema notturno" aria-label="Cambia tema">🌙</button>
<form class="card" id="form">
  <h1>__COMPANY__</h1>
  <div class="sub">Accesso alla piattaforma flotta</div>
  <label for="username">Utente</label>
  <input id="username" autocomplete="username" required>
  <label for="password">Password</label>
  <input id="password" type="password" autocomplete="current-password" required>
  <button type="submit">Entra</button>
  <div id="error"></div>
  <div class="sub" style="margin-top:16px">
    <a href="/verify">Verifica uno snapshot esportato</a>
  </div>
</form>
<script>
__THEME_JS__
document.getElementById('form').addEventListener('submit', async function (event) {
  event.preventDefault();
  const errorBox = document.getElementById('error');
  errorBox.textContent = '';
  try {
    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: document.getElementById('username').value.trim(),
        password: document.getElementById('password').value
      })
    });
    if (!response.ok) {
      let detail = 'accesso non riuscito';
      try { const body = await response.json(); if (body.detail) detail = body.detail; } catch (e) {}
      throw new Error(detail);
    }
    const next = new URLSearchParams(window.location.search).get('next');
    window.location.href = (next && next.charAt(0) === '/' && next.charAt(1) !== '/')
      ? next : '/';
  } catch (error) {
    errorBox.textContent = error.message;
  }
});
</script>
</body>
</html>
"""

PAGE = PAGE.replace("</head>", "<style>" + BASE_CSS + "</style></head>")
PAGE = PAGE.replace("__THEME_JS__", THEME_JS)
LOGIN_PAGE = LOGIN_PAGE.replace("</head>", "<style>" + LOGIN_CSS + "</style></head>")
LOGIN_PAGE = LOGIN_PAGE.replace("__THEME_JS__", THEME_JS)


def render_login(settings: Settings, bg_url: str = "") -> str:
    page = LOGIN_PAGE.replace("__COMPANY__", html.escape(settings.company))
    return with_custom_bg(page, bg_url)
