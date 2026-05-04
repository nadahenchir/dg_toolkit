// dashboard.js — DG Toolkit Dashboard

let allAssessments = [];
let modalTarget    = null;
let modalData      = [];

async function loadSession() {
  try {
    const res  = await fetch('/api/auth/session');
    if (!res.ok) return;
    const data = await res.json();
    const firstName = data.consultant_name.split(' ')[0];
    document.getElementById('welcome-name').textContent = firstName;
  } catch (_) {}
}

async function loadStats() {
  try {
    const res  = await fetch('/api/assessments?limit=200');
    if (!res.ok) return;
    const data = await res.json();
    allAssessments = data.assessments || data || [];

    const total    = allAssessments.length;
    const complete = allAssessments.filter(a => a.status === 'complete').length;
    const inProg   = allAssessments.filter(a => a.status === 'in_progress').length;

    document.getElementById('stat-total').textContent    = total;
    document.getElementById('stat-complete').textContent = complete;
    document.getElementById('stat-progress').textContent = inProg;

    renderRecent(allAssessments.slice(0, 5));
  } catch (_) {
    document.getElementById('recent-assessments').innerHTML =
      '<div class="db-empty">Could not load assessments.</div>';
  }
}

function renderRecent(list) {
  const container = document.getElementById('recent-assessments');
  if (!list.length) {
    container.innerHTML = '<div class="db-empty">No assessments yet. Start by creating one.</div>';
    return;
  }
  container.innerHTML = list.map(a => {
    const status = a.status || 'draft';
    const date   = a.created_at
      ? new Date(a.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
      : '—';
    const href = status === 'complete'
      ? `/results?assessment_id=${a.id}`
      : `/questionnaire?assessment_id=${a.id}`;
    return `
      <a class="db-recent-row" href="${href}">
        <span class="db-recent-org">${a.organization_name || '—'}</span>
        <span class="db-recent-meta">${a.consultant_name || '—'} · ${date}</span>
        <span class="db-recent-status ${status}">${status.replace('_', ' ')}</span>
      </a>
    `;
  }).join('');
}

// ── Modal ──────────────────────────────────────────────────────

function openModal(target) {
  modalTarget = target;

  document.getElementById('modal-title').textContent =
    target === 'questionnaire' ? 'Select Assessment to Resume' : 'Select Completed Assessment';

  document.getElementById('modal-search').value = '';

  // Filter by relevant status
  modalData = allAssessments.filter(a =>
    target === 'questionnaire'
      ? a.status !== 'complete'
      : a.status === 'complete'
  );

  renderModalList(modalData);
  document.getElementById('modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('modal-search').focus(), 100);
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
}

function filterModal(q) {
  const filtered = modalData.filter(a =>
    (a.organization_name || '').toLowerCase().includes(q.toLowerCase().trim())
  );
  renderModalList(filtered);
}

function renderModalList(list) {
  const el = document.getElementById('modal-list');
  if (!list.length) {
    el.innerHTML = '<div class="db-modal-empty">No assessments found.</div>';
    return;
  }
  el.innerHTML = list.map(a => {
    const status = a.status || 'draft';
    const date   = a.created_at
      ? new Date(a.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
      : '—';
    const href = modalTarget === 'questionnaire'
      ? `/questionnaire?assessment_id=${a.id}`
      : `/results?assessment_id=${a.id}`;
    return `
      <a class="db-modal-item" href="${href}">
        <div>
          <div class="db-modal-item-org">${a.organization_name || '—'}</div>
          <div class="db-modal-item-meta">${a.consultant_name || '—'} · ${date}</div>
        </div>
        <span class="db-modal-item-status ${status}">${status.replace('_', ' ')}</span>
      </a>
    `;
  }).join('');
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModal();
});

// Init
loadSession();
loadStats();