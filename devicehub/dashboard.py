"""Dashboard unificata, erede del design VisionOS.

Serve il pannello operativo: KPI, tabella flotta, mappa, censimento con
provisioning, e le schede dei moduli non ancora collegati dichiarate come tali.
Nessun dato finto: quello che non c'e' viene detto, non simulato.
"""

from __future__ import annotations

import html

from .config import Settings
from .theme import DASHBOARD_CSS, THEME_JS, with_custom_bg

PAGE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__COMPANY__ - Fleet VisionOS</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
<script>try{if(localStorage.getItem('dh_theme')!=='light')document.body.classList.add('dark');}catch(e){}</script>
<div class="app-shell">
<aside class="sidebar" id="sidebar" aria-label="Navigazione, profilo e controlli">
  <div class="brand">
    <div class="brand-mark"></div>
    <div>
      <h1>__COMPANY__</h1>
      <div class="sub">FleetHUD &middot; visionOS</div>
    </div>
    <button class="side-close" onclick="toggleSidebar(false)" aria-label="Chiudi navigazione">&times;</button>
  </div>

  <div class="sidebar-search">
    <input id="side-search" placeholder="Cerca dispositivi..." autocomplete="off"
           aria-label="Ricerca rapida dispositivi"
           oninput="renderSideResults(this.value)" onkeydown="sideSearchKey(event)">
    <div class="side-results" id="side-results"></div>
  </div>

  <div class="side-user">
    <div class="side-avatar" id="side-avatar">&mdash;</div>
    <div>
      <h4 id="side-name">&mdash;</h4>
      <p id="side-role">&mdash;</p>
    </div>
  </div>

  <div class="side-group-title">Navigazione</div>
  <div class="side-nav">
    <button class="active" data-tab="tab-dashboard" onclick="showTab('tab-dashboard', this)"><span class="ico">📊</span>Dashboard</button>
    <button data-tab="tab-map" onclick="showTab('tab-map', this)"><span class="ico">📍</span>Mappa</button>
    <button data-tab="tab-fleet" onclick="showTab('tab-fleet', this)"><span class="ico">🚚</span>Flotta<span class="count" id="side-fleet-count">0</span></button>
    <button data-tab="tab-census" onclick="showTab('tab-census', this)"><span class="ico">📡</span>Censimento</button>
    <button data-tab="tab-soc" onclick="showTab('tab-soc', this)"><span class="ico">🚨</span>Centro SOC<span class="count" id="side-soc-count">0</span></button>
    <button data-tab="tab-esg" onclick="showTab('tab-esg', this)"><span class="ico">🌿</span>Report ESG</button>
    <button data-tab="tab-maintenance" onclick="showTab('tab-maintenance', this)"><span class="ico">🛠️</span>Manutenzione</button>
    <button data-tab="tab-guida" onclick="showTab('tab-guida', this)"><span class="ico">🚦</span>Stile di guida</button>
    <button data-tab="tab-safety" onclick="showTab('tab-safety', this)"><span class="ico">🦺</span>Sicurezza</button>
    <button data-tab="tab-soluzioni" onclick="showTab('tab-soluzioni', this)"><span class="ico">🧩</span>Soluzioni</button>
    <button data-tab="tab-branding" onclick="showTab('tab-branding', this)"><span class="ico">🎨</span>Branding</button>
    <button data-tab="tab-system" id="side-system" style="display:none" onclick="showTab('tab-system', this)"><span class="ico">⚙️</span>Sistema</button>
    <button data-tab="tab-users" id="side-users" style="display:none" onclick="showTab('tab-users', this)"><span class="ico">👤</span>Utenti</button>
  </div>

  <div class="side-group-title">Controlli di sicurezza</div>
  <div class="side-nav">
    <div class="side-toggle-row">
      <div>Blocco motore<small id="side-engine-note">nessun mezzo selezionato</small></div>
      <label class="switch"><input id="side-engine" type="checkbox" disabled onchange="sideEngineToggle(this)"><span class="slider"></span></label>
    </div>
    <div class="side-toggle-row">
      <div>Modalità privacy<small id="side-privacy-note">nessun mezzo selezionato</small></div>
      <label class="switch"><input id="side-privacy" type="checkbox" disabled onchange="sidePrivacyToggle(this)"><span class="slider"></span></label>
    </div>
    <div class="side-status">Sicurezza WAL<span class="badge on" title="WAL e busy_timeout 30 s su ogni connessione">attiva</span></div>
    <div class="side-status">Ingestione TCP<span class="badge on">__TCP_PORT__</span></div>
  </div>

  <div class="side-group-title">Moduli dichiarati</div>
  <div class="side-nav">
    <button data-tab="tab-dossier" onclick="showTab('tab-dossier', this)"><span class="ico">🗂️</span>Fascicolo</button>
    <button data-tab="tab-video" onclick="showTab('tab-video', this)"><span class="ico">🎥</span>Video</button>
    <button data-tab="tab-logistics" onclick="showTab('tab-logistics', this)"><span class="ico">⛽</span>Logistica</button>
    <button data-tab="tab-compliance" onclick="showTab('tab-compliance', this)"><span class="ico">📄</span>Tachigrafo</button>
  </div>
</aside>
<div id="side-scrim" onclick="toggleSidebar(false)"></div>

<div class="workspace">
<header class="topbar">
  <div class="brand">
    <button class="menu-toggle" onclick="toggleSidebar()" aria-label="Apri navigazione">&#9776;</button>
    <div class="brand-mark"></div>
    <div>
      <h1>__COMPANY__</h1>
      <div class="sub">FleetHUD &middot; TCP __TCP_PORT__ &middot; API __API_PORT__</div>
    </div>
  </div>
  <div class="tools">
    <span class="brand-badge">FleetHUD</span>
    <button class="theme-toggle" id="theme-toggle" onclick="toggleTheme()" title="Tema notturno" aria-label="Cambia tema">🌙</button>
    <span id="vertical-badge" class="badge on" style="display:none"></span>
    <span id="who" class="sub">&nbsp;</span>
    <input id="token" type="password" placeholder="token API" style="width:150px">
    <button onclick="saveToken()">Salva</button>
    <button onclick="refresh()">Aggiorna</button>
    <button onclick="changePassword()">Password</button>
    <button onclick="logout()">Esci</button>
  </div>
</header>

<div id="offline-banner" style="display:none;margin:10px 18px;padding:8px 12px;border-radius:10px;background:#fef3c7;color:#92400e;font-size:12.5px;border:1px solid #fde68a"></div>

<aside class="emergency-hud" id="emergency-hud" hidden aria-live="assertive" aria-label="Allarme critico">
  <div class="emergency-head">
    <span class="emergency-kicker">Allarme critico</span>
    <button class="eh-close" onclick="dismissEmergencyHud()" aria-label="Chiudi pannello">&times;</button>
  </div>
  <strong id="eh-vehicle">&mdash;</strong>
  <span class="emergency-detail" id="eh-detail">&mdash;</span>
  <div class="row emergency-actions">
    <button class="danger" onclick="emergencyBlock()">Blocca motore</button>
    <button id="eh-street" onclick="emergencyStreetView()">Street View</button>
    <button onclick="emergencyTrack()">Tracciato</button>
  </div>
</aside>

<main>
  <section id="tab-dashboard" class="tab active" data-view="dashboard">
    <div class="tab-inner">
      <div class="kpis">
        <div class="kpi"><div class="label">Mezzi</div><div class="value" id="kpi-fleet">0</div></div>
        <div class="kpi"><div class="label">Online</div><div class="value" id="kpi-online" style="color:var(--ok)">0</div></div>
        <div class="kpi"><div class="label">In movimento</div><div class="value" id="kpi-moving" style="color:var(--accent)">0</div></div>
        <div class="kpi"><div class="label">Da abilitare</div><div class="value" id="kpi-pending" style="color:var(--warn)">0</div></div>
        <div class="kpi"><div class="label">Motori in marcia</div><div class="value" id="kpi-engines" style="color:var(--ok)">0</div></div>
        <div class="kpi"><div class="label">Blocchi attivi</div><div class="value" id="kpi-blocks" style="color:var(--accent)">0</div></div>
        <div class="kpi"><div class="label">Allarmi aperti</div><div class="value" id="kpi-alerts" style="color:var(--bad)">0</div></div>
      </div>

      <div class="panel" id="vertical-panel" style="display:none">
        <div class="row" style="justify-content:space-between">
          <h2 id="vertical-title" style="margin:0">Vista verticale</h2>
          <span class="sub" id="vertical-note"></span>
        </div>
        <div class="chips" id="vertical-functions"></div>
        <div id="heavy-panel" style="display:none;margin-top:16px">
          <h2 style="font-size:15px;margin:0 0 8px">Mezzi pesanti in servizio</h2>
          <div class="row" style="margin-bottom:10px">
            <select id="assign-device" onchange="prefillAssignment()" style="min-width:180px"></select>
            <select id="assign-driver" style="min-width:180px">
              <option value="">Nessun autista</option>
            </select>
            <input id="assign-trailer" placeholder="Rimorchio" style="width:120px">
            <input id="assign-trailer-type" placeholder="Tipo" style="width:140px">
            <button class="ok" onclick="saveAssignment()">Assegna</button>
          </div>
          <div class="scroll"><table>
            <thead><tr><th>Mezzo</th><th>Autista</th><th>Rimorchio</th><th>Stato</th><th>Velocita</th><th>Km</th><th>Allarmi</th></tr></thead>
            <tbody id="heavy-body"></tbody>
          </table></div>
        </div>
        <div class="kpis" style="margin-top:10px">
          <div class="kpi"><div class="label">Mezzi</div><div class="value" id="v-fleet">0</div></div>
          <div class="kpi"><div class="label">Online</div><div class="value" id="v-online" style="color:var(--ok)">0</div></div>
          <div class="kpi"><div class="label">Km totali</div><div class="value" id="v-km">0</div></div>
          <div class="kpi"><div class="label" id="v-moving-label">In movimento</div><div class="value" id="v-moving">0</div></div>
          <div class="kpi"><div class="label">Tasso utilizzo</div><div class="value" id="v-util">0%</div></div>
          <div class="kpi"><div class="label">Allarmi aperti</div><div class="value" id="v-alerts" style="color:var(--bad)">0</div></div>
          <div class="kpi"><div class="label">Scadenze manutenzione</div><div class="value" id="v-due">0</div></div>
        </div>
      </div>

      <div class="grid2">
        <div class="panel">
          <h2>Andamento velocita</h2>
          <canvas id="speedChart" height="150"></canvas>
        </div>
        <div class="panel">
          <h2>Km percorsi per mezzo</h2>
          <canvas id="kmChart" height="150"></canvas>
        </div>
      </div>

      <div class="panel">
        <h2>Flotta in tempo reale</h2>
        <div class="scroll"><table>
          <thead><tr><th>Mezzo</th><th>IMEI</th><th>Stato</th><th>Link</th><th>Velocita</th>
          <th>Carburante</th><th>Temp</th><th>RPM</th><th>Km</th><th>Comandi</th></tr></thead>
          <tbody id="fleet-body"></tbody>
        </table></div>
      </div>
    </div>
  </section>

  <section id="tab-map" class="tab">
    <div class="map-shell">
      <div id="map"></div>
      <div class="map-glass map-search-panel">
        <span class="search-icon" aria-hidden="true"></span>
        <input id="map-search" placeholder="Cerca targa, modello o IMEI" oninput="renderDeviceSidebar()">
        <span id="map-device-count" class="map-count">0</span>
      </div>
      <aside class="map-glass device-sidebar">
        <div class="map-side-head">
          <span>Dispositivi</span>
          <span class="muted" id="map-side-sub">flotta</span>
        </div>
        <div id="device-list" class="device-list"></div>
      </aside>
      <aside class="map-glass vehicle-card" id="vehicle-card">
        <div class="vehicle-head">
          <div>
            <div class="vehicle-plate" id="vd-plate">—</div>
            <div class="vehicle-model" id="vd-model">Seleziona un mezzo</div>
          </div>
          <span id="vd-status" class="status-pill offline">—</span>
        </div>
        <div class="vehicle-grid">
          <div><span>Velocità</span><strong id="vd-speed">—</strong></div>
          <div><span>Batteria</span><strong id="vd-battery">—</strong></div>
          <div><span>Ultimo segnale</span><strong id="vd-signal">—</strong></div>
        </div>
        <div class="vehicle-address">
          <span>Indirizzo attuale</span>
          <strong id="vd-address">—</strong>
        </div>
        <div class="row vehicle-actions">
          <button id="vd-follow" class="ok" onclick="toggleFollow()">Segui sulla mappa</button>
          <button onclick="replaySelected()">Visualizza Storico</button>
        </div>
        <div class="row vehicle-actions">
          <button id="vd-street" onclick="openSelectedStreetView()">Street View</button>
        </div>
        <div class="row vehicle-actions" id="vd-manage" style="display:none">
          <button onclick="editSelectedDevice()">Modifica mezzo</button>
          <button class="danger" onclick="deleteSelectedDevice()">Elimina mezzo</button>
        </div>
      </aside>
      <div class="map-glass map-controls">
        <button onclick="clearTrack()">Pulisci traccia</button>
        <button onclick="openGoogleMap()">Google</button>
        <button id="map-toggle" style="display:none" onclick="toggleMapTracks()">Mostra tracce</button>
        <span id="map-geofence-actions" style="display:none;gap:6px">
          <button class="ok" onclick="createGeofence()">Salva area</button>
          <button onclick="cancelGeofenceDrawing()">Annulla area</button>
        </span>
        <a id="gmaps-link" target="_blank" rel="noopener" href="#">Apri 3D</a>
        <a id="street-link" target="_blank" rel="noopener" href="#">Street View</a>
        <span id="map-note">Esri Dark Gray · marker GPS animati</span>
        <span id="map-hint" class="map-hint">Le posizioni arrivano dall'ultimo record di ogni tracker.</span>
      </div>
      <section class="map-glass playback-panel" id="playback-panel" aria-label="Player storico percorsi" hidden>
        <div class="playback-head">
          <div class="playback-ident">
            <span>Storico percorsi</span>
            <strong id="pb-vehicle">—</strong>
          </div>
          <div class="playback-kpis">
            <div><span>Km totali</span><strong id="pb-total-km">—</strong></div>
            <div><span>Durata viaggio</span><strong id="pb-duration">—</strong></div>
            <div><span>Velocità max</span><strong id="pb-max-speed">—</strong></div>
          </div>
          <button class="playback-exit" onclick="exitHistory()">Esci dallo storico</button>
        </div>
        <div class="playback-main">
          <button id="pb-play" class="playback-play" onclick="togglePlayback()" aria-label="Avvia riproduzione">▶</button>
          <div class="playback-speed" role="group" aria-label="Velocità di riproduzione">
            <button data-speed="1" class="active" onclick="setPlaybackSpeed(1)">1x</button>
            <button data-speed="2" onclick="setPlaybackSpeed(2)">2x</button>
            <button data-speed="5" onclick="setPlaybackSpeed(5)">5x</button>
            <button data-speed="10" onclick="setPlaybackSpeed(10)">10x</button>
          </div>
          <div class="playback-live">
            <strong id="pb-clock">--:--:--</strong>
            <span id="pb-current-speed">0 km/h</span>
          </div>
        </div>
        <input id="pb-slider" class="playback-slider" type="range" min="0" max="1000" step="1" value="0"
               aria-label="Posizione temporale" oninput="seekPlayback(this.value)">
        <div class="playback-foot">
          <div class="playback-dates" role="group" aria-label="Giorno dello storico">
            <button data-range="today" class="active" onclick="setHistoryDate('today')">Oggi</button>
            <button data-range="yesterday" onclick="setHistoryDate('yesterday')">Ieri</button>
            <label>Data specifica <input id="pb-date" type="date" onchange="setHistoryDate('custom', this.value)"></label>
            <button class="tiny" onclick="exportHistory('gpx')">GPX</button>
            <button class="tiny" onclick="exportHistory('kml')">KML</button>
          </div>
          <span id="pb-points">—</span>
        </div>
      </section>
      <iframe id="gmaps-frame" class="gmaps-frame" title="Google Maps"></iframe>
    </div>
    <div class="tab-inner map-under">
      <div class="panel">
        <div class="row" style="margin-top:0">
          <input id="export-imei" placeholder="IMEI" style="width:190px">
          <input id="export-hours" type="number" min="1" max="2160" value="24"
                 style="width:80px" title="ore di storico">
          <button onclick="exportPositions('csv')">Posizioni CSV</button>
          <button onclick="exportPositions('xlsx')">Posizioni XLSX</button>
          <span class="sub">ore di storico da esportare</span>
        </div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Attività recenti</h2>
          <div class="row">
            <select id="activity-imei" style="min-width:210px"></select>
            <input id="activity-hours" type="number" min="1" max="360" value="24"
                   style="width:80px" title="ore">
            <button onclick="loadActivity()">Carica</button>
            <button onclick="exportTrips('xlsx')" title="Scarica i tragitti di tutta la flotta">Tragitti XLSX</button>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <div class="kpi"><div class="label">Tragitti</div><div class="value" id="activity-trips">0</div></div>
          <div class="kpi"><div class="label">Soste</div><div class="value" id="activity-stops">0</div></div>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Tipo</th><th>Inizio</th><th>Fine</th><th>Durata</th>
          <th>Km</th><th>Velocita max</th></tr></thead>
          <tbody id="activity-body"></tbody>
        </table></div>
        <div class="empty" id="activity-empty" style="display:none">
          Nessun tragitto nelle ore indicate.
        </div>
      </div>
    </div>
  </section>

  <section id="tab-fleet" class="tab">
    <div class="tab-inner">
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Gestione flotta</h2>
          <div class="row">
            <button onclick="exportDataset('devices', 'csv')">CSV</button>
            <button onclick="exportDataset('devices', 'xlsx')">XLSX</button>
          </div>
        </div>
        <div class="scroll"><table>
          <thead><tr><th>Mezzo</th><th>IMEI</th><th>Stato</th><th>Link</th><th>Velocita</th>
          <th>Igni</th><th>Km</th><th>Comandi</th></tr></thead>
          <tbody id="fleet-full-body"></tbody>
        </table></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Costi e carburante</h2>
          <div class="row">
            <input id="fuel-month" type="month">
            <button onclick="loadFuel()">Aggiorna</button>
            <button onclick="exportDataset('fuel', 'csv')">CSV</button>
            <button onclick="exportDataset('fuel', 'xlsx')">XLSX</button>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <div class="kpi"><div class="label">Km</div><div class="value" id="fuel-km">0</div></div>
          <div class="kpi"><div class="label">Litri stimati</div><div class="value" id="fuel-liters">0</div></div>
          <div class="kpi"><div class="label">Costo</div><div class="value" id="fuel-cost">0</div></div>
          <div class="kpi"><div class="label">Cali anomali</div><div class="value" id="fuel-drops">0</div></div>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Mezzo</th><th>Km</th><th>Consumo</th><th>Litri</th><th>Costo</th>
          <th>Minimo (h)</th><th>Cali (L)</th></tr></thead>
          <tbody id="fuel-body"></tbody>
        </table></div>
        <div class="sub" style="margin-top:8px">
          Stima dichiarata: consumo per mezzo o di flotta e ore di minimo; il
          costo usa il prezzo configurato. I cali a motore spento sono sospetti.
        </div>
      </div>
    </div>
  </section>

  <section id="tab-census" class="tab">
    <div class="tab-inner">
      <div class="panel">
        <h2>Censimento dispositivi</h2>
        <div class="scroll"><table>
          <thead><tr><th>IMEI</th><th>Stato</th><th>Modello</th><th>Targa</th>
          <th>Primo contatto</th><th>Ultimo contatto</th><th>Azioni</th></tr></thead>
          <tbody id="census-body"></tbody>
        </table></div>
      </div>
      <div class="panel">
        <h2>Provisioning</h2>
        <div class="row">
          <input id="p_imei" placeholder="IMEI" style="width:180px">
          <input id="p_host" value="__PUBLIC_HOST__" placeholder="host" style="width:200px">
          <input id="p_port" value="__PUBLIC_PORT__" placeholder="porta" style="width:76px">
          <input id="p_apn" value="__APN__" placeholder="APN" style="width:190px">
          <button onclick="loadProvisioning()">Genera comandi</button>
          <button onclick="copyProvisioning()">Copia</button>
        </div>
        <pre id="prov"></pre>
      </div>
    </div>
  </section>

  <section id="tab-esg" class="tab">
    <div class="tab-inner">
      <div class="kpis">
        <div class="kpi"><div class="label">Km nel periodo</div><div class="value" id="esg-km">0</div></div>
        <div class="kpi"><div class="label">Litri stimati</div><div class="value" id="esg-liters">0</div></div>
        <div class="kpi"><div class="label">CO2 (kg)</div><div class="value" id="esg-co2" style="color:var(--warn)">0</div></div>
        <div class="kpi"><div class="label">CO2 per km</div><div class="value" id="esg-perkm">0</div></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Emissioni per periodo</h2>
          <div class="row">
            <select id="esg-days" onchange="loadEsg()">
              <option value="7">7 giorni</option>
              <option value="30" selected>30 giorni</option>
              <option value="90">90 giorni</option>
            </select>
            <button onclick="loadEsg()">Aggiorna</button>
          </div>
        </div>
        <canvas id="esgChart" height="150"></canvas>
        <div class="sub" id="esg-note" style="margin-top:10px"></div>
      </div>
      <div class="panel">
        <h2>Dettaglio per mezzo</h2>
        <div class="scroll"><table>
          <thead><tr><th>Mezzo</th><th>IMEI</th><th>Km</th><th>Litri stimati</th>
          <th>CO2 kg</th><th>g/km</th><th>Giorni con dati</th><th>Parametri</th></tr></thead>
          <tbody id="esg-body"></tbody>
        </table></div>
        <div class="empty" id="esg-empty" style="display:none">Nessun chilometraggio CAN nel periodo.</div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Snapshot mensili</h2>
          <div class="row">
            <input id="snap-month" placeholder="YYYY-MM" style="width:110px">
            <button onclick="createSnapshot()">Chiudi mese</button>
            <button onclick="loadSnapshots()">Aggiorna</button>
          </div>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Periodo</th><th>Creato</th><th>Da</th><th>Impronta</th><th></th></tr></thead>
          <tbody id="snap-body"></tbody>
        </table></div>
        <div class="sub" id="snap-note" style="margin-top:8px"></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Chiavi di firma</h2>
          <div class="row">
            <button onclick="loadKeys()">Aggiorna</button>
            <button class="danger" id="rotate-key" style="display:none" onclick="rotateKey()">Ruota chiave</button>
          </div>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Impronta</th><th>Creata</th><th>Da</th><th>Stato</th>
          <th>Snapshot</th></tr></thead>
          <tbody id="keys-body"></tbody>
        </table></div>
        <div class="sub" style="margin-top:8px">
          Gli snapshot chiusi restano verificabili con la chiave che li ha firmati.
        </div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Link dei report</h2>
          <div class="row">
            <input id="link-hours" type="number" min="1" max="720" value="72"
                   style="width:90px" title="ore di validita">
            <input id="link-max" type="number" min="1" max="1000" value="25"
                   style="width:80px" title="aperture massime">
            <button onclick="createLinkForSelected()">Crea link</button>
            <button onclick="loadLinks()">Aggiorna</button>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <label class="sub" for="link-snapshot">Snapshot</label>
          <select id="link-snapshot" onchange="loadLinks()" style="min-width:220px"></select>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Creato</th><th>Scade</th><th>Da</th><th>Aperture</th>
          <th>Stato</th><th></th></tr></thead>
          <tbody id="link-body"></tbody>
        </table></div>
        <div class="sub" style="margin-top:8px">
          Chi apre il link vede il solo report, fino alla scadenza o alla revoca.
        </div>
      </div>
    </div>
  </section>

  <section id="tab-maintenance" class="tab">
    <div class="tab-inner">
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Interventi e scadenze</h2>
          <div class="row">
            <button onclick="loadMaintenance()">Aggiorna</button>
            <button onclick="exportDataset('maintenance', 'csv')">CSV</button>
            <button onclick="exportDataset('maintenance', 'xlsx')">XLSX</button>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <select id="m_imei" style="min-width:210px"></select>
          <select id="m_kind">
            <option>Tagliando</option><option>Gomme</option><option>Revisione</option>
            <option>Riparazione</option><option>Altro</option>
          </select>
          <input id="m_due_date" type="date" title="scadenza">
          <input id="m_due_km" type="number" min="0" placeholder="km" style="width:100px">
          <input id="m_note" placeholder="nota" style="width:170px">
          <input id="m_repeat_km" type="number" min="1" placeholder="ripeti km" style="width:110px">
          <input id="m_repeat_months" type="number" min="1" max="120" placeholder="ripeti mesi"
                 style="width:115px">
          <button class="ok" onclick="createMaintenance()">Pianifica</button>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Mezzo</th><th>Tipo</th><th>Scadenza</th><th>Km previsti</th>
          <th>Note</th><th>Ripete</th><th>Stato</th><th></th></tr></thead>
          <tbody id="maint-body"></tbody>
        </table></div>
        <div class="empty" id="maint-empty" style="display:none">Nessun intervento pianificato.</div>
        <div class="sub" style="margin-top:8px">
          Scadenza a data o a chilometraggio: "scaduto" compare quando una
          delle due e' superata. Il completamento resta nello storico.
        </div>
      </div>
    </div>
  </section>

  <section id="tab-soluzioni" class="tab">
    <div class="tab-inner">
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Pacchetto e verticale</h2>
          <div class="row">
            <select id="sol-vertical">
              <option value="trasporti">Trasporti e logistica</option>
            </select>
            <select id="sol-connectivity">
              <option value="4g">Connettività 4G</option>
              <option value="2g">Connettività 2G</option>
              <option value="swiss_global">Svizzera + mappe globali</option>
            </select>
            <select id="sol-maps">
              <option value="osm">Mappe OpenStreetMap</option>
              <option value="google">Mappe Google</option>
              <option value="swiss">Mappe Svizzera</option>
            </select>
            <button class="ok" onclick="saveSolution()">Salva</button>
          </div>
        </div>
        <div class="sub" style="margin-top:8px">
          La scelta vale per il cliente dell'utente e viene usata come riferimento
          in demo e provisioning. Connettività e mappe non cambiano il SIM o il
          dispositivo installato: restano dati di configurazione del servizio.
        </div>
      </div>
      <div class="panel">
        <h2>Servizi della piattaforma</h2>
        <div class="sub" id="sol-status" style="white-space:pre-line;margin-top:6px"></div>
      </div>
    </div>
  </section>

  <section id="tab-guida" class="tab">
    <div class="tab-inner">
      <div class="kpis">
        <div class="kpi"><div class="label">Eventi 24h</div><div class="value" id="driving-events">0</div></div>
        <div class="kpi"><div class="label">Accelerazioni</div><div class="value" id="driving-accel" style="color:var(--warn)">0</div></div>
        <div class="kpi"><div class="label">Frenate</div><div class="value" id="driving-brake" style="color:var(--bad)">0</div></div>
        <div class="kpi"><div class="label">Punteggio migliore</div><div class="value" id="driving-score">—</div></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Stile di guida</h2>
          <div class="row">
            <input id="driver-name" placeholder="nome autista" style="width:150px">
            <input id="driver-badge" placeholder="badge iButton" style="width:130px">
            <select id="driver-tenant" style="display:none;width:150px"></select>
            <button class="ok" onclick="addDriver()">Aggiungi</button>
            <button onclick="loadDriving()">Aggiorna</button>
          </div>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Quando</th><th>Mezzo</th><th>Autista</th><th>Evento</th>
          <th>Velocità</th></tr></thead>
          <tbody id="driving-body"></tbody>
        </table></div>
        <div class="empty" id="driving-empty" style="display:none">Nessun evento brusco nelle ultime 24 ore.</div>
        <div class="sub" id="driving-drivers" style="margin-top:8px"></div>
        <div class="sub" style="margin-top:8px">
          Frenate e accelerazioni sono calcolate dalle variazioni di velocità
          delle posizioni registrate, con soglie configurabili. L'autista
          arriva dal badge iButton se `DEVICEHUB_DRIVER_IO_ID` è impostato.
        </div>
      </div>
    </div>
  </section>

  <section id="tab-safety" class="tab">
    <div class="tab-inner">
      <div class="kpis">
        <div class="kpi"><div class="label">Controlli</div><div class="value" id="safety-total">0</div></div>
        <div class="kpi"><div class="label">Conformi</div><div class="value" id="safety-ok" style="color:var(--ok)">0</div></div>
        <div class="kpi"><div class="label">Non conformi</div><div class="value" id="safety-bad" style="color:var(--bad)">0</div></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Sicurezza sul lavoro</h2>
          <button onclick="loadSafety()">Aggiorna</button>
        </div>
        <div class="row" style="margin-top:10px">
          <select id="s_imei" style="min-width:210px"></select>
          <select id="s_kind">
            <option>Cinture</option><option>Limiti di velocita</option>
            <option>Carico e masse</option><option>Documenti</option>
            <option>Dispositivi di protezione</option><option>Altro</option>
          </select>
          <label class="sub"><input type="checkbox" id="s_compliant" checked> conforme</label>
          <input id="s_note" placeholder="nota" style="width:230px">
          <button class="ok" onclick="createSafetyCheck()">Registra</button>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Quando</th><th>Mezzo</th><th>Controllo</th><th>Esito</th>
          <th>Nota</th><th>Operatore</th></tr></thead>
          <tbody id="safety-body"></tbody>
        </table></div>
        <div class="empty" id="safety-empty" style="display:none">Nessun controllo registrato.</div>
        <div class="sub" style="margin-top:8px">
          Una non conformita apre un allarme SAFETY nella scheda SOC. Il
          controllo e' una registrazione operatore, non una lettura del mezzo.
        </div>
      </div>
    </div>
  </section>

  <section id="tab-branding" class="tab">
    <div class="tab-inner">
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Branding del report</h2>
          <div class="row">
            <button onclick="loadBranding()">Aggiorna</button>
            <button onclick="previewBrandingPdf()">Anteprima PDF</button>
            <button class="ok" onclick="saveBranding()">Salva</button>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <label class="sub" for="brand-name">Nome</label>
          <input id="brand-name" placeholder="nome mostrato nel PDF" style="width:240px">
          <label class="sub" for="brand-color">Colore</label>
          <input id="brand-color" type="color" value="#0e7490"
                 style="width:60px;height:34px;padding:2px">
        </div>
        <div class="row" style="margin-top:10px">
          <input id="brand-logo" type="file" accept="image/png,image/jpeg">
          <button onclick="uploadBrandLogo()">Carica logo</button>
          <button class="danger" onclick="removeBrandLogo()">Rimuovi logo</button>
          <span class="sub" id="brand-logo-note"></span>
        </div>
        <div class="sub" style="margin-top:8px">
          Logo fino a 512 KB (PNG o JPEG). Nome, colore e logo valgono per il
          cliente dell'utente e finiscono nel PDF del report. L'anteprima usa
          nome e colore scritti nei campi, anche se non ancora salvati.
        </div>
        <div class="row" style="margin-top:16px">
          <label class="sub" for="brand-bg-url">Sfondo</label>
          <input id="brand-bg-url" placeholder="https://... oppure /statici/sfondo.jpg"
                 style="width:300px" oninput="previewBrandBackground(this.value.trim())">
          <button onclick="saveBrandBackground()">Salva URL</button>
        </div>
        <div class="row" style="margin-top:8px">
          <input id="brand-bg-file" type="file" accept="image/png,image/jpeg,image/webp">
          <button onclick="uploadBrandBackground()">Carica sfondo</button>
          <button onclick="setBrandBackgroundMode('default')">Usa predefinito</button>
          <button class="danger" onclick="setBrandBackgroundMode('none')">Nessuno sfondo</button>
          <button id="brand-bg-restore" style="display:none"
                  onclick="reactivateBrandBackground()">Riattiva sfondo</button>
          <span class="sub" id="brand-bg-note"></span>
        </div>
        <div class="bg-preview" id="brand-bg-preview">
          <span class="bg-preview-chip">Anteprima sfondo</span>
        </div>
        <div class="sub" style="margin-top:6px">
          Sfondo della dashboard, del report e della pagina di verifica del
          cliente: un URL (http, percorso statico o data:image) oppure
          un'immagine PNG, JPEG o WebP fino a 1,5 MB. "Usa predefinito"
          eredita lo sfondo del server; "Nessuno sfondo" lascia il tema pulito.
        </div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Destinatari allarmi</h2>
          <div class="row">
            <button onclick="loadNotificationSettings()">Aggiorna</button>
            <button class="ok" onclick="saveNotificationSettings()">Salva</button>
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <label class="sub" for="notify-emails">Email</label>
          <input id="notify-emails" placeholder="uno@cliente.it, due@cliente.it"
                 style="width:330px">
        </div>
        <div class="row" style="margin-top:8px">
          <label class="sub" for="notify-phones">SMS</label>
          <input id="notify-phones" placeholder="+39333..., +39334..."
                 style="width:330px">
        </div>
        <div class="sub" id="notify-channels" style="margin-top:8px"></div>
        <div class="sub" style="margin-top:8px">
          Se vuoti valgono i destinatari globali. Valgono solo per gli allarmi
          del cliente dell'utente; ogni canale ha un intervallo minimo tra due
          messaggi per lo stesso allarme. In demo l'email usa l'anteprima
          locale e SMS/voce restano nell'outbox senza traffico esterno.
        </div>
      </div>
    </div>
  </section>

  <section id="tab-soc" class="tab">
    <div class="tab-inner">
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Allarmi</h2>
          <div class="row">
            <label class="sub"><input type="checkbox" id="soc-open" checked onchange="loadAlerts()"> solo aperti</label>
            <button onclick="exportDataset('alerts', 'csv')">CSV</button>
            <button onclick="exportDataset('alerts', 'xlsx')">XLSX</button>
            <button onclick="loadAlerts()">Aggiorna</button>
          </div>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>#</th><th>Ora</th><th>Mezzo</th><th>Tipo</th><th>Gravita</th>
          <th>Dettaglio</th><th>Presa in carico</th></tr></thead>
          <tbody id="soc-body"></tbody>
        </table></div>
        <div class="empty" id="soc-empty" style="display:none">Nessun allarme aperto.</div>
      </div>
      <div class="panel">
        <h2>Audit comandi</h2>
        <div class="scroll"><table>
          <thead><tr><th>Ora</th><th>IMEI</th><th>Azione</th><th>Comando</th>
          <th>Esito</th><th>Operatore</th></tr></thead>
          <tbody id="audit-body"></tbody>
        </table></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Outbox notifiche</h2>
          <button onclick="loadNotificationOutbox()">Aggiorna</button>
        </div>
        <div class="sub" id="outbox-channels" style="margin-top:8px"></div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Ora</th><th>Canale</th><th>Stato</th><th>Destinatari</th>
          <th>Messaggio</th></tr></thead>
          <tbody id="outbox-body"></tbody>
        </table></div>
        <div class="empty" id="outbox-empty" style="display:none">
          Nessuna notifica: l'outbox si popola al primo allarme.
        </div>
        <div class="sub" style="margin-top:8px">
          In demo l'email viene inviata a Mailpit/MailHog se disponibile, oppure
          resta in anteprima; SMS e voce simulati restano qui senza consumare
          credito e senza chiamare numeri reali.
        </div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Zone (geofence)</h2>
          <button onclick="loadGeofences()">Aggiorna</button>
        </div>
        <div class="row" style="margin-top:10px">
          <select id="g_shape" onchange="updateGeofenceShape()" title="tipo di recinto">
            <option value="circle">Cerchio</option>
            <option value="polygon">Poligono area</option>
            <option value="line">Linea di confine</option>
          </select>
          <input id="g_name" placeholder="nome zona" style="width:170px">
          <span id="g_circle_fields" class="row">
            <input id="g_lat" type="number" step="0.000001" placeholder="latitudine" style="width:130px">
            <input id="g_lon" type="number" step="0.000001" placeholder="longitudine" style="width:130px">
            <input id="g_radius" type="number" min="25" max="50000" value="500"
                   style="width:90px" title="raggio in metri">
            <button onclick="geofenceFromMap()">Dal centro mappa</button>
          </span>
          <label class="sub"><input type="checkbox" id="g_click"> clic sulla mappa</label>
        </div>
        <div class="row" style="margin-top:10px">
          <button id="g_draw_start" onclick="startGeofenceDrawing()">Disegna sulla mappa</button>
          <button id="g_draw_finish" onclick="finishGeofenceDrawing()" disabled>Chiudi disegno</button>
          <button id="g_draw_cancel" onclick="cancelGeofenceDrawing()" disabled>Annulla</button>
          <span id="g_draw_hint" class="sub">Per il poligono servono almeno 3 punti; per la linea 2.</span>
        </div>
        <div class="row" style="margin-top:10px">
          <label class="sub"><input type="checkbox" id="g_schedule"> fasce orarie</label>
          <label class="sub"><input type="checkbox" id="g_weekdays" checked> Lun–Ven</label>
          <label class="sub"><input type="checkbox" id="g_weekend"> weekend intero</label>
          <label class="sub">dalle <input id="g_from" type="time" value="18:00" style="width:100px"></label>
          <label class="sub">alle <input id="g_to" type="time" value="08:00" style="width:100px"></label>
          <select id="g_tz" title="fuso orario del cantiere">
            <option value="Europe/Rome">Europe/Rome</option>
            <option value="Europe/Zurich">Europe/Zurich</option>
            <option value="UTC">UTC</option>
          </select>
          <button class="ok" onclick="createGeofence()">Crea</button>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Nome</th><th>Tipo</th><th>Geometria</th><th>Allarmi attivi</th><th></th></tr></thead>
          <tbody id="geo-body"></tbody>
        </table></div>
        <div class="empty" id="geo-empty" style="display:none">Nessuna zona definita.</div>
        <div class="sub" style="margin-top:8px">
          Ingresso, uscita e attraversamento generano un allarme in questa scheda,
          via email e webhook. Le fasce orarie limitano gli allarmi alla chiusura
          del cantiere; senza fasce la zona e' sempre attiva. Le zone senza
          cliente valgono per tutti i mezzi; quelle di un cliente solo per i suoi.
        </div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Regole di notifica</h2>
          <button class="ok" onclick="saveAlertRules()">Salva</button>
        </div>
        <div class="row" style="margin-top:10px">
          <label class="sub"><input type="checkbox" id="rule-speed-on"> velocita oltre</label>
          <input id="rule-speed" type="number" min="1" max="300" value="90" style="width:80px"> km/h
          <label class="sub"><input type="checkbox" id="rule-theft-on"> furto oltre</label>
          <input id="rule-theft" type="number" min="1" max="200" value="5" style="width:70px"> km/h a motore spento
        </div>
        <div class="row" style="margin-top:10px">
          <label class="sub"><input type="checkbox" id="hours-on"> accensione fuori orario</label>
          <label class="sub"><input type="checkbox" id="hours-weekdays" checked> Lun–Ven</label>
          <label class="sub"><input type="checkbox" id="hours-weekend"> weekend</label>
          <label class="sub">dalle <input id="hours-from" type="time" value="08:00" style="width:100px"></label>
          <label class="sub">alle <input id="hours-to" type="time" value="18:00" style="width:100px"></label>
          <select id="hours-tz" title="fuso orario della fascia lavorativa">
            <option value="Europe/Rome">Europe/Rome</option>
            <option value="Europe/Zurich">Europe/Zurich</option>
            <option value="UTC">UTC</option>
          </select>
          <button class="ok" onclick="saveWorkHours()">Salva fascia</button>
        </div>
        <div class="sub" style="margin-top:8px">
          Il furto e' un'euristica: movimento con accensione spenta oltre la
          soglia. Le regole valgono per il cliente e aprono un allarme; i canali
          configurati (email, SMS, voce) lo notificano secondo l'outbox.
        </div>
      </div>
    </div>
  </section>

  <section id="tab-system" class="tab">
    <div class="tab-inner">
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Aggiornamenti piattaforma</h2>
          <div class="row">
            <button onclick="loadUpdates()">Aggiorna</button>
            <button class="ok" onclick="checkUpdates()">Verifica aggiornamenti</button>
          </div>
        </div>
        <div class="sub" style="margin-top:10px" id="update-status">
          Apri la verifica per leggere il canale di rilascio configurato.
        </div>
        <div class="sub" id="update-notes" style="white-space:pre-line;margin-top:6px"></div>
        <div class="row" style="margin-top:12px">
          <button class="danger" id="update-apply" style="display:none"
                  onclick="applyUpdate()">Aggiorna piattaforma</button>
        </div>
      </div>
      <div class="panel">
        <h2>Versione e configurazione</h2>
        <div class="sub" id="update-info" style="white-space:pre-line;margin-top:6px"></div>
        <div class="sub" style="margin-top:10px">
          Il pacchetto deve contenere la cartella `devicehub/` ed essere indicato
          da un manifest con versione e SHA-256. L'aggiornamento non tocca
          database, `.env` e archivio; dopo l'installazione il servizio si
          riavvia e la pagina si ricarica.
        </div>
      </div>
    </div>
  </section>

  <section id="tab-users" class="tab">
    <div class="tab-inner">
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Utenti e clienti</h2>
          <button onclick="loadUsers()">Aggiorna</button>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Utente</th><th>Nome</th><th>Cliente</th><th>Ruolo</th>
          <th>Stato</th><th>Ultimo accesso</th><th>Azioni</th></tr></thead>
          <tbody id="users-body"></tbody>
        </table></div>
        <div class="empty" id="users-empty" style="display:none">Nessun utente.</div>
      </div>
      <div class="panel">
        <h2>Nuovo utente</h2>
        <div class="row">
          <input id="u_username" placeholder="utente" style="width:150px">
          <input id="u_name" placeholder="nome e cognome" style="width:190px">
          <input id="u_password" type="password" placeholder="password (min 10)" style="width:190px">
          <select id="u_role">
            <option value="manager">manager</option>
            <option value="soc">soc</option>
            <option value="viewer">viewer</option>
            <option value="admin">admin</option>
          </select>
          <input id="u_tenant" placeholder="cliente (es. Trasporti Rossi)" style="width:210px">
          <button class="ok" onclick="createUser()">Crea</button>
        </div>
        <div class="sub" style="margin-top:10px">
          Chi crea un utente gli impone il cambio password al primo accesso.
          Un utente senza cliente vede solo i mezzi senza cliente assegnato.
        </div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Azioni amministrative</h2>
          <button onclick="loadAdminActions()">Aggiorna</button>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Quando</th><th>Chi</th><th>Azione</th><th>Oggetto</th>
          <th>Dettaglio</th></tr></thead>
          <tbody id="admin-audit-body"></tbody>
        </table></div>
      </div>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <h2 style="margin:0">Indirizzi bloccati dai link</h2>
          <button onclick="loadLinkBlocks()">Aggiorna</button>
        </div>
        <div class="scroll" style="margin-top:10px"><table>
          <thead><tr><th>Indirizzo</th><th>Tentativi</th><th>Primo</th>
          <th>Bloccato fino</th><th>Stato</th></tr></thead>
          <tbody id="blocks-body"></tbody>
        </table></div>
        <div class="empty" id="blocks-empty" style="display:none">Nessun indirizzo bloccato.</div>
        <div class="sub" style="margin-top:8px">
          Lo sblocco vale subito: tentativi e blocco ripartono da zero. Utile
          quando un cliente condiviso dietro NAT resta chiuso fuori.
        </div>
      </div>
    </div>
  </section>

  __PENDING_TABS__

  <div class="panel">
    <h2>Log</h2>
    <div id="log">pronto.</div>
  </div>
</main>
</div>
</div>

<nav class="dock" aria-label="Navigazione principale">
  <button class="active" data-tab="tab-dashboard" onclick="showTab('tab-dashboard', this)"><span class="ico">📊</span>Dashboard</button>
  <button data-tab="tab-map" onclick="showTab('tab-map', this)"><span class="ico">📍</span>Mappa</button>
  <button data-tab="tab-fleet" onclick="showTab('tab-fleet', this)"><span class="ico">🚚</span>Flotta</button>
  <button data-tab="tab-census" onclick="showTab('tab-census', this)"><span class="ico">📡</span>Censimento</button>
  <button data-tab="tab-esg" onclick="showTab('tab-esg', this)"><span class="ico">🌿</span>ESG</button>
  <button data-tab="tab-maintenance" onclick="showTab('tab-maintenance', this)"><span class="ico">🛠️</span>Manutenzione</button>
  <button data-tab="tab-dossier" onclick="showTab('tab-dossier', this)"><span class="ico">🗂️</span>Fascicolo</button>
  <button data-tab="tab-soc" onclick="showTab('tab-soc', this)"><span class="ico">🚨</span>SOC</button>
  <button data-tab="tab-video" onclick="showTab('tab-video', this)"><span class="ico">🎥</span>Video</button>
  <button data-tab="tab-logistics" onclick="showTab('tab-logistics', this)"><span class="ico">⛽</span>Logistica</button>
  <button data-tab="tab-compliance" onclick="showTab('tab-compliance', this)"><span class="ico">📄</span>Tachigrafo</button>
  <button data-tab="tab-branding" onclick="showTab('tab-branding', this)"><span class="ico">🎨</span>Branding</button>
  <button data-tab="tab-guida" onclick="showTab('tab-guida', this)"><span class="ico">🚦</span>Guida</button>
  <button data-tab="tab-soluzioni" onclick="showTab('tab-soluzioni', this)"><span class="ico">🧩</span>Soluzioni</button>
  <button data-tab="tab-safety" onclick="showTab('tab-safety', this)"><span class="ico">🦺</span>Sicurezza</button>
  <button data-tab="tab-system" id="dock-system" style="display:none" onclick="showTab('tab-system', this)"><span class="ico">⚙️</span>Sistema</button>
  <button data-tab="tab-users" id="dock-users" style="display:none" onclick="showTab('tab-users', this)"><span class="ico">👤</span>Utenti</button>
</nav>
<div id="toast"></div>
<div id="modal" class="modal">
  <div class="modal-card">
    <h3 id="modal-title"></h3>
    <div id="modal-body" class="sub"></div>
    <input id="modal-input" style="display:none;width:100%;margin-top:10px">
    <div class="row" style="justify-content:flex-end;margin-top:16px">
      <button onclick="modalCancel()">Annulla</button>
      <button class="ok" id="modal-ok" onclick="modalConfirm()">Conferma</button>
    </div>
  </div>
</div>

<script>
const TOKEN_KEY = 'devicehub_token';
let devices = [];
let map = null;
let markers = {};
let track = null;
let geofences = [];
let geofenceLayer = null;
let geofenceDraftLayer = null;
let geofenceDraft = [];
let geofenceDrawing = false;
let playback = {
  active: false, imei: null, date: null, points: [], stats: null,
  stops: [], playing: false, progress: 0, speed: 1, raf: 0,
  lastFrame: 0, request: 0, layers: null, marker: null,
  line: null, casing: null
};
let selectedImei = null;
let followImei = null;
let currentUpdate = null;
let addressToken = 0;
const addressCache = {};
let mapAlertImeis = new Set();
let emergencyAlert = null;
let dismissedEmergencyAlert = null;
let charts = { speed: null, km: null };
let provisioningText = '';

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
  if (box.textContent === 'pronto.') box.textContent = '';
  box.appendChild(el('div', { class: kind || '', text: '[' + new Date().toLocaleTimeString('it-IT') + '] ' + message }));
  box.scrollTop = box.scrollHeight;
}

function saveToken() {
  const value = document.getElementById('token').value.trim();
  if (value) { localStorage.setItem(TOKEN_KEY, value); log('token salvato', 'okv'); }
  else { localStorage.removeItem(TOKEN_KEY); log('token rimosso'); }
  document.getElementById('token').value = '';
  refresh();
}

const QUEUE_KEY = 'dh_pending_ops';

function readQueue() {
  try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); }
  catch (error) { return []; }
}

function updateOfflineBanner() {
  const box = document.getElementById('offline-banner');
  if (!box) return;
  const pending = readQueue().length;
  box.style.display = (navigator.onLine && !pending) ? 'none' : 'block';
  box.textContent = navigator.onLine
    ? pending + ' operazioni in attesa di invio: sincronizzazione automatica'
    : 'Offline: le nuove inserzioni restano sul dispositivo e partiranno al ritorno della connessione';
}

function writeQueue(items) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(items));
  updateOfflineBanner();
}

async function flushQueue() {
  if (!navigator.onLine) { updateOfflineBanner(); return; }
  const items = readQueue();
  if (!items.length) return;
  const remaining = [];
  let sent = 0;
  for (const item of items) {
    try {
      const headers = { 'Content-Type': 'application/json' };
      const token = localStorage.getItem(TOKEN_KEY);
      if (token) headers['X-Api-Key'] = token;
      const response = await fetch(item.path, {
        method: item.method, headers: headers, body: item.body
      });
      if (response.ok) { sent += 1; }
      else { remaining.push(item); }
    } catch (error) { remaining.push(item); }
  }
  writeQueue(remaining);
  if (sent) {
    toast(sent + ' operazioni sincronizzate', 'okv');
    refresh();
  }
}

function enqueue(path, method, body) {
  const items = readQueue();
  items.push({ path: path, method: method, body: body, at: Date.now() });
  writeQueue(items);
}

async function api(path, options) {
  const opts = options || {};
  const headers = Object.assign({}, opts.headers || {});
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers['X-Api-Key'] = token;
  if (opts.body) headers['Content-Type'] = 'application/json';
  const method = (opts.method || 'GET').toUpperCase();
  const queueable = method !== 'GET' && typeof opts.body === 'string' &&
    !path.startsWith('/auth/');
  if (queueable && !navigator.onLine) {
    enqueue(path, method, opts.body);
    return {
      ok: true, status: 202,
      json: async function () { return { status: 'queued' }; }
    };
  }
  const response = await fetch(path, Object.assign({}, opts, { headers: headers }));
  if (response.status === 401) {
    const error = new Error('sessione scaduta');
    error.status = 401;
    if (!window.__loginRedirect) {
      window.__loginRedirect = true;
      const next = window.location.pathname + window.location.search;
      window.location.href = '/login?next=' + encodeURIComponent(next);
    }
    throw error;
  }
  if (!response.ok) {
    let detail = 'HTTP ' + response.status;
    try { const body = await response.json(); if (body.detail) detail = body.detail; } catch (e) {}
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response;
}

function showTab(id, button) {
  document.querySelectorAll('.tab').forEach(function (tab) { tab.classList.remove('active'); });
  document.querySelectorAll('.dock button, .side-nav button').forEach(function (item) { item.classList.remove('active'); });
  document.getElementById(id).classList.add('active');
  if (button) {
    button.classList.add('active');
    if (button.offsetParent !== null) {
      button.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
    }
  }
  const sideButton = document.querySelector('.side-nav [data-tab="' + id + '"]');
  if (sideButton) sideButton.classList.add('active');
  const sideBox = document.getElementById('side-results');
  if (sideBox) { sideBox.classList.remove('open'); }
  toggleSidebar(false);
  document.body.classList.toggle('map-mode', id === 'tab-map');
  if (id === 'tab-map') {
    ensureMap(); fillActivityDevices(); renderMapPanels(); loadMapAlerts(); loadGeofences();
    setTimeout(function () { if (map) map.invalidateSize(); }, 180);
    if (solutionConfig && solutionConfig.maps === 'google' &&
        typeof devices !== 'undefined' && devices.length) {
      openGoogleMap();
    }
  }
  if (id === 'tab-fleet') { loadFuel(); }
  if (id === 'tab-soc') { loadAlerts(); loadAudit(); loadNotificationOutbox(); loadGeofences(); loadAlertRules(); loadWorkHours(); }
  if (id === 'tab-maintenance') { loadMaintenance(); }
  if (id === 'tab-safety') { loadSafety(); }
  if (id === 'tab-guida') { loadDriving(); }
  if (id === 'tab-soluzioni') { loadSolution(); }
  if (id === 'tab-esg') { loadEsg(); loadSnapshots(); loadKeys(); }
  if (id === 'tab-branding') { loadBranding(); loadNotificationSettings(); }
  if (id === 'tab-system') { loadUpdates(); }
  if (id === 'tab-users') { loadUsers(); loadAdminActions(); loadLinkBlocks(); }
}

function renderSideResults(term) {
  const box = document.getElementById('side-results');
  if (!box) return;
  const query = String(term || '').trim().toLowerCase();
  box.textContent = '';
  if (!query) { box.classList.remove('open'); return; }
  const matches = devices.filter(function (device) {
    return [device.plate, device.model, device.imei]
      .join(' ').toLowerCase().indexOf(query) >= 0;
  }).slice(0, 7);
  if (!matches.length) {
    box.appendChild(el('div', { class: 'side-empty', text: 'Nessun dispositivo trovato.' }));
  }
  matches.forEach(function (device) {
    const button = el('button', { type: 'button' }, [
      el('span', { text: vehicleLabel(device) }),
      el('small', { text: device.imei + (device.connected ? ' \\u00b7 online' : ' \\u00b7 offline') })
    ]);
    button.addEventListener('click', function () { sideSearchPick(device.imei); });
    box.appendChild(button);
  });
  box.classList.add('open');
}

function sideSearchKey(event) {
  if (event.key === 'Escape') {
    event.target.value = '';
    const box = document.getElementById('side-results');
    if (box) box.classList.remove('open');
    return;
  }
  if (event.key !== 'Enter') return;
  const first = document.querySelector('#side-results button');
  if (first) first.click();
}

function sideSearchPick(imei) {
  showTab('tab-map', document.querySelector('.dock [data-tab="tab-map"]'));
  selectVehicle(imei);
  const sideInput = document.getElementById('side-search');
  if (sideInput) sideInput.value = '';
  const sideBox = document.getElementById('side-results');
  if (sideBox) { sideBox.classList.remove('open'); sideBox.textContent = ''; }
  const mapInput = document.getElementById('map-search');
  if (mapInput) mapInput.value = '';
  renderDeviceSidebar();
}

__THEME_JS__
function initGlassProximity() {
  if (!window.matchMedia || !window.matchMedia('(pointer:fine)').matches) return;
  let frame = 0;
  let pointerX = 0;
  let pointerY = 0;
  document.addEventListener('pointermove', function (event) {
    pointerX = event.clientX;
    pointerY = event.clientY;
    if (frame) return;
    frame = requestAnimationFrame(function () {
      frame = 0;
      document.querySelectorAll('.map-shell .map-glass').forEach(function (panel) {
        const rect = panel.getBoundingClientRect();
        const dx = Math.max(rect.left - pointerX, 0, pointerX - rect.right);
        const dy = Math.max(rect.top - pointerY, 0, pointerY - rect.bottom);
        panel.classList.toggle('glass-dim', Math.hypot(dx, dy) > 120);
      });
    });
  }, { passive: true });
}

function toggleSidebar(force) {
  const side = document.getElementById('sidebar');
  if (!side) return;
  const open = typeof force === 'boolean' ? force : !side.classList.contains('open');
  side.classList.toggle('open', open);
  const scrim = document.getElementById('side-scrim');
  if (scrim) scrim.classList.toggle('open', open);
  document.body.classList.toggle('side-lock', open && window.innerWidth <= 1100);
}

function syncSidebar() {
  const fleetCount = document.getElementById('side-fleet-count');
  if (fleetCount) fleetCount.textContent = devices.length;
  const toggle = document.getElementById('side-engine');
  const note = document.getElementById('side-engine-note');
  if (!toggle || !note) return;
  const device = selectedImei
    ? devices.find(function (item) { return item.imei === selectedImei; })
    : null;
  toggle.disabled = !device;
  toggle.checked = !!(device && device.engine_blocked);
  note.textContent = device
    ? vehicleLabel(device) + (device.engine_blocked ? ' \\u00b7 bloccato' : '')
    : 'nessun mezzo selezionato';
  const privacy = document.getElementById('side-privacy');
  const privacyNote = document.getElementById('side-privacy-note');
  if (privacy && privacyNote) {
    privacy.disabled = !device || !canManageFleet();
    privacy.checked = !!(device && device.privacy_mode);
    privacyNote.textContent = device
      ? vehicleLabel(device) + (device.privacy_mode ? ' · coordinate oscurate' : '')
      : 'nessun mezzo selezionato';
  }
}

function sideEngineToggle(input) {
  if (!selectedImei) { input.checked = false; return; }
  engineBlock(selectedImei, input.checked, input);
}

async function sidePrivacyToggle(input) {
  if (!selectedImei) { input.checked = false; return; }
  const imei = selectedImei;
  const enabled = input.checked;
  const proceed = await askConfirm(
    enabled ? 'Attivare la modalità privacy?' : 'Disattivare la modalità privacy?',
    enabled
      ? 'Le posizioni vengono salvate senza coordinate; odometro e dati CAN restano registrati. Il pulsante SOS conserva la posizione nel record di allarme.'
      : 'Il mezzo torna a registrare le coordinate di ogni posizione.',
    enabled ? 'Attiva' : 'Disattiva'
  );
  if (!proceed) { input.checked = !enabled; return; }
  try {
    await api('/devices/' + encodeURIComponent(imei) + '/privacy?enabled=' + enabled,
      { method: 'POST' });
    toast(enabled ? 'Modalità privacy attiva' : 'Modalità privacy disattivata', 'okv');
    refresh();
  } catch (error) {
    input.checked = !enabled;
    toast('Privacy: ' + error.message, 'bad');
  }
}

function addBaseLayer() {
  const provider = solutionConfig && solutionConfig.maps;
  let url = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}';
  let attribution = 'Tiles © Esri — Esri, DeLorme, NAVTEQ';
  if (provider === 'swiss') {
    url = 'https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg';
    attribution = 'swisstopo';
  }
  L.tileLayer(url, { attribution: attribution, maxZoom: 16 }).addTo(map);
}

function ensureMap() {
  if (map) return;
  map = L.map('map', { zoomControl: false }).setView([42.5, 12.5], 6);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  map.on('click', function (event) {
    if (geofenceDrawing) {
      addGeofencePoint(event.latlng);
      return;
    }
    const pick = document.getElementById('g_click');
    if (!pick || !pick.checked) return;
    document.getElementById('g_lat').value = event.latlng.lat.toFixed(6);
    document.getElementById('g_lon').value = event.latlng.lng.toFixed(6);
    toast('Punto preso dalla mappa', 'okv');
  });
  addBaseLayer();
  renderGeofenceLayers();
}

function fmt(value, digits) {
  if (value === null || value === undefined) return '\\u2014';
  return Number(value).toFixed(digits === undefined ? 1 : digits);
}

function vehicleLabel(device) {
  return device.plate || device.model || device.imei;
}

function renderAll() {
  renderKpis();
  if (solutionConfig) renderHeavyPanel();
  renderFleet(document.getElementById('fleet-body'), true);
  renderFleet(document.getElementById('fleet-full-body'), false);
  fillActivityDevices();
  fillMaintenanceDevices();
  fillSafetyDevices();
  renderCensus();
  renderMapMarkers();
  renderMapPanels();
  renderCharts();
}

function renderKpis() {
  const online = devices.filter(function (d) { return d.connected; }).length;
  const moving = devices.filter(function (d) { return (d.speed || 0) > 1; }).length;
  const pending = devices.filter(function (d) { return d.status !== 'active'; }).length;
  const engines = devices.filter(function (d) { return Number(d.ignition) > 0; }).length;
  const blocks = devices.filter(function (d) { return d.engine_blocked; }).length;
  document.getElementById('kpi-fleet').textContent = devices.length;
  document.getElementById('kpi-online').textContent = online;
  document.getElementById('kpi-moving').textContent = moving;
  document.getElementById('kpi-pending').textContent = pending;
  document.getElementById('kpi-engines').textContent = engines;
  document.getElementById('kpi-blocks').textContent = blocks;
  syncSidebar();
}

function statusBadge(device) {
  if (device.status !== 'active') return el('span', { class: 'badge warn', text: 'da abilitare' });
  return el('span', { class: 'badge on', text: 'abilitato' });
}

function linkBadge(device) {
  return el('span', { class: 'badge ' + (device.connected ? 'on' : 'off'),
                      text: device.connected ? 'online' : 'offline' });
}

function actionButtons(device, compact) {
  const wrap = el('div', { class: 'row' });
  const blocked = !!device.engine_blocked;
  wrap.appendChild(el('span', {
    class: 'badge ' + (blocked ? 'warn' : 'on'),
    text: blocked ? 'motore bloccato' : 'motore libero'
  }));
  if (blocked) {
    wrap.appendChild(el('button', {
      class: 'ok tiny', text: 'Sblocca',
      onclick: function () { engineBlock(device.imei, false, null, this); }
    }));
  } else {
    wrap.appendChild(el('button', {
      class: 'danger tiny', text: 'Blocca',
      onclick: function () { engineBlock(device.imei, true, null, this); }
    }));
  }
  wrap.appendChild(el('button', {
    class: 'tiny', text: 'Replay',
    onclick: function () { replay(device.imei); }
  }));
  if (canManageFleet()) {
    wrap.appendChild(el('button', {
      class: 'tiny', text: 'Modifica',
      onclick: function () { editDevice(device.imei); }
    }));
    wrap.appendChild(el('button', {
      class: 'danger tiny', text: 'Elimina',
      onclick: function () { deleteDevice(device.imei); }
    }));
  }
  if (!compact) {
    wrap.appendChild(el('button', {
      class: 'tiny', text: 'SMS',
      onclick: function () {
        document.getElementById('p_imei').value = device.imei;
        loadProvisioning();
        showTab('tab-census', document.querySelector('[data-tab="tab-census"]'));
      }
    }));
  }
  return wrap;
}

function showSkeleton() {
  const tbody = document.getElementById('fleet-body');
  if (tbody && !tbody.children.length) {
    for (let i = 0; i < 3; i += 1) {
      tbody.appendChild(el('tr', {}, [el('td', { colspan: '10' }, [
        el('div', { class: 'skeleton-glass', style: 'height:16px' })
      ])]));
    }
  }
  const list = document.getElementById('device-list');
  if (list && !list.children.length) {
    for (let j = 0; j < 3; j += 1) {
      list.appendChild(el('div', { class: 'skeleton-glass', style: 'height:44px;margin-bottom:6px' }));
    }
  }
}

function renderFleet(tbody, compact) {
  if (!tbody) return;
  tbody.textContent = '';
  if (!devices.length) {
    tbody.appendChild(el('tr', {}, [el('td', { colspan: compact ? '10' : '8', class: 'empty',
      text: 'Nessun dispositivo: collega un tracker o avvia il simulatore.' })]));
    return;
  }
  devices.forEach(function (device) {
    const cells = [
      el('td', {}, [el('strong', { text: vehicleLabel(device) })]),
      el('td', {}, [el('code', { text: device.imei })]),
      el('td', {}, [statusBadge(device)]),
      el('td', {}, [linkBadge(device)]),
      el('td', { text: device.speed === null || device.speed === undefined ? '\\u2014' : fmt(device.speed, 0) + ' km/h' })
    ];
    if (compact) {
      const fuel = device.can_fuel_liters === null || device.can_fuel_liters === undefined ? null : fmt(device.can_fuel_liters) + ' L';
      const fuelPct = device.can_fuel_pct === null || device.can_fuel_pct === undefined ? null : fmt(device.can_fuel_pct, 0) + '%';
      cells.push(el('td', { text: fuel === null && fuelPct === null ? '\u2014' : [fuel, fuelPct].filter(Boolean).join(' \u00b7 ') }));
      cells.push(el('td', { text: device.engine_temp === null || device.engine_temp === undefined ? '\\u2014' : fmt(device.engine_temp) + ' \\u00b0C' }));
      cells.push(el('td', { text: device.can_rpm === null || device.can_rpm === undefined ? '\\u2014' : fmt(device.can_rpm, 0) }));
      cells.push(el('td', { text: device.odometer_m === null || device.odometer_m === undefined ? '\\u2014' : fmt(device.odometer_m / 1000) + ' km' }));
    } else {
      cells.push(el('td', { text: device.ignition === null || device.ignition === undefined ? '\\u2014' : (device.ignition ? 'acceso' : 'spento') }));
      cells.push(el('td', { text: device.odometer_m === null || device.odometer_m === undefined ? '\\u2014' : fmt(device.odometer_m / 1000) + ' km' }));
    }
    cells.push(el('td', {}, [actionButtons(device, compact)]));
    tbody.appendChild(el('tr', {}, cells));
  });
}

function canManageFleet() {
  return !!currentUser && (currentUser.role === 'admin' || currentUser.role === 'manager');
}

async function editDevice(imei) {
  const device = devices.find(function (item) { return item.imei === imei; });
  if (!device) return;
  const plate = await askText('Modifica mezzo', 'Targa del mezzo (vuoto = nessuna)',
    device.plate || '', 'Avanti');
  if (plate === null) return;
  const model = await askText('Modifica mezzo', 'Modello del dispositivo',
    device.model || '', 'Salva');
  if (model === null) return;
  try {
    await api('/devices/' + encodeURIComponent(imei), {
      method: 'PATCH',
      body: JSON.stringify({ plate: plate, model: model })
    });
    toast('Mezzo aggiornato', 'okv');
    refresh();
  } catch (error) {
    if (error.status === 401) return;
    toast('Modifica mezzo: ' + error.message, 'bad');
  }
}

async function deleteDevice(imei) {
  const device = devices.find(function (item) { return item.imei === imei; });
  const label = device ? vehicleLabel(device) : imei;
  const proceed = await askConfirm(
    'Eliminare il mezzo?',
    label + ' (' + imei + '). Elimina definitivamente il record e i dati collegati: ' +
    'storico posizioni, allarmi, comandi, manutenzione, controlli di sicurezza e notifiche. ' +
    'L\u2019operazione non si pu\u00f2 annullare. Se il tracker \u00e8 ancora online, al prossimo ' +
    'invio il mezzo ricompare come "da abilitare".',
    'Elimina'
  );
  if (!proceed) return;
  try {
    await api('/devices/' + encodeURIComponent(imei), { method: 'DELETE' });
    if (selectedImei === imei) {
      selectedImei = null;
      document.getElementById('vd-plate').textContent = '\u2014';
      document.getElementById('vd-model').textContent = 'Seleziona un mezzo';
      const manage = document.getElementById('vd-manage');
      if (manage) manage.style.display = 'none';
    }
    if (followImei === imei) followImei = null;
    toast('Mezzo eliminato', 'okv');
    refresh();
  } catch (error) {
    if (error.status === 401) return;
    toast('Eliminazione: ' + error.message, 'bad');
  }
}

function renderCensus() {
  const tbody = document.getElementById('census-body');
  if (!tbody) return;
  tbody.textContent = '';
  if (!devices.length) {
    tbody.appendChild(el('tr', {}, [el('td', { colspan: '7', class: 'empty',
      text: 'Nessun IMEI ricevuto.' })]));
    return;
  }
  devices.forEach(function (device) {
    const actions = el('div', { class: 'row' });
    if (device.status !== 'active') {
      actions.appendChild(el('button', { class: 'ok tiny', text: 'Abilita',
        onclick: function () { activate(device.imei); } }));
    }
    actions.appendChild(el('button', { class: 'tiny', text: 'SMS',
      onclick: function () {
        document.getElementById('p_imei').value = device.imei;
        loadProvisioning();
      } }));
    tbody.appendChild(el('tr', {}, [
      el('td', {}, [el('code', { text: device.imei })]),
      el('td', {}, [statusBadge(device)]),
      el('td', { text: device.model || '\\u2014' }),
      el('td', { text: device.plate || '\\u2014' }),
      el('td', { class: 'muted', text: device.first_seen ? String(device.first_seen).replace('T', ' ') : '\\u2014' }),
      el('td', { class: 'muted', text: device.last_seen ? String(device.last_seen).replace('T', ' ') : '\\u2014' }),
      el('td', {}, [actions])
    ]));
  });
}

function hasCoordinates(lat, lon) {
  return lat !== null && lat !== undefined && lon !== null && lon !== undefined &&
    Number.isFinite(Number(lat)) && Number.isFinite(Number(lon));
}

function streetViewUrl(lat, lon) {
  return 'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=' +
    encodeURIComponent(lat) + ',' + encodeURIComponent(lon);
}

function openStreetView(lat, lon) {
  if (!hasCoordinates(lat, lon)) {
    toast('Posizione non disponibile o oscurata dalla modalità privacy', 'bad');
    return false;
  }
  window.open(streetViewUrl(lat, lon), '_blank', 'noopener');
  return true;
}

function openSelectedStreetView() {
  const device = devices.find(function (item) { return item.imei === selectedImei; });
  if (device) openStreetView(device.latitude, device.longitude);
}

function updateEmergencyHud(alerts) {
  const hud = document.getElementById('emergency-hud');
  if (!hud) return;
  const critical = (alerts || []).filter(function (alert) {
    if (alert.acknowledged_at) return false;
    const severity = String(alert.severity || '').toUpperCase();
    return severity === 'CRITICAL' || alert.kind === 'SOS' || alert.kind === 'THEFT';
  })[0];
  if (!critical) {
    emergencyAlert = null;
    dismissedEmergencyAlert = null;
    hud.hidden = true;
    return;
  }
  if (dismissedEmergencyAlert === critical.id) { hud.hidden = true; return; }
  emergencyAlert = critical;
  const device = devices.find(function (item) { return item.imei === critical.imei; });
  document.getElementById('eh-vehicle').textContent =
    device ? vehicleLabel(device) : (critical.plate || critical.imei || 'Mezzo');
  document.getElementById('eh-detail').textContent =
    (critical.kind || 'ALLARME') + ' · ' + (critical.detail || 'nessun dettaglio') +
    (critical.created_at ? ' · ' + String(critical.created_at).replace('T', ' ').slice(0, 16) : '');
  const street = document.getElementById('eh-street');
  if (street) {
    const lat = hasCoordinates(critical.latitude, critical.longitude)
      ? critical.latitude : (device ? device.latitude : null);
    const lon = hasCoordinates(critical.latitude, critical.longitude)
      ? critical.longitude : (device ? device.longitude : null);
    street.disabled = !hasCoordinates(lat, lon);
    street.title = street.disabled ? 'Coordinate non disponibili' : 'Apri Google Street View';
  }
  hud.hidden = false;
}

function dismissEmergencyHud() {
  if (emergencyAlert) dismissedEmergencyAlert = emergencyAlert.id;
  const hud = document.getElementById('emergency-hud');
  if (hud) hud.hidden = true;
}

function emergencyBlock() {
  if (emergencyAlert) engineBlock(emergencyAlert.imei, true);
}

function emergencyStreetView() {
  if (!emergencyAlert) return;
  const device = devices.find(function (item) { return item.imei === emergencyAlert.imei; });
  const lat = hasCoordinates(emergencyAlert.latitude, emergencyAlert.longitude)
    ? emergencyAlert.latitude : (device ? device.latitude : null);
  const lon = hasCoordinates(emergencyAlert.latitude, emergencyAlert.longitude)
    ? emergencyAlert.longitude : (device ? device.longitude : null);
  openStreetView(lat, lon);
}

function emergencyTrack() {
  if (!emergencyAlert) return;
  const imei = emergencyAlert.imei;
  showTab('tab-map', document.querySelector('.dock [data-tab="tab-map"]'));
  selectVehicle(imei);
  setTimeout(function () { selectVehicle(imei); replaySelected(); }, 220);
}

function mapPopup(device) {
  const lat = device.latitude;
  const lon = device.longitude;
  const head = '<b>' + vehicleLabel(device) + '</b><br>IMEI: ' + device.imei;
  if (!hasCoordinates(lat, lon)) {
    return head + '<br><span class="muted">Posizione non disponibile (privacy)</span>';
  }
  return head + '<br>' +
    '<a href="https://www.google.com/maps?q=' + encodeURIComponent(lat) + ',' +
    encodeURIComponent(lon) + '" target="_blank" rel="noopener">Google Maps 3D</a> · ' +
    '<a href="' + streetViewUrl(lat, lon) +
    '" target="_blank" rel="noopener">Street View</a>';
}

const STATUS_COLORS = {
  moving: '#34D399', stopped: '#FBBF24', alarm: '#FB7185', offline: '#64748B'
};

function deviceStatus(device) {
  if (!device.connected) return { key: 'offline', label: 'Offline' };
  if (mapAlertImeis.has(String(device.imei))) return { key: 'alarm', label: 'Allarme' };
  if ((device.speed || 0) > 1) return { key: 'moving', label: 'In movimento' };
  return { key: 'stopped', label: 'Fermo' };
}

function markerHtml(device, status) {
  const heading = Number(device.angle || 0);
  const color = STATUS_COLORS[status.key];
  return '<div class="gps-marker' + (device.imei === selectedImei ? ' selected' : '') +
    '" style="--state:' + color + '">' +
    '<span class="gps-ping"></span>' +
    '<svg class="gps-arrow" viewBox="0 0 24 24" aria-hidden="true" ' +
    'style="transform:rotate(' + heading + 'deg)">' +
    '<path d="M12 3 L19 20 L12 16.2 L5 20 Z"/></svg></div>';
}

function markerIcon(device, status) {
  return L.divIcon({
    className: 'gps-marker-host', html: markerHtml(device, status),
    iconSize: [38, 38], iconAnchor: [19, 19], popupAnchor: [0, -18]
  });
}

function updateMarkerSelection() {
  Object.keys(markers).forEach(function (imei) {
    const node = markers[imei].getElement();
    if (!node) return;
    const shell = node.querySelector('.gps-marker');
    if (shell) shell.classList.toggle('selected', imei === selectedImei);
  });
}

function renderMapMarkers() {
  if (!map || playback.active) return;
  devices.forEach(function (device) {
    if (device.latitude === null || device.latitude === undefined) return;
    const point = [device.latitude, device.longitude];
    const status = deviceStatus(device);
    const color = STATUS_COLORS[status.key];
    const heading = Number(device.angle || 0);
    let marker = markers[device.imei];
    if (!marker) {
      marker = L.marker(point, {
        icon: markerIcon(device, status), riseOnHover: true,
        title: vehicleLabel(device)
      }).addTo(map).bindPopup(mapPopup(device));
      marker._statusKey = status.key;
      marker.on('click', function () { selectVehicle(device.imei); });
      markers[device.imei] = marker;
    } else {
      marker.setLatLng(point).setPopupContent(mapPopup(device));
      if (marker._statusKey !== status.key) {
        marker.setIcon(markerIcon(device, status));
        marker._statusKey = status.key;
      }
      const node = marker.getElement();
      const arrow = node && node.querySelector('.gps-arrow');
      if (arrow) arrow.style.transform = 'rotate(' + heading + 'deg)';
      const shell = node && node.querySelector('.gps-marker');
      if (shell) shell.style.setProperty('--state', color);
    }
  });
  updateMarkerSelection();
  if (followImei) {
    const followed = devices.find(function (d) { return d.imei === followImei; });
    if (followed && followed.latitude !== null && followed.latitude !== undefined) {
      map.panTo([followed.latitude, followed.longitude], { animate: true, duration: .7 });
    }
  }
  if (devices.length && !map.trackFitted) {
    const points = devices.filter(function (d) { return d.latitude !== null && d.latitude !== undefined; })
                          .map(function (d) { return [d.latitude, d.longitude]; });
    if (points.length) { map.fitBounds(points, { padding: [40, 40], maxZoom: 15 }); map.trackFitted = true; }
  }
}

function updateFollowButton(device) {
  const button = document.getElementById('vd-follow');
  if (!button) return;
  const active = followImei === device.imei;
  button.classList.toggle('active', active);
  button.setAttribute('aria-pressed', active ? 'true' : 'false');
  button.textContent = active ? 'Segui attivo' : 'Segui sulla mappa';
}

function toggleFollow() {
  const device = devices.find(function (item) { return item.imei === selectedImei; });
  if (!device) return;
  followImei = followImei === device.imei ? null : device.imei;
  updateFollowButton(device);
  if (followImei && device.latitude !== null && device.latitude !== undefined) {
    ensureMap();
    map.flyTo([device.latitude, device.longitude], Math.max(map.getZoom(), 16), { duration: .8 });
  }
  toast(followImei ? 'Mappa agganciata al veicolo' : 'Segui disattivato', followImei ? 'okv' : '');
}

function loadVehicleAddress(device) {
  const box = document.getElementById('vd-address');
  if (!box) return;
  if (device.latitude === null || device.latitude === undefined) {
    box.textContent = 'Posizione non disponibile';
    return;
  }
  const fallback = Number(device.latitude).toFixed(5) + ', ' + Number(device.longitude).toFixed(5);
  box.textContent = fallback;
  const key = Number(device.latitude).toFixed(4) + ',' + Number(device.longitude).toFixed(4);
  if (addressCache[key]) { box.textContent = addressCache[key]; return; }
  const token = ++addressToken;
  fetch('https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18&addressdetails=1&accept-language=it' +
        '&lat=' + encodeURIComponent(device.latitude) + '&lon=' + encodeURIComponent(device.longitude),
        { headers: { 'Accept': 'application/json' } })
    .then(function (response) { return response.ok ? response.json() : null; })
    .then(function (data) {
      if (token !== addressToken || selectedImei !== device.imei) return;
      if (data && data.display_name) {
        addressCache[key] = data.display_name;
        box.textContent = data.display_name;
      }
    })
    .catch(function () { /* resta il fallback con le coordinate */ });
}

function renderVehicleCard() {
  const device = devices.find(function (item) { return item.imei === selectedImei; });
  if (!device) return;
  const status = deviceStatus(device);
  document.getElementById('vd-plate').textContent = vehicleLabel(device);
  document.getElementById('vd-model').textContent = (device.model || 'Tracker') + ' · ' + device.imei +
    (device.privacy_mode ? ' · privacy attiva' : '');
  const pill = document.getElementById('vd-status');
  pill.textContent = status.label;
  pill.className = 'status-pill ' + status.key;
  document.getElementById('vd-speed').textContent = Math.round(device.speed || 0) + ' km/h';
  const battery = device.battery_voltage;
  document.getElementById('vd-battery').textContent =
    battery !== null && battery !== undefined && battery !== ''
      ? Number(battery).toFixed(1).replace('.', ',') + ' V' : '—';
  let signal = '—';
  if (device.ts_ms) {
    signal = new Date(device.ts_ms).toLocaleString('it-IT', {
      day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
    });
  } else if (device.last_seen) {
    signal = String(device.last_seen).replace('T', ' ').slice(0, 16);
  }
  document.getElementById('vd-signal').textContent = signal;
  const manage = document.getElementById('vd-manage');
  if (manage) manage.style.display = canManageFleet() ? '' : 'none';
  updateFollowButton(device);
  loadVehicleAddress(device);
  const street = document.getElementById('vd-street');
  if (street) {
    const available = hasCoordinates(device.latitude, device.longitude);
    street.disabled = !available;
    street.textContent = available ? 'Street View' : 'Posizione protetta';
    street.title = available
      ? 'Apri Google Street View'
      : 'Coordinate non disponibili o oscurate dalla modalità privacy';
  }
}

function editSelectedDevice() {
  if (selectedImei) editDevice(selectedImei);
}

function deleteSelectedDevice() {
  if (selectedImei) deleteDevice(selectedImei);
}

function renderDeviceSidebar() {
  const list = document.getElementById('device-list');
  if (!list) return;
  const query = (document.getElementById('map-search').value || '')
    .toLowerCase().trim();
  const filtered = devices.filter(function (device) {
    if (playback.active && device.imei !== playback.imei) return false;
    return !query || [device.plate, device.model, device.imei, device.driver_name]
      .join(' ').toLowerCase().indexOf(query) !== -1;
  });
  list.innerHTML = '';
  filtered.forEach(function (device) {
    const status = deviceStatus(device);
    const item = el('button', {
      class: 'device-item' + (device.imei === selectedImei ? ' selected' : ''),
      onclick: function () { selectVehicle(device.imei); }
    }, [
      el('span', { class: 'status-dot ' + status.key, title: status.label }),
      el('span', { class: 'device-main' }, [
        el('strong', { text: vehicleLabel(device) }),
        el('small', { text: device.imei })
      ]),
      el('span', { class: 'status-text ' + status.key, text: status.label })
    ]);
    list.appendChild(item);
  });
  if (!filtered.length) {
    list.appendChild(el('div', { class: 'map-empty', text: 'Nessun dispositivo trovato' }));
  }
  const count = document.getElementById('map-device-count');
  if (count) count.textContent = filtered.length + ' / ' + devices.length;
  const sub = document.getElementById('map-side-sub');
  if (sub) sub.textContent = devices.filter(function (d) { return d.connected; }).length + ' online';
}

function renderMapPanels() {
  if (!devices.length) return;
  if (!selectedImei || !devices.some(function (d) { return d.imei === selectedImei; })) {
    selectedImei = devices[0].imei;
  }
  renderDeviceSidebar();
  renderVehicleCard();
}

async function loadMapAlerts() {
  try {
    const data = await (await api('/alerts?open_only=true&limit=100')).json();
    mapAlertImeis = new Set((data.alerts || []).map(function (alert) {
      return String(alert.imei || alert.device_imei || alert.device_id || '');
    }));
    updateEmergencyHud(data.alerts || []);
    renderMapMarkers();
    renderMapPanels();
  } catch (error) { /* gli stati restano quelli della telemetria */ }
}

function selectVehicle(imei) {
  selectedImei = imei;
  renderDeviceSidebar();
  renderVehicleCard();
  updateMarkerSelection();
  const device = devices.find(function (item) { return item.imei === imei; });
  const exportInput = document.getElementById('export-imei');
  if (exportInput) exportInput.value = imei;
  const activity = document.getElementById('activity-imei');
  if (activity && device) activity.value = imei;
  syncSidebar();
  if (map && device && device.latitude !== null && device.latitude !== undefined &&
      device.longitude !== null && device.longitude !== undefined &&
      Number.isFinite(Number(device.latitude)) && Number.isFinite(Number(device.longitude))) {
    const fly = function () {
      if (map) map.flyTo([device.latitude, device.longitude], Math.max(map.getZoom(), 15), {
        duration: .7
      });
    };
    if (map.getSize().x > 0) fly();
    else setTimeout(function () { if (map) { map.invalidateSize(); fly(); } }, 250);
  }
}

function centerSelected() {
  const device = devices.find(function (item) { return item.imei === selectedImei; });
  if (!device || device.latitude === null || device.latitude === undefined) return;
  ensureMap();
  map.flyTo([device.latitude, device.longitude], 16, { duration: .7 });
}

function replaySelected() {
  if (selectedImei) replay(selectedImei);
}

// I grafici leggono i token del tema: serie, tacche e griglia seguono
// l'accento attivo (Laser Lemon di notte, Forest Code di giorno).
function cssToken(name, fallback) {
  const value = getComputedStyle(document.body).getPropertyValue(name).trim();
  return value || fallback;
}

function accentRgba(alpha) {
  const hex = cssToken('--accent', '#B4501A').replace('#', '');
  const full = hex.length === 3
    ? hex.split('').map(function (part) { return part + part; }).join('')
    : hex;
  const value = parseInt(full, 16);
  return 'rgba(' + ((value >> 16) & 255) + ',' + ((value >> 8) & 255) + ',' + (value & 255) + ',' + alpha + ')';
}

function chartTheme() {
  return {
    accent: cssToken('--accent', '#B4501A'),
    fill: accentRgba(.72),
    faint: accentRgba(.12),
    tick: cssToken('--muted', 'rgba(16,52,42,.66)'),
    grid: cssToken('--line', 'rgba(120,72,40,.16)')
  };
}

function chartScales(theme, maxTicks) {
  const ticks = { color: theme.tick };
  if (maxTicks) ticks.maxTicksLimit = maxTicks;
  const grid = { color: theme.grid };
  return { x: { ticks: ticks, grid: grid }, y: { ticks: { color: theme.tick }, grid: grid } };
}

// Richiamata dall'evento dh:theme: un solo giro di update per tutti i grafici.
function rethemeCharts() {
  if (typeof Chart === 'undefined') return;
  const theme = chartTheme();
  if (charts.km) {
    charts.km.data.datasets[0].backgroundColor = theme.fill;
    charts.km.options.scales = chartScales(theme);
    charts.km.update();
  }
  if (charts.speed) {
    const dataset = charts.speed.data.datasets[0];
    dataset.borderColor = theme.accent;
    dataset.backgroundColor = theme.faint;
    dataset.pointBackgroundColor = theme.accent;
    charts.speed.options.plugins.legend.labels.color = theme.tick;
    charts.speed.options.scales = chartScales(theme, 6);
    charts.speed.update();
  }
  if (esgChart) {
    esgChart.data.datasets[0].backgroundColor = theme.fill;
    esgChart.data.datasets[0].hoverBackgroundColor = theme.accent;
    esgChart.options.plugins.legend.labels.color = theme.tick;
    esgChart.options.scales = chartScales(theme, 10);
    esgChart.update();
  }
}

document.addEventListener('dh:theme', rethemeCharts);

async function renderCharts() {
  if (typeof Chart === 'undefined') return;
  const theme = chartTheme();
  const kmData = devices.map(function (d) { return d.odometer_m ? d.odometer_m / 1000 : 0; });
  const kmLabels = devices.map(vehicleLabel);

  if (!charts.km) {
    charts.km = new Chart(document.getElementById('kmChart'), {
      type: 'bar',
      data: { labels: kmLabels, datasets: [{ label: 'km', data: kmData,
        backgroundColor: theme.fill, hoverBackgroundColor: theme.accent, borderRadius: 8 }] },
      options: { plugins: { legend: { display: false } },
        scales: chartScales(theme) }
    });
  } else {
    charts.km.data.labels = kmLabels;
    charts.km.data.datasets[0].data = kmData;
    charts.km.update();
  }

  if (!devices.length) return;
  try {
    const response = await api('/positions/' + encodeURIComponent(devices[0].imei) + '?limit=24');
    const payload = await response.json();
    const rows = payload.positions.slice().reverse();
    const values = rows.map(function (row) { return row.speed || 0; });
    const labels = rows.map(function (row) { return new Date(row.ts_ms).toLocaleTimeString('it-IT'); });
    if (!charts.speed) {
      charts.speed = new Chart(document.getElementById('speedChart'), {
        type: 'line',
        data: { labels: labels, datasets: [{ label: vehicleLabel(devices[0]), data: values,
          borderColor: theme.accent, backgroundColor: theme.faint,
          pointBackgroundColor: theme.accent, fill: true, tension: .35 }] },
        options: { plugins: { legend: { labels: { color: theme.tick } } },
          scales: chartScales(theme, 6) }
      });
    } else {
      charts.speed.data.labels = labels;
      charts.speed.data.datasets[0].data = values;
      charts.speed.data.datasets[0].label = vehicleLabel(devices[0]);
      charts.speed.update();
    }
  } catch (error) {
    log('grafico velocita: ' + error.message, 'err');
  }
}

async function refresh() {
  try {
    const response = await api('/devices');
    const payload = await response.json();
    devices = payload.devices;
    renderAll();
    renderVerticalDashboard();
  } catch (error) {
    log('lettura dispositivi: ' + error.message, 'err');
  }
  try {
    const alerts = await (await api('/alerts?open_only=true&limit=100')).json();
    const open = (alerts.alerts || []).length;
    const kpiAlerts = document.getElementById('kpi-alerts');
    if (kpiAlerts) {
      kpiAlerts.textContent = open;
      const alertCard = kpiAlerts.closest('.kpi');
      if (alertCard) alertCard.classList.toggle('card-alert-active', open > 0);
    }
    const sideSoc = document.getElementById('side-soc-count');
    if (sideSoc) sideSoc.textContent = open;
    updateEmergencyHud(alerts.alerts || []);
  } catch (error) {
    log('lettura allarmi: ' + error.message, 'err');
  }
}

async function engineBlock(imei, block, input, button) {
  const proceed = await askConfirm(
    block ? 'Bloccare il motore?' : 'Sbloccare il motore?',
    'Mezzo ' + imei + '. Il blocco viene rifiutato se il veicolo risulta in movimento.',
    block ? 'Blocca' : 'Sblocca'
  );
  if (!proceed) {
    if (input) input.checked = !block;
    return;
  }
  try {
    const response = await api('/devices/' + encodeURIComponent(imei) +
      '/engine_block?block=' + block + '&requested_by=dashboard', { method: 'POST' });
    const data = await response.json();
    log((block ? 'BLOCCO ' : 'SBLOCCO ') + imei + ': ' + data.command + ' -> ' + data.device_response, 'okv');
    toast((block ? 'Motore bloccato. Risposta del device: ' : 'Motore sbloccato. Risposta del device: ') + data.device_response, 'okv');
    // Il pulsante mostra "✓ Completato" prima che il refresh ridisegni la riga.
    if (button) { triggerActionFeedback(button); setTimeout(refresh, 2000); }
    else { refresh(); }
  } catch (error) {
    if (input) input.checked = !block;
    log((block ? 'BLOCCO ' : 'SBLOCCO ') + imei + ': ' + error.message, 'err');
    toast((block ? 'Blocco' : 'Sblocco') + ' non riuscito: ' + error.message, 'bad');
  }
}

async function activate(imei) {
  const plate = await askText('Abilita dispositivo', 'Targa del mezzo per ' + imei, '', 'Avanti');
  if (plate === null) return;
  const model = await askText('Modello', 'Modello del dispositivo', 'FMC150', 'Abilita');
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

async function replay(imei) {
  await openHistory(imei, 'today');
}

function replaySelected() {
  if (selectedImei) openHistory(selectedImei, 'today');
}

function localDay(offset) {
  const value = new Date();
  value.setDate(value.getDate() + offset);
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return value.getFullYear() + '-' + month + '-' + day;
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return hours ? hours + 'h ' + minutes + 'm' : minutes + ' min';
}

function formatClock(ms) {
  return new Date(ms).toLocaleTimeString('it-IT', {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

function playbackIcon(angle) {
  return L.divIcon({
    className: 'gps-marker-host',
    html: '<div class="gps-marker selected" style="--state:#38BDF8">' +
      '<span class="gps-ping"></span>' +
      '<svg class="gps-arrow" viewBox="0 0 24 24" aria-hidden="true" ' +
      'style="transform:rotate(' + Number(angle || 0) + 'deg)">' +
      '<path d="M12 3 L19 20 L12 16.2 L5 20 Z"/></svg></div>',
    iconSize: [38, 38], iconAnchor: [19, 19]
  });
}

function setPlaybackButton() {
  const button = document.getElementById('pb-play');
  if (!button) return;
  button.textContent = playback.playing ? '❚❚' : '▶';
  button.setAttribute('aria-label', playback.playing ? 'Metti in pausa' : 'Avvia riproduzione');
}

function cancelPlaybackFrame() {
  if (playback.raf) cancelAnimationFrame(playback.raf);
  playback.raf = 0;
}

function markPlaybackDate(kind, date) {
  document.querySelectorAll('.playback-dates [data-range]').forEach(function (button) {
    button.classList.toggle('active', button.getAttribute('data-range') === kind);
  });
  const input = document.getElementById('pb-date');
  if (input) input.value = date;
}

function clearPlaybackLayers() {
  if (playback.layers && map) { map.removeLayer(playback.layers); }
  if (playback.marker && map) { map.removeLayer(playback.marker); }
  playback.layers = null;
  playback.marker = null;
  playback.line = null;
  playback.casing = null;
  if (track && map) { map.removeLayer(track); track = null; }
}

function hideLiveMarkers() {
  if (!map) return;
  Object.keys(markers).forEach(function (imei) {
    if (map.hasLayer(markers[imei])) map.removeLayer(markers[imei]);
  });
}

function restoreLiveMarkers() {
  if (!map) return;
  Object.keys(markers).forEach(function (imei) {
    if (!map.hasLayer(markers[imei])) markers[imei].addTo(map);
  });
}

// Inquadra il tragitto lasciando libero il pannello dello storico (250 px in
// basso). map.stop() annulla un flyTo ancora in corso, che altrimenti
// riprenderebbe il sopravvento; invalidateSize evita di calcolare lo zoom su
// una misura del contenitore non aggiornata dopo un cambio scheda.
function fitPlaybackRoute() {
  if (!playback.line || !map || !map.hasLayer(playback.line)) return;
  const bounds = playback.line.getBounds();
  if (!bounds.isValid()) return;
  map.stop();
  map.invalidateSize({ pan: false });
  // animate:false evita che una zoom-animation in corso (flyTo appena
  // interrotto) sovrascriva il fit appena impostato.
  map.fitBounds(bounds, {
    paddingTopLeft: [50, 50], paddingBottomRight: [50, 250], maxZoom: 15,
    animate: false
  });
}

function drawPlaybackRoute() {
  clearPlaybackLayers();
  const points = playback.points;
  if (!points.length || !map) return;
  const group = L.layerGroup().addTo(map);
  playback.layers = group;
  const latlngs = points.map(function (row) {
    return [Number(row.latitude), Number(row.longitude)];
  });

  if (latlngs.length >= 2) {
    // Doppia linea: il bordo chiaro sotto stacca il tracciato dai tile, la
    // linea in accento resta leggibile anche sui fondi più chiari.
    playback.casing = L.polyline(latlngs, {
      color: '#FFFFFF', weight: 6, opacity: 0.9,
      lineCap: 'round', lineJoin: 'round'
    }).addTo(group);
    playback.line = L.polyline(latlngs, {
      color: '#C85A17', weight: 4, opacity: 1.0,
      lineCap: 'round', lineJoin: 'round'
    }).addTo(group);
  }

  playback.stops.forEach(function (stop) {
    const dot = L.circleMarker([Number(stop.latitude), Number(stop.longitude)], {
      radius: 4.5, color: '#FBBF24', weight: 1.5,
      fillColor: '#FBBF24', fillOpacity: 1, className: 'history-stop'
    });
    dot.bindPopup('Sosta prolungata · ' + formatDuration(stop.duration_s));
    group.addLayer(dot);
  });

  const first = points[0];
  playback.marker = L.marker([Number(first.latitude), Number(first.longitude)], {
    icon: playbackIcon(Number(first.angle || 0)), zIndexOffset: 1000
  }).addTo(map);

  if (playback.line) {
    fitPlaybackRoute();
  } else {
    map.setView([Number(first.latitude), Number(first.longitude)], 15);
  }
}

function playbackPointAt(progress) {
  const points = playback.points;
  if (!points.length) return null;
  const firstMs = Number(points[0].ts_ms);
  const lastMs = Number(points[points.length - 1].ts_ms);
  const span = Math.max(1, lastMs - firstMs);
  const target = firstMs + Math.max(0, Math.min(1, progress)) * span;
  let low = 0, high = points.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (Number(points[middle].ts_ms) <= target) low = middle;
    else high = middle - 1;
  }
  const start = points[low];
  const end = points[Math.min(low + 1, points.length - 1)];
  const segment = Math.max(1, Number(end.ts_ms) - Number(start.ts_ms));
  const fraction = Math.max(0, Math.min(1, (target - Number(start.ts_ms)) / segment));
  const startAngle = Number(start.angle || 0);
  const endAngle = Number(end.angle || startAngle);
  let deltaAngle = ((endAngle - startAngle + 540) % 360) - 180;
  const startSpeed = Number(start.speed || 0);
  return {
    latitude: Number(start.latitude) + (Number(end.latitude) - Number(start.latitude)) * fraction,
    longitude: Number(start.longitude) + (Number(end.longitude) - Number(start.longitude)) * fraction,
    angle: startAngle + deltaAngle * fraction,
    speed: startSpeed + (Number(end.speed || 0) - startSpeed) * fraction,
    ts_ms: target
  };
}

function applyPlaybackProgress(progress) {
  if (!playback.active) return;
  playback.progress = Math.max(0, Math.min(1, progress));
  const point = playbackPointAt(playback.progress);
  if (!point) return;
  if (playback.marker) {
    playback.marker.setLatLng([point.latitude, point.longitude]);
    const node = playback.marker.getElement();
    const arrow = node && node.querySelector('.gps-arrow');
    if (arrow) arrow.style.transform = 'rotate(' + point.angle + 'deg)';
  }
  const clock = document.getElementById('pb-clock');
  if (clock) clock.textContent = formatClock(point.ts_ms);
  const speed = document.getElementById('pb-current-speed');
  if (speed) speed.textContent = Math.round(point.speed) + ' km/h';
  const slider = document.getElementById('pb-slider');
  if (slider) {
    slider.value = String(Math.round(playback.progress * 1000));
    slider.style.setProperty('--progress', (playback.progress * 100).toFixed(1) + '%');
  }
}

function playbackStep(now) {
  if (!playback.playing || !playback.active) return;
  const elapsed = Math.max(0, now - playback.lastFrame);
  playback.lastFrame = now;
  // 1x riproduce l'intero percorso in circa 30 secondi.
  const next = playback.progress + (elapsed / 30000) * playback.speed;
  if (next >= 1) {
    playback.progress = 1;
    playback.playing = false;
    setPlaybackButton();
    applyPlaybackProgress(1);
    return;
  }
  applyPlaybackProgress(next);
  playback.raf = requestAnimationFrame(playbackStep);
}

function togglePlayback() {
  if (!playback.active || !playback.points.length) return;
  if (playback.playing) {
    playback.playing = false;
    cancelPlaybackFrame();
    setPlaybackButton();
    return;
  }
  if (playback.progress >= .999) playback.progress = 0;
  playback.playing = true;
  playback.lastFrame = performance.now();
  setPlaybackButton();
  playback.raf = requestAnimationFrame(playbackStep);
}

function seekPlayback(value) {
  if (!playback.active) return;
  playback.playing = false;
  cancelPlaybackFrame();
  setPlaybackButton();
  applyPlaybackProgress(Number(value) / 1000);
}

function setPlaybackSpeed(value) {
  playback.speed = Number(value) || 1;
  document.querySelectorAll('.playback-speed [data-speed]').forEach(function (button) {
    button.classList.toggle('active', Number(button.getAttribute('data-speed')) === playback.speed);
  });
  playback.lastFrame = performance.now();
}

function updatePlaybackSummary(data) {
  const device = devices.find(function (item) { return item.imei === playback.imei; });
  const total = document.getElementById('pb-total-km');
  const duration = document.getElementById('pb-duration');
  const maximum = document.getElementById('pb-max-speed');
  if (total) total.textContent = Number(data.total_km || 0).toLocaleString('it-IT', {
    minimumFractionDigits: 1, maximumFractionDigits: 1
  }) + ' km';
  if (duration) duration.textContent = formatDuration(data.duration_s);
  if (maximum) maximum.textContent = Math.round(Number(data.max_speed_kmh || 0)) + ' km/h';
  const vehicle = document.getElementById('pb-vehicle');
  if (vehicle) vehicle.textContent = device ? vehicleLabel(device) : (playback.imei || '—');
  const points = document.getElementById('pb-points');
  if (points) points.textContent = data.raw_count
    ? data.raw_count + ' posizioni · ' + data.count + ' punti RDP'
    : 'Nessuna posizione per questa data';
}

async function loadHistoryDate(date) {
  if (!playback.active || !playback.imei) return;
  const request = ++playback.request;
  const imei = playback.imei;
  playback.date = date;
  playback.playing = false;
  playback.progress = 0;
  cancelPlaybackFrame();
  setPlaybackButton();
  clearPlaybackLayers();
  hideLiveMarkers();
  const panel = document.getElementById('playback-panel');
  if (panel) panel.hidden = false;
  document.body.classList.add('history-mode');
  document.getElementById('pb-date').value = date;
  document.getElementById('pb-points').textContent = 'Caricamento…';
  const play = document.getElementById('pb-play');
  if (play) play.disabled = true;
  try {
    const query = new URLSearchParams({
      date: date, tz_offset: String(new Date().getTimezoneOffset())
    });
    const response = await api('/positions/' + encodeURIComponent(imei) + '/history?' + query.toString());
    const data = await response.json();
    if (request !== playback.request || !playback.active || playback.imei !== imei) return;
    playback.points = (data.positions || []).filter(function (row) {
      return row.latitude !== null && row.latitude !== undefined &&
             row.longitude !== null && row.longitude !== undefined;
    });
    playback.stops = data.stops || [];
    playback.stats = data;
    updatePlaybackSummary(data);
    drawPlaybackRoute();
    if (playback.points.length) {
      applyPlaybackProgress(0);
    } else {
      document.getElementById('pb-clock').textContent = '--:--:--';
      document.getElementById('pb-current-speed').textContent = '0 km/h';
      const emptySlider = document.getElementById('pb-slider');
      if (emptySlider) {
        emptySlider.value = '0';
        emptySlider.style.setProperty('--progress', '0%');
        emptySlider.disabled = true;
      }
      setPlaybackButton();
    }
    if (play) play.disabled = !playback.points.length;
    const slider = document.getElementById('pb-slider');
    if (slider) slider.disabled = !playback.points.length;
    document.getElementById('map-hint').textContent = data.raw_count
      ? 'Storico ' + imei + ': ' + data.raw_count + ' posizioni, ' + data.count + ' punti dopo RDP'
      : 'Nessuna posizione per il giorno selezionato';
  } catch (error) {
    if (request !== playback.request || !playback.active) return;
    clearPlaybackLayers();
    playback.points = [];
    document.getElementById('pb-points').textContent = 'Errore: ' + error.message;
    toast('Storico ' + imei + ': ' + error.message, 'err');
  }
}

async function openHistory(imei, range) {
  if (!imei) return;
  ensureMap();
  // Lo storico prende il controllo della vista: niente fit automatico della
  // flotta al primo "Esci" e niente flyTo che vinca sul fit del percorso.
  map.trackFitted = true;
  map.stop();
  selectedImei = imei;
  playback.active = true;
  playback.imei = imei;
  playback.speed = 1;
  playback.progress = 0;
  playback.playing = false;
  document.querySelectorAll('.playback-speed [data-speed]').forEach(function (button) {
    button.classList.toggle('active', button.getAttribute('data-speed') === '1');
  });
  document.body.classList.add('history-mode');
  const panel = document.getElementById('playback-panel');
  if (panel) panel.hidden = false;
  const date = range === 'yesterday' ? localDay(-1)
    : (range && /^\\d{4}-\\d{2}-\\d{2}$/.test(range) ? range : localDay(0));
  const kind = range === 'yesterday' ? 'yesterday' : (range && /^\\d{4}/.test(range) ? 'custom' : 'today');
  markPlaybackDate(kind, date);
  showTab('tab-map', document.querySelector('[data-tab="tab-map"]'));
  renderVehicleCard();
  renderDeviceSidebar();
  updateMarkerSelection();
  await loadHistoryDate(date);
}

function setHistoryDate(kind, value) {
  if (!playback.active) return;
  const date = kind === 'today' ? localDay(0)
    : kind === 'yesterday' ? localDay(-1) : value;
  if (!date) return;
  markPlaybackDate(kind, date);
  loadHistoryDate(date);
}

function exitHistory() {
  playback.active = false;
  playback.playing = false;
  
  cancelPlaybackFrame();
  clearPlaybackLayers();
  playback.points = [];
  playback.stops = [];
  playback.progress = 0;
  document.body.classList.remove('history-mode');
  const panel = document.getElementById('playback-panel');
  if (panel) panel.hidden = true;
  renderMapMarkers();
  restoreLiveMarkers();
  renderDeviceSidebar();
  if (playback.imei) selectVehicle(playback.imei);
  document.getElementById('map-hint').textContent = "Le posizioni arrivano dall'ultimo record di ogni tracker.";
}

function clearTrack() {
  if (playback.active) { exitHistory(); return; }
  clearPlaybackLayers();
  document.getElementById('map-hint').textContent = "Le posizioni arrivano dall'ultimo record di ogni tracker.";
}

async function loadProvisioning() {
  const imei = document.getElementById('p_imei').value.trim();
  if (!/^\\d{14,16}$/.test(imei)) { log('IMEI non valido: attese 14-16 cifre', 'err'); return; }
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
    log('comandi generati per ' + imei, 'okv');
  } catch (error) {
    log('provisioning ' + imei + ': ' + error.message, 'err');
  }
}

async function copyProvisioning() {
  if (!provisioningText) { log('nessun comando da copiare', 'err'); return; }
  try { await navigator.clipboard.writeText(provisioningText); log('comandi copiati', 'okv'); }
  catch (error) { log('copia non riuscita', 'err'); }
}

async function checkAuth() {
  try {
    const response = await api('/auth/me');
    const payload = await response.json();
    const who = document.getElementById('who');
    const user = payload.user;
    currentUser = user;
    const dockUsers = document.getElementById('dock-users');
    if (dockUsers) dockUsers.style.display = user.role === 'admin' ? '' : 'none';
    const dockSystem = document.getElementById('dock-system');
    if (dockSystem) dockSystem.style.display = user.role === 'admin' ? '' : 'none';
    const sideUsers = document.getElementById('side-users');
    if (sideUsers) sideUsers.style.display = user.role === 'admin' ? '' : 'none';
    const sideSystem = document.getElementById('side-system');
    if (sideSystem) sideSystem.style.display = user.role === 'admin' ? '' : 'none';
    const displayName = user.full_name || user.username;
    const sideName = document.getElementById('side-name');
    if (sideName) sideName.textContent = displayName;
    const sideRole = document.getElementById('side-role');
    if (sideRole) {
      const roleLabel = user.role === 'admin' ? 'Amministratore'
        : (user.role === 'manager' ? 'Manager flotta' : 'Vista flotta');
      sideRole.textContent = roleLabel +
        (user.tenant_name ? ' \\u00b7 ' + user.tenant_name : '');
    }
    const sideAvatar = document.getElementById('side-avatar');
    if (sideAvatar) {
      const initials = displayName.split(/\\s+/).filter(Boolean).slice(0, 2)
        .map(function (word) { return word.charAt(0); }).join('').toUpperCase();
      sideAvatar.textContent = initials || 'CM';
    }
    who.textContent = (user.full_name || user.username) +
      (user.tenant_name ? ' \\u00b7 ' + user.tenant_name : '') +
      (payload.auth === 'open' ? ' \\u00b7 primo avvio senza login' : '');
  } catch (error) {
    if (error.status === 401) { window.location.href = '/login'; return; }
    log('sessione: ' + error.message, 'err');
  }
}

async function logout() {
  try { await fetch('/auth/logout', { method: 'POST' }); } catch (error) {}
  window.location.href = '/login';
}

const ALERT_KIND_LABELS = {
  SOS: 'SOS',
  JAMMING: 'Jamming GPS/GSM',
  UNPLUG: 'Taglio alimentazione',
  THEFT: 'Furto (movimento a motore spento)',
  FUEL_THEFT: 'Calo carburante',
  SPEED: 'Velocità',
  GEOFENCE_ENTER: 'Ingresso zona',
  GEOFENCE_EXIT: 'Uscita zona',
  GEOFENCE_CROSS: 'Attraversamento confine',
  IGNITION_OUT_OF_HOURS: 'Accensione fuori orario',
  HARSH_ACCEL: 'Accelerazione brusca',
  HARSH_BRAKE: 'Frenata brusca',
  SAFETY: 'Non conformità sicurezza',
  MAINTENANCE_DUE: 'Manutenzione scaduta'
};

function alertKindLabel(kind) {
  return ALERT_KIND_LABELS[kind] || kind;
}

const ALERT_POSITION_KINDS = [
  'SOS', 'SPEED', 'THEFT', 'FUEL_THEFT', 'JAMMING', 'UNPLUG',
  'GEOFENCE_ENTER', 'GEOFENCE_EXIT', 'GEOFENCE_CROSS', 'IGNITION_OUT_OF_HOURS'
];

function alertPosition(alert) {
  // L'allarme conserva la posizione solo per SOS: per gli altri vale l'ultima
  // posizione nota del mezzo, che in modalita' privacy e' NULL.
  if (hasCoordinates(alert.latitude, alert.longitude)) {
    return { lat: alert.latitude, lon: alert.longitude, privacy: false };
  }
  const device = devices.find(function (item) { return item.imei === alert.imei; });
  // Con la privacy attiva non si usa nessuna coordinata del mezzo, nemmeno
  // quella precedente al cambio: la riga resta senza link.
  if (device && device.privacy_mode) return { lat: null, lon: null, privacy: true };
  if (device && hasCoordinates(device.latitude, device.longitude)) {
    return { lat: device.latitude, lon: device.longitude, privacy: false };
  }
  return { lat: null, lon: null, privacy: false };
}

async function loadAlerts() {
  const openOnly = document.getElementById('soc-open').checked;
  try {
    const response = await api('/alerts?open_only=' + openOnly + '&limit=100');
    const payload = await response.json();
    const sideSoc = document.getElementById('side-soc-count');
    if (sideSoc) {
      sideSoc.textContent = payload.alerts.filter(function (alert) {
        return !alert.acknowledged_at;
      }).length;
    }
    const body = document.getElementById('soc-body');
    body.textContent = '';
    payload.alerts.forEach(function (alert) {
      const position = alertPosition(alert);
      const health = alert.acknowledged_at
        ? el('span', { class: 'muted', text: alert.acknowledged_by || 'preso in carico' })
        : el('button', { class: 'ok tiny', text: 'Prendi in carico',
                        onclick: function () { ackAlert(alert.id); } });
      body.appendChild(el('tr', {}, [
        el('td', { class: 'muted', text: '#' + alert.id }),
        el('td', { class: 'muted', text: String(alert.created_at || '').replace('T', ' ') }),
        el('td', { text: alert.plate || alert.imei }),
        el('td', { text: alertKindLabel(alert.kind) }),
        el('td', {}, [el('span', { class: 'badge warn', text: alert.severity })]),
        el('td', { text: alert.detail || '' }),
        el('td', {}, [el('div', { class: 'row', style: 'gap:6px' }, [
          health,
          hasCoordinates(position.lat, position.lon)
            ? el('a', { class: 'tiny', href: streetViewUrl(position.lat, position.lon),
                        target: '_blank', rel: 'noopener', text: 'Street View' })
            : ALERT_POSITION_KINDS.indexOf(alert.kind) !== -1
              ? el('span', { class: 'muted', text: position.privacy
                  ? 'posizione oscurata (privacy)' : 'posizione non disponibile' })
              : ''
        ])])
      ]));
    });
    document.getElementById('soc-empty').style.display = payload.count ? 'none' : 'block';
  } catch (error) {
    log('allarmi: ' + error.message, 'err');
  }
}

async function ackAlert(id) {
  try {
    await api('/alerts/' + id + '/ack', { method: 'POST' });
    log('allarme #' + id + ' preso in carico', 'okv');
    loadAlerts();
    loadAudit();
  } catch (error) {
    log('presa in carico #' + id + ': ' + error.message, 'err');
  }
}

async function loadAudit() {
  try {
    const response = await api('/commands?limit=50');
    const payload = await response.json();
    const body = document.getElementById('audit-body');
    body.textContent = '';
    payload.commands.forEach(function (item) {
      body.appendChild(el('tr', {}, [
        el('td', { class: 'muted', text: String(item.created_at || '').replace('T', ' ') }),
        el('td', {}, [el('code', { text: item.imei })]),
        el('td', { text: item.action }),
        el('td', {}, [el('code', { text: item.command })]),
        el('td', {}, [el('span', { class: 'badge ' + (item.accepted ? 'on' : 'warn'),
                                  text: item.accepted ? 'ok' : 'rifiutato' })]),
        el('td', { class: 'muted', text: item.requested_by || '' })
      ]));
    });
  } catch (error) {
    log('audit: ' + error.message, 'err');
  }
}

function channelSummary(channels) {
  channels = channels || {};
  const email = channels.email || {};
  const sms = channels.sms || {};
  const voice = channels.voice || {};
  function state(item, label, extra) {
    if (!item.enabled) return label + ': spento';
    return label + ': ' + (item.mode || 'live') +
      (item.configured === false ? ' (da configurare)' : '') +
      (extra ? ' · ' + extra : '');
  }
  return [
    state(email, 'Email', email.from || ''),
    state(sms, 'SMS', sms.provider || ''),
    state(voice, 'Voce', voice.provider || '')
  ].join(' · ');
}

async function loadNotificationOutbox() {
  const body = document.getElementById('outbox-body');
  if (!body) return;
  try {
    const response = await api('/notifications/outbox?limit=100');
    const payload = await response.json();
    const summary = document.getElementById('outbox-channels');
    if (summary) summary.textContent = channelSummary(payload.channels);
    body.textContent = '';
    payload.items.forEach(function (item) {
      const status = item.status || 'unknown';
      const badge = status === 'sent' || status === 'simulated' ? 'on'
        : status === 'preview' ? 'warn' : 'off';
      const channel = item.channel === 'email' ? 'Email'
        : item.channel === 'voice' ? 'Voce' : 'SMS';
      const message = item.subject
        ? item.subject + ' — ' + item.body
        : item.body;
      body.appendChild(el('tr', {}, [
        el('td', { class: 'muted', text: String(item.created_at || '').replace('T', ' ') }),
        el('td', { text: channel + (item.provider ? ' / ' + item.provider : '') }),
        el('td', {}, [el('span', { class: 'badge ' + badge, text: status })]),
        el('td', { text: item.recipients || '' }),
        el('td', { style: 'white-space:pre-wrap;max-width:420px',
                   title: (item.detail || '') + ' — ' + (message || ''),
                   text: String(message || '').slice(0, 220) +
                         (String(message || '').length > 220 ? '…' : '') })
      ]));
    });
    const empty = document.getElementById('outbox-empty');
    if (empty) empty.style.display = payload.count ? 'none' : 'block';
  } catch (error) {
    log('outbox: ' + error.message, 'err');
  }
}

async function changePassword() {
  const current = await askText('Cambio password', 'Password attuale', '', 'Avanti');
  if (!current) return;
  const next = await askText('Cambio password', 'Nuova password (almeno 10 caratteri)', '', 'Aggiorna');
  if (!next) return;
  try {
    await api('/auth/password', {
      method: 'POST',
      body: JSON.stringify({ current: current, new: next })
    });
    log('password aggiornata', 'okv');
    toast('Password aggiornata: la sessione resta valida', 'okv');
    checkAuth();
  } catch (error) {
    log('password: ' + error.message, 'err');
    toast('Password non aggiornata: ' + error.message, 'bad');
  }
}

let esgChart = null;

async function loadEsg() {
  const days = document.getElementById('esg-days').value;
  try {
    const response = await api('/esg?days=' + days);
    const data = await response.json();
    document.getElementById('esg-km').textContent = fmt(data.totals.km, 1);
    document.getElementById('esg-liters').textContent = fmt(data.totals.liters, 1);
    document.getElementById('esg-co2').textContent = fmt(data.totals.co2_kg, 1);
    document.getElementById('esg-perkm').textContent = fmt(data.totals.grams_per_km, 0) + ' g';
    document.getElementById('esg-note').textContent =
      'Stima su ' + fmt(data.assumptions.fuel_l_per_100km, 1) + ' L/100 km e ' +
      fmt(data.assumptions.co2_kg_per_liter, 2) + ' kg CO2/L; distanza da odometro CAN.' +
      ' Indicatore dichiarato, non un report certificato.';
    const body = document.getElementById('esg-body');
    body.textContent = '';
    data.devices.forEach(function (row) {
      body.appendChild(el('tr', {}, [
        el('td', { text: row.plate || row.imei }),
        el('td', {}, [el('code', { text: row.imei })]),
        el('td', { text: fmt(row.km, 1) }),
        el('td', { text: fmt(row.liters, 1) }),
        el('td', { text: fmt(row.co2_kg, 1) }),
        el('td', { text: fmt(row.grams_per_km, 0) }),
        el('td', { text: String(row.days) }),
        el('td', {}, [
          el('span', { class: 'badge ' + (row.params_source === 'veicolo' ? 'on' : 'off'),
                       text: row.params_source === 'veicolo' ? 'propri' : 'flotta' }),
          el('button', { class: 'tiny', text: 'Imposta',
            onclick: function () {
              editEsgParams(row.imei, row.fuel_l_per_100km, row.co2_kg_per_liter);
            } })
        ])
      ]));
    });
    document.getElementById('esg-empty').style.display = data.devices.length ? 'none' : 'block';
    const labels = data.daily.map(function (point) { return point.date.slice(5); });
    const values = data.daily.map(function (point) { return point.co2_kg; });
    const theme = chartTheme();
    if (!esgChart) {
      esgChart = new Chart(document.getElementById('esgChart'), {
        type: 'bar',
        data: { labels: labels, datasets: [{ label: 'CO2 kg', data: values,
          backgroundColor: theme.fill, hoverBackgroundColor: theme.accent,
          borderRadius: 10, borderSkipped: false }] },
        options: { plugins: { legend: { labels: { color: theme.tick } } },
          scales: chartScales(theme, 10) }
      });
    } else {
      esgChart.data.labels = labels;
      esgChart.data.datasets[0].data = values;
      esgChart.update();
    }
    log('ESG ' + days + ' giorni: ' + fmt(data.totals.km, 1) + ' km, ' +
        fmt(data.totals.co2_kg, 1) + ' kg CO2', 'okv');
  } catch (error) {
    log('ESG: ' + error.message, 'err');
  }
}

let currentUser = null;
let toastTimer = null;

function toast(message, kind) {
  const box = document.getElementById('toast');
  if (!box) return;
  box.textContent = message;
  box.className = 'show' + (kind ? ' ' + kind : '');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { box.className = ''; }, 4500);
}

async function editEsgParams(imei, fuel, factor) {
  const fuelText = await askText('Parametri ESG', 'Consumo in L/100 km per ' + imei +
    ' (vuoto = valore di flotta)', String(fuel), 'Avanti');
  if (fuelText === null) return;
  const factorText = await askText('Parametri ESG', 'Fattore CO2 in kg per litro' +
    ' (vuoto = valore di flotta)', String(factor), 'Salva');
  if (factorText === null) return;
  const query = new URLSearchParams();
  if (fuelText.trim()) query.set('fuel_l_per_100km', fuelText.trim());
  if (factorText.trim()) query.set('co2_kg_per_liter', factorText.trim());
  try {
    await api('/devices/' + encodeURIComponent(imei) + '/esg?' + query.toString(),
              { method: 'POST' });
    toast('Parametri ESG aggiornati per ' + imei, 'okv');
    loadEsg();
  } catch (error) {
    toast('Parametri ESG: ' + error.message, 'bad');
  }
}

async function loadUsers() {
  try {
    const response = await api('/users');
    const payload = await response.json();
    const body = document.getElementById('users-body');
    body.textContent = '';
    payload.users.forEach(function (user) {
      const actions = el('div', { class: 'row' });
      actions.appendChild(el('button', {
        class: 'tiny', text: 'Reset password',
        onclick: function () { resetPassword(user.username); }
      }));
      if (user.locked_until) {
        actions.appendChild(el('button', {
          class: 'ok tiny', text: 'Sblocca',
          onclick: function () { unlockUser(user.username); }
        }));
      }
      actions.appendChild(el('button', {
        class: user.active ? 'danger tiny' : 'ok tiny',
        text: user.active ? 'Disattiva' : 'Attiva',
        onclick: function () { toggleUser(user.username, !user.active); }
      }));
      let state;
      if (user.locked_until) state = el('span', { class: 'badge warn', text: 'bloccato' });
      else if (user.must_change) state = el('span', { class: 'badge warn', text: 'cambio password' });
      else state = el('span', { class: 'badge ' + (user.active ? 'on' : 'off'),
                                text: user.active ? 'attivo' : 'disattivato' });
      body.appendChild(el('tr', {}, [
        el('td', {}, [el('code', { text: user.username })]),
        el('td', { text: user.full_name || '\\u2014' }),
        el('td', { text: user.tenant_name || '\\u2014' }),
        el('td', { text: user.role }),
        el('td', {}, [state]),
        el('td', { class: 'muted', text: user.last_login_at
          ? String(user.last_login_at).replace('T', ' ') : '\\u2014' }),
        el('td', {}, [actions])
      ]));
    });
    document.getElementById('users-empty').style.display = payload.count ? 'none' : 'block';
  } catch (error) {
    log('utenti: ' + error.message, 'err');
    toast('Utenti: ' + error.message, 'bad');
  }
}

async function createUser() {
  const username = document.getElementById('u_username').value.trim();
  const password = document.getElementById('u_password').value;
  const role = document.getElementById('u_role').value;
  const tenant = document.getElementById('u_tenant').value.trim();
  const fullName = document.getElementById('u_name').value.trim();
  if (!username) { toast('Serve un nome utente', 'bad'); return; }
  if (password.length < 10) {
    toast('La password deve avere almeno 10 caratteri', 'bad');
    return;
  }
  const body = { username: username, password: password, role: role };
  if (tenant) body.tenant = tenant;
  if (fullName) body.full_name = fullName;
  try {
    await api('/users', { method: 'POST', body: JSON.stringify(body) });
    document.getElementById('u_username').value = '';
    document.getElementById('u_password').value = '';
    document.getElementById('u_name').value = '';
    toast('Utente ' + username + ' creato', 'okv');
    loadUsers();
  } catch (error) {
    toast('Creazione: ' + error.message, 'bad');
  }
}

async function resetPassword(username) {
  const password = await askText(
    'Reimposta password',
    'Nuova password per ' + username + ' (almeno 10 caratteri)',
    '',
    'Reimposta'
  );
  if (!password) return;
  try {
    await api('/users/' + encodeURIComponent(username) + '/password', {
      method: 'POST', body: JSON.stringify({ password: password })
    });
    toast('Password di ' + username + ' reimpostata: cambio obbligatorio', 'okv');
    loadUsers();
  } catch (error) {
    toast('Reset: ' + error.message, 'bad');
  }
}

async function unlockUser(username) {
  try {
    await api('/users/' + encodeURIComponent(username) + '/unlock', { method: 'POST' });
    toast(username + ' sbloccato', 'okv');
    loadUsers();
  } catch (error) {
    toast('Sblocco: ' + error.message, 'bad');
  }
}

async function toggleUser(username, active) {
  const proceed = await askConfirm(
    active ? 'Riattivare utente?' : 'Disattivare utente?',
    username + (active ? '' : '. Le sessioni aperte cadono subito.'),
    active ? 'Riattiva' : 'Disattiva'
  );
  if (!proceed) return;
  try {
    await api('/users/' + encodeURIComponent(username) + '/active?active=' + active,
              { method: 'POST' });
    toast(username + (active ? ' riattivato' : ' disattivato'), 'okv');
    loadUsers();
  } catch (error) {
    toast('Utente: ' + error.message, 'bad');
  }
}

async function createSnapshot() {
  const month = document.getElementById('snap-month').value.trim();
  if (month && !/^\\d{4}-\\d{2}$/.test(month)) {
    toast('Mese nel formato YYYY-MM', 'bad');
    return;
  }
  const query = month ? '?month=' + encodeURIComponent(month) : '';
  try {
    const response = await api('/esg/snapshot' + query, { method: 'POST' });
    const data = await response.json();
    toast('Snapshot ' + data.period + ' creato e sigillato', 'okv');
    loadSnapshots();
  } catch (error) {
    toast('Snapshot: ' + error.message, 'bad');
  }
}

async function loadSnapshots() {
  try {
    const response = await api('/esg/snapshots');
    const payload = await response.json();
    const body = document.getElementById('snap-body');
    body.textContent = '';
    payload.snapshots.forEach(function (snap) {
      body.appendChild(el('tr', {}, [
        el('td', { text: snap.period }),
        el('td', { class: 'muted', text: String(snap.created_at || '').replace('T', ' ') }),
        el('td', { class: 'muted', text: snap.created_by || '\\u2014' }),
        el('td', {}, [el('code', { text: snap.digest.slice(0, 12) + '...' })]),
        el('td', {}, [
          el('button', { class: 'tiny', text: 'Report',
            onclick: function () { window.open('/report/' + snap.id, '_blank'); } }),
          el('button', { class: 'tiny', text: 'PDF',
            onclick: function () { window.open('/esg/snapshots/' + snap.id + '/pdf', '_blank'); } }),
          el('button', { class: 'tiny', text: 'Verifica',
            onclick: function () { openSnapshot(snap.id); } }),
          el('button', { class: 'tiny', text: 'Link',
            onclick: function () { createReportLink(snap.id); } }),
          el('button', { class: 'tiny', text: 'Invia',
            onclick: function () { sendReport(snap.id); } })
        ])
      ]));
    });
    document.getElementById('snap-note').textContent = payload.count
      ? 'Lo snapshot congela i numeri del mese: non viene ricalcolato.'
      : 'Nessuno snapshot: chiudi un mese per congelarne i numeri.';
    fillLinkSnapshots(payload.snapshots);
    loadLinks();
  } catch (error) {
    toast('Snapshot: ' + error.message, 'bad');
  }
}

async function openSnapshot(id) {
  try {
    const response = await api('/esg/snapshots/' + id);
    const data = await response.json();
    const totals = data.report.totals;
    const state = data.signature_ok ? 'firma valida'
      : (data.digest_ok ? 'non firmato' : 'impronta alterata');
    toast('Mese ' + data.snapshot.period + ': ' + fmt(totals.km, 1) + ' km, ' +
          fmt(totals.co2_kg, 1) + ' kg CO2. ' + state,
          data.signature_ok ? 'okv' : (data.digest_ok ? '' : 'bad'));
  } catch (error) {
    toast('Snapshot: ' + error.message, 'bad');
  }
}

async function loadKeys() {
  const rotate = document.getElementById('rotate-key');
  const isAdmin = currentUser && currentUser.role === 'admin';
  if (rotate) rotate.style.display = isAdmin ? '' : 'none';
  if (!isAdmin) return;
  try {
    const response = await api('/esg/signing-keys');
    const payload = await response.json();
    const body = document.getElementById('keys-body');
    body.textContent = '';
    payload.keys.forEach(function (key) {
      body.appendChild(el('tr', {}, [
        el('td', {}, [el('code', { text: key.fingerprint })]),
        el('td', { class: 'muted', text: String(key.created_at || '').replace('T', ' ') }),
        el('td', { text: key.created_by || 'setup' }),
        el('td', {}, [el('span', { class: 'badge ' + (key.active ? 'on' : 'off'),
                                  text: key.active ? 'attiva' : 'ritirata' })]),
        el('td', { text: String(key.snapshots || 0) })
      ]));
    });
  } catch (error) {
    toast('Chiavi: ' + error.message, 'bad');
  }
}

async function rotateKey() {
  const proceed = await askConfirm(
    'Ruotare la chiave di firma?',
    'Gli snapshot gia chiusi restano verificabili con la chiave che li ha firmati. La chiave precedente viene archiviata.',
    'Ruota'
  );
  if (!proceed) return;
  try {
    const response = await api('/esg/signing-key/rotate', { method: 'POST' });
    const data = await response.json();
    toast('Nuova chiave attiva: ' + data.fingerprint, 'okv');
    loadKeys();
  } catch (error) {
    toast('Rotazione: ' + error.message, 'bad');
  }
}

async function loadBranding() {
  const note = document.getElementById('brand-logo-note');
  if (!currentUser || (currentUser.role !== 'admin' && currentUser.role !== 'manager')) return;
  try {
    const response = await api('/branding');
    const data = await response.json();
    const nameInput = document.getElementById('brand-name');
    const colorInput = document.getElementById('brand-color');
    if (nameInput) nameInput.value = data.display_name || '';
    if (colorInput) colorInput.value = data.primary_color || '#0e7490';
    if (note) {
      note.textContent = data.has_logo
        ? 'logo caricato (' + data.logo_mime + ')' : 'nessun logo';
    }
    const bgInput = document.getElementById('brand-bg-url');
    if (bgInput) bgInput.value = data.bg_mode === 'custom' ? (data.bg_image || '') : '';
    const bgNote = document.getElementById('brand-bg-note');
    if (bgNote) {
      if (data.bg_mode === 'none') {
        bgNote.textContent = data.has_saved_bg
          ? 'nessuno sfondo; quello salvato resta e si riattiva'
          : 'nessuno sfondo, scelto dal cliente';
      } else if (data.has_bg_file) bgNote.textContent = 'immagine caricata';
      else if (data.bg_image) bgNote.textContent = 'URL salvato';
      else if (data.bg_default) bgNote.textContent = 'predefinito del server';
      else bgNote.textContent = 'nessuno sfondo';
    }
    const bgRestore = document.getElementById('brand-bg-restore');
    if (bgRestore) {
      bgRestore.style.display = data.has_saved_bg && data.bg_mode !== 'custom' ? '' : 'none';
    }
    previewBrandBackground(data.bg_url || '');
  } catch (error) {
    toast('Branding: ' + error.message, 'bad');
  }
}

async function saveBranding() {
  const name = document.getElementById('brand-name').value.trim();
  const color = document.getElementById('brand-color').value.trim();
  try {
    await api('/branding', {
      method: 'POST',
      body: JSON.stringify({ display_name: name, primary_color: color })
    });
    toast('Branding salvato', 'okv');
    loadBranding();
  } catch (error) {
    toast('Branding: ' + error.message, 'bad');
  }
}

async function uploadBrandLogo() {
  const input = document.getElementById('brand-logo');
  const file = input && input.files && input.files[0];
  if (!file) { toast('Scegli un file PNG o JPEG', 'bad'); return; }
  if (file.size > 512 * 1024) { toast('Logo troppo grande: massimo 512 KB', 'bad'); return; }
  try {
    const response = await fetch('/branding/logo', {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file
    });
    if (!response.ok) {
      let detail = 'HTTP ' + response.status;
      try { const body = await response.json(); if (body.detail) detail = body.detail; } catch (e) {}
      throw new Error(detail);
    }
    input.value = '';
    toast('Logo caricato', 'okv');
    loadBranding();
  } catch (error) {
    toast('Logo: ' + error.message, 'bad');
  }
}

async function removeBrandLogo() {
  const proceed = await askConfirm(
    'Rimuovere il logo?',
    'Il PDF del report tornera senza logo, con il solo nome.',
    'Rimuovi'
  );
  if (!proceed) return;
  try {
    await api('/branding/logo', { method: 'DELETE' });
    toast('Logo rimosso', 'okv');
    loadBranding();
  } catch (error) {
    toast('Logo: ' + error.message, 'bad');
  }
}

function previewBrandBackground(url) {
  const box = document.getElementById('brand-bg-preview');
  if (!box) return;
  if (url) box.style.setProperty('--bg-preview-image', 'url("' + url + '")');
  else box.style.removeProperty('--bg-preview-image');
}

async function saveBrandBackground() {
  const input = document.getElementById('brand-bg-url');
  const url = input ? input.value.trim() : '';
  try {
    const response = await api('/branding/background', {
      method: 'POST',
      body: JSON.stringify({ url: url })
    });
    const data = await response.json();
    toast(url ? 'Sfondo salvato' : 'Sfondo rimosso', 'okv');
    previewBrandBackground(data.bg_url || '');
    loadBranding();
  } catch (error) {
    toast('Sfondo: ' + error.message, 'bad');
  }
}

async function uploadBrandBackground() {
  const input = document.getElementById('brand-bg-file');
  const file = input && input.files && input.files[0];
  if (!file) { toast('Scegli un PNG, JPEG o WebP', 'bad'); return; }
  if (file.size > 1.5 * 1024 * 1024) { toast('Immagine troppo grande: massimo 1,5 MB', 'bad'); return; }
  try {
    const response = await fetch('/branding/background/file', {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file
    });
    if (!response.ok) {
      let detail = 'HTTP ' + response.status;
      try { const body = await response.json(); if (body.detail) detail = body.detail; } catch (e) {}
      throw new Error(detail);
    }
    const data = await response.json();
    input.value = '';
    toast('Sfondo caricato', 'okv');
    previewBrandBackground(data.bg_url || '');
    loadBranding();
  } catch (error) {
    toast('Sfondo: ' + error.message, 'bad');
  }
}

async function reactivateBrandBackground() {
  try {
    const response = await api('/branding/background', {
      method: 'POST',
      body: JSON.stringify({ mode: 'custom' })
    });
    await response.json();
    toast('Sfondo riattivato', 'okv');
    loadBranding();
  } catch (error) {
    toast('Sfondo: ' + error.message, 'bad');
  }
}

async function setBrandBackgroundMode(mode) {
  const none = mode === 'none';
  const proceed = await askConfirm(
    none ? 'Togliere lo sfondo?' : 'Usare il predefinito del server?',
    none
      ? 'Dashboard, report e verifica del cliente tornano al tema pulito, senza foto ne velo.'
      : 'Il cliente eredita lo sfondo configurato sul server, se presente.',
    none ? 'Togli' : 'Usa predefinito'
  );
  if (!proceed) return;
  try {
    const response = await api('/branding/background', {
      method: 'POST',
      body: JSON.stringify({ mode: mode })
    });
    const data = await response.json();
    const input = document.getElementById('brand-bg-url');
    if (input) input.value = '';
    previewBrandBackground(data.bg_url || '');
    toast(none ? 'Sfondo tolto' : 'Sfondo predefinito', 'okv');
    loadBranding();
  } catch (error) {
    toast('Sfondo: ' + error.message, 'bad');
  }
}

async function loadNotificationSettings() {
  if (!currentUser || (currentUser.role !== 'admin' && currentUser.role !== 'manager')) return;
  try {
    const response = await api('/notifications');
    const data = await response.json();
    document.getElementById('notify-emails').value = data.emails || '';
    document.getElementById('notify-phones').value = data.phones || '';
    const channels = document.getElementById('notify-channels');
    if (channels) channels.textContent = channelSummary(data.channels);
  } catch (error) {
    toast('Destinatari: ' + error.message, 'bad');
  }
}

async function saveNotificationSettings() {
  const emails = document.getElementById('notify-emails').value.trim();
  const phones = document.getElementById('notify-phones').value.trim();
  try {
    await api('/notifications', { method: 'POST', body: JSON.stringify({
      emails: emails, phones: phones }) });
    toast('Destinatari salvati', 'okv');
    loadNotificationSettings();
  } catch (error) {
    toast('Destinatari: ' + error.message, 'bad');
  }
}

function previewBrandingPdf() {
  const query = new URLSearchParams();
  const name = document.getElementById('brand-name').value.trim();
  const color = document.getElementById('brand-color').value.trim();
  if (name) query.set('display_name', name);
  if (color) query.set('primary_color', color);
  const suffix = query.toString() ? '?' + query.toString() : '';
  window.open('/branding/preview.pdf' + suffix, '_blank');
}

async function loadLinkBlocks() {
  const body = document.getElementById('blocks-body');
  const empty = document.getElementById('blocks-empty');
  if (!body || !currentUser || currentUser.role !== 'admin') return;
  try {
    const response = await api('/links/blocked');
    const payload = await response.json();
    body.textContent = '';
    payload.blocks.forEach(function (item) {
      const state = item.blocked ? 'bloccato' : 'in osservazione';
      body.appendChild(el('tr', {}, [
        el('td', { text: item.ip }),
        el('td', { text: String(item.failures) }),
        el('td', { class: 'muted', text: String(item.first_at || '').replace('T', ' ') }),
        el('td', { class: 'muted', text: item.blocked_until
          ? String(item.blocked_until).replace('T', ' ') : '\\u2014' }),
        el('td', {}, [
          el('span', { class: 'badge ' + (item.blocked ? 'off' : 'on'), text: state }),
          el('button', { class: 'tiny', text: 'Sblocca',
            onclick: function () { unblockIp(item.ip); } })
        ])
      ]));
    });
    if (empty) empty.style.display = payload.blocks.length ? 'none' : 'block';
  } catch (error) {
    toast('Blocchi: ' + error.message, 'bad');
  }
}

async function unblockIp(ip) {
  const proceed = await askConfirm(
    'Sbloccare ' + ip + '?',
    'Tentativi e blocco vengono azzerati subito.',
    'Sblocca'
  );
  if (!proceed) return;
  try {
    await api('/links/unblock?ip=' + encodeURIComponent(ip), { method: 'POST' });
    toast('Indirizzo sbloccato', 'okv');
    loadLinkBlocks();
  } catch (error) {
    toast('Sblocco: ' + error.message, 'bad');
  }
}

function exportDataset(dataset, format) {
  window.location = '/export/' + dataset + '?format=' + format;
}

function exportTrips(format) {
  const hours = Number(document.getElementById('activity-hours').value || 24);
  window.location = '/export/trips?format=' + format + '&hours=' + hours;
}

function exportPositions(format) {
  const imei = document.getElementById('export-imei').value.trim();
  const hours = Number(document.getElementById('export-hours').value || 24);
  if (!imei) { toast("Indica l'IMEI da esportare", 'bad'); return; }
  window.location = '/export/positions?format=' + format + '&imei=' +
    encodeURIComponent(imei) + '&hours=' + hours;
}

function exportHistory(format) {
  if (!playback.active || !playback.imei) {
    toast('Apri prima uno storico dalla mappa', 'bad');
    return;
  }
  const dateInput = document.getElementById('pb-date');
  const date = (dateInput && dateInput.value) || localDay(0);
  const query = new URLSearchParams({
    date: date,
    tz_offset: String(new Date().getTimezoneOffset()),
    format: format
  });
  window.location = '/positions/' + encodeURIComponent(playback.imei) +
    '/history/export?' + query.toString();
}

function geofenceShapeLabel(shape) {
  return shape === 'polygon' ? 'Poligono'
    : shape === 'line' ? 'Linea di confine' : 'Cerchio';
}

function geofenceScheduleText(schedule) {
  if (!Array.isArray(schedule) || !schedule.length) return 'Sempre attivo';
  const labels = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom'];
  return schedule.map(function (window) {
    const days = (window.days || []).slice().sort(function (a, b) { return a - b; });
    let dayText = days.map(function (day) { return labels[day] || '?'; }).join(', ');
    if (days.length === 7) dayText = 'Tutti i giorni';
    else if (days.length === 5 && days[0] === 0 && days[4] === 4) dayText = 'Lun–Ven';
    else if (days.length === 2 && days[0] === 5 && days[1] === 6) dayText = 'Sab–Dom';
    return dayText + ' ' + window.start + '–' + (window.end === '24:00' ? '24' : window.end);
  }).join(' · ');
}

function renderGeofenceLayers() {
  if (!map) return;
  if (geofenceLayer) map.removeLayer(geofenceLayer);
  geofenceLayer = L.layerGroup().addTo(map);
  geofences.forEach(function (zone) {
    const shape = zone.shape || 'circle';
    const style = {
      color: '#38bdf8', weight: 2, opacity: .9, fillColor: '#38bdf8',
      fillOpacity: shape === 'line' ? 0 : .10,
      dashArray: shape === 'line' ? '8 6' : null
    };
    let layer = null;
    if (shape === 'polygon') {
      layer = L.polygon((zone.geometry || []).map(function (point) {
        return [Number(point[0]), Number(point[1])];
      }), style);
    } else if (shape === 'line') {
      layer = L.polyline((zone.geometry || []).map(function (point) {
        return [Number(point[0]), Number(point[1])];
      }), style);
    } else {
      layer = L.circle([Number(zone.latitude), Number(zone.longitude)], {
        radius: Number(zone.radius_m || 0), color: style.color, weight: style.weight,
        fillColor: style.fillColor, fillOpacity: style.fillOpacity
      });
    }
    if (layer) layer.bindTooltip(zone.name, { sticky: true }).addTo(geofenceLayer);
  });
}

function drawGeofenceDraft() {
  if (!map) return;
  if (!geofenceDraftLayer) geofenceDraftLayer = L.layerGroup().addTo(map);
  geofenceDraftLayer.clearLayers();
  if (!geofenceDraft.length) return;
  const shape = document.getElementById('g_shape').value;
  const points = geofenceDraft.map(function (point) { return [point[0], point[1]]; });
  const style = { color: '#fbbf24', weight: 3, dashArray: '7 5', fillOpacity: .08 };
  if (shape === 'polygon' && points.length >= 3) {
    L.polygon(points, style).addTo(geofenceDraftLayer);
  } else if (points.length >= 2) {
    L.polyline(points, style).addTo(geofenceDraftLayer);
  }
  geofenceDraft.forEach(function (point, index) {
    L.circleMarker(point, { radius: 5, color: '#fbbf24', fillColor: '#fbbf24',
      fillOpacity: 1 }).bindTooltip(String(index + 1)).addTo(geofenceDraftLayer);
  });
}

function addGeofencePoint(latlng) {
  if (!geofenceDrawing) return;
  geofenceDraft.push([Number(latlng.lat.toFixed(7)), Number(latlng.lng.toFixed(7))]);
  drawGeofenceDraft();
  const hint = document.getElementById('g_draw_hint');
  if (hint) hint.textContent = geofenceDraft.length + ' punti: continua a cliccare la mappa.';
}

function updateGeofenceDrawingButtons() {
  const start = document.getElementById('g_draw_start');
  const finish = document.getElementById('g_draw_finish');
  const cancel = document.getElementById('g_draw_cancel');
  if (start) start.disabled = geofenceDrawing;
  if (finish) finish.disabled = !geofenceDrawing;
  if (cancel) cancel.disabled = !geofenceDrawing && !geofenceDraft.length;
  const actions = document.getElementById('map-geofence-actions');
  if (actions) actions.style.display = (geofenceDrawing || geofenceDraft.length) ? 'inline-flex' : 'none';
}

function clearGeofenceDraft() {
  geofenceDraft = [];
  geofenceDrawing = false;
  if (geofenceDraftLayer) geofenceDraftLayer.clearLayers();
  updateGeofenceDrawingButtons();
  const hint = document.getElementById('g_draw_hint');
  if (hint) hint.textContent = 'Per il poligono servono almeno 3 punti; per la linea 2.';
}

function updateGeofenceShape() {
  const shape = document.getElementById('g_shape').value;
  const circle = document.getElementById('g_circle_fields');
  if (circle) circle.style.display = shape === 'circle' ? 'flex' : 'none';
  clearGeofenceDraft();
  if (shape !== 'circle') {
    const hint = document.getElementById('g_draw_hint');
    if (hint) hint.textContent = 'Scegli “Disegna sulla mappa”, poi clicca i vertici.';
  }
}

function startGeofenceDrawing() {
  const shape = document.getElementById('g_shape').value;
  if (shape === 'circle') {
    toast('Per il cerchio usa centro e raggio, oppure scegli poligono/linea', 'bad');
    return;
  }
  ensureMap();
  geofenceDraft = [];
  geofenceDrawing = true;
  showTab('tab-map', document.querySelector('[data-tab="tab-map"]'));
  drawGeofenceDraft();
  updateGeofenceDrawingButtons();
  const hint = document.getElementById('g_draw_hint');
  if (hint) hint.textContent = 'Clicca sulla mappa per aggiungere i punti.';
}

function finishGeofenceDrawing() {
  const shape = document.getElementById('g_shape').value;
  const minimum = shape === 'polygon' ? 3 : 2;
  if (geofenceDraft.length < minimum) {
    toast(shape === 'polygon' ? 'Servono almeno 3 vertici' : 'Servono almeno 2 punti', 'bad');
    return;
  }
  geofenceDrawing = false;
  updateGeofenceDrawingButtons();
  const hint = document.getElementById('g_draw_hint');
  if (hint) hint.textContent = geofenceDraft.length + ' punti pronti: premi Crea per salvare.';
}

function cancelGeofenceDrawing() {
  clearGeofenceDraft();
}

function buildGeofenceSchedule() {
  if (!document.getElementById('g_schedule').checked) return [];
  const from = document.getElementById('g_from').value;
  const to = document.getElementById('g_to').value;
  const weekdays = document.getElementById('g_weekdays').checked;
  const weekend = document.getElementById('g_weekend').checked;
  if (!weekdays && !weekend) throw new Error('Seleziona almeno un giorno');
  if (!from || !to) throw new Error('Indica ora di inizio e fine');
  const windows = [];
  if (weekdays) windows.push({ days: [0, 1, 2, 3, 4], start: from, end: to });
  if (weekend) windows.push({ days: [5, 6], start: '00:00', end: '24:00' });
  return windows;
}

async function loadGeofences() {
  const body = document.getElementById('geo-body');
  const empty = document.getElementById('geo-empty');
  if (!body) return;
  try {
    const response = await api('/geofences');
    const payload = await response.json();
    geofences = payload.geofences || [];
    body.textContent = '';
    geofences.forEach(function (zone) {
      const shape = zone.shape || 'circle';
      const count = (zone.geometry || []).length;
      const geometry = shape === 'circle'
        ? Number(zone.latitude).toFixed(4) + ', ' + Number(zone.longitude).toFixed(4) +
          ' · ' + Number(zone.radius_m) + ' m'
        : count + (shape === 'polygon' ? ' vertici' : ' punti');
      body.appendChild(el('tr', {}, [
        el('td', { text: zone.name }),
        el('td', { text: geofenceShapeLabel(shape) }),
        el('td', { class: 'muted', text: geometry }),
        el('td', { class: 'muted', text: geofenceScheduleText(zone.schedule) }),
        el('td', {}, [el('button', { class: 'tiny danger', text: 'Elimina',
          onclick: function () { deleteGeofence(zone.id); } })])
      ]));
    });
    if (empty) empty.style.display = geofences.length ? 'none' : 'block';
    renderGeofenceLayers();
  } catch (error) {
    toast('Zone: ' + error.message, 'bad');
  }
}

async function createGeofence() {
  const name = document.getElementById('g_name').value.trim();
  const shape = document.getElementById('g_shape').value;
  if (!name) { toast('Nome zona mancante', 'bad'); return; }
  let schedule;
  try { schedule = buildGeofenceSchedule(); }
  catch (error) { toast(error.message, 'bad'); return; }
  const payload = {
    name: name, shape: shape, schedule: schedule,
    timezone: document.getElementById('g_tz').value
  };
  if (shape === 'circle') {
    const latitude = Number(document.getElementById('g_lat').value);
    const longitude = Number(document.getElementById('g_lon').value);
    const radius = Number(document.getElementById('g_radius').value || 500);
    if (!isFinite(latitude) || !isFinite(longitude)) {
      toast('Coordinate non valide', 'bad'); return;
    }
    payload.latitude = latitude;
    payload.longitude = longitude;
    payload.radius_m = radius;
  } else {
    const minimum = shape === 'polygon' ? 3 : 2;
    if (geofenceDraft.length < minimum) {
      toast('Disegna prima almeno ' + minimum + ' punti sulla mappa', 'bad');
      return;
    }
    payload.geometry = geofenceDraft.slice();
  }
  try {
    await api('/geofences', { method: 'POST', body: JSON.stringify(payload) });
    toast('Zona creata', 'okv');
    clearGeofenceDraft();
    document.getElementById('g_name').value = '';
    await loadGeofences();
  } catch (error) {
    toast('Zona: ' + error.message, 'bad');
  }
}

async function deleteGeofence(id) {
  const proceed = await askConfirm(
    'Eliminare la zona?',
    'Non verranno piu generati allarmi di ingresso, uscita o attraversamento per questa zona.',
    'Elimina'
  );
  if (!proceed) return;
  try {
    await api('/geofences/' + id, { method: 'DELETE' });
    toast('Zona eliminata', 'okv');
    await loadGeofences();
  } catch (error) {
    toast('Zona: ' + error.message, 'bad');
  }
}

async function loadAlertRules() {
  if (!currentUser || (currentUser.role !== 'admin' && currentUser.role !== 'manager')) return;
  try {
    const response = await api('/alert-rules');
    const payload = await response.json();
    const speed = payload.rules.speed || {};
    const theft = payload.rules.theft || {};
    document.getElementById('rule-speed').value = speed.threshold || 90;
    document.getElementById('rule-speed-on').checked = Boolean(speed.enabled);
    document.getElementById('rule-theft').value = theft.threshold || 5;
    document.getElementById('rule-theft-on').checked = Boolean(theft.enabled);
  } catch (error) {
    toast('Regole: ' + error.message, 'bad');
  }
}

async function saveAlertRules() {
  const rules = [
    { kind: 'speed', threshold: Number(document.getElementById('rule-speed').value),
      enabled: document.getElementById('rule-speed-on').checked },
    { kind: 'theft', threshold: Number(document.getElementById('rule-theft').value),
      enabled: document.getElementById('rule-theft-on').checked }
  ];
  try {
    for (const rule of rules) {
      await api('/alert-rules', { method: 'POST', body: JSON.stringify(rule) });
    }
    toast('Regole salvate', 'okv');
    loadAlertRules();
  } catch (error) {
    toast('Regole: ' + error.message, 'bad');
  }
}

async function loadWorkHours() {
  if (!currentUser || (currentUser.role !== 'admin' && currentUser.role !== 'manager')) return;
  try {
    const response = await api('/work-hours');
    const payload = await response.json();
    const hours = payload.work_hours || {};
    document.getElementById('hours-on').checked = Boolean(hours.enabled);
    document.getElementById('hours-tz').value = hours.timezone || 'Europe/Rome';
    const windows = hours.schedule || [];
    const weekdays = windows.find(function (w) { return (w.days || []).indexOf(0) !== -1; });
    const weekend = windows.find(function (w) { return (w.days || []).indexOf(5) !== -1; });
    document.getElementById('hours-weekdays').checked = Boolean(weekdays);
    document.getElementById('hours-weekend').checked = Boolean(weekend);
    if (weekdays) {
      document.getElementById('hours-from').value = weekdays.start;
      document.getElementById('hours-to').value =
        weekdays.end === '24:00' ? '00:00' : weekdays.end;
    }
  } catch (error) {
    toast('Fascia lavorativa: ' + error.message, 'bad');
  }
}

function workHoursSchedule() {
  const weekdays = document.getElementById('hours-weekdays').checked;
  const weekend = document.getElementById('hours-weekend').checked;
  const from = document.getElementById('hours-from').value;
  const to = document.getElementById('hours-to').value;
  if (!weekdays && !weekend) throw new Error('Seleziona almeno un giorno');
  if (!from || !to) throw new Error('Indica ora di inizio e fine');
  const windows = [];
  if (weekdays) windows.push({ days: [0, 1, 2, 3, 4], start: from, end: to });
  if (weekend) windows.push({ days: [5, 6], start: from, end: to });
  return windows;
}

async function saveWorkHours() {
  const enabled = document.getElementById('hours-on').checked;
  let schedule = [];
  if (enabled) {
    try { schedule = workHoursSchedule(); }
    catch (error) { toast(error.message, 'bad'); return; }
  }
  try {
    await api('/work-hours', { method: 'POST', body: JSON.stringify({
      enabled: enabled,
      schedule: schedule,
      timezone: document.getElementById('hours-tz').value
    }) });
    toast('Fascia lavorativa salvata', 'okv');
    loadWorkHours();
  } catch (error) {
    toast('Fascia lavorativa: ' + error.message, 'bad');
  }
}

function fillSafetyDevices() {
  const select = document.getElementById('s_imei');
  if (!select) return;
  const current = select.value;
  select.textContent = '';
  devices.forEach(function (device) {
    const option = document.createElement('option');
    option.value = device.imei;
    option.textContent = vehicleLabel(device) + ' - ' + device.imei;
    select.appendChild(option);
  });
  if (current) select.value = current;
}

let solutionConfig = null;

async function renderVerticalDashboard() {
  const panel = document.getElementById('vertical-panel');
  if (!panel || !solutionConfig || typeof devices === 'undefined') return;
  const total = devices.length;
  const online = devices.filter(function (device) { return device.connected; }).length;
  const moving = devices.filter(function (device) { return (device.speed || 0) > 1; }).length;
  const km = devices.reduce(function (sum, device) {
    return sum + (device.odometer_m ? device.odometer_m / 1000 : 0);
  }, 0);
  document.getElementById('v-fleet').textContent = total;
  document.getElementById('v-online').textContent = online;
  document.getElementById('v-moving').textContent = moving;
  document.getElementById('v-util').textContent =
    (total ? Math.round((moving / total) * 100) : 0) + '%';
  document.getElementById('v-km').textContent = Math.round(km).toLocaleString('it-IT');
  try {
    const alerts = await (await api('/alerts?open_only=true&limit=100')).json();
    document.getElementById('v-alerts').textContent = alerts.alerts.length;
  } catch (error) { /* il conteggio resta invariato */ }
  try {
    const maintenance = await (await api('/maintenance?open_only=true')).json();
    const items = maintenance.items || maintenance.maintenance || [];
    const due = items.filter(function (item) {
      return ['due', 'overdue', 'scaduto'].indexOf(item.status) !== -1;
    }).length;
    document.getElementById('v-due').textContent = due;
  } catch (error) { /* il conteggio resta invariato */ }
}

let assignmentDrivers = null;

async function fillAssignmentSelectors() {
  const select = document.getElementById('assign-device');
  if (!select) return;
  if (!devices || !devices.length) return;
  const current = select.value;
  select.innerHTML = '';
  devices.forEach(function (device) {
    const option = document.createElement('option');
    option.value = device.imei;
    option.textContent = vehicleLabel(device) + ' · ' + device.imei;
    select.appendChild(option);
  });
  if (current) select.value = current;
  if (!assignmentDrivers) {
    try {
      const data = await (await api('/drivers')).json();
      assignmentDrivers = data.drivers || [];
    } catch (error) { assignmentDrivers = []; }
  }
  const badgeSelect = document.getElementById('assign-driver');
  if (!badgeSelect) return;
  const selected = badgeSelect.value;
  badgeSelect.innerHTML = '<option value="">Nessun autista</option>';
  assignmentDrivers.forEach(function (driver) {
    const option = document.createElement('option');
    option.value = driver.badge;
    option.textContent = driver.name + ' (' + driver.badge + ')';
    badgeSelect.appendChild(option);
  });
  badgeSelect.value = selected;
  prefillAssignment();
}

function prefillAssignment() {
  const imei = document.getElementById('assign-device').value;
  const device = (devices || []).find(function (item) { return item.imei === imei; });
  if (!device) return;
  document.getElementById('assign-driver').value = device.driver_badge || '';
  document.getElementById('assign-trailer').value = device.trailer_plate || '';
  document.getElementById('assign-trailer-type').value = device.trailer_type || '';
}

async function saveAssignment() {
  const imei = document.getElementById('assign-device').value;
  if (!imei) { toast('Seleziona un mezzo', 'bad'); return; }
  const badge = document.getElementById('assign-driver').value;
  const plate = document.getElementById('assign-trailer').value.trim();
  const kind = document.getElementById('assign-trailer-type').value.trim();
  try {
    await api('/devices/' + encodeURIComponent(imei) + '/driver', {
      method: 'POST', body: JSON.stringify({ badge: badge })
    });
    await api('/devices/' + encodeURIComponent(imei) + '/trailer', {
      method: 'POST', body: JSON.stringify({ plate: plate, type: kind })
    });
    toast('Assegnazione salvata', 'ok');
    await refresh();
  } catch (error) {
    toast('Assegnazione: ' + error.message, 'bad');
  }
}

async function renderHeavyPanel() {
  const panel = document.getElementById('heavy-panel');
  if (!panel) return;
  const show = solutionConfig && solutionConfig.vertical === 'trasporti_pesanti';
  panel.style.display = show ? 'block' : 'none';
  if (!show || typeof devices === 'undefined') return;
  await fillAssignmentSelectors();
  let alerts = [];
  try {
    const data = await (await api('/alerts?open_only=true&limit=200')).json();
    alerts = data.alerts || [];
  } catch (error) { /* tabella senza conteggi */ }
  const counts = {};
  alerts.forEach(function (alert) {
    const key = String(alert.imei || alert.device_imei || alert.device_id || '');
    counts[key] = (counts[key] || 0) + 1;
  });
  const body = document.getElementById('heavy-body');
  if (!body) return;
  body.innerHTML = '';
  devices.forEach(function (device) {
    const row = document.createElement('tr');
    [vehicleLabel(device),
      device.driver_name
        ? device.driver_name + ' (' + device.driver_badge + ')'
        : (device.driver_badge || '—'),
      device.trailer_plate
        ? device.trailer_plate + (device.trailer_type ? ' · ' + device.trailer_type : '')
        : '—',
      device.connected ? 'Online' : 'Offline',
      Math.round(device.speed || 0) + ' km/h',
      Math.round((device.odometer_m || 0) / 1000).toLocaleString('it-IT') + ' km',
      counts[String(device.imei)] || 0].forEach(function (value) {
      const cell = document.createElement('td');
      cell.textContent = String(value);
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
}

function toggleMapTracks() {
  const body = document.body;
  body.classList.toggle('maps-google');
  const googleOn = body.classList.contains('maps-google');
  const toggle = document.getElementById('map-toggle');
  if (toggle) toggle.textContent = googleOn ? 'Mostra tracce' : 'Google Maps';
  const frame = document.getElementById('gmaps-frame');
  if (googleOn && frame && frame.src) {
    frame.style.display = 'block';
  } else if (!googleOn && frame) {
    frame.style.display = 'none';
    ensureMap();
    setTimeout(function () { if (map) map.invalidateSize(); }, 100);
  }
}

function applySolution(data) {
  solutionConfig = data;
  const details = {};
  (data.vertical_details || []).forEach(function (item) {
    details[item.id] = item;
  });
  const current = details[data.vertical] || {};
  const labels = {};
  const notes = {};
  (data.vertical_details || []).forEach(function (item) {
    labels[item.id] = item.label;
    notes[item.id] = item.note;
  });
  const movingLabels = {
    trasporti_pesanti: 'In movimento', bus: 'In servizio', rifiuti: 'In raccolta',
    corrieri: 'In consegna', noleggio: 'Noleggiati', macchine_operatrici: 'In uso',
    sgombero_neve: 'In intervento', moto_bici: 'In movimento',
    imbarcazioni: 'In navigazione', persone: 'In movimento',
    trasporti: 'In movimento'
  };
  const badge = document.getElementById('vertical-badge');
  if (badge) {
    badge.textContent = (labels[data.vertical] || data.vertical) + ' · ' +
      data.connectivity.toUpperCase();
    badge.style.display = 'inline-block';
  }
  const panel = document.getElementById('vertical-panel');
  if (panel) {
    panel.style.display = 'block';
    document.getElementById('vertical-title').textContent =
      labels[data.vertical] || data.vertical;
    document.getElementById('vertical-note').textContent = notes[data.vertical] || '';
    const box = document.getElementById('vertical-functions');
    if (box) {
      box.innerHTML = '';
      (current.functions || []).forEach(function (fn) {
        const chip = document.createElement('span');
        chip.className = 'chip ' + fn.status;
        chip.textContent = fn.label;
        chip.title = (fn.note || '') + ' (' + fn.status + ')';
        box.appendChild(chip);
      });
    }
  }
  if (map) {
    map.eachLayer(function (layer) {
      if (layer instanceof L.TileLayer) map.removeLayer(layer);
    });
    addBaseLayer();
  }
  document.body.classList.toggle('maps-google', data.maps === 'google');
  const mapNote = document.getElementById('map-note');
  if (mapNote) {
    mapNote.textContent = data.maps === 'google'
      ? 'Modalità Google: embed come mappa; “Mostra tracce” riporta a OpenStreetMap'
      : data.maps === 'swiss'
        ? 'Mappe SwissTopo; tracce e marker sulla mappa'
        : 'mappa incorporata OpenStreetMap, Google in embed';
  }
  const toggle = document.getElementById('map-toggle');
  if (toggle) toggle.style.display = data.maps === 'google' ? '' : 'none';
  const movingLabel = document.getElementById('v-moving-label');
  if (movingLabel) {
    movingLabel.textContent = movingLabels[data.vertical] || 'In uso';
  }
  if (data.maps !== 'google') {
    const frame = document.getElementById('gmaps-frame');
    if (frame) frame.style.display = 'none';
  }
  renderVerticalDashboard();
  renderHeavyPanel();
}

async function loadSolution() {
  try {
    const data = await (await api('/solutions')).json();
    const select = document.getElementById('sol-vertical');
    if (select && data.vertical_details) {
      select.innerHTML = '';
      data.vertical_details.forEach(function (item) {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = item.label;
        select.appendChild(option);
      });
    }
    applySolution(data);
    document.getElementById('sol-vertical').value = data.vertical;
    document.getElementById('sol-connectivity').value = data.connectivity;
    document.getElementById('sol-maps').value = data.maps;
    const current = (data.vertical_details || []).find(function (item) {
      return item.id === data.vertical;
    });
    document.getElementById('sol-status').textContent = [
      'Verticale: ' + (current ? current.label : data.vertical),
      'Funzioni: verde attivo, arancio parziale, blu hardware, grigio da sviluppare.',
      '',
      'Attivi nel software: localizzazione e storico, geofence e allarmi,',
      'report PDF/ESG archiviabili, blocco motore, manutenzione, carburante,',
      'anti-jammer, stile di guida e identificazione autista.',
      '',
      'Da abilitare con hardware/servizio: tachigrafo digitale, dashcam,',
      'sensori aggiuntivi, SIM 4G e copertura Svizzera.',
      '',
      'La verticale selezionata non cambia i dati raccolti: imposta il',
      'riferimento di pacchetto per demo e configurazione.'
    ].join(String.fromCharCode(10));
  } catch (error) {
    toast('Soluzioni: ' + error.message, 'bad');
  }
}

async function saveSolution() {
  try {
    await api('/solutions', {
      method: 'POST',
      body: JSON.stringify({
        vertical: document.getElementById('sol-vertical').value,
        connectivity: document.getElementById('sol-connectivity').value,
        maps: document.getElementById('sol-maps').value
      })
    });
    toast('Pacchetto salvato', 'okv');
    loadSolution();
  } catch (error) {
    if (error.status === 401) return;
    toast('Pacchetto: ' + error.message, 'bad');
  }
}

async function loadDriving() {
  const body = document.getElementById('driving-body');
  if (!body) return;
  if (currentUser && currentUser.role === 'admin') {
    const select = document.getElementById('driver-tenant');
    select.style.display = '';
    if (!select.options.length) {
      try {
        const tenants = await (await api('/tenants')).json();
        tenants.tenants.forEach(function (tenant) {
          const option = document.createElement('option');
          option.value = tenant.id;
          option.textContent = tenant.name;
          select.appendChild(option);
        });
      } catch (error) { /* la lista autisti resta utilizzabile */ }
    }
  }
  try {
    const data = await (await api('/driving?hours=24')).json();
    document.getElementById('driving-events').textContent = data.count;
    document.getElementById('driving-accel').textContent = data.accel;
    document.getElementById('driving-brake').textContent = data.brake;
    document.getElementById('driving-score').textContent =
      data.drivers.length ? data.drivers[0].score : '—';
    body.textContent = '';
    data.events.forEach(function (event) {
      const tr = document.createElement('tr');
      const values = [
        new Date(event.ts_ms).toLocaleString('it-IT'),
        event.plate || event.imei,
        event.driver || '—',
        event.kind === 'HARSH_BRAKE' ? 'Frenata' : 'Accelerazione',
        event.speed_before + ' → ' + event.speed_after + ' km/h'
      ];
      values.forEach(function (value) {
        const cell = document.createElement('td');
        cell.textContent = value;
        tr.appendChild(cell);
      });
      body.appendChild(tr);
    });
    document.getElementById('driving-empty').style.display =
      data.events.length ? 'none' : 'block';
    document.getElementById('driving-drivers').textContent = data.drivers.length
      ? data.drivers.map(function (driver) {
          return driver.name + ' (' + driver.events + ' eventi, punteggio ' +
            driver.score + ')';
        }).join(' · ')
      : 'Nessun autista identificato: aggiungi un badge o configura ID IO.';
  } catch (error) {
    toast('Guida: ' + error.message, 'bad');
  }
}

async function addDriver() {
  const name = document.getElementById('driver-name').value.trim();
  const badge = document.getElementById('driver-badge').value.trim();
  const tenantSelect = document.getElementById('driver-tenant');
  const tenantId = tenantSelect.value ? Number(tenantSelect.value) : null;
  try {
    await api('/drivers', {
      method: 'POST',
      body: JSON.stringify({ name: name, badge: badge, tenant_id: tenantId })
    });
    toast('Autista salvato', 'okv');
    loadDriving();
  } catch (error) {
    toast('Autista: ' + error.message, 'bad');
  }
}

async function loadSafety() {
  fillSafetyDevices();
  const body = document.getElementById('safety-body');
  const empty = document.getElementById('safety-empty');
  if (!body) return;
  try {
    const response = await api('/safety/checks');
    const payload = await response.json();
    body.textContent = '';
    payload.checks.forEach(function (check) {
      body.appendChild(el('tr', {}, [
        el('td', { class: 'muted', text: String(check.checked_at || '').replace('T', ' ') }),
        el('td', { text: check.plate || check.imei }),
        el('td', { text: check.kind }),
        el('td', {}, [el('span', {
          class: 'badge ' + (check.compliant ? 'on' : 'off'),
          text: check.compliant ? 'conforme' : 'non conforme' })]),
        el('td', { class: 'muted', text: check.note || '\u2014' }),
        el('td', { class: 'muted', text: check.checked_by || '' })
      ]));
    });
    document.getElementById('safety-total').textContent = payload.summary.total;
    document.getElementById('safety-ok').textContent = payload.summary.compliant;
    document.getElementById('safety-bad').textContent = payload.summary.non_compliant;
    if (empty) empty.style.display = payload.checks.length ? 'none' : 'block';
  } catch (error) {
    toast('Sicurezza: ' + error.message, 'bad');
  }
}

async function createSafetyCheck() {
  const imei = document.getElementById('s_imei').value;
  if (!imei) { toast('Nessun mezzo selezionato', 'bad'); return; }
  const note = document.getElementById('s_note').value.trim();
  try {
    await api('/safety/checks', { method: 'POST', body: JSON.stringify({
      imei: imei,
      kind: document.getElementById('s_kind').value,
      compliant: document.getElementById('s_compliant').checked,
      note: note || null }) });
    toast('Controllo registrato', 'okv');
    document.getElementById('s_note').value = '';
    loadSafety();
  } catch (error) {
    toast('Sicurezza: ' + error.message, 'bad');
  }
}

function openGoogleMap() {
  const select = document.getElementById('activity-imei');
  let device = null;
  if (select && select.value) {
    device = devices.find(function (item) { return item.imei === select.value; });
  }
  if (!device) {
    device = devices.find(function (item) {
      return item.latitude !== null && item.latitude !== undefined;
    });
  }
  if (!device) { toast('Nessun mezzo con posizione', 'bad'); return; }
  const lat = device.latitude;
  const lon = device.longitude;
  const frame = document.getElementById('gmaps-frame');
  frame.style.display = 'block';
  frame.src = 'https://maps.google.com/maps?q=' + lat + ',' + lon +
    '&z=16&output=embed';
  document.getElementById('gmaps-link').href =
    'https://www.google.com/maps?q=' + lat + ',' + lon;
  document.getElementById('street-link').href =
    'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=' + lat + ',' + lon;
}

function fillActivityDevices() {
  const select = document.getElementById('activity-imei');
  if (!select) return;
  const current = select.value;
  select.textContent = '';
  devices.forEach(function (device) {
    const option = document.createElement('option');
    option.value = device.imei;
    option.textContent = vehicleLabel(device) + ' - ' + device.imei;
    select.appendChild(option);
  });
  if (current) select.value = current;
}

function formatStamp(ms) {
  if (!ms) return '\u2014';
  return new Date(ms).toLocaleString('it-IT');
}

async function loadActivity() {
  const select = document.getElementById('activity-imei');
  if (!select) return;
  fillActivityDevices();
  const imei = select.value;
  const hours = Number(document.getElementById('activity-hours').value || 24);
  if (!imei) { toast('Nessun mezzo disponibile', 'bad'); return; }
  const body = document.getElementById('activity-body');
  const empty = document.getElementById('activity-empty');
  try {
    const response = await api('/activity/' + encodeURIComponent(imei) + '?hours=' + hours);
    const payload = await response.json();
    body.textContent = '';
    payload.trips.forEach(function (trip) {
      body.appendChild(el('tr', {}, [
        el('td', { text: 'tragitto' }),
        el('td', { class: 'muted', text: formatStamp(trip.start_ms) }),
        el('td', { class: 'muted', text: formatStamp(trip.end_ms) }),
        el('td', { text: fmt(trip.duration_min, 0) + ' min' }),
        el('td', { text: fmt((trip.distance_m || 0) / 1000, 1) + ' km' }),
        el('td', { text: fmt(trip.max_speed, 0) + ' km/h' })
      ]));
    });
    payload.stops.forEach(function (stop) {
      body.appendChild(el('tr', {}, [
        el('td', { text: 'sosta' }),
        el('td', { class: 'muted', text: formatStamp(stop.start_ms) }),
        el('td', { class: 'muted', text: formatStamp(stop.end_ms) }),
        el('td', { text: fmt(stop.duration_min, 0) + ' min' }),
        el('td', { class: 'muted', text: '\u2014' }),
        el('td', { class: 'muted', text: '\u2014' })
      ]));
    });
    document.getElementById('activity-trips').textContent = payload.counts.trips;
    document.getElementById('activity-stops').textContent = payload.counts.stops;
    if (empty) empty.style.display = body.children.length ? 'none' : 'block';
  } catch (error) {
    toast('Attivita: ' + error.message, 'bad');
  }
}

async function loadFuel() {
  const monthInput = document.getElementById('fuel-month');
  const body = document.getElementById('fuel-body');
  if (!body) return;
  if (monthInput && !monthInput.value) {
    const now = new Date();
    monthInput.value = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0');
  }
  const suffix = monthInput && monthInput.value ? '?month=' + monthInput.value : '';
  try {
    const response = await api('/fuel/report' + suffix);
    const payload = await response.json();
    body.textContent = '';
    payload.items.forEach(function (item) {
      body.appendChild(el('tr', {}, [
        el('td', { text: item.plate || item.imei }),
        el('td', { text: fmt(item.km, 1) }),
        el('td', { class: 'muted', text: fmt(item.consumption_l_per_100km, 1) + ' L/100' }),
        el('td', { text: fmt(item.liters, 1) }),
        el('td', { text: '\u20ac ' + fmt(item.cost_eur, 2) }),
        el('td', { text: fmt(item.idle_hours, 1) }),
        el('td', { class: item.theft_suspected ? 'badge off' : 'muted',
          text: item.fuel_drop_liters ? fmt(item.fuel_drop_liters, 1) + ' L' : '\u2014' })
      ]));
    });
    document.getElementById('fuel-km').textContent = fmt(payload.totals.km, 1);
    document.getElementById('fuel-liters').textContent = fmt(payload.totals.liters, 1);
    document.getElementById('fuel-cost').textContent = '\u20ac ' + fmt(payload.totals.cost_eur, 2);
    document.getElementById('fuel-drops').textContent = fmt(payload.totals.fuel_drop_liters, 1) + ' L';
  } catch (error) {
    toast('Carburante: ' + error.message, 'bad');
  }
}

function geofenceFromMap() {
  ensureMap();
  const center = map.getCenter();
  document.getElementById('g_lat').value = center.lat.toFixed(6);
  document.getElementById('g_lon').value = center.lng.toFixed(6);
  toast('Coordinate prese dal centro mappa', 'okv');
}

function fillMaintenanceDevices() {
  const select = document.getElementById('m_imei');
  if (!select) return;
  const current = select.value;
  select.textContent = '';
  devices.forEach(function (device) {
    const option = document.createElement('option');
    option.value = device.imei;
    option.textContent = vehicleLabel(device) + ' - ' + device.imei;
    select.appendChild(option);
  });
  if (current) select.value = current;
}

function maintenanceState(item) {
  if (item.completed_at) return { cls: 'off', text: 'completato' };
  if (item.status === 'overdue') return { cls: 'bad', text: 'scaduto' };
  if (item.due_date) {
    const due = new Date(item.due_date + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Math.round((due - today) / 86400000);
    if (days >= 0 && days <= 30) {
      return { cls: 'warn', text: days === 0 ? 'scade oggi' : 'tra ' + days + ' g' };
    }
  }
  if (item.due_odometer_km && item.odometer_km !== null &&
      item.odometer_km !== undefined) {
    const left = item.due_odometer_km - item.odometer_km;
    if (left > 0 && left <= 1000) {
      return { cls: 'warn', text: 'tra ' + Math.round(left) + ' km' };
    }
  }
  return { cls: 'on', text: 'pianificato' };
}

async function loadMaintenance() {
  const body = document.getElementById('maint-body');
  const empty = document.getElementById('maint-empty');
  if (!body) return;
  fillMaintenanceDevices();
  try {
    const response = await api('/maintenance?open_only=false');
    const payload = await response.json();
    body.textContent = '';
    payload.items.forEach(function (item) {
      const state = maintenanceState(item);
      const cells = [
        el('td', { text: item.plate || item.imei }),
        el('td', { text: item.kind }),
        el('td', { class: 'muted', text: item.due_date || '\u2014' }),
        el('td', { class: 'muted', text: item.due_odometer_km ? String(item.due_odometer_km) + ' km' : '\u2014' }),
        el('td', { class: 'muted', text: item.note || '' }),
        el('td', { class: 'muted', text: [
          item.repeat_km ? 'ogni ' + item.repeat_km + ' km' : '',
          item.repeat_months ? 'ogni ' + item.repeat_months + ' mesi' : ''
        ].filter(Boolean).join(' · ') || '\u2014' }),
        el('td', {}, [el('span', { class: 'badge ' + state.cls, text: state.text })])
      ];
      if (!item.completed_at) {
        cells.push(el('td', {}, [el('button', { class: 'tiny ok', text: 'Completa',
          onclick: function () { completeMaintenance(item.id); } })]));
      } else {
        cells.push(el('td', { class: 'muted', text: item.completed_by || '' }));
      }
      body.appendChild(el('tr', {}, cells));
    });
    if (empty) empty.style.display = payload.items.length ? 'none' : 'block';
  } catch (error) {
    toast('Manutenzione: ' + error.message, 'bad');
  }
}

async function createMaintenance() {
  const imei = document.getElementById('m_imei').value;
  const kind = document.getElementById('m_kind').value;
  const dueDate = document.getElementById('m_due_date').value;
  const dueKm = document.getElementById('m_due_km').value;
  const note = document.getElementById('m_note').value.trim();
  const repeatKm = document.getElementById('m_repeat_km').value;
  const repeatMonths = document.getElementById('m_repeat_months').value;
  if (!imei) { toast('Nessun mezzo selezionato', 'bad'); return; }
  if (!dueDate && !dueKm) {
    toast('Indica una data o un chilometraggio', 'bad'); return;
  }
  try {
    await api('/maintenance', { method: 'POST', body: JSON.stringify({
      imei: imei, kind: kind, due_date: dueDate || null,
      due_odometer_km: dueKm ? Number(dueKm) : null, note: note || null,
      repeat_km: repeatKm ? Number(repeatKm) : null,
      repeat_months: repeatMonths ? Number(repeatMonths) : null }) });
    toast('Intervento pianificato', 'okv');
    document.getElementById('m_note').value = '';
    document.getElementById('m_due_km').value = '';
    document.getElementById('m_due_date').value = '';
    document.getElementById('m_repeat_km').value = '';
    document.getElementById('m_repeat_months').value = '';
    loadMaintenance();
  } catch (error) {
    toast('Manutenzione: ' + error.message, 'bad');
  }
}

async function completeMaintenance(id) {
  const proceed = await askConfirm(
    'Segnare completato?',
    "L'intervento resta nello storico con data e operatore.",
    'Completa'
  );
  if (!proceed) return;
  try {
    await api('/maintenance/' + id + '/complete', { method: 'POST' });
    toast('Intervento completato', 'okv');
    loadMaintenance();
  } catch (error) {
    toast('Manutenzione: ' + error.message, 'bad');
  }
}

function fillLinkSnapshots(snapshots) {
  const select = document.getElementById('link-snapshot');
  if (!select) return;
  const current = select.value;
  select.textContent = '';
  snapshots.forEach(function (snap) {
    const option = document.createElement('option');
    option.value = String(snap.id);
    option.textContent = snap.period + ' (id ' + snap.id + ')';
    select.appendChild(option);
  });
  if (current) select.value = current;
}

function selectedLinkSnapshot() {
  const select = document.getElementById('link-snapshot');
  return select && select.value ? Number(select.value) : null;
}

async function loadLinks() {
  const id = selectedLinkSnapshot();
  const body = document.getElementById('link-body');
  if (!body) return;
  body.textContent = '';
  if (!id) return;
  try {
    const response = await api('/esg/snapshots/' + id + '/links');
    const payload = await response.json();
    payload.links.forEach(function (link) {
      const state = link.revoked ? 'revocato' : (link.expired ? 'scaduto' : 'attivo');
      const badgeClass = link.revoked || link.expired ? 'off' : 'on';
      body.appendChild(el('tr', {}, [
        el('td', { class: 'muted', text: String(link.created_at || '').replace('T', ' ') }),
        el('td', { class: 'muted', text: String(link.expires_at || '').replace('T', ' ') }),
        el('td', { text: link.created_by || '\u2014' }),
        el('td', { text: String(link.used_count || 0) + ' / ' + String(link.max_uses || 0) }),
        el('td', {}, [el('span', { class: 'badge ' + badgeClass, text: state })]),
        el('td', {}, [el('button', { class: 'tiny', text: 'Revoca',
          onclick: function () { revokeLink(id, link.token_hash); } })])
      ]));
    });
    if (!payload.links.length) {
      body.appendChild(el('tr', {}, [el('td', { colspan: '6', class: 'muted',
        text: 'Nessun link per questo snapshot.' })]));
    }
  } catch (error) {
    toast('Link: ' + error.message, 'bad');
  }
}

async function revokeLink(id, tokenHash) {
  const proceed = await askConfirm(
    'Revocare il link?',
    'Chi lo ha ricevuto non potra piu aprire il report.',
    'Revoca'
  );
  if (!proceed) return;
  try {
    await api('/esg/snapshots/' + id + '/link/revoke?token_hash=' +
              encodeURIComponent(tokenHash), { method: 'POST' });
    toast('Link revocato', 'okv');
    loadLinks();
  } catch (error) {
    toast('Revoca: ' + error.message, 'bad');
  }
}

async function createLinkForSelected() {
  const id = selectedLinkSnapshot();
  if (!id) { toast('Nessuno snapshot selezionato', 'bad'); return; }
  const hours = Number(document.getElementById('link-hours').value || 72);
  const maxUses = Number(document.getElementById('link-max').value || 25);
  if (!hours || hours < 1 || hours > 720) {
    toast('Ore non valide: usare un numero tra 1 e 720', 'bad');
    return;
  }
  if (!maxUses || maxUses < 1 || maxUses > 1000) {
    toast('Aperture non valide: usare un numero tra 1 e 1000', 'bad');
    return;
  }
  try {
    const response = await api('/esg/snapshots/' + id + '/link?hours=' + hours +
                               '&max_uses=' + maxUses, { method: 'POST' });
    const data = await response.json();
    try {
      await navigator.clipboard.writeText(data.url);
      toast('Link copiato, scade il ' + String(data.expires_at).replace('T', ' '), 'okv');
    } catch (error) {
      toast('Link: ' + data.url);
    }
    loadLinks();
  } catch (error) {
    toast('Link: ' + error.message, 'bad');
  }
}

async function createReportLink(id) {
  const hours = await askText(
    'Link per il cliente',
    'Ore di validita del link (1-720). Chi lo apre non deve fare accesso.',
    '72',
    'Crea'
  );
  if (hours === null) return;
  const value = parseInt(hours, 10);
  if (!value || value < 1 || value > 720) {
    toast('Ore non valide: usare un numero tra 1 e 720', 'bad');
    return;
  }
  try {
    const response = await api('/esg/snapshots/' + id + '/link?hours=' + value,
                               { method: 'POST' });
    const data = await response.json();
    try {
      await navigator.clipboard.writeText(data.url);
      toast('Link copiato, scade il ' + String(data.expires_at).replace('T', ' '), 'okv');
    } catch (error) {
      toast('Link (scade ' + String(data.expires_at).replace('T', ' ') + '): ' + data.url);
    }
  } catch (error) {
    toast('Link: ' + error.message, 'bad');
  }
}

async function sendReport(id) {
  const proceed = await askConfirm(
    'Inviare il report al cliente?',
    'Il report va ai destinatari configurati (DEVICEHUB_REPORT_TO). Il collegamento richiede un accesso alla piattaforma.',
    'Invia'
  );
  if (!proceed) return;
  try {
    const response = await api('/esg/snapshots/' + id + '/send', { method: 'POST' });
    const data = await response.json();
    toast('Report inviato a ' + data.recipients.join(', '), 'okv');
  } catch (error) {
    toast('Invio: ' + error.message, 'bad');
  }
}

async function loadAdminActions() {
  try {
    const response = await api('/audit/admin?limit=100');
    const payload = await response.json();
    const body = document.getElementById('admin-audit-body');
    body.textContent = '';
    payload.actions.forEach(function (item) {
      body.appendChild(el('tr', {}, [
        el('td', { class: 'muted', text: String(item.created_at || '').replace('T', ' ') }),
        el('td', { text: item.actor || '\\u2014' }),
        el('td', { text: item.action }),
        el('td', { text: item.target || '\\u2014' }),
        el('td', { class: 'muted', text: item.detail || '' })
      ]));
    });
  } catch (error) {
    toast('Audit: ' + error.message, 'bad');
  }
}

async function loadUpdates() {
  const applyButton = document.getElementById('update-apply');
  if (applyButton) applyButton.style.display = 'none';
  try {
    const data = await (await api('/updates')).json();
    currentUpdate = data;
    document.getElementById('update-info').textContent = [
      'Versione installata: ' + data.current,
      'Canale: ' + (data.configured ? data.source : 'non configurato'),
      'Cartella di installazione: ' + data.install_dir
    ].join(String.fromCharCode(10));
    document.getElementById('update-status').textContent = data.configured
      ? 'Pronto per la verifica del canale di rilascio.'
      : 'Aggiornamenti non configurati: impostare DEVICEHUB_UPDATE_URL nel file .env.';
  } catch (error) {
    if (error.status === 401) return;
    toast('Aggiornamenti: ' + error.message, 'bad');
  }
}

async function checkUpdates() {
  const status = document.getElementById('update-status');
  const notes = document.getElementById('update-notes');
  const applyButton = document.getElementById('update-apply');
  status.textContent = 'Verifica in corso...';
  notes.textContent = '';
  applyButton.style.display = 'none';
  try {
    const data = await (await api('/updates/check', { method: 'POST' })).json();
    currentUpdate = data;
    if (!data.configured) {
      status.textContent = 'Aggiornamenti non configurati: impostare DEVICEHUB_UPDATE_URL nel file .env.';
      return;
    }
    if (data.available) {
      status.textContent = 'Aggiornamento disponibile: ' + data.latest +
        ' (installata ' + data.current + ')' +
        (data.published_at ? ' \u00b7 ' + data.published_at : '');
      notes.textContent = data.notes || 'Nessuna nota di rilascio.';
      applyButton.textContent = 'Aggiorna a ' + data.latest;
      applyButton.style.display = '';
    } else {
      status.textContent = 'Nessun aggiornamento: la versione ' + data.current +
        ' \u00e8 la pi\u00f9 recente.';
    }
  } catch (error) {
    if (error.status === 401) return;
    status.textContent = 'Verifica non riuscita: ' + error.message;
  }
}

async function applyUpdate() {
  if (!currentUpdate || !currentUpdate.available) return;
  const proceed = await askConfirm(
    'Aggiornare la piattaforma?',
    'Verr\u00e0 installata la versione ' + currentUpdate.latest + ' dal canale configurato. ' +
    'Prima della copia viene creato un backup: se qualcosa va storto la versione ' +
    'precedente viene ripristinata. Poi il servizio si riavvier\u00e0 e la pagina si ' +
    'ricaricher\u00e0. Database, .env e archivio non vengono modificati.',
    'Aggiorna'
  );
  if (!proceed) return;
  const status = document.getElementById('update-status');
  const applyButton = document.getElementById('update-apply');
  applyButton.style.display = 'none';
  status.textContent = 'Download e verifica del pacchetto...';
  try {
    await api('/updates/apply', {
      method: 'POST',
      body: JSON.stringify({ restart: true })
    });
    status.textContent = 'Aggiornamento installato. Riavvio del servizio...';
  } catch (error) {
    if (error.status === 401) return;
    if (typeof error.status === 'number') {
      status.textContent = 'Aggiornamento non riuscito: ' + error.message;
      applyButton.style.display = '';
      return;
    }
    status.textContent = 'Riavvio del servizio in corso...';
  }
  waitForPlatformRestart(0);
}

function waitForPlatformRestart(attempt) {
  const tries = attempt || 0;
  if (tries > 40) {
    document.getElementById('update-status').textContent =
      'Installazione completata. Se la pagina non risponde, riavviare il servizio.';
    return;
  }
  setTimeout(function () {
    fetch('/health', { cache: 'no-store' }).then(function (response) {
      if (response.ok) {
        document.getElementById('update-status').textContent =
          'Piattaforma aggiornata. Ricarico la pagina...';
        setTimeout(function () { window.location.reload(); }, 800);
      } else {
        waitForPlatformRestart(tries + 1);
      }
    }).catch(function () { waitForPlatformRestart(tries + 1); });
  }, 1000);
}

let modalResolve = null;
let modalMode = 'confirm';

function openDialog(options) {
  document.getElementById('modal-title').textContent = options.title;
  document.getElementById('modal-body').textContent = options.body || '';
  const input = document.getElementById('modal-input');
  input.style.display = options.input ? 'block' : 'none';
  input.value = options.value || '';
  document.getElementById('modal-ok').textContent = options.okText || 'Conferma';
  document.getElementById('modal').classList.add('open');
  modalMode = options.input ? 'text' : 'confirm';
  setTimeout(function () {
    if (options.input) input.focus(); else document.getElementById('modal-ok').focus();
  }, 30);
  return new Promise(function (resolve) { modalResolve = resolve; });
}

function closeDialog(value) {
  document.getElementById('modal').classList.remove('open');
  if (modalResolve) {
    const resolve = modalResolve;
    modalResolve = null;
    resolve(value);
  }
}

function modalCancel() { closeDialog(null); }

function modalConfirm() {
  if (modalMode === 'text') closeDialog(document.getElementById('modal-input').value);
  else closeDialog(true);
}

function askConfirm(title, body, okText) {
  return openDialog({ title: title, body: body, okText: okText });
}

function askText(title, label, value, okText) {
  return openDialog({ title: title, body: label, input: true, value: value, okText: okText });
}

document.getElementById('modal-input').addEventListener('keydown', function (event) {
  if (event.key === 'Enter') { event.preventDefault(); modalConfirm(); }
  if (event.key === 'Escape') { modalCancel(); }
});

window.addEventListener('load', function () {
  initGlassProximity();
  showSkeleton();
  checkAuth().then(function () { loadSolution(); refresh(); });
  setInterval(function () { refresh(); renderVerticalDashboard(); }, 15000);
  updateOfflineBanner();
  flushQueue();
  window.addEventListener('online', function () { updateOfflineBanner(); flushQueue(); });
  window.addEventListener('offline', updateOfflineBanner);
  setInterval(flushQueue, 20000);
});
</script>
</body>
</html>
"""

PAGE = PAGE.replace("</head>", "<style>" + DASHBOARD_CSS + "</style></head>")
PAGE = PAGE.replace("__THEME_JS__", THEME_JS)


def _pending_tabs() -> str:
    """Schede dichiarate, senza dati inventati."""
    modules = [
        ("tab-dossier", "Fascicolo documentale", "Serve l'archiviazione dei file (oggi il servizio salva "
         "solo telemetria): richiede storage oggetti e regole di accesso per tenant."),
        ("tab-video", "Video control room", "Serve l'integrazione con gli stream delle telecamere."),
        ("tab-logistics", "Logistica & rifornimenti", "Serve il registro rifornimenti e il costo per km."),
        ("tab-compliance", "Tachigrafo", "Serve l'integrazione con i file .DDD e le API del tachigrafo."),
    ]
    blocks = []
    for tab_id, title, note in modules:
        blocks.append(
            f'<section id="{tab_id}" class="tab" data-view="operative"><div class="tab-inner"><div class="panel">'
            f'<h2>{html.escape(title)}</h2>'
            f'<div class="pending-note">{html.escape(note)}</div>'
            f'</div></div></section>'
        )
    return "\n  ".join(blocks)


def render_dashboard(settings: Settings, bg_url: str = "") -> str:
    page = (
        PAGE.replace("__COMPANY__", html.escape(settings.company))
        .replace("__TCP_PORT__", str(settings.tcp_port))
        .replace("__API_PORT__", str(settings.api_port))
        .replace("__PUBLIC_HOST__", html.escape(settings.public_host))
        .replace("__PUBLIC_PORT__", str(settings.public_port))
        .replace("__APN__", html.escape(settings.apn))
        .replace("__PENDING_TABS__", _pending_tabs())
    )
    return with_custom_bg(page, bg_url)
