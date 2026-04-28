/* ============================================================
   recommendations.js — Recommendations page logic
   ============================================================ */

let assessmentId  = null;
let recsData      = null;
let allRecs       = [];

/* ── Init ── */
window.addEventListener('DOMContentLoaded', async () => {
  const params = new URLSearchParams(window.location.search);
  assessmentId = parseInt(params.get('assessment_id'));

  if (!assessmentId) { showError('No assessment ID provided.'); return; }

  try {
    const [assessment, recs] = await Promise.all([
      apiFetch(`/assessments/${assessmentId}`),
      apiFetch(`/assessments/${assessmentId}/recommendations`),
    ]);

    recsData = recs;
    allRecs  = recs.recommendations || [];

    render(assessment, recs);

    // If Layer 3 not done yet, poll until narratives are ready
    if (!recs.rag_ready) {
      pollForNarratives();
    }

  } catch (err) {
    showError(err.message || 'Failed to load recommendations.');
  }
});

/* ── Render ── */
function render(assessment, recs) {
  document.getElementById('org-name').textContent        = assessment.organization_name;
  document.getElementById('consultant-name').textContent = assessment.consultant_name;

  if (recs.rag_ready) {
    document.getElementById('rag-ready-badge').style.display = 'flex';
  }

  // Summary bar
  document.getElementById('total-count').textContent = recs.summary.total;
  document.getElementById('qw-count').textContent    = recs.summary.quick_wins;
  document.getElementById('st-count').textContent    = recs.summary.strategic;
  document.getElementById('fi-count').textContent    = recs.summary.fill_in;

  // Populate domain filter
  const domainSelect = document.getElementById('filter-domain');
  recs.by_domain.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d.domain_id;
    opt.textContent = d.domain_name;
    domainSelect.appendChild(opt);
  });

  renderCards(recs.by_domain);

  document.getElementById('loading-screen').style.display = 'none';
  document.getElementById('rec-content').style.display    = 'flex';
}

/* ── Render cards grouped by domain ── */
function renderCards(byDomain) {
  const grid = document.getElementById('recommendations-grid');
  grid.innerHTML = '';

  byDomain.forEach(domain => {
    const group = document.createElement('div');
    group.className = 'rec-domain-group';
    group.dataset.domainId = domain.domain_id;

    group.innerHTML = `
      <div class="rec-domain-header" onclick="toggleDomain(this)" style="cursor:pointer;">
        <span class="rec-domain-label">${domain.domain_name}</span>
        <span class="rec-domain-count" id="domain-count-${domain.domain_id}">${domain.recommendations.length}</span>
        <svg class="domain-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" style="margin-left:auto;transition:transform 0.2s;color:var(--kpmg-blue);flex-shrink:0;">
          <path d="M3 5l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="domain-cards-body" style="display:none;flex-direction:column;gap:6px;padding-top:4px;"></div>
    `;

    const body = group.querySelector('.domain-cards-body');
    domain.recommendations.forEach(rec => {
      body.appendChild(buildRecCard(rec));
    });

    grid.appendChild(group);
  });
}

/* ── Toggle domain expand/collapse ── */
function toggleDomain(header) {
  const body    = header.nextElementSibling;
  const chevron = header.querySelector('.domain-chevron');
  const isOpen  = body.style.display !== 'none';
  body.style.display      = isOpen ? 'none' : 'flex';
  chevron.style.transform = isOpen ? '' : 'rotate(180deg)';
}

/* ── Build a single recommendation card ── */
function buildRecCard(rec) {
  const card = document.createElement('div');
  card.className = 'rec-card';
  card.dataset.domainId = rec.domain_id;
  card.dataset.category = rec.action_category;
  card.dataset.impact   = rec.impact;
  card.dataset.effort   = rec.effort;

  const categoryClass = {
    'Quick Win': 'quick-win',
    'Strategic': 'strategic',
    'Fill In':   'fill-in',
  }[rec.action_category] || '';

  let narrativeHTML = '';
  if (recsData.rag_ready && rec.rag_narrative) {
    const paragraphs = rec.rag_narrative
      .split(/\n\n+/)
      .filter(p => p.trim())
      .map(p => `<p>${p.trim()}</p>`)
      .join('');

    narrativeHTML = `
      <button class="rec-narrative-btn" onclick="toggleNarrative(this)">
        <span class="rag-dot"></span>
        Consulting Narrative
        <svg class="chevron" width="12" height="12" viewBox="0 0 12 12" fill="none" style="margin-left:auto">
          <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <div class="rec-narrative-body">${paragraphs}</div>
    `;
  }

  card.innerHTML = `
    <div class="rec-card-header">
      <div class="rec-card-left">
        <div class="rec-kpi-name">${rec.kpi_name}</div>
        <div class="rec-action-text">${rec.action_text}</div>
        <div class="rec-meta">
          <span class="rec-badge ${categoryClass}">${rec.action_category}</span>
          <span class="level-badge current">L${rec.maturity_level} → L${rec.to_level}</span>
        </div>
      </div>
    </div>
    ${narrativeHTML}
  `;

  return card;
}

/* ── Toggle narrative ── */
function toggleNarrative(btn) {
  btn.classList.toggle('open');
  btn.nextElementSibling.classList.toggle('open');
}

/* ── Poll for narratives (Layer 3 still running) ── */
function pollForNarratives() {
  // Show a subtle indicator that narratives are being generated
  const badge = document.getElementById('rag-ready-badge');
  badge.style.display = 'flex';
  badge.innerHTML = `
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style="animation:spin 1s linear infinite">
      <circle cx="6" cy="6" r="4.5" stroke="#718096" stroke-width="1.2" stroke-dasharray="14 8"/>
    </svg>
    <span style="color:var(--text-muted);font-weight:700;">Generating narratives...</span>
  `;

  const interval = setInterval(async () => {
    try {
      const recs = await apiFetch(`/assessments/${assessmentId}/recommendations`);
      if (recs.rag_ready) {
        clearInterval(interval);
        recsData = recs;

        // Re-render cards with narratives now available
        renderCards(recs.by_domain);

        // Update badge
        badge.innerHTML = `
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <circle cx="6" cy="6" r="5" stroke="#2E7D32" stroke-width="1.2"/>
            <path d="M3.5 6l2 2 3-3" stroke="#2E7D32" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span style="color:#2E7D32;font-weight:700;">AI Narratives Ready</span>
        `;
      }
    } catch (e) {
      clearInterval(interval);
    }
  }, 5000); // poll every 5 seconds
}

/* ── Apply filters ── */
function applyFilters() {
  const domainVal   = document.getElementById('filter-domain').value;
  const categoryVal = document.getElementById('filter-category').value;
  const impactVal   = document.getElementById('filter-impact').value;
  const effortVal   = document.getElementById('filter-effort').value;

  const hasFilter = domainVal || categoryVal || impactVal || effortVal;
  document.getElementById('filter-reset').style.display = hasFilter ? 'block' : 'none';

  ['filter-domain','filter-category','filter-impact','filter-effort'].forEach(id => {
    const el = document.getElementById(id);
    el.classList.toggle('active', !!el.value);
  });

  let totalVisible = 0;

  document.querySelectorAll('.rec-domain-group').forEach(group => {
    const groupDomainId = group.dataset.domainId;
    let visibleInGroup  = 0;

    group.querySelectorAll('.rec-card').forEach(card => {
      const matchDomain   = !domainVal   || String(card.dataset.domainId) === String(domainVal);
      const matchCategory = !categoryVal || card.dataset.category === categoryVal;
      const matchImpact   = !impactVal   || card.dataset.impact   === impactVal;
      const matchEffort   = !effortVal   || card.dataset.effort   === effortVal;

      const visible = matchDomain && matchCategory && matchImpact && matchEffort;
      card.classList.toggle('hidden', !visible);
      if (visible) visibleInGroup++;
    });

    const countBadge = document.getElementById(`domain-count-${groupDomainId}`);
    if (countBadge) countBadge.textContent = visibleInGroup;
    group.style.display = visibleInGroup === 0 ? 'none' : 'flex';
    totalVisible += visibleInGroup;
  });

  document.getElementById('no-results').style.display = totalVisible === 0 ? 'block' : 'none';
}

/* ── Reset filters ── */
function resetFilters() {
  ['filter-domain','filter-category','filter-impact','filter-effort'].forEach(id => {
    const el = document.getElementById(id);
    el.value = '';
    el.classList.remove('active');
  });
  document.getElementById('filter-reset').style.display = 'none';

  document.querySelectorAll('.rec-card').forEach(c => c.classList.remove('hidden'));
  document.querySelectorAll('.rec-domain-group').forEach(g => {
    g.style.display = 'flex';
    const countBadge = document.getElementById(`domain-count-${g.dataset.domainId}`);
    if (countBadge) countBadge.textContent = g.querySelectorAll('.rec-card').length;
  });

  document.getElementById('no-results').style.display = 'none';
}

/* ── Back navigation ── */
function goBack() {
  window.location.href = `/results?assessment_id=${assessmentId}`;
}

/* ── Error ── */
function showError(msg) {
  document.getElementById('loading-screen').innerHTML =
    `<p style="color:var(--error-color);font-size:13px;font-weight:700">${msg}</p>`;
}