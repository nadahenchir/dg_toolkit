/* ============================================================
   api.js — shared helpers across all DG Toolkit pages
   ============================================================ */

const API = '/api';

/* ── Toast ── */
function toast(msg, type = 'success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast ${type} show`;
  setTimeout(() => { t.className = 'toast'; }, 3500);
}

/* ── Loading overlay ── */
function loading(show, msg = 'Processing…') {
  document.getElementById('loading-text').textContent = msg;
  document.getElementById('loading').classList.toggle('show', show);
}

/* ── Generic fetch wrapper ── */
async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}