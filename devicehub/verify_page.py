"""Pagina pubblica di verifica di uno snapshot esportato.

Il controllo avviene interamente nel browser: impronta SHA-256 con WebCrypto e
firma Ed25519 con WebCrypto, con ripiego sulla libreria `@noble/ed25519` dal
CDN se il browser non espone ancora Ed25519. Il file non viene inviato al
server, quindi la pagina si puo' usare anche su una macchina diversa.
"""

from __future__ import annotations

import html

from .config import Settings
from .theme import VERIFY_CSS, with_custom_bg

PAGE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__COMPANY__ &middot; Verifica snapshot</title>
</head>
<body>
<header>
  <div>
    <h1>__COMPANY__ &middot; Verifica di uno snapshot</h1>
    <div class="sub">il file resta nel browser: nessun caricamento sul server</div>
  </div>
  <div class="sub"><a href="/">Dashboard</a> &middot; <a href="/login">Accesso</a></div>
</header>

<main>
  <section class="panel">
    <h2>1. File esportato</h2>
    <label for="file">Snapshot (JSON)</label>
    <input id="file" type="file" accept=".json,application/json">
    <div class="drop" id="drop">Trascina qui il file esportato, oppure scegli il file sopra.</div>
    <label for="trusted">Chiave pubblica del fornitore (PEM, consigliata)</label>
    <input id="trusted" type="file" accept=".pem,.txt,text/plain">
    <div class="sub" id="key-note" style="margin-top:8px">
      Senza chiave esterna la firma dimostra solo che il file non e cambiato:
      per dimostrare anche chi lo ha firmato serve la chiave pubblica ricevuta
      dal fornitore.
    </div>
  </section>

  <section class="panel">
    <h2>2. Esito</h2>
    <table>
      <tbody>
        <tr><th>Documento</th><td id="doc-line" class="sub">nessun file</td></tr>
        <tr><th>Periodo</th><td id="period-line">&mdash;</td></tr>
        <tr><th>Congelato il</th><td id="created-line">&mdash;</td></tr>
        <tr><th>Impronta SHA-256</th><td id="digest-line">&mdash;</td></tr>
        <tr><th>Firma Ed25519</th><td id="signature-line">&mdash;</td></tr>
        <tr><th>Chiave pubblica</th><td id="key-line">&mdash;</td></tr>
        <tr><th>Esito</th><td id="verdict">&mdash;</td></tr>
      </tbody>
    </table>
    <div id="error"></div>
    <div class="note sub" id="meaning">
      La verifica prova che il contenuto non e cambiato dopo la chiusura del
      mese. Non certifica la correttezza dei dati ricevuti dai GPS: quello
      dipende dal dispositivo e dalla configurazione.
    </div>
  </section>

  <section class="panel">
    <h2>Da dove arriva il file</h2>
    <ul class="sub">
      <li>Dalla dashboard: scheda ESG, snapshot del mese, pulsante Report.</li>
      <li>Oppure via API: <code>GET /esg/snapshots/{id}/export</code>.</li>
      <li>Lo stesso controllo si puo fare senza browser con
          <code>scripts/verify_snapshot.py</code>.</li>
    </ul>
  </section>
</main>

<script>
const FORMAT = 'devicehub-esg-snapshot/1';
const state = { document: null, trustedPem: null };

function text(id, value) {
  const node = document.getElementById(id);
  if (node) node.textContent = value;
}

function badge(id, label, kind) {
  const node = document.getElementById(id);
  if (!node) return;
  node.textContent = '';
  const span = document.createElement('span');
  span.className = 'badge ' + kind;
  span.textContent = label;
  node.appendChild(span);
}

function b64ToBytes(value) {
  const clean = String(value || '').replace(/\\s+/g, '');
  const binary = atob(clean);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function pemToDer(pem) {
  const body = String(pem || '')
    .replace(/-----BEGIN [^-]+-----/g, '')
    .replace(/-----END [^-]+-----/g, '')
    .replace(/\\s+/g, '');
  return b64ToBytes(body);
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest))
    .map(function (byte) { return byte.toString(16).padStart(2, '0'); })
    .join('');
}

async function ed25519Verify(signature, message, rawKey) {
  try {
    const key = await crypto.subtle.importKey('raw', rawKey, { name: 'Ed25519' }, false, ['verify']);
    return await crypto.subtle.verify({ name: 'Ed25519' }, key, signature, message);
  } catch (nativeError) {
    const module = await import('https://cdn.jsdelivr.net/npm/@noble/ed25519@2.1.0/+esm');
    return await module.verify(signature, message, rawKey);
  }
}

async function verifySnapshot(document, trustedPem) {
  const result = {
    digest_ok: false, signature_ok: false, key_ok: false,
    fingerprint: null, expected_fingerprint: null, error: null,
    snapshot: (document && document.snapshot) || {}
  };
  if (!document || document.format !== FORMAT) {
    result.error = 'Il file non e un export di snapshot DeviceHub.';
    return result;
  }
  const snapshot = result.snapshot;
  const payload = document.payload;
  const expected = snapshot.digest || '';
  result.expected_fingerprint = snapshot.fingerprint || null;
  if (typeof payload !== 'string' || !expected) {
    result.error = 'Documento incompleto: mancano payload o impronta.';
    return result;
  }

  const payloadBytes = new TextEncoder().encode(payload);
  result.digest_ok = (await sha256Hex(payloadBytes)) === expected;

  const publicPem = trustedPem || snapshot.public_key || '';
  if (!publicPem) {
    result.error = 'Nessuna chiave pubblica: ne il file ne la chiave fornita.';
    return result;
  }
  const der = pemToDer(publicPem);
  result.fingerprint = (await sha256Hex(der)).slice(0, 32);
  result.key_ok = result.fingerprint === result.expected_fingerprint;
  const rawKey = der.slice(der.length - 32);
  try {
    result.signature_ok = await ed25519Verify(
      b64ToBytes(snapshot.signature), payloadBytes, rawKey
    );
  } catch (error) {
    result.error = 'Verifica della firma non disponibile: ' + error.message;
  }
  return result;
}

function render(result) {
  text('error', result.error || '');
  if (!result.snapshot || !result.snapshot.period) return;
  const snapshot = result.snapshot;
  text('doc-line', 'snapshot ' + snapshot.id + ' creato da ' + (snapshot.created_by || 'sconosciuto'));
  text('period-line', snapshot.period || '-');
  text('created-line', String(snapshot.created_at || '').replace('T', ' '));
  text('digest-line', result.digest_ok ? 'integra' : 'alterata');
  text('signature-line', result.signature_ok ? 'valida'
    : (snapshot.signature ? 'non valida' : 'assente'));
  text('key-line', result.fingerprint
    ? result.fingerprint + (result.key_ok ? ' (attesa, ok)' : ' (attesa ' + (result.expected_fingerprint || 'assente') + ')')
    : '-');
  if (result.digest_ok && result.signature_ok && result.key_ok) {
    badge('verdict', 'VERIFICATO', 'ok');
  } else {
    badge('verdict', 'NON VERIFICATO', 'bad');
  }
}

async function check() {
  text('error', '');
  if (!state.document) {
    text('doc-line', 'nessun file');
    badge('verdict', 'in attesa di un file', 'warn');
    return;
  }
  const result = await verifySnapshot(state.document, state.trustedPem);
  render(result);
}

function readFile(file, kind) {
  return new Promise(function (resolve, reject) {
    const reader = new FileReader();
    reader.onload = function () { resolve(String(reader.result || '')); };
    reader.onerror = function () { reject(new Error('lettura del file non riuscita')); };
    if (kind === 'text') reader.readAsText(file);
    else reader.readAsText(file);
  });
}

async function loadDocument(file) {
  try {
    const raw = await readFile(file, 'json');
    state.document = JSON.parse(raw);
    text('doc-line', file.name);
    await check();
  } catch (error) {
    state.document = null;
    text('doc-line', file.name);
    text('error', 'File non leggibile: ' + error.message);
    badge('verdict', 'file non valido', 'bad');
  }
}

async function loadTrustedKey(file) {
  if (!file) { state.trustedPem = null; await check(); return; }
  try {
    state.trustedPem = await readFile(file, 'text');
    text('key-note', 'Chiave esterna caricata: la verifica controlla anche il firmatario.');
    await check();
  } catch (error) {
    text('error', 'Chiave non leggibile: ' + error.message);
  }
}

function wire() {
  const input = document.getElementById('file');
  const trusted = document.getElementById('trusted');
  const drop = document.getElementById('drop');
  input.addEventListener('change', function () {
    if (input.files && input.files[0]) loadDocument(input.files[0]);
  });
  trusted.addEventListener('change', function () {
    loadTrustedKey(trusted.files && trusted.files[0]);
  });
  ['dragenter', 'dragover'].forEach(function (name) {
    drop.addEventListener(name, function (event) {
      event.preventDefault();
      drop.classList.add('on');
    });
  });
  ['dragleave', 'drop'].forEach(function (name) {
    drop.addEventListener(name, function (event) {
      event.preventDefault();
      drop.classList.remove('on');
    });
  });
  drop.addEventListener('drop', function (event) {
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) loadDocument(file);
  });
}

window.__verifySnapshot = verifySnapshot;
window.addEventListener('DOMContentLoaded', wire);
</script>
</body>
</html>
"""

PAGE = PAGE.replace("</head>", "<style>" + VERIFY_CSS + "</style></head>")


def render_verify_page(settings: Settings, bg_url: str = "") -> str:
    page = PAGE.replace("__COMPANY__", html.escape(settings.company))
    return with_custom_bg(page, bg_url)
