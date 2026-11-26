"""Report mensile congelato: pagina stampabile, con verifica di impronta e firma."""

from __future__ import annotations

import html
from urllib.parse import quote

from .config import Settings
from .theme import EXPIRED_CSS, REPORT_CSS, with_custom_bg

PAGE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__COMPANY__ &middot; Report mensile</title>
</head>
<body>
<header>
  <div>
    <h1>__COMPANY__ &middot; Report mensile congelato</h1>
    <div class="sub" id="period">periodo in caricamento...</div>
  </div>
  <div class="row">
    <button onclick="window.print()">Stampa</button>
    <a href="__PDF_URL__">Scarica PDF</a>
    <a href="/">Torna alla dashboard</a>
  </div>
</header>

<main>
  <section class="kpis">
    <div class="kpi"><div class="label">Km</div><div class="value" id="kpi-km">0</div></div>
    <div class="kpi"><div class="label">Litri stimati</div><div class="value" id="kpi-liters">0</div></div>
    <div class="kpi"><div class="label">CO2 (kg)</div><div class="value" id="kpi-co2">0</div></div>
    <div class="kpi"><div class="label">CO2 per km</div><div class="value" id="kpi-gkm">0</div></div>
  </section>

  <section class="panel">
    <h2>Integrita del documento</h2>
    <div class="row" style="margin-bottom:10px">
      <span class="badge" id="badge-digest">impronta...</span>
      <span class="badge" id="badge-signature">firma...</span>
      <span class="sub" id="fingerprint"></span>
    </div>
    <div class="sub">Impronta SHA-256:</div>
    <code id="digest"></code>
    <div class="sub" style="margin-top:10px" id="status"></div>
  </section>

  <section class="panel">
    <h2>Emissioni per giorno</h2>
    <canvas id="dailyChart" height="120"></canvas>
  </section>

  <section class="panel">
    <h2>Dettaglio per mezzo</h2>
    <table>
      <thead><tr><th>Mezzo</th><th>IMEI</th><th>Km</th><th>Litri stimati</th>
      <th>CO2 kg</th><th>g/km</th><th>Parametri</th></tr></thead>
      <tbody id="devices-body"></tbody>
    </table>
    <div class="sub" id="empty" style="display:none;margin-top:10px">Nessun chilometraggio nel periodo.</div>
  </section>

  <section class="panel">
    <h2>Nota di calcolo</h2>
    <div class="sub" id="assumptions"></div>
  </section>
</main>

<script>
const SNAPSHOT_ID = __SNAPSHOT_ID__;
const DATA_URL = '__DATA_URL__';

function el(tag, props, children) {
  const node = document.createElement(tag);
  Object.entries(props || {}).forEach(function (entry) {
    const key = entry[0], value = entry[1];
    if (key === 'text') node.textContent = value;
    else node.setAttribute(key, value);
  });
  [].concat(children || []).forEach(function (child) { if (child) node.appendChild(child); });
  return node;
}

function fmt(value, digits) {
  if (value === null || value === undefined) return '-';
  return Number(value).toFixed(digits === undefined ? 1 : digits);
}

function render(data) {
  const report = data.report;
  const totals = report.totals;
  document.getElementById('period').textContent =
    'Periodo ' + report.period + ' - congelato il ' +
    String(data.snapshot.created_at || '').replace('T', ' ') +
    (data.snapshot.created_by ? ' da ' + data.snapshot.created_by : '');
  document.getElementById('kpi-km').textContent = fmt(totals.km, 1);
  document.getElementById('kpi-liters').textContent = fmt(totals.liters, 1);
  document.getElementById('kpi-co2').textContent = fmt(totals.co2_kg, 1);
  document.getElementById('kpi-gkm').textContent = fmt(totals.grams_per_km, 0) + ' g';
  document.getElementById('digest').textContent = data.snapshot.digest;

  const badgeDigest = document.getElementById('badge-digest');
  badgeDigest.textContent = data.digest_ok ? 'impronta integra' : 'impronta alterata';
  badgeDigest.className = 'badge ' + (data.digest_ok ? 'ok' : 'bad');

  const badgeSignature = document.getElementById('badge-signature');
  if (data.signature_ok) {
    badgeSignature.textContent = 'firma valida';
    badgeSignature.className = 'badge ok';
  } else if (data.snapshot.signature) {
    badgeSignature.textContent = 'firma non valida';
    badgeSignature.className = 'badge bad';
  } else {
    badgeSignature.textContent = 'non firmato';
    badgeSignature.className = 'badge warn';
  }
  document.getElementById('fingerprint').textContent = data.snapshot.fingerprint
    ? 'chiave ' + data.snapshot.fingerprint : '';
  document.getElementById('status').textContent = data.signature_ok
    ? 'La firma Ed25519 corrisponde alla chiave pubblica: il contenuto non e stato modificato dopo la chiusura del mese.'
    : 'Verifica non completata: conservare la chiave pubblica fuori dal server per un controllo indipendente.';

  const body = document.getElementById('devices-body');
  body.textContent = '';
  report.devices.forEach(function (row) {
    body.appendChild(el('tr', {}, [
      el('td', { text: row.plate || row.imei }),
      el('td', {}, [el('code', { text: row.imei })]),
      el('td', { text: fmt(row.km, 1) }),
      el('td', { text: fmt(row.liters, 1) }),
      el('td', { text: fmt(row.co2_kg, 1) }),
      el('td', { text: fmt(row.grams_per_km, 0) }),
      el('td', { text: row.params_source === 'veicolo' ? 'propri del mezzo' : 'flotta' })
    ]));
  });
  document.getElementById('empty').style.display = report.devices.length ? 'none' : 'block';

  const a = report.assumptions;
  document.getElementById('assumptions').textContent =
    'Distanza da odometro CAN (AVL 87). Consumo ' + fmt(a.fuel_l_per_100km, 1) +
    ' L/100 km e fattore ' + fmt(a.co2_kg_per_liter, 2) +
    ' kg CO2/L, salvo parametri propri del mezzo. Indicatore dichiarato, non un report certificato da un ente.';

  const labels = report.daily.map(function (point) { return point.date.slice(5); });
  const values = report.daily.map(function (point) { return point.co2_kg; });
  new Chart(document.getElementById('dailyChart'), {
    type: 'bar',
    data: { labels: labels, datasets: [{ label: 'CO2 kg', data: values,
      backgroundColor: 'rgba(14,116,144,.55)', borderRadius: 6 }] },
    options: { plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: '#5b6b7c', maxTicksLimit: 12 } },
                y: { ticks: { color: '#5b6b7c' } } } }
  });
}

(async function load() {
  try {
    const response = await fetch(DATA_URL);
    if (response.status === 401) { window.location.href = '/login'; return; }
    if (response.status === 404) throw new Error('link non valido o scaduto');
    if (!response.ok) throw new Error('HTTP ' + response.status);
    render(await response.json());
  } catch (error) {
    document.getElementById('status').textContent = 'Report non disponibile: ' + error.message;
  }
})();
</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
</body>
</html>
"""

PAGE = PAGE.replace("</head>", "<style>" + REPORT_CSS + "</style></head>")


def render_report_page(
    settings: Settings, snapshot_id: int, bg_url: str = ""
) -> str:
    page = (
        PAGE.replace("__COMPANY__", html.escape(settings.company))
        .replace("__SNAPSHOT_ID__", str(int(snapshot_id)))
        .replace("__DATA_URL__", f"/esg/snapshots/{int(snapshot_id)}")
        .replace("__PDF_URL__", f"/esg/snapshots/{int(snapshot_id)}/pdf")
    )
    return with_custom_bg(page, bg_url)


def render_token_page(settings: Settings, token: str, bg_url: str = "") -> str:
    """Report aperto da un link con token: si legge senza account."""
    page = (
        PAGE.replace("__COMPANY__", html.escape(settings.company))
        .replace("__SNAPSHOT_ID__", "0")
        .replace("__DATA_URL__", "/public/report/" + quote(token, safe=""))
        .replace(
            "__PDF_URL__", "/public/report/" + quote(token, safe="") + "/pdf"
        )
    )
    return with_custom_bg(page, bg_url)


def render_expired_page(settings: Settings) -> str:
    return render_unavailable_page(
        settings, "Il collegamento a questo report non e' piu' utilizzabile."
    )


def render_unavailable_page(
    settings: Settings, reason: str, bg_url: str = ""
) -> str:
    page = (
        EXPIRED_PAGE.replace("__COMPANY__", html.escape(settings.company))
        .replace("__REASON__", html.escape(reason))
    )
    return with_custom_bg(page, bg_url)


EXPIRED_PAGE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__COMPANY__ &middot; Link scaduto</title>
</head>
<body>
<div class="card">
  <h1>Link non valido o scaduto</h1>
  <p>__REASON__</p>
  <p>Chiedere un nuovo link al fornitore, oppure accedere alla
     piattaforma per consultare il report.</p>
  <p><a href="/login">Accesso</a></p>
</div>
</body>
</html>
"""

EXPIRED_PAGE = EXPIRED_PAGE.replace("</head>", "<style>" + EXPIRED_CSS + "</style></head>")
